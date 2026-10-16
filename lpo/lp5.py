"""星夜重圓 (Starwish Reunion, com.Starwish.LP1 v1.13) - its back end, in the local server.

The Android app (built by lp5_apk.py) calls http://10.0.2.2:<port>/ - the PC, as the
Android emulator sees it - so server.py hands these to handle() here:

  * /php/Ajax/<Name>.php       the game's ~27 calls: login by device or name/password,
                               gold/stones, stamina, level unlocks, ranks, mail,
                               settings.  JSON, every reply with "Success": true.
  * /AssetBundles/android/...  the 29 level bundles the app streams, downloaded from
                               the publisher by lp5_android.py into <package>/lp5/.

Players live in lpo/reunion_players.json.  "Start game" on the title screen logs in by
device (the first start creates a local player); "Other account" logs in by name and
password (an unknown name becomes a local player).

The Mods panel edits a player's unlocks, ranks and wallet here; every change keeps the
value it replaced, so Restore puts the player back exactly.  The app reads all of it at
its next login.
"""
import hashlib
import json
import os
import posixpath
import secrets
import threading
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / "lp5"                         # downloads, bundles, the built APK
BUNDLES = ROOT / "AssetBundles" / "android"
PLAYERS = HERE / "reunion_players.json"
TABLES = HERE / "lp5_tables.json"

GAMES = 17
LEVELS = 7
STONES = 8
MAX_STRENGTH = 60
RECOVER_SECONDS = 600
REQUIRE_NORM = [75, 78, 81, 84, 87, 90]            # BuyLevel.RequireNorm (accuracy %)
RANKS = ["Miss", "Nice", "Great", "Excellent", "Perfect"]
RANK_ORDER = {r: i for i, r in enumerate(RANKS)}
# The world map's order, and each game's name - for the Mods panel
GAME_ORDER = [15, 12, 10, 8, 13, 9, 3, 7, 4, 2, 6, 1, 5, 16, 14, 11, 17]
BUNDLE_NAMES = (["g1_lv1", "g1_lv2", "g4_lv4", "g4_lv5", "g4_lv7"]
                + ["g%d_lv%d" % (g, lv) for g in (7, 8, 9) for lv in range(1, 8)]
                + ["g11", "g13", "g14"])

_LOCK = threading.Lock()
_HOOKS = {"log": print}


def configure(**hooks):
    _HOOKS.update(hooks)


def log(msg):
    try:
        _HOOKS["log"](msg)
    except Exception:                                                 # noqa: BLE001
        print(msg)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _tables():
    try:
        return json.loads(TABLES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ─── players ─────────────────────────────────────────────────────────────────

def load_db():
    try:
        return json.loads(PLAYERS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"next_id": 1001, "players": {}, "devices": {}}


def save_db(db):
    tmp = PLAYERS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
    for attempt in range(20):                      # Windows: a reader may hold it open
        try:
            os.replace(tmp, PLAYERS)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def _pw_hash(pw, salt=None):
    salt = salt or secrets.token_hex(8)
    return {"salt": salt, "hash": hashlib.pbkdf2_hmac(
        "sha256", pw.encode(), bytes.fromhex(salt), 60000).hex()}


def _new_player(db, login, pw=None, email="null"):
    uid = db["next_id"]
    db["next_id"] += 1
    p = {"ID": uid, "Name": login, "LoginID": login, "Email": email,
         "Password": _pw_hash(pw) if pw else None,
         "Gold": 0, "Staratom": 0, "Stones": [0] * STONES,
         "Strength": MAX_STRENGTH, "LastRecoveryTime": _now(),
         "UnlockedGame": 1, "UnlockedLevel": [1] * GAMES, "UnlockedStar": [0] * GAMES,
         "RankOverride": {}, "Language": "TC", "BGM": 1, "SFX": 1, "VO": 1,
         "LastLoginTime": _now(), "DeviceCode": "null", "results": [], "created": _now()}
    db["players"][str(uid)] = p
    return p


def _by_id(db, uid):
    try:
        return db["players"].get(str(int(float(uid))))
    except (TypeError, ValueError):
        return None


def _by_login(db, login):
    login = (login or "").strip().lower()
    for p in db["players"].values():
        if p["LoginID"].lower() == login or (p.get("Email") or "").lower() == login:
            return p
    return None


def account_player(db, acct, create=False):
    """The 星夜重圓 save that belongs to a launcher account (by its email)."""
    email = (acct.get("email") or "").lower()
    for p in db["players"].values():
        if (p.get("AccountEmail") or "").lower() == email:
            return p
    if not create:
        return None
    name = acct.get("login_name") or email.split("@")[0]
    p = _by_login(db, name)
    if p is None or p.get("AccountEmail"):
        p = _new_player(db, name)
    p["AccountEmail"] = acct.get("email")
    p["Name"] = (acct.get("profile") or {}).get("name") or name
    log("  lp5: %s plays as %s" % (acct.get("email"), p["LoginID"]))
    return p


def account_stats(acct):
    """Stat blocks for the accounts page (same shape as server._stat)."""
    p = account_player(load_db(), acct)
    if not p:
        return []
    passed = sum(1 for g in range(1, GAMES + 1) for lv in range(1, LEVELS + 1)
                 if highest_rank(p, g, lv) not in (None, "Miss"))
    plays = len(p.get("results") or [])
    stat = lambda label, value, hint: {"label": label, "value": str(value), "hint": hint}
    return [s for s in (
        stat("Gold", p.get("Gold", 0), "coins earned in the mini-games"),
        stat("Games open", "%d / %d" % (p.get("UnlockedGame", 1), GAMES), "on the world map"),
        stat("Levels open", "%d / %d" % (sum(p.get("UnlockedLevel") or []), GAMES * LEVELS),
             "across all 17 games"),
        stat("Levels passed", passed, "rank better than Miss"),
        stat("Stars made", sum(1 for v in (p.get("UnlockedStar") or []) if v), "of 17"),
        stat("Stones", sum(p.get("Stones") or []), "all eight kinds"),
        stat("Rounds played", plays, "every finished round"),
    ) if s["value"] not in ("0", "")]


def _pipe(values):
    return "|".join(str(v) for v in values)


def _recover(p):
    """60 at most, one point every 10 minutes since LastRecoveryTime."""
    last = datetime.strptime(p["LastRecoveryTime"], "%Y-%m-%d %H:%M:%S")
    if p["Strength"] >= MAX_STRENGTH:
        p["LastRecoveryTime"] = _now()
        return
    gained = int((datetime.now() - last).total_seconds() // RECOVER_SECONDS)
    if gained > 0:
        p["Strength"] = min(MAX_STRENGTH, p["Strength"] + gained)
        p["LastRecoveryTime"] = (last + timedelta(seconds=gained * RECOVER_SECONDS)
                                 ).strftime("%Y-%m-%d %H:%M:%S")


def _user_reply(p):
    return {"Success": True, "State": "Done", "ID": str(p["ID"]), "Name": p["Name"],
            "Email": p.get("Email") or "null", "Staratom": str(p["Staratom"]),
            "IsTesting": "0", "Gold": str(p["Gold"]), "Stones": _pipe(p["Stones"]),
            "Strength": str(p["Strength"]), "LastRecoveryTime": p["LastRecoveryTime"],
            "Language": p.get("Language") or "TC", "UnlockedGame": str(p["UnlockedGame"]),
            "UnlockedLevel": _pipe(p["UnlockedLevel"]), "UnlockedStar": _pipe(p["UnlockedStar"]),
            "BGMOn": str(p["BGM"]), "SFXOn": str(p["SFX"]), "VOOn": str(p["VO"]),
            "LastLoginTime": p["LastLoginTime"], "IsSchoolUser": "0"}


def _best(p, gid, lv, key, reduce=max):
    vals = [r[key] for r in p["results"] if r["GameID"] == gid and r["Level"] == lv]
    return reduce(vals) if vals else None


def highest_rank(p, gid, lv):
    """The rank the map shows: a Mods override first, else the best result."""
    over = (p.get("RankOverride") or {}).get("%d-%d" % (gid, lv))
    if over:
        return over
    return _best(p, gid, lv, "Rank", reduce=lambda v: max(v, key=lambda r: RANK_ORDER.get(r, -1)))


# ─── php/Ajax ────────────────────────────────────────────────────────────────

def ajax(name, f, db):
    """One php/Ajax call -> (reply dict or text, db changed)."""
    ok = {"Success": True}
    uid = f.get("ID") or f.get("UserID")
    p = _by_id(db, uid) if uid not in (None, "", "null") else None

    if name == "GetVersionNum":
        if f.get("Type") == "QB":
            return "|".join(["0"] * GAMES), False          # the client only compares
        return dict(ok, VersionNo="0.0.0"), False           # never newer than the app
    if name == "GetStandardTime":
        return _tables().get("standard_time") or {"Success": True,
                                                  "data": [["100"] * LEVELS] * GAMES}, False
    if name == "CheckUserLastLogin":
        return dict(ok, State=True), False                  # no kicks from a local server
    if name == "Logout":
        return ok, False
    if name == "GetUserNameByDeviceCode":
        pid = db["devices"].get(f.get("deviceCode") or "")
        q = _by_id(db, pid) if pid else None
        return dict(ok, State="true", LoginID=q["LoginID"] if q else "null",
                    UserID=str(q["ID"]) if q else "0"), False
    if name == "Login":
        if f.get("LoginMethod") == "DeviceID":
            dev = f.get("DeviceID") or ""
            p = _by_id(db, db["devices"].get(dev)) if dev else None
            if p is None and f.get("Acc") not in (None, "", "null"):
                p = _by_login(db, f["Acc"])
            if p is None:                                   # first start on this device
                p = _new_player(db, "player%d" % db["next_id"])
                log("  lp5: new local player %s for device %s" % (p["LoginID"], dev[:12]))
            db["devices"][dev] = p["ID"]
            p["DeviceCode"] = dev
        else:
            acc, pw = (f.get("Acc") or "").strip(), f.get("Pw") or ""
            p = _by_login(db, acc)
            # A launcher account signs in with its own name and password, and its
            # 星夜重圓 save is tied to it - the accounts page shows that save's stats.
            accounts = _HOOKS.get("accounts")
            acct = accounts.verify(acc, pw, touch=False) if (accounts and acc and pw) else None
            if acct:
                p = account_player(db, acct, create=True)
                p["Password"] = _pw_hash(pw)
            elif p is None:
                if not acc or not pw:
                    return dict(ok, State="NotExist"), False
                p = _new_player(db, acc, pw)
                log("  lp5: new local player %r" % acc)
            elif p.get("Password") and _pw_hash(pw, p["Password"]["salt"]) != p["Password"]:
                return dict(ok, State="WrongPassword"), False
            elif not p.get("Password"):
                p["Password"] = _pw_hash(pw)                # a device player gets a password
        _recover(p)
        p["LastLoginTime"] = _now()
        return _user_reply(p), True
    if name == "CheckRepeated":
        typ = f.get("Type")
        lid = _by_login(db, f.get("LoginID")) if f.get("LoginID") else None
        em = _by_login(db, f.get("Email")) if f.get("Email") else None
        if typ == "All":
            state = "All" if lid and em else "LoginID" if lid else "Email" if em else "NotRepeated"
        else:
            state = "Repeated" if (lid if typ == "LoginID" else em) else "NotRepeated"
        return dict(ok, State=state), False
    if name == "GetUserData":                               # binding: look up another account
        q = _by_login(db, f.get("Acc"))
        if not q or not q.get("Password") or \
                _pw_hash(f.get("Pw") or "", q["Password"]["salt"]) != q["Password"]:
            return dict(ok, State="Fail"), False
        return dict(ok, State="Success", ID=str(q["ID"]), Name=q["Name"], Gold=str(q["Gold"]),
                    Staratom=str(q["Staratom"]), Stones=_pipe(q["Stones"])), False

    if p is None:
        return {"Success": False, "Error": "no such local player"}, False

    if name == "InsertUserDeviceBinding":
        if f.get("Type") == "Create":                       # this device player -> an account
            login = (f.get("LoginName") or "").strip()
            if login and not _by_login(db, login):
                p["LoginID"] = p["Name"] = login
                p["Password"] = _pw_hash(f.get("Password") or "")
                p["Email"] = f.get("Email") or "null"
            return dict(ok, State="Success", NewID=str(p["ID"])), True
        q = _by_id(db, f.get("ID"))                         # Link: this device -> that account
        if q:
            db["devices"][f.get("DeviceCode") or ""] = q["ID"]
        return dict(ok, State="Success" if q else "Fail"), True
    if name == "UpdateUserDeviceBinding":
        dev = f.get("DeviceCode") or "null"
        if dev != "null":
            db["devices"][dev] = p["ID"]
        p["DeviceCode"] = dev
        return ok, True
    if name == "GetSetting":
        return dict(ok, BGM=str(p["BGM"]), SFX=str(p["SFX"]), VO=str(p["VO"])), False
    if name == "ChangeSetting":
        key = {"BGMOn": "BGM", "SFXOn": "SFX", "VOOn": "VO"}.get(f.get("Name"), f.get("Name"))
        if key in ("BGM", "SFX", "VO"):
            p[key] = 1 if str(f.get("Value")).lower() in ("1", "true", "on") else 0
        elif key == "Language":
            p["Language"] = f.get("Value") or "TC"
        return ok, True
    if name == "UpdateStrength":
        _recover(p)
        if f.get("Type") == "One":
            p["Strength"] = max(0, min(999, p["Strength"] + int(float(f.get("Amount") or 0))))
        return dict(ok, Strength=str(p["Strength"]), LastRecoveryTime=p["LastRecoveryTime"]), True
    if name in ("GetMail", "ReceiveAllMails", "ReceiveOneMail"):
        return dict(ok, Staratom=str(p["Staratom"]),
                    MailList={"ID": [], "Message": [], "Items": [], "IsReceived": []}), False
    if name == "CheckIfFirstTime":
        gid, lv = int(f.get("GameID") or 0), int(f.get("Level") or 0)
        played = any(r["GameID"] == gid and r["Level"] == lv for r in p["results"])
        return dict(ok, IsNull=not played), False
    if name == "GetLevelData":
        ranks = [[highest_rank(p, g, lv) or "null" for lv in range(1, LEVELS + 1)]
                 for g in range(1, GAMES + 1)]
        return dict(ok, HighestRank=ranks), False
    if name == "GetUserNorms":
        data = [[_best(p, g, lv, "Accucary") or 0 for lv in range(1, LEVELS + 1)]
                for g in range(1, GAMES + 1)]
        return dict(ok, Data=data), False
    if name in ("GetPassedLevel", "GetPlayedGames"):
        passed = [sum(1 for lv in range(1, LEVELS + 1)
                      if (highest_rank(p, g, lv) or "Miss") != "Miss")
                  for g in range(1, GAMES + 1)]
        if name == "GetPassedLevel":
            return dict(ok, Data=[str(n) for n in passed]), False
        played1 = [1 if (any(r["GameID"] == g and r["Level"] == 1 for r in p["results"])
                         or (p.get("RankOverride") or {}).get("%d-1" % g)) else 0
                   for g in range(1, GAMES + 1)]
        return dict(ok, Data=[str(n) for n in passed], IsPlayedLevel1=[str(n) for n in played1],
                    UnlockedStar=p["UnlockedStar"]), False
    if name == "MakeStar":
        star = int(float(f.get("Star") or 0))
        if 0 <= star < GAMES:
            p["UnlockedStar"][star] = 1
        elif 1 <= star <= GAMES:
            p["UnlockedStar"][star - 1] = 1
        return dict(ok, UnlockedStar=_pipe(p["UnlockedStar"])), True
    if name == "UploadScore":
        gid, lv = int(f.get("GameID") or 0), int(f.get("Level") or 0)
        row = {"GameID": gid, "Level": lv, "Gold": int(float(f.get("Gold") or 0)),
               "Accucary": int(float(f.get("Accucary") or 0)), "Time": float(f.get("Time") or 0),
               "NumOfCorr": int(float(f.get("NumOfCorr") or 0)),
               "NumOfQuestion": int(float(f.get("NumOfQuestion") or 0)),
               "Rank": f.get("Rank") or "Miss", "At": _now()}
        p["results"].append(row)
        del p["results"][:-2000]
        p["Gold"] = max(0, p["Gold"] + row["Gold"])        # a failed round reports < 0
        got = [int(float(x or 0)) for x in (f.get("ReceivedStones") or "").split("|") if x != ""]
        for i, n in enumerate(got[:STONES]):
            p["Stones"][i] = max(0, p["Stones"][i] + n)
        if f.get("IsUnlockNextGame") == "1":
            p["UnlockedGame"] = min(GAMES, p["UnlockedGame"] + 1)
        return dict(ok, Gold=str(p["Gold"]), Stones=_pipe(p["Stones"])), True
    if name == "UnlockNewLevel":
        gid = int(f.get("GameID") or 0)
        if 1 <= gid <= GAMES and p["UnlockedLevel"][gid - 1] < LEVELS:
            nxt = p["UnlockedLevel"][gid - 1] + 1             # the level being bought
            prices = _tables().get("level_price") or []
            price = prices[gid - 1][nxt - 2] if prices else [0] * 6
            have = p["Stones"][:5] + [p["Staratom"]]
            norm = _best(p, gid, nxt - 1, "Accucary") or 0
            if all(h >= c for h, c in zip(have, price)) and norm >= REQUIRE_NORM[nxt - 2]:
                for i in range(5):
                    p["Stones"][i] -= price[i]
                p["Staratom"] -= price[5]
                p["UnlockedLevel"][gid - 1] = nxt
        return dict(ok, Staratom=str(p["Staratom"]), Stones=_pipe(p["Stones"]),
                    UnlockedLevel=_pipe(p["UnlockedLevel"])), True
    if name == "GetTopTen":
        return _top_ten(db, p), False
    if name == "UpdateStaratomByUserID":
        p["Staratom"] += int(float(f.get("addStaratom") or 0))
        return dict(ok, Staratom=str(p["Staratom"])), True
    if name == "useProductKey":                             # the shop is gone; any key gives 120
        p["Staratom"] += 120
        return dict(ok, State="Success", AddedStaratom="120", Staratom=str(p["Staratom"])), True
    return ok, False


def _top_ten(db, me):
    """Best score per player per game, from local players only."""
    top, mine_all = [], []
    pad = lambda vals, n=10: [str(v) for v in vals][:n] + ["null"] * (n - len(vals[:n]))
    for g in range(1, GAMES + 1):
        rows = []
        for q in db["players"].values():
            res = [r for r in q["results"] if r["GameID"] == g]
            if res:
                r = max(res, key=lambda r: (r["Gold"], -r["Time"]))
                rows.append((r["Gold"], q["Name"], r["Level"], r["Time"], q["ID"]))
        rows.sort(key=lambda t: (-t[0], t[3]))
        top.append({"Name": pad([r[1] for r in rows]), "Score": pad([r[0] for r in rows]),
                    "Level": pad([r[2] for r in rows]), "UsedTime": pad([r[3] for r in rows])})
        mine = [(i + 1, r) for i, r in enumerate(rows) if r[4] == me["ID"]]
        mine_all.append({"Rank": pad([i for i, _ in mine], 3), "Name": pad([r[1] for _, r in mine], 3),
                         "Score": pad([r[0] for _, r in mine], 3),
                         "Level": pad([r[2] for _, r in mine], 3),
                         "UsedTime": pad([r[3] for _, r in mine], 3)})
    return {"Success": True, "Top": top, "Self": mine_all}


# ─── Mods ────────────────────────────────────────────────────────────────────

MOD_FIELDS = ("UnlockedGame", "UnlockedLevel", "UnlockedStar", "RankOverride",
              "Gold", "Staratom", "Stones", "Strength")
PRESETS = [
    {"id": "unlock_all", "label": "Unlock every game and level",
     "detail": "All 17 games open, levels 1-7 in each",
     "set": {"UnlockedGame": GAMES, "UnlockedLevel": [LEVELS] * GAMES}},
    {"id": "all_stars", "label": "Make all 17 stars",
     "detail": "Every constellation star already made", "set": {"UnlockedStar": [1] * GAMES}},
    {"id": "perfect_all", "label": "Perfect on every level",
     "detail": "Highest rank Perfect on all 119 levels (counts as passed)",
     "set": {"RankOverride": {"%d-%d" % (g, lv): "Perfect"
                              for g in range(1, GAMES + 1) for lv in range(1, LEVELS + 1)}}},
    {"id": "rich", "label": "Fill the wallet",
     "detail": "99,999 gold, 9,999 star atoms, 999 of each stone",
     "set": {"Gold": 99999, "Staratom": 9999, "Stones": [999] * STONES}},
    {"id": "stamina", "label": "Full stamina", "detail": "Stamina 999 (60 is the normal cap)",
     "set": {"Strength": 999}},
]


def _clean(field, value):
    """A Mods value, clamped to what the client can show."""
    def ints(v, n, lo, hi):
        if isinstance(v, str):
            v = [x for x in v.replace("|", ",").split(",") if x.strip() != ""]
        out = [max(lo, min(hi, int(float(x)))) for x in list(v)[:n]]
        if len(out) != n:
            raise ValueError("%s needs %d numbers" % (field, n))
        return out
    if field == "UnlockedGame":
        return max(1, min(GAMES, int(float(value))))
    if field == "UnlockedLevel":
        return ints(value, GAMES, 1, LEVELS)
    if field == "UnlockedStar":
        return ints(value, GAMES, 0, 1)
    if field == "Stones":
        return ints(value, STONES, 0, 999999)
    if field in ("Gold", "Staratom"):
        return max(0, min(9999999, int(float(value))))
    if field == "Strength":
        return max(0, min(999, int(float(value))))
    if field == "RankOverride":
        out = {}
        for key, rank in dict(value or {}).items():
            g, _, lv = str(key).partition("-")
            if rank in RANKS and 1 <= int(g) <= GAMES and 1 <= int(lv) <= LEVELS:
                out["%d-%d" % (int(g), int(lv))] = rank
        return out
    raise ValueError("not a moddable field: %s" % field)


def players_payload():
    db = load_db()
    out = []
    for p in sorted(db["players"].values(), key=lambda q: q["ID"]):
        out.append({"ID": p["ID"], "Name": p["Name"], "LoginID": p["LoginID"],
                    "AccountEmail": p.get("AccountEmail") or "",
                    "LastLoginTime": p.get("LastLoginTime"),
                    "fields": {k: p.get(k) for k in MOD_FIELDS},
                    "best": {"%d-%d" % (g, lv): highest_rank(p, g, lv)
                             for g in range(1, GAMES + 1) for lv in range(1, LEVELS + 1)
                             if highest_rank(p, g, lv)},
                    "undo": sorted((p.get("mods_undo") or {}).keys())})
    return {"players": out, "presets": [{k: v for k, v in pr.items() if k != "set"}
                                        for pr in PRESETS],
            "games": GAMES, "levels": LEVELS, "ranks": RANKS, "map_order": GAME_ORDER}


def apply_mod(pid, preset=None, fields=None):
    """Set fields (a preset's or the given ones), remembering the old values once."""
    changes = {}
    if preset:
        found = [pr for pr in PRESETS if pr["id"] == preset]
        if not found:
            raise ValueError("unknown preset %s" % preset)
        changes.update(found[0]["set"])
    for k, v in (fields or {}).items():
        changes[k] = v
    if not changes:
        raise ValueError("nothing to change")
    with _LOCK:
        db = load_db()
        p = _by_id(db, pid)
        if p is None:
            raise ValueError("no player %s" % pid)
        undo = p.setdefault("mods_undo", {})
        for field, value in changes.items():
            value = _clean(field, value)
            if field not in undo:                  # first change since the last restore
                undo[field] = p.get(field, {} if field == "RankOverride" else None)
            p[field] = value                       # the rank grid always sends all of it
        save_db(db)
        log("lp5 mods: player %s - %s" % (pid, ", ".join(sorted(changes))))
        return {"ok": True, "changed": sorted(changes)}


def restore_mods(pid):
    """Put back every value the Mods panel replaced."""
    with _LOCK:
        db = load_db()
        p = _by_id(db, pid)
        if p is None:
            raise ValueError("no player %s" % pid)
        undo = p.pop("mods_undo", {}) or {}
        for field, old in undo.items():
            if old is None:
                p.pop(field, None)
            else:
                p[field] = old
        p.setdefault("RankOverride", {})
        save_db(db)
        log("lp5 mods: player %s restored (%s)" % (pid, ", ".join(sorted(undo)) or "nothing"))
        return {"ok": True, "restored": sorted(undo)}


# ─── HTTP ────────────────────────────────────────────────────────────────────

def owns(path):
    low = (path or "").split("?")[0].lower()
    # the patched app pads its address with ./ segments: //php/Ajax, /./AssetBundles ...
    low = posixpath.normpath("/" + low.lstrip("/"))
    return low.startswith(("/php/ajax/", "/assetbundles/"))


def bundles_state():
    have = [n for n in BUNDLE_NAMES if (BUNDLES / (n + ".unity3d")).is_file()]
    return len(have), len(BUNDLE_NAMES)


def handle(method, raw_path, body=b""):
    """(status, content type, bytes) for one request from the app."""
    split = urllib.parse.urlsplit(raw_path)
    path = posixpath.normpath("/" + urllib.parse.unquote(split.path).lstrip("/"))
    if path.lower().startswith("/php/ajax/") and path.lower().endswith(".php"):
        f = {k: v[-1] for k, v in urllib.parse.parse_qs(split.query, keep_blank_values=True).items()}
        if body:
            f.update({k: v[-1] for k, v in urllib.parse.parse_qs(
                body.decode("utf-8", "replace"), keep_blank_values=True).items()})
        name = path.rsplit("/", 1)[-1][:-4]
        with _LOCK:
            db = load_db()
            try:
                out, changed = ajax(name, f, db)
            except Exception as exc:                                  # noqa: BLE001
                log("  lp5 %s failed: %s" % (name, exc))
                out, changed = {"Success": False, "Error": str(exc)[:80]}, False
            if changed:
                save_db(db)
        shown = {k: ("***" if k.lower() in ("pw", "password") else v[:24]) for k, v in f.items()}
        text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        log("lp5 %s %s -> %s" % (name, shown, text[:100]))
        return 200, "application/json; charset=utf-8", text.encode("utf-8")
    if path.lower().startswith("/assetbundles/"):
        rel = path[len("/AssetBundles/"):]                # android/g13.unity3d
        target = (ROOT / "AssetBundles" / rel).resolve()
        try:
            target.relative_to((ROOT / "AssetBundles").resolve())
        except ValueError:
            return 403, "text/plain", b"forbidden"
        if not target.is_file():
            log("  lp5 404 %s - the bundles are fetched when the game is set up" % path)
            return 404, "text/plain", b"not found"
        log("lp5 bundle %s" % target.name)
        return 200, "application/octet-stream", target.read_bytes()
    return 404, "text/plain", b"not found"
