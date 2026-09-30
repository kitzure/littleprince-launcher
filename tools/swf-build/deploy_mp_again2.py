#!/usr/bin/env python3
"""Confirm the new code survived the round trip, then deploy to every served copy."""
import hashlib
import pathlib
import shutil
import sys

NEW = pathlib.Path("/tmp/lib_one.swf")
OUT = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as")
L = pathlib.Path.home() / "Downloads/littleprince-launcher"
KEEP = pathlib.Path.home() / "lpo_build/swf_backups"
KEEP.mkdir(exist_ok=True)

md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

print("=== the rebuilt class after the round trip ===")
text = OUT.read_text()
for probe, label in (("function mpPlayAgain", "the shared play-again method"),
                     ("mpPlayAgain(_loc4_)", "the release-dispatch branch calls it"),
                     ('mpPlayAgain("clip")', "the clip's own release calls it"),
                     ("retryBtn.onRelease", "the clip carries an onRelease"),
                     ("closed a leftover popup", "the popup close is still there"),
                     ("substr(0,8) == \"btnRetry\"", "accepts any language's button"),
                     ("tmp_title:", "the earlier title hardening is intact")):
    print("   %-40s %s" % (label, probe in text))
print("   new lib.swf: %d bytes  md5 %s" % (NEW.stat().st_size, md5(NEW)))

print("\n=== deploy ===")
for p in sorted(L.rglob("lib.swf")):
    if md5(p) == md5(NEW):
        print("   %-52s already current" % str(p.relative_to(L)))
        continue
    keep = KEEP / (p.parent.relative_to(L).as_posix().replace("/", "_") + ".bak")
    shutil.copy2(p, keep)
    shutil.copy2(NEW, p)
    print("   %-52s -> %s  (backup kept in lpo_build/swf_backups)" % (str(p.relative_to(L)), md5(p)))

print("\n=== read back ===")
for p in sorted(L.rglob("lib.swf")):
    print("   %-52s %s %s" % (str(p.relative_to(L)), md5(p),
                              "OK" if md5(p) == md5(NEW) else "MISMATCH"))
backups = sorted(KEEP.glob("*.bak*"))
print("\nbackups (outside the pack tree): %d" % len(backups))
for b in backups:
    print("   %s  %d bytes" % (b.name, b.stat().st_size))
