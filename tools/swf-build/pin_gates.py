#!/usr/bin/env python3
"""Pin the actual gates: LP1's level unlock + LP1's card fields, and LP3's `process`."""
import pathlib

def grep(tag, keys, limit=8):
    root = pathlib.Path("/tmp/x_%s" % tag)
    if not root.exists():
        print("--- %s: not exported" % tag)
        return
    print("--- %s" % tag)
    n = 0
    for f in sorted(root.rglob("*.as")):
        for i, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
            low = line.lower()
            if any(k in low for k in keys):
                print("    %s:%d %s" % (f.name, i, line.strip()[:104]))
                n += 1
                if n >= limit:
                    return
    if not n:
        print("    (no hits)")

print("=== what got exported for LP1 ===")
for d in "/tmp/x_lp1_game1", "/tmp/x_lp1_card", "/tmp/lp1_src":
    p = pathlib.Path(d)
    if p.exists():
        files = list(p.rglob("*.as"))
        print("  %-18s %d scripts: %s" % (d, len(files),
                                          [f.name for f in files[:6]]))

print("\n=== LP1: the level gate ===")
grep("lp1_game1", ["gameresult", "gamelevel", "levelnum", "levnum", "unlock", "starnum",
                   "totstar", "openev", "clicklev"])
print("\n=== LP1: card fields ===")
grep("lp1_card", ["gamecards", "cards", "cardnum", "owncard"])
grep("lp1_game1", ["gamecards"])
print("\n=== LP3: process (the per-game progress?) ===")
grep("lp3_gamea1", ["process", "curlev", "lev"])
print("\n=== LP3: what hands a card to the player ===")
grep("lp3_buycard", ["gamecards", "curuser.score", "score -", "cost"])
