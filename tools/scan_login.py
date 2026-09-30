#!/usr/bin/env python3
"""What do the cloud games' login screens talk to?

Decompress every SWF in cloud/LP1|LP2|LP3 and pull out the interesting strings:
service names, gateway urls, login-ish identifiers.  No guessing from the UI.
"""
import re
import zlib
from pathlib import Path

CLOUD = Path.home() / "Downloads/littleprince-patcher/cloud"
WORDS = (b"service", b"gateway", b"login", b"Login", b"account", b"Account",
         b"register", b"password", b"amf", b"http")
TEXT = re.compile(rb"[ -~]{4,120}")


def body(path: Path) -> bytes:
    raw = path.read_bytes()
    try:
        if raw[:3] == b"CWS":
            return b"FWS" + raw[3:8] + zlib.decompress(raw[8:])
        if raw[:3] == b"ZWS":
            return b"FWS" + raw[3:8] + zlib.decompress(raw[8:], -15)
    except Exception:
        return b""
    return raw


for game in ("LP1", "LP2", "LP3"):
    print("=" * 70)
    print(game)
    seen = set()
    for swf in sorted((CLOUD / game).glob("*.swf")):
        data = body(swf)
        if not data:
            continue
        hits = set()
        for m in TEXT.finditer(data):
            s = m.group(0)
            if any(w in s for w in WORDS):
                s2 = s.decode("ascii", "replace").strip()
                if 6 <= len(s2) <= 110 and not s2.startswith(("class ", "var ", "function ")):
                    hits.add(s2)
        for h in sorted(hits)[:14]:
            if h not in seen:
                seen.add(h)
                print("  %-14s %s" % (swf.name, h))
