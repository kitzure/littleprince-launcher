"""星願思語 (Little Prince 4, the "horoscope" game) - served by the local server.

The publisher's web build, CanvasToy.swf, talks to three places:

  * games/...                    its textures, atlases and music, beside the SWF
  * www1.../lp4/phpServices/*.php   login, saves, scores, shop and items - plain
                                 form posts answered with name=value text, not AMF
  * XML_QuestionBank.php, ItemManagement.php's catalogue and BackEndEdit/omg.txt -
                                 data the publisher still serves; fetch_lp4.py keeps
                                 a copy in <package>/lp4/

server.py hands every /lp4/ request (and anything for horoscope.little-prince.com.hk)
to handle() here.  The player is a launcher account: the same rule as the other
games - the account is made on the accounts page, the login box takes its login
name - and the LP4 save lives on that account under "lp4".

The SWF has the publisher's addresses compiled in.  It is served with its constant
pool rewritten (swfpatch.py) to the address the page was opened on, so the client's
calls come back here with or without the hosts redirect.  The file on disk stays
the publisher's bytes.
"""
import json
import re
import secrets
import threading
import time
import urllib.parse
from pathlib import Path

import swfpatch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / "lp4"                       # the mirror (fetch_lp4.py)
PAGE = HERE / "web" / "lp4.html"                 # the Flash page at /lp4/games/
SWF = "CanvasToy.swf"
HOST = "horoscope.little-prince.com.hk"          # the same site as www1.../lp4/

ROLES = 31                                       # allies the save keeps a slot for
GAMES = 25                                       # score slots per difficulty tier
SCORE_KEYS = ("level_one", "level_two", "level_three", "level_four", "level_five",
              "level_six", "level_seven")
# The licence the client reads at login.  HAVE_SERIAL_PERSON is the full product:
# seven difficulty tiers and every battle (warscene 93).  DEMO_PERSON is the trial.
DEFAULT_SERIAL = "HAVE_SERIAL_PERSON"

_LOCK = threading.Lock()
_PHP_LOCK = threading.Lock()
_PATCHED = {}                                    # origin -> patched SWF bytes
_HOOKS = {"log": print, "accounts": None, "resolve": None, "default_profile": {}}


def configure(**hooks):
    """server.py passes its logger, accounts module and login-name resolver."""
    _HOOKS.update(hooks)


def log(msg):
    try:
        _HOOKS["log"](msg)
    except Exception:                                                 # noqa: BLE001
        print(msg)


# ─── is it here? ─────────────────────────────────────────────────────────────

def state():
    """{ready, missing, names} for the portal's fifth card."""
    try:
        import fetch_lp4
        missing, wrong = fetch_lp4.check(ROOT)
    except Exception as exc:                                          # noqa: BLE001
        return {"ready": False, "missing": 0, "names": [], "error": str(exc)[:120]}
    left = missing + wrong
    return {"ready": not left, "missing": len(left), "names": left[:4]}


def owns(path, host):
    """Is this request LP4's?"""
    host = (host or "").split(":")[0].lower()
    path = (path or "").split("?")[0]
    return host == HOST or path.startswith(("/lp4/", "/swlp4/")) or path == "/lp4"


# ─── the player ──────────────────────────────────────────────────────────────

def _acc():
    return _HOOKS["accounts"]


def _blank_save():
    return {"serial": DEFAULT_SERIAL, "bgmOn": 1, "soundOn": 1, "done_assessment": 0,
            "coins": 1000, "soldierLv": [1] + [0] * (ROLES - 1),
            "soldierExp": [0] * ROLES, "game_maxlv": [], "complete_map": [0],
            "booklet": [0] * 6, "hiscore": {}, "results": [], "items": {},
            "inuse": {}, "equip": [0] * ROLES, "maps_won": [], "mail": []}


def _save_of(acct):
    save = dict(_blank_save())
    save.update((acct or {}).get("lp4") or {})
    return save


def _by_uid(acc_id):
    try:
        want = str(int(float(acc_id)))
    except (TypeError, ValueError):
        return None
    for a in _acc().all_accounts():
        if str(a.get("uid")) == want:
            return a
    return None


def _display_name(acct):
    prof = acct.get("profile") or {}
    return prof.get("name") or acct.get("login_name") or acct.get("email", "").split("@")[0]


def _change(acct, mutate):
    """Edit one account's LP4 save under the accounts lock."""
    def apply(a):
        save = _save_of(a)
        mutate(save)
        a["lp4"] = save
    return _acc().transaction(acct["email"], apply)


# ─── helpers ─────────────────────────────────────────────────────────────────

def _csv(values):
    return ",".join(str(v) for v in values)


def _ints(text):
    out = []
    for part in str(text or "").split(","):
        try:
            out.append(int(float(part)))
        except ValueError:
            out.append(0)
    return out


def _enc(pairs):
    """name=value&... in this order - the client reads some replies by position."""
    return "&".join("%s=%s" % (k, v) for k, v in pairs)


def _exp_for_levels(exp, add):
    """Experience after `add` more levels, on the curve the ranking screen uses."""
    lv, step, left = 1, 100, exp
    while left - (step + 10 * lv) >= 0:
        left -= step + 10 * lv
        step += 10 * lv
        lv += 1
    need = 0
    for _ in range(add):
        need += step + 10 * lv - left
        step += 10 * lv
        lv += 1
        left = 0
    return exp + need


def _table(name):
    """A mirrored ItemManagement catalogue: ({field: [values]}, raw text)."""
    try:
        text = (ROOT / "_data" / "items" / ("%s.txt" % name)).read_text(encoding="utf-8")
    except OSError:
        return {}, ""
    out = {}
    for kv in text.split("&"):
        k, _, v = kv.partition("=")
        out[k] = v.split(",")
    return out, text


def _item_function(item_id):
    t, _ = _table("GetItemFunction")
    try:
        i = t["itemID"].index(str(item_id))
        return int(t["Function"][i]), t["Value"][i]
    except (KeyError, ValueError, IndexError):
        return 0, "0"


# ─── phpServices ─────────────────────────────────────────────────────────────

def _login_reply(acct):
    save = _save_of(acct)
    prof = acct.get("profile") or {}
    gender = 1 if str(prof.get("sex") or "1") == "2" else 0
    return _enc([("accId", acct["uid"]), ("roleId", 1), ("userName", _display_name(acct)),
                 ("gender", gender), ("serial", save.get("serial") or DEFAULT_SERIAL),
                 ("lockAC", 0), ("schoolID", -1), ("bgmOn", save["bgmOn"]),
                 ("soundOn", save["soundOn"]), ("done_assessment", save["done_assessment"])])


def php(name, f):
    """One phpServices call.  Returns the reply text."""
    accounts = _acc()
    if name in ("login.php", "login2.php"):
        typed = (f.get("accountID") or "").strip()
        acct = _HOOKS["resolve"](typed) if typed else None
        if not acct:
            # same rule as LP1-3 and the online client: the account comes first
            log("  lp4 login: '%s' is not an account made on the accounts page - refused"
                % typed)
            return "accId=-1"
        log("  lp4 login: '%s' -> %s (uid %s) [password not checked: this is the "
            "local mirror]" % (typed, acct["email"], acct["uid"]))
        if "lp4" not in acct:
            _change(acct, lambda save: None)          # a first visit gets a save
        return _login_reply(acct)
    if name == "PlayLogin.php":
        return "Success=0"                            # no portal session: show the login
    if name == "Logout.php":
        return "ok"
    if name == "checkUsername.php":
        free = _HOOKS["resolve"]((f.get("username") or "").strip()) is None
        return "useable=%d" % (1 if free else 0)
    if name == "register.php":
        # The game's own sign-up form makes an ordinary launcher account (it shows on
        # the accounts page like any other).  The form asks no email, so one is made.
        login = (f.get("loginname") or "").strip().lower()
        try:
            prof = dict(_HOOKS["default_profile"] or {})
            prof["sex"] = "2" if str(f.get("gender")) == "1" else "1"
            accounts.create("%s@lp4.local" % login, f.get("password") or "", prof,
                            name=(f.get("name") or login), login_name=login)
        except ValueError as exc:
            log("  lp4 register: '%s' refused (%s)" % (login, exc))
            taken = "taken" in str(exc) or "already" in str(exc)
            return "status=%s" % ("username_occupied" if taken else "fail")
        log("  lp4 register: made the account '%s'" % login)
        return "status=success"

    if name == "ItemManagement.php" and f.get("method") in ("GetItemFunction", "GetShopItem"):
        return _table(f["method"])[1]                 # catalogue reads carry no account

    acct = _by_uid(f.get("accId") or f.get("uid"))
    if acct is None:
        return "error=no account"
    save = _save_of(acct)
    reply = [""]

    if name == "downloadSavadata.php":
        return _enc([("coins", save["coins"]), ("soldierLv", _csv(save["soldierLv"])),
                     ("soldierExp", _csv(save["soldierExp"])),
                     ("game_maxlv", _csv(save["game_maxlv"])),
                     ("complete_map", _csv(save["complete_map"])),
                     ("booklet", _csv(save["booklet"])), ("isDeveloper", 0)])
    if name == "downloadGameHiScore.php":
        hs = save["hiscore"]
        if not hs:
            return _enc([(k, "") for k in SCORE_KEYS])
        blank = _csv([-2] + [0] * (GAMES - 1))
        return _enc([(k, hs.get(k) or blank) for k in SCORE_KEYS])
    if name == "downloadResult.php":
        rows = [r for r in save["results"]
                if str(r.get("gameID")) == str(f.get("gameID"))
                and str(r.get("gameLv")) == str(f.get("gameLv"))]
        last = rows[-10:]
        scores = [int(float(r.get("gameScore") or 0)) for r in rows] or [0]
        correct = [int(float(r.get("correct_count") or 0)) for r in rows] or [0]
        return _enc([("gameScoreArray", _csv(int(float(r.get("gameScore") or 0)) for r in last)),
                     ("correctCountArray", _csv(r.get("correct_count") or 0 for r in last)),
                     ("playTimeArray", _csv(r["time"][5:16] for r in last)),
                     ("highest_score", max(scores)),
                     ("average_score", sum(scores) // len(scores)),
                     ("average_c_count", sum(correct) // len(correct))])
    if name == "getRankData.php":
        return _ranks(f)
    if name in ("createSavedata.php", "doCreateXMPPlayer.php", "uploadSlideStrokeData.php"):
        return "success"
    if name in ("downloadSlide.php", "downloadStroke.php", "getWordDef.php"):
        return "myString=&slideID=&slideTitle=&slideDate="

    def write(mutate_save):
        def go(s):
            reply[0] = mutate_save(s) or ""
        _change(acct, go)
        return reply[0]

    if name == "updateSavedata.php":
        def m(s):
            s["coins"] = int(float(f.get("coins") or s["coins"]))
            for key in ("soldierLv", "soldierExp", "game_maxlv", "complete_map", "booklet"):
                if f.get(key) is not None:
                    s[key] = _ints(f[key])
            return "success"
        return write(m)
    if name == "updateGameHiScore.php":
        def m(s):
            for k in SCORE_KEYS:
                if f.get(k):
                    s["hiscore"][k] = f[k]
            return "success"
        return write(m)
    if name == "submitScore.php":
        def m(s):
            row = {k: f.get(k, "") for k in ("gameID", "gameLv", "gameScore", "correct_count",
                                              "wrong_count", "perfect_corr_count",
                                              "answer_count")}
            row["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
            s["results"].append(row)
            del s["results"][:-500]
            return "success"
        return write(m)
    if name == "recordLogin.php":
        return write(lambda s: s.__setitem__("last_login", time.strftime("%Y-%m-%d %H:%M:%S"))
                     or "success")
    if name == "updateSetting.php":
        def m(s):
            s["bgmOn"] = int(f.get("bgmOn") or 0)
            s["soundOn"] = int(f.get("soundOn") or 0)
            return "success"
        return write(m)
    if name == "setAssessComplete.php":
        return write(lambda s: s.__setitem__("done_assessment", 1) or "success")
    if name == "activateSerial.php":
        return write(lambda s: s.__setitem__("serial", DEFAULT_SERIAL) or "status=success")
    if name == "ItemManagement.php":
        if f.get("method") in READ_ONLY_ITEMS:
            return _items(save, f)                    # a read must not rewrite the file
        return write(lambda s: _items(s, f))
    return ""


# ItemManagement methods that only look.  The client fires several of these at once;
# sending them through a write made Windows refuse the accounts file's replace while
# another request had it open ("Access is denied"), and the shop then showed 0 coins.
READ_ONLY_ITEMS = ("GetMoney", "GetExp", "GetTotalItemList", "GetItemList",
                   "GetInRoleItemList", "GetInMailItemList")


def _ranks(f):
    players = [(a, _save_of(a)) for a in _acc().all_accounts() if a.get("lp4")]
    kind = f.get("rankType")
    if kind == "game":                                # JSON list of {Name, Score}
        gid, glv = str(f.get("gameID")), str(f.get("gameLevel"))
        best = []
        for a, s in players:
            sc = [int(float(r.get("gameScore") or 0)) for r in s["results"]
                  if str(r.get("gameID")) == gid and str(r.get("gameLv")) == glv]
            if sc:
                best.append({"Name": _display_name(a), "Score": str(max(sc))})
        best.sort(key=lambda r: -int(r["Score"]))
        return json.dumps(best[:10], ensure_ascii=False)

    def board(field, value):
        rows = sorted(players, key=lambda p: -value(p[1]))[:10]
        return _enc([("name", "".join(_display_name(a) + ";" for a, _ in rows)),
                     (field, "".join("%d;" % value(s) for _, s in rows))])

    def avg_exp(s):
        live = [e for lv, e in zip(s["soldierLv"], s["soldierExp"]) if lv >= 1]
        return sum(live) / len(live) if live else 0

    if kind == "coin":
        return board("coins", lambda s: s["coins"])
    if kind == "soldier":
        return board("soldier_avg_exp", avg_exp)
    if kind == "mission":
        return board("mapnum", lambda s: len(s["maps_won"]))
    return ""


def _items(s, f):
    """ItemManagement.php for one player's save - the shop, wardrobe and props."""
    m = f.get("method")
    inv, inuse = s["items"], s["inuse"]
    owned = [i for i in sorted(inv, key=int) if inv[i] > 0]
    if m == "GetMoney":
        return "coins=%d" % s["coins"]
    if m == "GetExp":
        return _enc([("lv", _csv(s["soldierLv"])), ("exp", _csv(s["soldierExp"]))])
    if m == "GetTotalItemList":
        return _enc([("itemID", _csv(owned)), ("count", _csv(inv[i] for i in owned))])
    if m == "GetItemList":
        return _enc([("itemID", _csv(owned)), ("count", _csv(inv[i] for i in owned)),
                     ("inuse", _csv(inuse.get(i, 0) + s["equip"].count(int(i))
                                    for i in owned))])
    if m == "GetInRoleItemList":
        return "roleitem=" + _csv(s["equip"])
    if m == "GetInMailItemList":
        mail = s.get("mail") or []
        return "&#*".join([
            "id=" + _csv(x["id"] for x in mail), "item=" + _csv(x["item"] for x in mail),
            "count=" + _csv(x["count"] for x in mail), "date=" + _csv(x["date"] for x in mail),
            "sender=" + "~`#".join(x["sender"] for x in mail),
            "message=" + "~`#".join(x["message"] for x in mail)])
    if m == "GetItem":                                # claim a mailed present
        rid = str(f.get("recordid"))
        for x in list(s.get("mail") or []):
            if str(x["id"]) == rid:
                inv[str(x["item"])] = inv.get(str(x["item"]), 0) + int(x["count"])
                s["mail"].remove(x)
                return "success"
        return "no object"
    if m == "BuyItem":
        t, _ = _table("GetShopItem")
        iid, num = str(f.get("itemid")), max(1, int(float(f.get("num") or 1)))
        try:
            price = int(t["Price"][t["ID"].index(iid)])
        except (KeyError, ValueError, IndexError):
            return "no object"
        if s["coins"] < price * num:
            return "not enough money"
        s["coins"] -= price * num
        inv[iid] = inv.get(iid, 0) + num
        return "success"
    if m == "UseItem":
        iid, role = str(f.get("itemid")), int(float(f.get("Roleid") or 0))
        keep = f.get("Keepuse") == "true"
        if inv.get(iid, 0) <= 0:
            return "no object"
        func, value = _item_function(iid)
        if func == 1:                                 # money
            inv[iid] -= 1
            s["coins"] += int(float(value or 0))
        elif func in (2, 3):                          # experience / a whole level
            inv[iid] -= 1
            if 0 <= role < ROLES:
                exp = s["soldierExp"][role]
                s["soldierExp"][role] = (exp + int(float(value or 0)) if func == 2
                                         else _exp_for_levels(exp, int(float(value or 1))))
        elif int(iid) >= 40:                          # battle prop, switched on/off
            if keep:
                inuse[iid] = 1
            else:
                inuse.pop(iid, None)
        elif 0 <= role < ROLES:                       # equipment for one soldier
            s["equip"][role] = int(iid) if keep else 0
        return "success"
    if m == "UnloadItem":
        role = int(float(f.get("Roleid") or 0))
        if 0 <= role < ROLES:
            s["equip"][role] = 0
        return "success"
    if m == "InWar":                                  # the client already took the cost
        active = [i for i in sorted(inuse, key=int) if inv.get(i, 0) > 0]
        if not active:
            return "no itemuse"
        for i in active:                              # a prop lasts one battle
            inv[i] -= 1
            if inv[i] <= 0:
                inuse.pop(i, None)
        return "itemuse=" + _csv(active)
    if m == "EndWar":
        cp, win = str(f.get("checkpoint")), f.get("iswin") == "true"
        if win and cp not in s["maps_won"]:
            s["maps_won"].append(cp)
            t, _ = _table("GetShopItem")
            reward = secrets.choice(t.get("ID") or ["1"])
            inv[reward] = inv.get(reward, 0) + 1
            return "item=%s" % reward
        return "item=null"
    return ""


# ─── question banks ──────────────────────────────────────────────────────────

def _question_bank(f):
    mode = re.sub(r"[^A-Za-z0-9]", "", f.get("mode") or "")
    set_name = re.sub(r"[^A-Za-z0-9_-]", "", f.get("setName") or "default") or "default"
    for name in ("%s_%s.xml" % (mode, set_name), "%s_default.xml" % mode):
        path = ROOT / "_data" / "qb" / name
        if path.is_file():
            return path.read_bytes()
    log("  lp4: no question bank for %r - run fetch_lp4.py" % mode)
    return b'<?xml version="1.0" encoding="UTF-8" ?><data></data>'


# ─── the SWF and the page ────────────────────────────────────────────────────

def patched_swf(origin):
    """CanvasToy.swf with the publisher's addresses pointed at `origin`."""
    with _LOCK:
        if origin not in _PATCHED:
            src = (ROOT / "games" / SWF).read_bytes()
            rules = [("http://www1.little-prince.com.hk/", origin + "/"),
                     ("http://www.little-prince.com.hk/", origin + "/"),
                     ("http://%s/" % HOST, origin + "/lp4/"),
                     ("www1.little-prince.com.hk", origin[len("http://"):])]
            data, hits = swfpatch.patch_swf(src, rules)
            _PATCHED[origin] = data
            log("lp4: CanvasToy.swf served for %s (%d addresses rewritten)"
                % (origin, len(hits)))
        return _PATCHED[origin]


CTYPES = {".png": "image/png", ".jpg": "image/jpeg", ".xml": "text/xml; charset=utf-8",
          ".mp3": "audio/mpeg", ".swf": "application/x-shockwave-flash",
          ".js": "application/javascript", ".json": "application/json",
          ".txt": "text/plain; charset=utf-8", ".html": "text/html; charset=utf-8"}

CROSSDOMAIN = (b'<?xml version="1.0"?><cross-domain-policy>'
               b'<allow-access-from domain="*" secure="false"/>'
               b'<allow-http-request-headers-from domain="*" headers="*"/>'
               b'</cross-domain-policy>')


def handle(method, raw_path, host, body=b""):
    """Answer one LP4 request: (status, content type, bytes[, location])."""
    split = urllib.parse.urlsplit(raw_path)
    path = urllib.parse.unquote(split.path)
    plain_host = (host or "").split(":")[0].lower()
    if plain_host == HOST and not path.startswith("/lp4/"):
        path = "/lp4" + path                          # horoscope.* is www1.../lp4/
    origin = "http://%s" % (host or "127.0.0.1")
    if path in ("/lp4", "/lp4/", "/lp4/games"):
        return 302, "text/plain", b"", "/lp4/games/"
    if path.endswith(("crossdomain.xml", "clientaccesspolicy.xml")):
        return 200, "application/xml", CROSSDOMAIN
    if path in ("/lp4/games/", "/lp4/games/index.html"):
        return 200, CTYPES[".html"], PAGE.read_bytes()
    if path == "/lp4/games/" + SWF:
        if not (ROOT / "games" / SWF).is_file():
            return 404, "text/plain", b"LP4 is not installed - download it from the portal"
        return 200, CTYPES[".swf"], patched_swf(origin)

    form = {k: v[-1] for k, v in urllib.parse.parse_qs(split.query, keep_blank_values=True).items()}
    if body:
        form.update({k: v[-1] for k, v in
                     urllib.parse.parse_qs(body.decode("utf-8", "replace"),
                                           keep_blank_values=True).items()})
    if path.startswith("/lp4/phpServices/"):
        name = path.rsplit("/", 1)[-1]
        try:
            with _PHP_LOCK:                           # one LP4 call at a time
                text = php(name, form)
        except Exception as exc:                                      # noqa: BLE001
            log("  lp4 %s failed: %s" % (name, exc))
            text = ""
        shown = {k: ("***" if "pw" in k.lower() or "pass" in k.lower() else v[:40])
                 for k, v in form.items()}
        log("lp4 %s %s %s -> %s" % (method, name, shown, text[:90].replace("\n", " ")))
        return 200, "text/plain; charset=utf-8", text.encode("utf-8")
    if path.endswith("XML_QuestionBank.php"):
        log("lp4 question bank %s/%s" % (form.get("mode"), form.get("setName")))
        return 200, CTYPES[".xml"], _question_bank(form)
    if path.startswith("/swlp4/") or path.endswith(".php"):
        return 200, "text/plain; charset=utf-8", b""  # the online dictionary etc.

    rel = path[len("/lp4/"):]
    if rel.endswith("/"):
        return 200, "text/plain", b""                 # vo/?lang=c&vo=3: empty there too
    try:
        target = (ROOT / rel).resolve()
        target.relative_to(ROOT.resolve())
    except (OSError, ValueError):
        return 403, "text/plain", b"forbidden"
    if not target.is_file():
        log("  lp4 404 %s" % path)
        return 404, "text/plain", b"not in the local copy"
    return 200, CTYPES.get(target.suffix.lower(), "application/octet-stream"), target.read_bytes()


# ─── Mods: the accounts page's 星願思語 tab ───────────────────────────────────
# Same idea as the other games' mods: a preset or a few fields are written to the
# account's LP4 save, and the first time a field is touched its old value is kept
# so "Restore" can put everything back.  The game reads it at its next login.

MAX_TIER = 6                     # 簡單 容易 中等 複雜 困難 特別
SERIALS = ("HAVE_SERIAL_PERSON", "LIMITED_EDITION_RELEASE", "HKEDCITY", "DEMO_PERSON")
MOD_FIELDS = ("coins", "serial", "soldierLv", "soldierExp", "game_maxlv", "items")

PRESETS = [
    {"id": "all_levels", "label": "Open every difficulty",
     "detail": "All 24 mini-games open up to 特別 (the sixth level).",
     "set": lambda s: s.update(game_maxlv=[-2] + [MAX_TIER] * (GAMES - 1))},
    {"id": "all_soldiers", "label": "Unlock every soldier",
     "detail": "All 31 allies join, each at least level 10 for battle.",
     "set": lambda s: s.update(soldierLv=[max(1, int(v or 0)) for v in
                                          (list(s.get("soldierLv") or []) + [0] * ROLES)[:ROLES]],
                               soldierExp=[max(int(v or 0), _exp_for_levels(0, 9)) for v in
                                           (list(s.get("soldierExp") or []) + [0] * ROLES)[:ROLES]])},
    {"id": "rich", "label": "999,999 coins",
     "detail": "For battles and the shop.",
     "set": lambda s: s.update(coins=999999)},
    {"id": "all_items", "label": "Every shop item ×99",
     "detail": "All 52 items in the bag; equip them from 檢閱士兵.",
     "set": lambda s: s.update(items={str(i): 99 for i in range(1, 53)})},
    {"id": "full_licence", "label": "Full licence",
     "detail": "HAVE_SERIAL_PERSON: every tier and war map (new players already have it).",
     "set": lambda s: s.update(serial=DEFAULT_SERIAL)},
]


def _snapshot(save, keys):
    undo = save.setdefault("mods_undo", {})
    for k in keys:
        if k not in undo:
            undo[k] = json.loads(json.dumps(save.get(k)))


def _clean_field(name, value):
    if name == "coins":
        return max(0, min(99999999, int(float(value))))
    if name == "serial":
        if value not in SERIALS:
            raise ValueError("unknown licence %r" % value)
        return value
    if name in ("soldierLv", "soldierExp", "game_maxlv"):
        vals = [int(float(v)) for v in (value if isinstance(value, list) else str(value).split(","))]
        if name == "game_maxlv":
            vals = ([-2] + [max(1, min(MAX_TIER, v)) for v in vals[1:]])[:GAMES]
        else:
            vals = [max(0, v) for v in vals][:ROLES]
        return vals
    if name == "items":
        return {str(int(k)): max(0, min(999, int(v))) for k, v in dict(value).items() if int(v) > 0}
    raise ValueError("not an LP4 mod field: %s" % name)


def mods_state(email):
    acct = _acc().get(email)
    if not acct:
        raise ValueError("no account %s" % email)
    s = _save_of(acct)
    names, _ = _table("GetItemFunction")
    return {"email": acct.get("email"), "name": _display_name(acct),
            "played": bool(acct.get("lp4")),
            "fields": {k: s.get(k) for k in MOD_FIELDS},
            "undo": sorted((s.get("mods_undo") or {}).keys()),
            "presets": [{k: v for k, v in p.items() if k != "set"} for p in PRESETS],
            "serials": list(SERIALS), "tiers": MAX_TIER, "games": GAMES - 1, "roles": ROLES,
            "item_names": (names or {}).get("Name") or []}


def apply_mod(email, preset=None, fields=None):
    acct = _acc().get(email)
    if not acct:
        raise ValueError("no account %s" % email)
    chosen = None
    if preset:
        chosen = next((p for p in PRESETS if p["id"] == preset), None)
        if not chosen:
            raise ValueError("unknown preset %s" % preset)
    clean = {k: _clean_field(k, v) for k, v in (fields or {}).items()}

    def mutate(save):
        before = {k: json.dumps(save.get(k)) for k in MOD_FIELDS}
        trial = json.loads(json.dumps(save))
        if chosen:
            chosen["set"](trial)
        trial.update(clean)
        touched = [k for k in MOD_FIELDS if json.dumps(trial.get(k)) != before[k]]
        _snapshot(save, touched)
        for k in touched:
            save[k] = trial[k]
    _change(acct, mutate)
    log("lp4 mods: %s %s" % (email, preset or ",".join(clean)))
    return mods_state(email)


def restore_mods(email):
    acct = _acc().get(email)
    if not acct:
        raise ValueError("no account %s" % email)

    def mutate(save):
        for k, v in (save.pop("mods_undo", None) or {}).items():
            save[k] = v
    _change(acct, mutate)
    return mods_state(email)
