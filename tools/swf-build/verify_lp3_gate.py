#!/usr/bin/env python3
"""Apply the new presets, then replicate LP3's own level-gate expression on the reply."""
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
    blobs = srv.amf0.decode(srv.dispatch_service("login", target, body))
    return next(b for b in blobs if isinstance(b, dict) and "response" in b)


print("=== applying ===")
for pid in ("lp3_levels", "lp3_points", "lp2_points"):
    acct, written = srv.apply_mods(EMAIL, pid)
    print("  %-12s wrote %s" % (pid, sorted(written)))

print("\n=== LP3 login ===")
p3 = login("Prince3_personal.serviceRequest")
print("  score:", p3.get("score"))
gr = p3.get("gameResult")
print("  gameResult: %d games, %d level rows" % (len(gr), sum(len(g) for g in gr)))
print("  game 2 (疾走馬車) rows:", gr[2])

print("\n=== the client's own rule, replayed on the reply ===")
print("  GameBar.showLevel: level N available when int(gameResult[g][N-2][2]) >= maxscore[g][N-2]")
ok_all = True
for g, maxrow in enumerate(srv.LP3_LEVEL_MAXSCORES):
    avail = [1]
    for n in range(2, len(maxrow) + 1):
        prev = gr[g][n - 2]
        got = int(float(prev[2]))
        if got >= maxrow[n - 2]:
            avail.append(n)
        else:
            ok_all = False
    if g < 3 or len(maxrow) > 5:
        print("   game %-2d levels %d -> available %s" % (g, len(maxrow), avail))
print("  every level of every game available:", ok_all)

print("\n=== LP2 login ===")
p2 = login("Prince2_personal.serviceRequest")
print("  score:", p2.get("score"))
print("  itemReport rows:", len(p2.get("itemReport") or []),
      " scoreReport games:", len(p2.get("scoreReport") or []))

print("\n=== LP1 still fine ===")
p1 = login("Prince1_personal.serviceRequest")
print("  score:", p1.get("score"), " level rows:", sum(len(g) for g in p1.get("gameResult")))
