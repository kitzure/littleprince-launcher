#!/usr/bin/env python3
"""Clean the mirror and verify all three cloud games really load."""
import json
import subprocess
import sys
from pathlib import Path

CLOUD = Path.home() / "Downloads/littleprince-patcher/cloud"
CHROME = sorted(Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome"))[-1]

# 1. a SWF built a query-string url and we stored it as a file
junk = [p for p in CLOUD.rglob("*") if p.is_file() and any(c in p.name for c in "?&=")]
for p in junk:
    print("removing junk: %s" % p.relative_to(CLOUD))
    p.unlink()

# 2. rewrite the manifest from what is actually here
lines = []
for game in ("LP1", "LP2", "LP3"):
    for p in sorted((CLOUD / game).rglob("*")):
        if p.is_file():
            lines.append("%s/%s\t%d" % (game, p.relative_to(CLOUD / game).as_posix(),
                                        p.stat().st_size))
(CLOUD / "files.txt").write_text("\n".join(lines) + "\n")
print("manifest: %d files" % len(lines))

# 3. render each game for real and report what it could not load
for game in ("LP1", "LP2", "LP3"):
    r = subprocess.run(["node", "/tmp/p2/shot_cdp.js", str(CHROME),
                        "http://127.0.0.1:8080/LP/personal/%s/" % game,
                        "/tmp/p2/cdp/%s.png" % game, "26000"],
                       capture_output=True, text=True, timeout=300)
    i = r.stdout.find("{")
    info = json.loads(r.stdout[i:]) if i >= 0 else {}
    errs = [e for e in info.get("http_errors", []) if "favicon" not in e]
    playing = [c for c in info.get("console", []) if "Loading SWF" in str(c)]
    print("\n%s: screenshot %d bytes" % (game, info.get("bytes", 0)))
    print("   requested SWF: %s" % (playing[0].split("Loading SWF file ")[-1] if playing else "?"))
    print("   unloadable files: %s" % (errs or "none"))
