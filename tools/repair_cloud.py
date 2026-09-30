#!/usr/bin/env python3
"""Complete the cloud mirror: find every asset each cloud game references and
fetch the ones we are missing straight from the publisher.

LP2 stalled on twelve `fx/*.mp3` files the first crawl never saw, because a SWF
asks for its audio by name at runtime - the file list cannot be obtained by
following links alone.  So read the SWFs: their asset names sit as plain strings
in the ABC pool (decompress CWS/ZWS first), which gives the real list.
"""
import re
import sys
import urllib.request
import zlib
from pathlib import Path

sys.path.insert(0, str(Path.home() / "Downloads/littleprince-patcher/lpo"))
import fetch_client as fc                                            # noqa: E402

CLOUD = Path.home() / "Downloads/littleprince-patcher/cloud"
PUBLIC = "http://www1.little-prince.com.hk/LP/personal/"

ASSET = re.compile(rb"[A-Za-z0-9_][A-Za-z0-9_/.\-]{2,70}\."
                   rb"(?:mp3|swf|xml|txt|jpg|jpeg|png|gif|dat|cxd|json)")
SKIP_PREFIX = ("http://", "https://", "www.", "data:", "class ", "var ", "function ")


def body(path: Path) -> bytes:
    """SWF bytes with any compression removed."""
    raw = path.read_bytes()
    if raw[:3] == b"CWS":
        return b"FWS" + raw[3:8] + zlib.decompress(raw[8:])
    if raw[:3] == b"ZWS":
        return b"FWS" + raw[3:8] + zlib.decompress(raw[8:], -15)
    return raw


def referenced(folder: Path) -> set:
    """Asset-looking names inside every SWF in this game folder."""
    names = set()
    for swf in sorted(folder.glob("*.swf")):
        try:
            data = body(swf)
        except Exception as exc:                                      # noqa: BLE001
            print("   ! %s: %s" % (swf.name, exc))
            continue
        for m in ASSET.finditer(data):
            name = m.group(0).decode("ascii", "replace").lstrip("/")
            if name.startswith(SKIP_PREFIX) or ".." in name or len(name) < 5:
                continue
            if "/" not in name and not name.lower().endswith((".swf", ".txt")):
                continue                    # bare words are not paths
            names.add(name)
    return names


def main() -> int:
    base, host_header = fc.resolve_base(PUBLIC)
    print("publisher: %s (Host: %s)" % (base, host_header or "-"))
    total_added = []
    for game in ("LP1", "LP2", "LP3"):
        folder = CLOUD / game
        names = referenced(folder)
        have = {str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file()}
        want = sorted(n for n in names if n not in have)
        print("\n%s: %d referenced, %d missing" % (game, len(names), len(want)))
        for rel in want:
            url = base + game + "/" + rel
            try:
                req = urllib.request.Request(url)
                if host_header:
                    req.add_header("Host", host_header)
                with urllib.request.urlopen(req, timeout=25) as r:
                    data = r.read()
                if r.status != 200 or not data:
                    print("   - %-30s http %s" % (rel, r.status))
                    continue
            except Exception as exc:                                  # noqa: BLE001
                print("   - %-30s %s" % (rel, str(exc)[:60]))
                continue
            dest = folder / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            total_added.append("%s/%s" % (game, rel))
            print("   + %-30s %8d bytes" % (rel, len(data)))
    print("\nadded %d files" % len(total_added))
    return 0


if __name__ == "__main__":
    sys.exit(main())
