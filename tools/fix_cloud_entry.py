#!/usr/bin/env python3
"""Take each cloud game's entry SWF from the publisher's own index page.

The host pages I generate hardcoded LP1's `start.swf`, but LP2 and LP3 load
`index.swf` - so those two showed an empty stage (404 on the entry file).
The publisher's original page is the source of truth; read it, do not guess.
"""
import re
import sys
from pathlib import Path

CLOUD = Path.home() / "Downloads/littleprince-patcher/cloud"


def entry_of(original: Path) -> str:
    """The movie the publisher's own page plays."""
    html = original.read_text(errors="replace")
    # AC_FL_RunContent(p1, p2, ..., 'movie', 'x.swf', ...) or <param name="movie" value="x.swf">
    for pattern in (r"""['"](?:movie|src|data)['"]\s*,\s*['"]([^'"]+\.swf)['"]""",
                    r"""name=["']movie["']\s+value=["']([^"']+\.swf)["']""",
                    r"""data=["']([^"']+\.swf)["']"""):
        m = re.search(pattern, html, re.I)
        if m:
            return m.group(1)
    raise SystemExit("no entry swf found in %s" % original)


fixed = []
for game in ("LP1", "LP2", "LP3"):
    folder = CLOUD / game
    original = folder / "index.original.html"
    page = folder / "index.html"
    if not original.exists() or not page.exists():
        print("skip %s (missing page)" % game)
        continue
    want = entry_of(original)
    html = page.read_text()
    m = re.search(r'const ENTRY = "([^"]+)"', html)
    have = m.group(1) if m else None
    if have == want:
        print("%s: already %s" % (game, want))
        continue
    if not (folder / want).exists():
        print("%s: !! publisher loads %s but it is NOT in the mirror" % (game, want))
    html = re.sub(r'const ENTRY = "[^"]+"', 'const ENTRY = "%s"' % want, html, count=1)
    page.write_text(html)
    fixed.append((game, have, want))
    print("%s: entry %s -> %s" % (game, have, want))

print("fixed:", fixed or "nothing")
sys.exit(0 if not fixed or all(True for _ in fixed) else 1)
