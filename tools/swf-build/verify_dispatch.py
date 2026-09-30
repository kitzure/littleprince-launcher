#!/usr/bin/env python3
"""Verify through dispatch_service - the entry the gateway actually calls - not through
the reply builders.  The LP1 break was invisible to a builder-level check."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402

print("=== dispatch_service, one call per family ===")
cases = [
    ("LP1 login", "login", "Prince1_personal.serviceRequest"),
    ("LP2 login", "login", "Prince2_personal.serviceRequest"),
    ("LP3 login", "login", "Prince3_personal.serviceRequest"),
    ("crystal total tab", "getCrystalsRank2", "PrinceOnline.serviceRequest"),
    ("month crystal tab", "getMonthCrystalsRank", "PrinceOnline.serviceRequest"),
    ("mini-game score tab", "getMonthScoreRank", "PrinceOnline.serviceRequest"),
    ("maze gate", "canPlayMaze", "PrinceOnline.serviceRequest"),
    ("notice board", "getNotice", "PrinceOnline.serviceRequest"),
    ("friends", "getMyFriends", "PrinceOnline.serviceRequest"),
    ("unknown service", "somethingUnknown", "PrinceOnline.serviceRequest"),
]
bad = []
for label, svc, target in cases:
    body = srv.encode_strict_array([{"type": svc, "loginName": "wangzi1",
                                     "data": ["wangzi1", "x"]}])
    try:
        out = srv.dispatch_service(svc, target, body)
    except Exception as e:                                              # noqa: BLE001
        out = None
        print("  %-22s RAISED %s: %s" % (label, type(e).__name__, e))
    ok = isinstance(out, (bytes, bytearray)) and len(out) > 0
    print("  %-22s -> %s%s" % (label, type(out).__name__ if out is not None else "None",
                               "" if ok else "     <<< BROKEN"))
    if not ok:
        bad.append(label)

print("\n=== the branches that were swallowed are back in dispatch_service ===")
import inspect
src = inspect.getsource(srv.dispatch_service)
for probe in ("prince%d_personal", "getnotice", "friendresultingame", "getmyfriends",
              "lpo_rank_reply(rank_reply_name", "iscore_numbers", "return build_generic"):
    print("   %-32s %s" % (probe, probe in src))
print("   dispatch_service source lines:", len(src.splitlines()))

print("\n=== the leaderboard fix still behaves ===")
print("   getCrystalsRank2 ->", srv.rank_reply_name("getCrystalsRank2"))
print("   getMonthCrystalsRank ->", srv.rank_reply_name("getMonthCrystalsRank"))
print("\nRESULT:", "all dispatch cases answer" if not bad else "still broken: %s" % bad)
