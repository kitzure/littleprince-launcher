#!/usr/bin/env python3
"""Export the small SWFs that carry the level/card gates, then grep them."""
import pathlib
import subprocess
import sys

JAR = pathlib.Path.home() / "lpo_build/ffdec/ffdec.jar"
L = pathlib.Path.home() / "Downloads/littleprince-launcher"

print("=== what is in LP1's first game folder and LP3's root ===")
for d in ("cloud/LP1/game1", "cloud/LP1/game13"):
    p = L / d
    if p.is_dir():
        print("  %s: %s" % (d, sorted(f.name for f in p.iterdir())[:8]))
print("  cloud/LP1 swfs:", sorted(f.name for f in (L / "cloud/LP1").glob("*.swf")))

targets = []
g1 = L / "cloud/LP1/game1"
if g1.is_dir():
    targets += [("lp1_game1", s) for s in sorted(g1.glob("*.swf"))]
c1 = L / "cloud/LP1/card.swf"
if c1.is_file():
    targets.append(("lp1_card", c1))
for name, path in (("lp3_card", L / "cloud/LP3/card.swf"),
                   ("lp3_buycard", L / "cloud/LP3/buycard.swf"),
                   ("lp3_cardseq", L / "cloud/LP3/cardseq.swf"),
                   ("lp3_gamea1", L / "cloud/LP3/gamea1.swf")):
    if path.is_file():
        targets.append((name, path))

for tag, swf in targets:
    out = "/tmp/x_%s" % tag
    r = subprocess.run(["java", "-jar", str(JAR), "-export", "script", out, str(swf)],
                       capture_output=True, text=True)
    n = len(list(pathlib.Path(out).rglob("*.as"))) if pathlib.Path(out).exists() else 0
    print("  %-12s %-28s %d scripts  rc=%d" % (tag, swf.name, n, r.returncode))

print("\n=== grepping for the gates ===")
for tag, _ in targets:
    root = pathlib.Path("/tmp/x_%s" % tag)
    if not root.exists():
        continue
    hits = []
    for f in root.rglob("*.as"):
        t = f.read_text(errors="ignore")
        for i, line in enumerate(t.splitlines(), 1):
            low = line.lower()
            if any(k in low for k in ("gamecards", "cardsequence", "unlock",
                                      "levelmax", "openlev", "levlock")):
                hits.append("%s:%d %s" % (f.name, i, line.strip()[:100]))
    print("--- %s: %d hit(s)" % (tag, len(hits)))
    for h in hits[:12]:
        print("    " + h)
