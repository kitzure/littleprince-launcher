#!/usr/bin/env python3
"""Repair the botched restore.

My earlier sweep replaced `this.mcBtnManager.addMCButton(<button>, "a", null, "b")` with a
stub that named the WRONG captured group (the manager, not the button), and the restore then
passed the manager itself as the button.  Recover the real calls from the export of the good
build (the publisher's own code) and put the right ones back.

The stub in label_mp_result_end is the retry button's - retry is registered by mpWireRetry,
so that one must simply go.  The other is the button whose hover the user lost.
"""
import hashlib
import pathlib
import re
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()
JAR = HOME / "lpo_build/ffdec/ffdec-cli.jar"
L = HOME / "Downloads/littleprince-launcher"
KEEP = HOME / "lpo_build/swf_backups"
TOOLS = HOME / "Downloads/littleprince-patcher-handoff/tools"
SRC = pathlib.Path("/tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as")
md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

GOOD = pathlib.Path("/tmp/lpo_good_exp/scripts/PrinceOnline/UI_multiplay.as")
if not GOOD.exists():
    shutil.rmtree("/tmp/lpo_good_exp", ignore_errors=True)
    subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                    "/tmp/lpo_good_exp", "/tmp/lib_good.swf"], capture_output=True, text=True)
g = GOOD.read_text()
print("=== the publisher's original addMCButton calls (from the good build) ===")
for m in re.finditer(r"([\w\.]+)\.addMCButton\(([^;]*?)\);", g):
    line = g[:m.start()].count("\n") + 1
    ctx = re.findall(r"function (\w+)\(", g[max(0, m.start() - 3000):m.start()])
    print("   L%-5d %-22s %s   [in %s]" % (line, m.group(1), m.group(2)[:64],
                                           ctx[-1] if ctx else "?"))

# what the deployed class has now
shutil.rmtree("/tmp/lpo_re", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_re", str(L / "lpo/patches/lib/lib.swf")], capture_output=True, text=True)
shutil.copy2(pathlib.Path("/tmp/lpo_re/scripts/PrinceOnline/UI_multiplay.as"), SRC)
src = SRC.read_text()
bad = re.findall(r"[^\n]*addMCButton\(mcBtnManager[^\n]*", src)
print("\n=== the bad lines I just shipped ===")
for b in bad:
    print("   " + b.strip()[:100])
print("count:", len(bad))
