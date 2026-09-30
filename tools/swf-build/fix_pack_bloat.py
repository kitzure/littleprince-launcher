#!/usr/bin/env python3
"""Two 577 KB backups named *.bak-mpagain slipped past the build's exclusion and inflated
the pack by 1.15 MB.  Keep them, but outside the launcher tree, then re-ship."""
import pathlib
import shutil
import subprocess

L = pathlib.Path.home() / "Downloads/littleprince-launcher"
KEEP = pathlib.Path.home() / "lpo_build/swf_backups"
KEEP.mkdir(exist_ok=True)

print("=== what the build excludes ===")
bl = pathlib.Path.home() / "Downloads/littleprince-patcher-handoff/tools/build_local.py"
for i, line in enumerate(bl.read_text().splitlines(), 1):
    if "bak" in line.lower() or "exclude" in line.lower() or "ignore" in line.lower():
        print("   build_local.py:%d %s" % (i, line.strip()[:100]))

print("\n=== moving the backups out of the pack tree ===")
for p in sorted(L.rglob("*.bak-mpagain")):
    dest = KEEP / (p.parent.relative_to(L).as_posix().replace("/", "_") + ".bak-mpagain")
    shutil.move(str(p), str(dest))
    print("   %s -> %s (%d bytes)" % (p.relative_to(L), dest.name, dest.stat().st_size))

print("\n=== the launcher tree now ===")
for p in sorted(L.rglob("lib.swf")) + sorted(L.rglob("*.bak*")):
    print("   %-58s %d bytes" % (str(p.relative_to(L)), p.stat().st_size))

print("\n=== rebuild + ship ===")
T = pathlib.Path.home() / "Downloads/littleprince-patcher-handoff/tools"
for script in ("build_local.py", "ship_launcher_pack.py"):
    r = subprocess.run(["python3", str(T / script)], capture_output=True, text=True, cwd=T)
    tail = [l for l in r.stdout.splitlines() if l.strip()][-3:]
    print("   %s:" % script)
    for l in tail:
        print("      " + l)
