#!/usr/bin/env python3
"""One shot: the writer's game_result handling, LP3's level table, LP1's level gate."""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402

src = pathlib.Path(srv.__file__).read_text()

print("=== the preset writer's extra sections (beyond profile/progress) ===")
i = src.find("def apply_mods")
chunk = src[i:i + 3000]
for line in chunk.splitlines():
    s = line.strip()
    if s.startswith(("if ", "elif ", "preset.get(", "for ", "accounts.", "written", "log.info")):
        print("   " + s[:104])

print("\n=== what LP3's own client says the levels are (miniGameSetting) ===")
p3 = pathlib.Path("/tmp/lp3_src/scripts/__Packages/Prince3/PrinceSystem.as").read_text(errors="ignore")
m = re.search(r"miniGameSetting\s*=\s*(.{0,400})", p3, re.S)
print("   " + (m.group(1)[:300].replace("\r", "").replace("\n", " ") if m else "not found in the package"))

print("\n=== does the server know LP3's level counts? ===")
for name in dir(srv):
    if "LEVEL" in name.upper() or "GAMESPEC" in name.upper() or "LP3" in name.upper():
        v = getattr(srv, name)
        if isinstance(v, (list, tuple, dict)):
            print("   %-18s %s" % (name, str(v)[:150]))
        elif isinstance(v, (int, str)):
            print("   %-18s %r" % (name, v))

print("\n=== LP1: which reply fields exist for levels/cards ===")
i = src.find('game.lower() == "prince1"')
print("   " + "\n   ".join(l.strip() for l in src[i:i + 1400].splitlines()
                           if "payload[" in l or "=" in l and "payload" in l)[:600])
