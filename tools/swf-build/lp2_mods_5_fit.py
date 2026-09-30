#!/usr/bin/env python3
"""Fit LP2's string fields to the client's own slot counts at the login.

The test showed `defeatedBoss` arriving as "" for an account that never saved - and
"".split(",") is [""], a one-slot array, so `defeatedBoss[bossID-1]` reads undefined for
every boss.  The client's own default is 4 slots (SaveLoadSystem.createUser pushes 4) and
bossQue is 4 rows of 4.  Fit at the login, never in the store - the same rule the other
games' arrays follow.
"""
import pathlib
import subprocess
import sys

S = pathlib.Path.home() / "Downloads/littleprince-launcher/lpo/server.py"
src = S.read_text()

ANCHOR = '''def lp2_blank_score_report() -> list:'''
HELPERS = '''def lp2_defeated_boss(prog: dict) -> str:
    """The 4 boss slots, 0/1.  The client's own default record is 4 (SaveLoadSystem),
    and it reads this as a comma string and int()s every entry, so a short value has to
    be padded here or every boss past its last slot reads undefined."""
    raw = _lp2_saved(prog, "defeatedBoss")
    vals = []
    for v in str(raw or "").split(","):
        v = v.strip()
        if v == "":
            continue
        try:
            vals.append(str(int(float(v))))
        except ValueError:
            continue
    return ",".join((vals + ["0"] * 4)[:4])


def lp2_boss_que(prog: dict) -> str:
    """The boss queue: 4 rows of 4, rows split on "," and values on ":" - the shape the
    client's own twoDArray2Str writes and str2TwoDArray reads back."""
    raw = str(_lp2_saved(prog, "bossQue") or "")
    rows = []
    for row in raw.split(","):
        vals = [v.strip() for v in row.split(":") if v.strip() != ""]
        fixed = []
        for v in vals:
            try:
                fixed.append(str(int(float(v))))
            except ValueError:
                fixed.append("0")
        rows.append((fixed + ["0"] * 4)[:4])
    while len(rows) < 4:
        rows.append(["0"] * 4)
    return ",".join(":".join(r) for r in rows[:4])


def lp2_blank_score_report() -> list:'''

if ANCHOR in src:
    src = src.replace(ANCHOR, HELPERS, 1)
    print("helpers added")
else:
    print("!! anchor not found")
    sys.exit(1)

OLD = '''                "equipment": lp2_saved("equipment", ""),
                "bossQue": lp2_saved("bossQue", ""),
                "defeatedBoss": lp2_saved("defeatedBoss", ""),'''
NEW = '''                "equipment": lp2_saved("equipment", ""),
                "bossQue": lp2_boss_que(prog),
                "defeatedBoss": lp2_defeated_boss(prog),'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    print("reply now fits the boss fields")
else:
    print("!! reply anchor not found")
    sys.exit(1)

S.write_text(src)
r = subprocess.run([sys.executable, "-m", "py_compile", str(S)], capture_output=True, text=True)
print("py_compile:", "OK" if r.returncode == 0 else r.stderr[-400:])

sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402

print("\n=== the two fields, before and after the fix ===")
cases = [
    ("never saved", {}),
    ("preset 1,1,1,1", {"defeatedBoss": "1,1,1,1"}),
    ("partial 1", {"defeatedboss": "1"}),
    ("garbage", {"defeatedBoss": "x,y"}),
]
for label, prog in cases:
    print("  defeatedBoss %-16s -> %r" % (label, srv.lp2_defeated_boss(prog)))
for label, prog in [("never saved", {}), ("4x4 zeros", {"bossQue": "0:0:0:0,0:0:0:0,0:0:0:0,0:0:0:0"}),
                    ("short row", {"bossque": "5"})]:
    print("  bossQue      %-16s -> %r" % (label, srv.lp2_boss_que(prog)))

print("\n=== end to end again (wangzi1) ===")
T = "Prince2_personal.serviceRequest"
body = srv.encode_strict_array([{"type": "login", "loginName": "wangzi1", "data": ["wangzi1", "x"]}])
reply = srv.cloud_login_reply(srv.encode_amf0_response(T, "/1", body), T)
payload = next((b for b in srv.cloud_requests(reply) if isinstance(b, dict) and "gemreport" in b), None)
print("  defeatedboss:", repr(payload.get("defeatedboss")))
print("  bossque     :", repr(payload.get("bossque")))
print("  gemReport   :", payload.get("gemreport"))
print("  scoreReport :", len(payload.get("scorereport") or []), "games")
