#!/usr/bin/env python3
"""Remove the duplicated LP2 preset block (the first patch run added it, then the
retry added it again)."""
import pathlib
import subprocess
import sys

S = pathlib.Path.home() / "Downloads/littleprince-launcher/lpo/server.py"
src = S.read_text()

BLOCK = '''    {
        "id": "lp2_bosses", "game": "LP2",'''
END = '''    {
        "id": "lp3_cards", "game": "LP3",'''

first = src.find(BLOCK)
second = src.find(BLOCK, first + 1)
if second == -1:
    print("no duplicate found; nothing to do")
    sys.exit(0)

# the duplicate runs from the second BLOCK up to the lp3_cards entry that follows it
end = src.find(END, second)
if end == -1:
    print("!! could not find the end of the duplicate")
    sys.exit(1)

removed = src[second:end]
src = src[:second] + src[end:]
S.write_text(src)
print("removed %d chars (the second copy)" % len(removed))

for k in ("lp2_bosses", "lp2_gems", "lp2_levels"):
    print("  %s now appears %d time(s)" % (k, src.count('"%s"' % k)))

r = subprocess.run([sys.executable, "-m", "py_compile", str(S)], capture_output=True, text=True)
print("py_compile:", "OK" if r.returncode == 0 else r.stderr[-400:])

sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402
ids = [p["id"] for p in srv.MODS_PRESETS]
print("\npreset ids:", ids)
print("unique    :", len(ids) == len(set(ids)))
print("LP2 presets:", [p["id"] for p in srv.MODS_PRESETS if p["game"] == "LP2"])
