#!/usr/bin/env python3
"""What presets exist today, and kick off the LP1/LP3 source exports."""
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402

print("=== presets today ===")
for p in srv.MODS_PRESETS:
    keys = sorted((p.get("profile") or {}).keys()) + \
           sorted((p.get("progress") or {}).keys())
    print("  %-16s %-4s %-30s writes %s" % (p["id"], p["game"], p["label"], keys))

print("\n=== LP1 / LP3 login payload fields the server sends ===")
for game in ("prince1", "prince3"):
    src = pathlib.Path(srv.__file__).read_text()
    i = src.find('game.lower() == "%s"' % game)
    if i < 0:
        i = src.find("game_lower == \"%s\"" % game)
    print("  %s branch at char %d" % (game, i))
    chunk = src[i:i + 1600]
    for line in chunk.splitlines():
        s = line.strip()
        if ("payload[" in s or "profile.get(" in s or "saved.get(" in s) and "=" in s:
            print("     ", s[:110])
        if s.startswith("# ") and "branch" in s.lower():
            print("     ", s[:110])

print("\n=== kicking off the source exports (this is the slow part) ===")
launcher = pathlib.Path.home() / "Downloads/littleprince-launcher"
for game, out in (("LP1", "/tmp/lp1_src"), ("LP3", "/tmp/lp3_src")):
    swf = launcher / "cloud" / game / "index.swf"
    if not swf.is_file():
        print("  %s: no %s" % (game, swf))
        continue
    job = subprocess.Popen(
        ["java", "-jar", str(pathlib.Path.home() / "ffdec/ffdec.jar"),
         "-export", "script", out, str(swf)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("  %s -> %s (pid %d)" % (game, out, job.pid))
print("  exports started in the background; they take a few minutes")
