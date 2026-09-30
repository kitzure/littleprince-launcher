#!/usr/bin/env python3
"""Decode each cloud game's login reply as it comes back through dispatch_service.

"returns bytes" is not enough: this checks the payload each game actually reads.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402

EMAIL = "wangzi1@littleprince.local"

for code, target, keys in (
        ("LP1", "Prince1_personal.serviceRequest", ("stars", "gems", "cards", "gameRecords")),
        ("LP2", "Prince2_personal.serviceRequest", ("gemReport", "scoreReport", "itemReport",
                                                    "defeatedBoss", "bossQue", "equipment")),
        ("LP3", "Prince3_personal.serviceRequest", ("gems", "gameCards", "cards", "items",
                                                    "process", "tGem")),
):
    body = srv.encode_strict_array([{"type": "login", "loginName": "wangzi1",
                                     "data": ["wangzi1", "x"]}])
    out = srv.dispatch_service("login", target, body)
    print("=== %s ===" % code)
    if not isinstance(out, (bytes, bytearray)) or not out:
        print("   BROKEN: dispatch returned %r" % (out,))
        continue
    try:
        blobs = srv.amf0.decode(out)
    except Exception as e:                                              # noqa: BLE001
        print("   reply does not decode: %s" % e)
        continue
    payload = next((b for b in (blobs if isinstance(blobs, list) else [blobs])
                    if isinstance(b, dict) and any(k in b for k in keys)), None)
    if payload is None:
        got = [sorted(b.keys())[:6] for b in (blobs if isinstance(blobs, list) else [blobs])
               if isinstance(b, dict)]
        print("   no payload with %s - keys seen: %s" % (keys, got))
        continue
    print("   reply %d bytes, payload keys: %d" % (len(out), len(payload)))
    for k in keys:
        v = payload.get(k)
        if v is None:
            present = [kk for kk in payload if kk.lower() == k.lower()]
            v = payload[present[0]] if present else None
        if isinstance(v, str):
            shown = v[:60]
        elif isinstance(v, list):
            shown = "[%d items] %s" % (len(v), v[:3])
        else:
            shown = v
        print("     %-13s %s" % (k, shown))
