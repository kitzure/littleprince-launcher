#!/usr/bin/env python3
"""Every mirrored file, checked against the publisher's own copy.

The manifest records the sizes *we* downloaded, so a truncated download would be
recorded as correct.  This asks the publisher for each file's length instead, and
re-validates each SWF header (stage size included) with the RECT fields the right way
round: xmin/xmax/ymin/ymax, not x/y/w/h.
"""
import struct
import sys
import urllib.request
import zlib
from pathlib import Path

PKG = Path.home() / "Downloads/littleprince-patcher"
CLOUD = PKG / "cloud"
sys.path.insert(0, str(PKG / "lpo"))
import fetch_client as fc                                              # noqa: E402

BASE = "http://www1.little-prince.com.hk/LP/personal/"


def swf_shape(raw: bytes):
    """(version, width, height, error) - the RECT is xmin,xmax,ymin,ymax in twips."""
    if raw[:3] not in (b"FWS", b"CWS", b"ZWS"):
        return None, 0, 0, "not a SWF (starts %r)" % raw[:4]
    try:
        body = raw[8:] if raw[:3] == b"FWS" else (
            zlib.decompress(raw[8:]) if raw[:3] == b"CWS"
            else zlib.decompress(raw[8:], -15))
    except Exception as exc:                                           # noqa: BLE001
        return raw[3], 0, 0, "unreadable: %s" % exc
    nbits = body[0] >> 3
    nbytes = (5 + nbits * 4 + 7) // 8
    if not nbits or len(body) < nbytes:
        return raw[3], 0, 0, "no frame size"
    bits = "".join(format(b, "08b") for b in body[:nbytes])[5:5 + nbits * 4]
    xmin, xmax, ymin, ymax = (int(bits[i * nbits:(i + 1) * nbits], 2) for i in range(4))
    return raw[3], (xmax - xmin) // 20, (ymax - ymin) // 20, ""


def main() -> int:
    base, host = fc.resolve_base(BASE)
    print("publisher: %s\n" % base)
    problems = []
    swfs = mp3s = 0
    for path in sorted(CLOUD.rglob("*")):
        if not path.is_file() or path.name == "files.txt" or path.suffix == ".html":
            continue
        rel = path.relative_to(CLOUD).as_posix()
        local = path.read_bytes()
        # what the publisher serves for this file
        try:
            req = urllib.request.Request(base + rel, headers={"Range": "bytes=0-0"})
            if host:
                req.add_header("Host", host)
            with urllib.request.urlopen(req, timeout=25) as r:
                crange = r.headers.get("Content-Range", "")
            remote = int(crange.split("/")[-1]) if "/" in crange else None
        except Exception as exc:                                       # noqa: BLE001
            print("%-38s publisher: %s" % (rel[:38], str(exc)[:40]))
            problems.append((rel, "not served by the publisher"))
            continue
        if remote is not None and remote != len(local):
            print("%-38s SIZE local %d vs publisher %d" % (rel[:38], len(local), remote))
            problems.append((rel, "size differs"))
            continue
        if path.suffix.lower() == ".swf":
            swfs += 1
            version, w, h, err = swf_shape(local)
            if err:
                problems.append((rel, err))
                print("%-38s %s" % (rel[:38], err))
            elif w < 100 or h < 100:
                problems.append((rel, "%dx%d stage" % (w, h)))
                print("%-38s small stage %dx%d" % (rel[:38], w, h))
        elif path.suffix.lower() == ".mp3":
            mp3s += 1
            if local[:3] != b"ID3" and local[0] != 0xFF:
                problems.append((rel, "not an mp3"))
                print("%-38s not an mp3 (%r)" % (rel[:38], local[:4]))
    print("\n%d swf, %d mp3 checked against the publisher" % (swfs, mp3s))
    print("%d problem(s)" % len(problems))
    for rel, why in problems[:12]:
        print("   %-40s %s" % (rel, why))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
