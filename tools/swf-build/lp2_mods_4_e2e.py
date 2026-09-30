#!/usr/bin/env python3
"""Prove the LP2 login reply carries real boards.

Uses the server's own AMF helpers to build a client-shaped login and calls the live
reply builder - the recipe in the skill: the login name must sit at the packet's top
level (loginName/loginname), not only inside data.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402

TARGET = "Prince2_personal.serviceRequest"


def reply_for(login_name):
    try:
        body = srv.encode_strict_array([{"type": "login", "loginName": login_name,
                                         "data": [login_name, "x"]}])
        packet = srv.encode_amf0_response(TARGET, "/1", body)
    except Exception as e:                                              # noqa: BLE001
        print("  cannot build a packet:", e)
        return None
    return srv.cloud_login_reply(packet, TARGET)


def decode(reply):
    try:
        return srv.cloud_requests(reply)
    except Exception:                                                   # noqa: BLE001
        try:
            return srv.amf0.decode(reply)
        except Exception as e:                                          # noqa: BLE001
            print("  reply not decodable:", e)
            return None


names = ["wangzi1"]
for name in names:
    print(f"=== login as {name!r} ===")
    raw = reply_for(name)
    if not raw:
        continue
    print("  reply bytes:", len(raw))
    blobs = decode(raw)
    payload = None
    for b in (blobs if isinstance(blobs, list) else [blobs]):
        if isinstance(b, dict) and "gemReport" in b:
            payload = b
    if payload is None:
        print("  (no payload with gemReport - probably a refused login)")
        for b in (blobs if isinstance(blobs, list) else [blobs]):
            if isinstance(b, dict):
                print("   keys:", sorted(b.keys())[:10])
        continue
    gr, sr, ir = payload.get("gemReport"), payload.get("scoreReport"), payload.get("itemReport")
    print("  gemReport   :", gr, "-> list?", isinstance(gr, list), "len", len(gr) if isinstance(gr, list) else "-")
    print("  itemReport  :", ir, "-> list?", isinstance(ir, list))
    if isinstance(sr, list):
        rows = [len(g) for g in sr]
        print("  scoreReport : %d games, rows %s (spec %s)"
              % (len(sr), rows[:6], [len(g) for g in srv.LP2_LEVELS][:6]))
        print("  first row   :", sr[0][0])
    else:
        print("  scoreReport :", type(sr).__name__)
    for k in ("defeatedBoss", "bossQue", "equipment", "score", "firstHint"):
        print(f"  {k:<13}:", repr(payload.get(k))[:60])
    break
