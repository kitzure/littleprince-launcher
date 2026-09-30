#!/usr/bin/env python3
"""Verify the CLICK listener survived, deploy it, and ship."""
import hashlib
import pathlib
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()
NEW = pathlib.Path("/tmp/lib_one.swf")
OUT = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as")
L = HOME / "Downloads/littleprince-launcher"
KEEP = HOME / "lpo_build/swf_backups"
TOOLS = HOME / "Downloads/littleprince-patcher-handoff/tools"
md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

print("=== the class after the round trip ===")
text = OUT.read_text()
checks = (("addEventListener", "a real listener is present"),
          ("MouseEvent.CLICK", "and it is the CLICK event"),
          ('mpPlayAgain("clip")', "it calls the shared action"),
          ("onRelease = function", "NO as2 onRelease assignment left"),
          ("function mpPlayAgain", "the shared method"),
          ("mpPlayAgain(_loc4_)", "the manager dispatch path"),
          ("closed a leftover popup", "the popup close"),
          ("tmp_title:", "the title hardening"))
for probe, label in checks:
    got = probe in text
    want = not label.startswith("NO ")
    print("   %-36s %s%s" % (label, got, "" if got == want else "   <<< UNEXPECTED"))

print("\n=== deploy ===")
for p in sorted(L.rglob("lib.swf")):
    if md5(p) == md5(NEW):
        print("   %-46s already current" % str(p.relative_to(L)))
        continue
    shutil.copy2(p, KEEP / (p.parent.relative_to(L).as_posix().replace("/", "_") + ".bak"))
    shutil.copy2(NEW, p)
    print("   %-46s -> %s" % (str(p.relative_to(L)), md5(p)))
for p in sorted(L.rglob("lib.swf")):
    assert md5(p) == md5(NEW), "deploy mismatch on %s" % p
print("   both copies verified at %s" % md5(NEW))

print("\n=== build + ship ===")
for script in ("build_local.py", "ship_launcher_pack.py"):
    r = subprocess.run(["python3", str(TOOLS / script)], capture_output=True, text=True, cwd=TOOLS)
    print("   %s:" % script)
    for line in [l for l in r.stdout.splitlines() if l.strip()][-3:]:
        print("      " + line)
    if r.returncode != 0:
        print("      stderr:", r.stderr[-300:])
        sys.exit(1)
