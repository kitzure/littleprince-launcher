#!/usr/bin/env python3
"""The LP1/LP3 preset definitions and the constants they build from."""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402

print("=== LP1_LEVELS ===")
lv = getattr(srv, "LP1_LEVELS", None)
print("  type:", type(lv).__name__, " len:", len(lv) if hasattr(lv, "__len__") else "?")
print("  value:", str(lv)[:300])

print("\n=== the LP1 / LP3 presets as written ===")
src = pathlib.Path(srv.__file__).read_text()
for pid in ("lp1_levels", "lp1_scores", "lp1_gems", "lp3_cards", "lp3_gems"):
    i = src.find('"id": "%s"' % pid)
    if i < 0:
        print("  %s: not found" % pid)
        continue
    chunk = src[i:i + 900]
    end = chunk.find('\n    },')
    print("--- %s ---" % pid)
    print(chunk[:end if end > 0 else 700])

print("\n=== LP3: what the reply carries and what the client writes back ===")
i = src.find('game.lower() == "prince3"')
print(src[i:i + 900] if i > 0 else "  (prince3 branch not found by that spelling)")
