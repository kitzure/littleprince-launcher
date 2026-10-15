"""Probe the v1.0a wardrobe / mods-undo / avatar paths against a throwaway copy.

Usage (from the launcher folder, any shell):  python tools/probe_v10a.py
It copies the launcher's current files into a temporary folder, uses a fake item
catalogue and two synthetic accounts there, and deletes the folder afterwards.
Your real lpo/accounts.json and game folder are never touched.
"""
import http.cookiejar, json, os, shutil, socket, sys, tempfile, threading, time, traceback
import urllib.request, zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
work = Path(tempfile.mkdtemp(prefix="lp-probe-"))
tree, gamedir = work / "tree", work / "game"
# The launcher's tracked files as they are on disk now (edits included). Installed
# clients, the browser, accounts, logs and caches are untracked, so never copied.
import subprocess
listed = subprocess.run(["git", "-C", str(HERE), "ls-files", "-z"], capture_output=True,
                        check=True).stdout.decode("utf-8").split("\0")
for name in filter(None, listed):
    src = HERE / name
    if not src.is_file() or name.startswith("tools/"):
        continue
    (tree / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, tree / name)
with socket.socket() as s:                 # any free port, so a running launcher is fine
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
print("probe: temporary copy at %s, port %d" % (work, port))
gamedir.mkdir(parents=True, exist_ok=True)
xml = """<settings><items>
<type name="hat"><item id="H_A"/><item id="H_B"/></type>
<type name="cloth"><item id="C_A"/><item id="運動服"/></type>
<type name="item"><item id="POT_A" quantity="5"/><item id="POT_B" quantity="3"/></type>
<type name="weapon"><item id="W_A" quantity="50"/></type>
</items></settings>"""
(gamedir / "settings.cxd").write_bytes(zlib.compress(xml.encode("utf-8")))
(gamedir / "index.swf").write_bytes(b"FWS\x0a" + b"\0" * 20)
os.environ["LPO_GAME_DIR"] = str(gamedir)
os.environ["LPO_PORT"] = str(port)
sys.path.insert(0, str(tree / "lpo"))
sys.path.insert(0, str(tree))
acc_file = tree / "lpo" / "accounts.json"
if acc_file.exists():
    acc_file.unlink()

from lpo import server as S, accounts as A  # noqa: E402

results = []
def check(name, cond, detail=""):
    results.append((bool(cond), name, detail))
    print(("PASS " if cond else "FAIL ") + name + ("  -- " + str(detail) if detail else ""))

def run(name, fn):
    try:
        fn()
    except Exception as e:
        check(name + " (raised)", False, "%s: %s" % (type(e).__name__, e))
        traceback.print_exc()

# 1. item categorisation
def t_catalogue():
    rows = json.loads(S.lpo_items_json(S.lpo_item_catalogue()))
    check("catalogue read from synthetic settings.cxd", len(S.lpo_item_catalogue()) == 7, S.lpo_item_catalogue())
    check("sportswear excluded", all(r[1] != "運動服" for r in rows))
    by = {r[1]: r for r in rows}
    check("clothes -> wardrobe kind 1", by["H_A"] == [1, "H_A"] and by["C_A"] == [1, "C_A"])
    check("potions -> bag kind 2 w/ native qty & distinct pos",
          by["POT_A"] == [2, "POT_A", 0, 5] and by["POT_B"] == [2, "POT_B", 1, 3], [by["POT_A"], by["POT_B"]])
    check("weapon -> storage kind 3", by["W_A"] == [3, "W_A", 0, 50], by["W_A"])
run("catalogue", t_catalogue)

# 2. login-view repair of old [1, potion] grants: position collisions?
def t_repair():
    prof = {"items": json.dumps([[1, "POT_A"], [2, "POT_B", 0, 3]])}
    rows = S.lpo_profile_items(prof)
    pos = [r[2] for r in rows if r[0] == 2]
    check("repaired legacy potion does not collide with a later bag slot",
          len(pos) == len(set(pos)), rows)
    prof2 = {"items": json.dumps([[2, "POT_B", 0, 3], [1, "POT_A"]])}
    rows2 = S.lpo_profile_items(prof2)
    pos2 = [r[2] for r in rows2 if r[0] == 2]
    check("repaired legacy potion skips an earlier bag slot", len(pos2) == len(set(pos2)), rows2)
    bad = {"items": json.dumps([[1, "H_A"], [2, "POT_B", "x", 3]])}
    try:
        S.lpo_profile_items(bad); ok = True
    except Exception as e:
        ok = False; bad_err = e
    check("malformed 4-field row does not crash login view", ok, "" if ok else repr(bad_err))
    if ok:
        rows3 = S.lpo_profile_items(bad)
        check("malformed bag row kept and re-slotted", [r for r in rows3 if r[1] == "POT_B"] == [[2, "POT_B", 0, 3]], rows3)
    mixed = {"items": json.dumps([[1, "W_A"], [1, "POT_A"], [3, "W_X", 0, 9], [2, "POT_B", 0, 3],
                                  [2, "POT_C", "1.0", "2"]])}
    rows4 = S.lpo_profile_items(mixed)
    for kind in (2, 3):
        p = [r[2] for r in rows4 if r[0] == kind]
        check("kind %d slots unique in mixed legacy list" % kind, len(p) == len(set(p)), rows4)
    check("float-string slot accepted", [2, "POT_C", 1, 2] in rows4, rows4)
run("repair", t_repair)

# 3. closet capacity
def t_closet():
    check("default pages = 2", S.lpo_closet_pages({}) == 2)
    check("closetLv 5 honoured", S.lpo_closet_pages({"closetLv": "5"}) == 5)
    check("closetLv below 2 floored", S.lpo_closet_pages({"closetLv": "0"}) == 2)
    check("unlimitedWardrobe -> >=99", S.lpo_closet_pages({"unlimitedWardrobe": "1"}) >= 99)
    many = {"unlimitedWardrobe": "1", "items": json.dumps([[1, "X%d" % i] for i in range(1000)])}
    check("unlimited grows with inventory (1000 items -> 112 pages)", S.lpo_closet_pages(many) == 112,
          S.lpo_closet_pages(many))
run("closet", t_closet)

# 4. web flow with a real HTTP server
srv = S.ReusableTCPServer(("127.0.0.1", port), S.LittlePrinceHandler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % port

def client():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def call(op, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        r = op.open(req, timeout=10)
        return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:200]

alice, bob = client(), client()
st, a = call(alice, "POST", "/web/api/register",
             {"email": "probe-a@example.test", "password": "pass1234", "name": "ProbeA", "login_name": "probea"})
check("register synthetic account A", st == 201, (st, a if st != 201 else ""))
st, b = call(bob, "POST", "/web/api/register",
             {"email": "probe-b@example.test", "password": "pass5678", "name": "ProbeB", "login_name": "probeb"})
check("register synthetic account B", st == 201, st)
EA = "probe-a@example.test"

def t_web():
    # seed a pre-existing custom inventory + equipped hat
    A.update(EA, {"items": json.dumps([[1, "CUSTOM"], [2, "POT_B", 0, 1]]), "hat": "CUSTOM", "coins": "321"},
             profile_keys=set(S.DEFAULT_PROFILE))
    before = json.loads(json.dumps(A.get(EA)))
    st, r = call(alice, "POST", "/web/api/mods", {"email": EA, "preset": "lpo_items"})
    check("apply lpo_items -> 200", st == 200, (st, r))
    rows = S.lpo_profile_items(A.get(EA)["profile"])
    names = [x[1] for x in rows]
    check("lpo_items additive: CUSTOM kept", "CUSTOM" in names, names)
    check("lpo_items: no duplicate POT_B", names.count("POT_B") == 1, names)
    bag = [x[2] for x in rows if x[0] == 2]
    check("lpo_items: bag positions unique", len(bag) == len(set(bag)), rows)
    check("lpo_items does not change wardrobe capacity",
          S.lpo_closet_pages(A.get(EA)["profile"]) == 2)
    st, r = call(alice, "POST", "/web/api/mods", {"email": EA, "preset": "lpo_wardrobe"})
    check("apply lpo_wardrobe -> 200", st == 200, (st, r))
    check("wardrobe pages >= 99 after preset", S.lpo_closet_pages(A.get(EA)["profile"]) >= 99)
    st, r = call(alice, "GET", "/web/api/mods?email=" + EA)
    undo = r.get("undo") if isinstance(r, dict) else None
    check("mods status reports backups, no legacy", undo and undo["backed_up_fields"] >= 2 and undo["legacy_fields"] == 0, undo)
    check("mods listing exposes only own account", st == 200 and [x["email"] for x in r["accounts"]] == [EA],
          r.get("accounts") if isinstance(r, dict) else r)
    # cross-account protections
    st, r = call(alice, "POST", "/web/api/mods", {"email": "probe-b@example.test", "preset": "lpo_wardrobe"})
    check("cannot mod another account (403)", st == 403, (st, r))
    st, r = call(alice, "GET", "/web/api/mods?email=probe-b@example.test")
    check("cannot view another account's mods (403)", st == 403, (st, r))
    st, r = call(alice, "POST", "/web/api/mods", {"email": EA, "fields": {"password": "x"}})
    check("protected field rejected", st >= 400 and "password" not in json.dumps(A.get(EA).get("profile", {})), (st, r))
    # play happens: in-game save after mods (coins change) then revert
    A.update(EA, {"coins": "999"}, profile_keys=set(S.DEFAULT_PROFILE))
    st, r = call(alice, "POST", "/web/api/mods", {"email": EA, "action": "revert"})
    check("revert -> 200", st == 200, (st, r))
    after = A.get(EA)
    check("revert restores items exactly", after["profile"].get("items") == before["profile"].get("items"),
          after["profile"].get("items"))
    check("revert clears unlimitedWardrobe", str(after["profile"].get("unlimitedWardrobe", "0")) != "1")
    check("revert keeps unrelated coins progress (999)", after["profile"].get("coins") == "999",
          after["profile"].get("coins"))
    check("revert keeps equipped CUSTOM hat", after["profile"].get("hat") == "CUSTOM", after["profile"].get("hat"))
    check("undo metadata removed", S.MODS_UNDO_KEY not in after)
    check("password hash untouched", after.get("password") == before.get("password")
          and after.get("salt") == before.get("salt"))
run("web mods", t_web)

def t_equipped_after_revert():
    # equip a granted item, then revert: it must fall back to default, not stay equipped-but-unowned
    A.update(EA, {"items": "[]", "hat": "", "cloth": "C_DEFAULT"}, profile_keys=set(S.DEFAULT_PROFILE))
    call(alice, "POST", "/web/api/mods", {"email": EA, "preset": "lpo_items"})
    A.update(EA, {"hat": "H_A"}, profile_keys=set(S.DEFAULT_PROFILE))
    call(alice, "POST", "/web/api/mods", {"email": EA, "action": "revert"})
    p = A.get(EA)["profile"]
    check("granted hat unequipped after revert", p.get("hat") == S.DEFAULT_PROFILE.get("hat", ""),
          (p.get("hat"), S.DEFAULT_PROFILE.get("hat")))
run("equipped revert", t_equipped_after_revert)

def t_saves():
    S.CURRENT_PLAYER["email"] = EA
    A.update(EA, {"items": json.dumps([[1, "H_A"]]), "closetLv": "2", "unlimitedWardrobe": "0", "hat": "H_A"},
             profile_keys=set(S.DEFAULT_PROFILE))
    amf = S.amf0
    def save(pairs):
        objs = [amf.AmfObject({"type": t, "data": d}) for t, d in pairs]
        body = amf.encode([objs])
        return S.persist_player_update(body)
    # Find how player_update parses; fall back to calling _collect_pairs directly.
    out = {}
    S._collect_pairs([{"type": "hat", "data": "H_B"}, {"type": "hat", "data": ""},
                      {"type": "coins", "data": 5}, {"type": "coins", "data": 7}], out)
    check("char part: last change wins (hat removed)", out.get("hat") == "", out)
    check("non-part: first value kept (unchanged behaviour)", out.get("coins") == 5, out)
    upd = {}
    try:
        ok = save([("addClosetLv", 1)])
        p = A.get(EA)["profile"]
        check("addClosetLv save -> closetLv 3", ok and p.get("closetLv") == "3", (ok, p.get("closetLv")))
        A.update(EA, {"unlimitedWardrobe": "1"}, profile_keys=set(S.DEFAULT_PROFILE))
        save([("addClosetLv", 1)])
        p = A.get(EA)["profile"]
        check("paid expansion under unlimited mod stays real level (4)", p.get("closetLv") == "4", p.get("closetLv"))
        save([("addItem", "H_B")])
        names = [r[1] for r in S.lpo_profile_items(A.get(EA)["profile"])]
        check("addItem persists", "H_B" in names, names)
        save([("removeItem", "H_A")])
        names = [r[1] for r in S.lpo_profile_items(A.get(EA)["profile"])]
        check("removeItem persists", "H_A" not in names, names)
        save([("addItem", "C_A"), ("addItem", "POT_A"), ("addItem", "W_A")])
        rows = S.lpo_profile_items(A.get(EA)["profile"])
        names = [r[1] for r in rows]
        check("three addItem in one send all persist", {"C_A", "POT_A", "W_A"} <= set(names), rows)
        check("potion/weapon from addItem land in bag/storage",
              [r[0] for r in rows if r[1] in ("POT_A", "W_A")] == [2, 3], rows)
        save([("addItem", "X_TMP"), ("removeItem", "X_TMP")])
        names = [r[1] for r in S.lpo_profile_items(A.get(EA)["profile"])]
        check("add then remove in one send -> absent", "X_TMP" not in names, names)
        save([("removeItem", "C_A"), ("addItem", "C_A")])
        names = [r[1] for r in S.lpo_profile_items(A.get(EA)["profile"])]
        check("remove then add in one send -> present", "C_A" in names, names)
        save([("addItem", "運動服")])
        names = [r[1] for r in S.lpo_profile_items(A.get(EA)["profile"])]
        check("sportswear still refused", "運動服" not in names, names)
        raw = A.get(EA)
        check("no op key leaks into the account", "_wardrobe_ops" not in json.dumps(raw)
              and "additem" not in json.dumps(raw).lower(), "")
        S.CURRENT_PLAYER["email"] = ""
        before_default = json.dumps(S.load_profile(), sort_keys=True)
        ok = save([("addItem", "H_A")])
        check("addItem with nobody signed in saves nothing", not ok
              and json.dumps(S.load_profile(), sort_keys=True) == before_default, ok)
        S.CURRENT_PLAYER["email"] = EA
    except Exception as e:
        check("AMF save path (raised)", False, repr(e)); traceback.print_exc()
run("saves", t_saves)

def t_login_closet():
    body = (tree / "lpo" / "captures" / "bodies" / "login4.bin").read_bytes()
    vals = S.amf0.decode(body)
    has = any(isinstance(v, dict) and "closetLv" in v for v in vals)
    check("login4 capture has top-level closetLv", has,
          [list(v.keys())[:12] for v in vals if isinstance(v, dict)])
    prof = dict(S.DEFAULT_PROFILE, unlimitedWardrobe="1")
    out = S.amf0.decode(S.apply_profile(body, prof))
    got = [v.get("closetLv") for v in out if isinstance(v, dict) and "closetLv" in v]
    check("login reply closetLv rewritten to >=99 under mod", got and float(got[0]) >= 99, got)
run("login closet", t_login_closet)

def t_avatar():
    st, r = call(alice, "GET", "/web/api/avatar")
    check("avatar endpoint 200 signed in", st == 200, st)
    if st == 200:
        check("avatar payload has no password/progress/undo",
              not any(k in json.dumps(r) for k in ("password", "salt", "_mods_undo", "progress")), list(r))
        check("appearance has 16 parts", len(r.get("appearance", {})) == 16, len(r.get("appearance", {})))
        check("avatar rendered (url present)", bool(r.get("avatar_url")), (r.get("avatar_url"), S.avatar.last_error() if hasattr(S, "avatar") and hasattr(S.avatar, "last_error") else ""))
        if r.get("avatar_url"):
            img = urllib.request.urlopen(base + r["avatar_url"], timeout=10).read()
            check("avatar PNG served", img[:8] == b"\x89PNG\r\n\x1a\n", len(img))
    st, r = call(client(), "GET", "/web/api/avatar")
    check("avatar endpoint 401 signed out", st == 401, st)
    st, r = call(alice, "GET", "/web/api/avatar?email=probe-b@example.test")
    check("avatar of other local account (appearance only)", st == 200 and "password" not in json.dumps(r), st)
    # concurrent renders through the cache lock
    errs = []
    def hit():
        try:
            s, _ = call(alice, "GET", "/web/api/avatar")
            if s != 200: errs.append(s)
        except Exception as e:
            errs.append(repr(e))
    ts = [threading.Thread(target=hit) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    check("8 concurrent avatar requests OK", not errs, errs)
run("avatar", t_avatar)

srv.shutdown()
fails = [r for r in results if not r[0]]
print("\n%d checks, %d failed" % (len(results), len(fails)))
for _, n, d in fails:
    print("  FAIL:", n, "--", d)
shutil.rmtree(work, ignore_errors=True)
sys.exit(1 if fails else 0)
