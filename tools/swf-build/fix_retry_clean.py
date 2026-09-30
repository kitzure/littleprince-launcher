#!/usr/bin/env python3
"""Rebuild from the last good SWF, changing ONLY the button lookup.

The last good build is the one whose panel rendered (players + button) - its md5 is
d0c547407d39e99cc8ff915099fc393f, kept as a backup on the previous deploy.  My later
patches each re-exported and re-added the helper, stacking duplicate method definitions
(illegal in AS3), which is why the panel now draws nothing at all.
"""
import hashlib
import pathlib
import re
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()
JAR = HOME / "lpo_build/ffdec/ffdec-cli.jar"
KEEP = HOME / "lpo_build/swf_backups"
GOOD = "d0c547407d39e99cc8ff915099fc393f"
md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

print("=== backups available ===")
cands = []
for b in sorted(KEEP.glob("*.bak*")) + sorted(KEEP.glob("*.bak")):
    m = md5(b)
    print("   %-46s %s %s" % (b.name, m, "<<< the good one" if m == GOOD else ""))
    if m == GOOD:
        cands.append(b)
if not cands:
    print("!! the last good build is not in the backups")
    sys.exit(1)
base = cands[0]

# ── clean export of the good build ───────────────────────────────────────────
shutil.rmtree("/tmp/lpo_re", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_re", str(base)], capture_output=True, text=True)
SRC = pathlib.Path("/tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as")
shutil.copy2(pathlib.Path("/tmp/lpo_re/scripts/PrinceOnline/UI_multiplay.as"), SRC)
src = SRC.read_text()
print("\nbase: %s (%d chars)" % (base.name, len(src)))
print("   helpers defined:", src.count("function setupMpRetryButton"))
print("   calls made     :", src.count("setupMpRetryButton();"))

# ── only change: look up the plain btnRetry first ────────────────────────────
OLD = '''         var retryBtn:MovieClip = this["btnRetry" + Bridge.user.TextLanguage];'''
NEW = '''         var retryBtn:MovieClip = this["btnRetry"];
         if(retryBtn == null)
         {
            retryBtn = this["btnRetry" + Bridge.user.TextLanguage];
         }'''
n = src.count(OLD)
print("\nlookup sites to fix:", n)
if n != 1:
    print("!! expected exactly one lookup site")
    sys.exit(1)
src = src.replace(OLD, NEW, 1)
SRC.write_text(src)
print("patched: plain btnRetry is checked first")

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print(r.stdout[-700:])
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer complained - NOT deploying")
    sys.exit(1)

out = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as").read_text()
print("=== after the round trip ===")
print("   helpers defined  :", out.count("function setupMpRetryButton"), "(must be 1)")
print("   calls made       :", out.count("setupMpRetryButton();"), "(must be 1)")
print("   plain lookup     :", 'this["btnRetry"]' in out)
