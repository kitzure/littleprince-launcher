#!/usr/bin/env python3
"""Rebuild cloud/files.txt.

A file listed with size 0 is only checked for existence - that is what the host
pages we generate get, so a repair can never replace them with the publisher's
originals (which have no player configuration and would show a blank stage).
"""
from pathlib import Path

CLOUD = Path.home() / "Downloads/littleprince-patcher/cloud"
GENERATED = {f"{g}/index.html" for g in ("LP1", "LP2", "LP3")}

lines = []
for game in ("LP1", "LP2", "LP3"):
    for p in sorted((CLOUD / game).rglob("*")):
        if not p.is_file():
            continue
        rel = "%s/%s" % (game, p.relative_to(CLOUD / game).as_posix())
        size = 0 if rel in GENERATED else p.stat().st_size
        lines.append("%s\t%d" % (rel, size))
(CLOUD / "files.txt").write_text("\n".join(lines) + "\n")
print("cloud/files.txt: %d files (%d presence-only)" % (len(lines), len(GENERATED)))
