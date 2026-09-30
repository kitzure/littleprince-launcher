#!/usr/bin/env python3
"""Verify the rebuilt class, then deploy it to every lib.swf the launcher serves."""
import hashlib
import pathlib
import shutil
import subprocess
import sys

NEW = pathlib.Path("/tmp/lib_one.swf")
OUT = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as")
L = pathlib.Path.home() / "Downloads/littleprince-launcher"

md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

print("=== the rebuilt class really contains the fix ===")
text = OUT.read_text()
for probe, label in (("closed a leftover popup", "popup close on the result frame"),
                     ('substr(0,8) == "btnRetry"', "accepts any language's retry button"),
                     ("Bridge.flow.toGameRoom()", "the play-again action"),
                     ("tmp_title:", "earlier title hardening kept"),
                     ("no retry button on this frame", "earlier retry guard kept")):
    print("   %-34s %s" % (label, probe in text))
print("   new lib.swf: %d bytes  md5 %s" % (NEW.stat().st_size, md5(NEW)))

print("\n=== every lib.swf the launcher serves ===")
targets = sorted(p for p in L.rglob("lib.swf"))
for p in targets:
    print("   %-58s %d bytes  md5 %s" % (str(p.relative_to(L)), p.stat().st_size, md5(p)))

if not targets:
    print("!! no lib.swf found")
    sys.exit(1)

print("\n=== deploying ===")
stamp = ".bak-mpagain"
for p in targets:
    if md5(p) == md5(NEW):
        print("   %-58s already current" % str(p.relative_to(L)))
        continue
    shutil.copy2(p, str(p) + stamp)
    shutil.copy2(NEW, p)
    print("   %-58s -> %s (backup %s)" % (str(p.relative_to(L)), md5(p), stamp))

print("\n=== read back ===")
for p in targets:
    print("   %-58s %s %s" % (str(p.relative_to(L)), md5(p),
                              "OK" if md5(p) == md5(NEW) else "MISMATCH"))
