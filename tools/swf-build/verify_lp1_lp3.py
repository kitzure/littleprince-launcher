#!/usr/bin/env python3
"""Apply the level/card presets to the test account and read the LP1/LP3 logins back."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402
import accounts                                                         # noqa: E402

EMAIL = "wangzi1@littleprince.local"
body = srv.encode_strict_array([{"type": "login", "loginName": "wangzi1",
                                 "data": ["wangzi1", "x"]}])


def login(target):
    out = srv.dispatch_service("login", target, body)
    blobs = srv.amf0.decode(out)
    return next(b for b in blobs if isinstance(b, dict) and "response" in b)


print("=== applying the presets ===")
for pid in ("lp1_levels", "lp3_levels", "lp3_cards", "lp3_unlimited"):
    acct, written = srv.apply_mods(EMAIL, pid)
    print("  %-14s wrote %s" % (pid, sorted(written)))

print("\n=== LP1 login, decoded ===")
p1 = login("Prince1_personal.serviceRequest")
gr = p1.get("gameResult")
rows = sum(len(g) for g in gr) if isinstance(gr, list) else 0
scored = sum(1 for g in gr for r in g if isinstance(r, list) and len(r) > 2
             and str(r[2]) not in ("", "0")) if isinstance(gr, list) else 0
print("  games:", len(gr) if isinstance(gr, list) else "?", " level rows:", rows,
      " rows with a score:", scored)
print("  stars:", str(p1.get("stars"))[:44], "...")
print("  gems :", str(p1.get("gems"))[:30])
print("  cards fields:", {k: str(p1.get(k))[:20] for k in ("card", "cards", "gameCards")})

print("\n=== LP3 login, decoded ===")
p3 = login("Prince3_personal.serviceRequest")
print("  process   :", str(p3.get("process"))[:90])
gc = str(p3.get("gameCards") or "")
print("  gameCards : %d slots, first 8 = %s" % (len(gc.split(",")), gc.split(",")[:8]))
print("  cards     :", str(p3.get("cards"))[:40])
print("  gems      :", str(p3.get("gems"))[:34])

print("\n=== the unlimited-cards clamp ===")
prog = accounts.get_progress(accounts.get(EMAIL) or {}) or {}
print("  flag      :", prog.get("lp3unlimited"))
before = str(prog.get("gameCards") or "")[:12]
srv.persist_player_update(
    srv.amf0.encode([{"type": "gameCards",
                      "data": ",".join(["1"] * 50)}]))
prog = accounts.get_progress(accounts.get(EMAIL) or {}) or {}
after = str(prog.get("gameCards") or "")
print("  stored before:", before, " after the client saved 1s:", after.split(",")[:6], "...")
print("  held at the floor:", all(v == srv.LP3_CARD_FLOOR for v in after.split(",") if v))

print("\n=== dispatch battery (no regressions) ===")
bad = []
for label, svc, target in (("LP1 login", "login", "Prince1_personal.serviceRequest"),
                           ("LP2 login", "login", "Prince2_personal.serviceRequest"),
                           ("LP3 login", "login", "Prince3_personal.serviceRequest"),
                           ("crystal tab", "getCrystalsRank2", "PrinceOnline.serviceRequest"),
                           ("maze", "canPlayMaze", "PrinceOnline.serviceRequest"),
                           ("notice", "getNotice", "PrinceOnline.serviceRequest"),
                           ("friends", "getMyFriends", "PrinceOnline.serviceRequest")):
    b = srv.encode_strict_array([{"type": svc, "loginName": "wangzi1", "data": ["wangzi1", "x"]}])
    o = srv.dispatch_service(svc, target, b)
    ok = isinstance(o, (bytes, bytearray)) and len(o) > 0
    print("  %-12s %s" % (label, "ok" if ok else "BROKEN"))
    if not ok:
        bad.append(label)
print("RESULT:", "all good" if not bad else bad)
