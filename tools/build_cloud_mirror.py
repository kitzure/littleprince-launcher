#!/usr/bin/env python3
"""Build the local mirror of the cloud portal inside the package.

Layout mirrors the publisher's own:
    cloud/                 the portal page (three game buttons) + css + images
    cloud/LP1|LP2|LP3/     each game's own page, its SWFs and its audio
"""
import re, shutil, urllib.request, urllib.error, zlib
from pathlib import Path

BASE = "http://www1.little-prince.com.hk"
SRC = Path("/tmp/p2/cloud")
PKG = Path.home() / "Downloads" / "littleprince-patcher"
DST = PKG / "cloud"
UA = "Mozilla/5.0 (LittlePrinceBrowserHome)"
ENTRY = {"LP1": "start.swf", "LP2": "index.swf", "LP3": "index.swf"}
TITLES = {"LP1": "Little Prince", "LP2": "Starwish Legend", "LP3": "Starwish Adventure"}


def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


shutil.rmtree(DST, ignore_errors=True)
DST.mkdir(parents=True)

# ── portal page + its assets ─────────────────────────────────────────────────
(DST / "index.html").write_bytes(get("/LP/personal/"))
(DST / "css").mkdir()
(DST / "css" / "style.css").write_bytes(get("/LP/personal/css/style.css"))
(DST / "images").mkdir()
try:
    (DST / "images" / "favicon.ico").write_bytes(get("/LP/personal/images/favicon.ico"))
except urllib.error.HTTPError:
    print("  (no favicon)")

# ── each game ────────────────────────────────────────────────────────────────
manifest = {}
for game, entry in ENTRY.items():
    rows = [l.split("\t") for l in (SRC / f"manifest_{game}.txt").read_text().splitlines() if "\t" in l]
    manifest[game] = [(n, int(s)) for n, s in rows]
    gdir = DST / game
    for name, size in manifest[game]:
        src = SRC / game / name
        dst = gdir / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    # the game's own host page (what /LP/personal/LPn/ serves) + its JS
    (gdir / "index.html").write_bytes(get(f"/LP/personal/{game}/"))
    try:
        (gdir / "AC_RunActiveContent.js").write_bytes(get(f"/LP/personal/{game}/AC_RunActiveContent.js"))
    except urllib.error.HTTPError:
        print(f"  {game}: no AC_RunActiveContent.js")
    print(f"  {game}: {len(manifest[game])} files, "
          f"{sum(s for _, s in manifest[game])/1e6:.1f} MB, entry {entry}")

totals = sum(sum(s for _, s in v) for v in manifest.values())
print(f"\nmirror: {DST}  ({totals/1e6:.1f} MB of game files + the portal page)")
for p in sorted(DST.rglob("*")):
    if p.is_file() and p.parent == DST:
        print("   ", p.relative_to(DST), p.stat().st_size)
