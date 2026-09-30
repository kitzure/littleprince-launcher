#!/usr/bin/env python3
"""Ask the local server the same question LP1/LP2/LP3 ask at their login screen."""
import json
import struct
import sys
import urllib.request
from pathlib import Path

PKG = Path.home() / "Downloads/littleprince-patcher"
sys.path.insert(0, str(PKG / "lpo"))
import amf0                                                            # noqa: E402

import os
BASE = os.environ.get("CLOUD_GATEWAY",
    "http://www.little-prince.com.hk/littleprince/amfservice/gateway.php")


def raw_str(s: str) -> bytes:
    b = s.encode()
    return struct.pack(">H", len(b)) + b


def packet(body: bytes, target="/1") -> bytes:
    return (b"\x00\x00" + b"\x00\x00" + b"\x00\x01"
            + raw_str(target) + raw_str("null")
            + struct.pack(">I", len(body)) + body)


def ask(service: str, request: dict):
    # NetConnection.call(service, resObj, data): the body is one value, a strict array
    body = amf0.encode([[amf0.AmfObject(request)]])
    # the service name lives in the packet's method field, exactly as the client sends it
    pkt = (b"\x00\x00" + b"\x00\x00" + b"\x00\x01"
           + raw_str(service) + raw_str("/1") + raw_str("null")
           + struct.pack(">I", len(body)) + body)
    req = urllib.request.Request(BASE, data=pkt,
                                 headers={"Content-Type": "application/x-amf"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, r.read()


def show(label, status, data):
    print("\n%s: http %s, %d bytes" % (label, status, len(data)))
    for probe in (b"loginSuccess", b"loginFail", b"getRank"):
        if probe in data:
            print("   contains %s" % probe.decode())
    try:
        vals = amf0.decode(data)
    except Exception as exc:                                          # noqa: BLE001
        print("   (could not decode: %s)" % exc)
        return
    for v in vals:
        if isinstance(v, dict):
            keys = list(v.keys())
            interesting = {k: v[k] for k in ("response", "loginName", "name", "message")
                           if k in v}
            print("   response object with %d fields:" % len(keys))
            print("   %s" % json.dumps(interesting))
            print("   all fields: %s" % ", ".join(keys[:20]))


for service in ("Prince1_personal.serviceRequest", "Prince2_personal.serviceRequest",
                "Prince3_personal.serviceRequest"):
    st, data = ask(service, {"type": "login", "loginname": "tester", "password": "anything"})
    show("%s  login" % service.split("_")[0], st, data)

st, data = ask("Prince1_personal.serviceRequest", {"type": "getRank"})
show("Prince1 getRank", st, data)
