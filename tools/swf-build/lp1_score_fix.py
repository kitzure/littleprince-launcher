#!/usr/bin/env python3
"""LP1: actually send `score` (積分) in the login reply, and prove a purchase persists."""
import pathlib
import subprocess
import sys

S = pathlib.Path.home() / "Downloads/littleprince-launcher/lpo/server.py"
src = S.read_text()

OLD = '''            payload["gameCards"] = ""
            payload["ip"] = ""'''
NEW = '''            # 積分 - the 部首咭 panel's 總分, and what its cards are bought with.  This
            # was never sent: the reply kept the captured account's 0, so the panel
            # always showed 總分 0 and no card could be bought however the profile was
            # set.  Saved copy first (the client sends `score` back), then the profile.
            payload["score"] = (lp1_saved.get("score") or profile.get("score")
                                or payload.get("score") or "0")
            payload["gameCards"] = ""
            payload["ip"] = ""'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    print("patched: LP1's reply now carries score (積分)")
else:
    print("!! anchor not found")
    sys.exit(1)

S.write_text(src)
r = subprocess.run([sys.executable, "-m", "py_compile", str(S)], capture_output=True, text=True)
print("py_compile:", "OK" if r.returncode == 0 else r.stderr[-400:])

sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402
import accounts                                                         # noqa: E402

EMAIL = "wangzi1@littleprince.local"
body = srv.encode_strict_array([{"type": "login", "loginName": "wangzi1",
                                 "data": ["wangzi1", "x"]}])


def lp1_login():
    blobs = srv.amf0.decode(srv.dispatch_service(
        "login", "Prince1_personal.serviceRequest", body))
    return next(b for b in blobs if isinstance(b, dict) and "response" in b)


print("\nscore before the preset:", lp1_login().get("score"))
srv.apply_mods(EMAIL, "lp1_points")
print("score after  the preset:", lp1_login().get("score"))

print("\n=== a purchase, in the client's own request shape ===")
for shape, payload in (("reqestList", {"reqestList": [{"type": "cards", "data": "3,1,0,2"}]}),
                       ("bare array", [{"type": "cards", "data": "3,1,0,2"}])):
    raw = srv.amf0.encode([payload]) if shape == "reqestList" else srv.amf0.encode(payload)
    got = srv.player_update(raw)[0]
    print("  %-11s -> player_update extracted %s" % (shape, got))
    if got:
        print("              persist:", srv.persist_player_update(raw))
        acct = accounts.get(EMAIL) or {}
        print("              stored cards now:",
              str((acct.get("profile") or acct).get("cards"))[:30],
              "| progress:", str(accounts.get_progress(acct).get("cards"))[:30])
        break
print("\nreply now sends score =", lp1_login().get("score"),
      "and cards =", repr(lp1_login().get("cards")))
