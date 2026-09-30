#!/usr/bin/env python3
"""The daily maze gate: default open, and the setting is respected per player."""
import json, struct, sys, urllib.request, urllib.error
from pathlib import Path

PKG = Path.home() / "Downloads/littleprince-patcher"
sys.path.insert(0, str(PKG / "lpo"))
import amf0                                     # noqa: E402
import accounts                                 # noqa: E402

BASE = "http://127.0.0.1:8080"


def packet(values, target="/1", response="null"):
    body = amf0.encode(values)

    def rs(t):
        b = t.encode()
        return struct.pack("!H", len(b)) + b

    return (struct.pack("!HHH", 0, 0, 1) + rs(target) + rs(response)
            + struct.pack("!I", len(body)) + body)


def unwrap(pkt):
    if len(pkt) < 6:
        return []
    off = 6

    def rs(o):
        n = struct.unpack("!H", pkt[o:o + 2])[0]
        return pkt[o + 2:o + 2 + n].decode("utf-8", "replace"), o + 2 + n

    _, off = rs(off)
    _, off = rs(off)
    blen = struct.unpack("!I", pkt[off:off + 4])[0]
    off += 4
    return amf0.decode(pkt[off:off + blen])


def call(values):
    req = urllib.request.Request(BASE + "/littleprince/amfservice/gateway.php",
                                 data=packet(values),
                                 headers={"Content-Type": "application/x-amf"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return unwrap(r.read())


def maze():
    """Log in first (that is what sets the current player), then ask."""
    call([amf0.AmfObject({"type": "login4", "loginname": EMAIL, "password": "mazepw"})])
    out = call([amf0.AmfObject({"type": "canPlayMaze"})])
    for v in out:
        if isinstance(v, dict) and "result" in v:
            return v["result"]
    return None


EMAIL = "maze@local.test"
if accounts.exists(EMAIL):
    accounts.delete(EMAIL)
accounts.create(EMAIL, "mazepw", {})

print("1. default (nothing configured)")
import server as _srv
KEYS = set(_srv.DEFAULT_PROFILE.keys())
accounts.update(EMAIL, {"maze_open": True}, profile_keys=KEYS)
print("   canPlayMaze ->", maze())

print("2. this player turns it off")
acct = accounts.get(EMAIL)
prof = acct["profile"]
prof["maze_open"] = False
accounts.update(EMAIL, {"maze_open": False}, profile_keys=KEYS)
print("   stored maze_open:", accounts.get(EMAIL)["profile"].get("maze_open"))
print("   canPlayMaze ->", maze())

print("3. back on (open every day)")
import server as _srv
KEYS = set(_srv.DEFAULT_PROFILE.keys())
accounts.update(EMAIL, {"maze_open": True}, profile_keys=KEYS)
print("   canPlayMaze ->", maze())

accounts.delete(EMAIL)
print("\ncleaned up the test account:", not accounts.exists(EMAIL))
