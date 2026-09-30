#!/usr/bin/env python3
"""Heal the cloud mirror by listening to the games themselves.

Render each game in a real browser, collect every file it asks for and we do not
have, download those from the publisher, and repeat.  A SWF requests its music
and effects by name at runtime, so this is the only reliable source for them -
a string scan and a link crawl both miss them.
"""
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path.home() / "Downloads/littleprince-patcher/lpo"))
import fetch_client as fc                                            # noqa: E402

CLOUD = Path.home() / "Downloads/littleprince-patcher/cloud"
PUB = "http://www1.little-prince.com.hk/LP/personal/"
CHROME = sorted(Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome"))[-1]
LOCAL = "http://127.0.0.1:8080/LP/personal/%s/"
GAMES = ("LP1", "LP2", "LP3")


def render(game: str) -> dict:
    """Screenshot the game in a real browser and report its failures."""
    out = "/tmp/p2/cdp/%s.png" % game
    r = subprocess.run(["node", "/tmp/p2/shot_cdp.js", str(CHROME), LOCAL % game, out, "14000"],
                       capture_output=True, text=True, timeout=240)
    i = r.stdout.find("{")
    if i < 0:
        print("   ! no output from the browser for %s" % game)
        return {}
    return json.loads(r.stdout[i:])


def wanted(info: dict) -> set:
    """Local paths this game asked for and did not get."""
    hits = set()
    for line in list(info.get("http_errors", [])) + list(info.get("failed", [])):
        m = re.search(r"(/LP/personal/[^ \"']+)", line)
        if m and not m.group(1).endswith("favicon.ico"):
            hits.add(m.group(1))
    return hits


def main() -> int:
    base, host = fc.resolve_base(PUB)
    print("publisher: %s   (Host header: %s)" % (base, host or "-"))
    session = []
    for attempt in range(1, 6):
        todo = set()
        sizes = {}
        for game in GAMES:
            info = render(game)
            sizes[game] = info.get("bytes", 0)
            todo |= wanted(info)
        print("\npass %d: %s" % (attempt, ", ".join("%s %d b" % (g, sizes[g]) for g in GAMES)))
        added = 0
        for path in sorted(todo):
            rel = path.split("/LP/personal/", 1)[1]
            dest = CLOUD / rel
            if dest.exists():
                print("   = %-28s already here" % rel)
                continue
            try:
                req = urllib.request.Request(base + rel)
                if host:
                    req.add_header("Host", host)
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = r.read()
                    status = r.status
                if status != 200 or not data:
                    print("   - %-28s http %s" % (rel, status))
                    continue
            except Exception as exc:                                  # noqa: BLE001
                print("   - %-28s %s" % (rel, str(exc)[:50]))
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            session.append(rel)
            added += 1
            print("   + %-28s %8d bytes" % (rel, len(data)))
        if not todo:
            print("\nnothing missing - all three games load cleanly")
            break
        if not added:
            print("\n%d still missing and the publisher does not serve them" % len(todo))
            break
        time.sleep(1)

    # the manifest the package verifies against
    lines = []
    for g in GAMES:
        for p in sorted((CLOUD / g).rglob("*")):
            if p.is_file():
                lines.append("%s/%s\t%d" % (g, p.relative_to(CLOUD / g).as_posix(), p.stat().st_size))
    (CLOUD / "files.txt").write_text("\n".join(lines) + "\n")
    print("\nmanifest: cloud/files.txt, %d files" % len(lines))
    print("downloaded this session: %d" % len(session))
    return 0


if __name__ == "__main__":
    sys.exit(main())
