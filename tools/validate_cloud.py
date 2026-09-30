#!/usr/bin/env python3
"""Is every file in the cloud mirror really what its name says?

A SWF that is truncated, or an HTML error page saved as .swf, makes Flash say the
file is too small / not a movie.  Also prints each SWF's declared stage size, since a
1x1 stage is the other thing that reads as "too small".
"""
import re
import struct
import zlib
from pathlib import Path

CLOUD = Path.home() / "Downloads/littleprince-patcher/cloud"


def swf_info(raw: bytes):
    """(version, stage_width, stage_height, declared_length) or None if not a SWF."""
    if raw[:3] not in (b"FWS", b"CWS", b"ZWS"):
        return None
    version = raw[3]
    rest = raw[8:]
    comp = raw[:3]
    try:
        if comp == b"FWS":
            body = rest
        elif comp == b"CWS":
            body = zlib.decompress(rest)
        else:
            body = zlib.decompress(rest, -15)
    except Exception:
        return ("unreadable", version, 0, 0, len(raw))
    # the header is an RECT: 5 bits of size, then that many bits each for x/y/w/h
    if not body:
        return ("empty", version, 0, 0, len(raw))
    nbits = body[0] >> 3
    total_bits = 5 + nbits * 4
    nbytes = (total_bits + 7) // 8
    if len(body) < nbytes:
        return ("truncated-rect", version, 0, 0, len(raw))
    bits = "".join(format(b, "08b") for b in body[:nbytes])[5:total_bits]
    vals = [int(bits[i * nbits:(i + 1) * nbits], 2) for i in range(4)]
    w, h = vals[2] / 20.0, vals[3] / 20.0            # twips -> pixels
    declared = struct.unpack("<I", raw[4:8])[0]
    return ("ok", version, round(w), round(h), declared)


bad = []
print("%-34s %-6s %-9s %-11s %s" % ("file", "kind", "stage", "declared", "note"))
for path in sorted(CLOUD.rglob("*")):
    if not path.is_file() or path.name == "files.txt":
        continue
    rel = path.relative_to(CLOUD).as_posix()
    raw = path.read_bytes()
    head = raw[:200].lstrip()
    if head.startswith(b"<") or b"<html" in head.lower():
        print("%-34s HTML!  %s" % (rel[:34], "an error page saved as a file"))
        bad.append((rel, "html"))
        continue
    if not path.name.lower().endswith(".swf"):
        continue
    info = swf_info(raw)
    if info is None:
        print("%-34s not a SWF (starts %r)" % (rel[:34], raw[:4]))
        bad.append((rel, "not-swf"))
        continue
    state, version, w, h, declared = info
    note = ""
    if state != "ok":
        note = state
        bad.append((rel, state))
    elif w <= 1 or h <= 1:
        note = "!! tiny stage"
        bad.append((rel, "tiny-stage"))
    elif declared != len(raw):
        note = "length mismatch"
        bad.append((rel, "length"))
    print("%-34s v%-5s %-9s %-11s %s" % (rel[:34], version, "%dx%d" % (w, h), declared, note))

print("\n%d suspicious file(s)" % len(bad))
for rel, why in bad:
    print("   %-40s %s" % (rel, why))
