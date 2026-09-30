#!/usr/bin/env python3
"""The click works now - only the hover/press feedback is missing.

That feedback comes from mcBtnManager.addMCButton (it maps the clip's _up/_over/_down
frames and plays the hover sounds).  I removed it because I suspected it of blanking the
stage, but the evidence now says the blanking was the throwing lookup, not this call - the
button found on mp_result_end is a real display object, and the click listener the manager
would also install is harmless here.

Re-add it inside a guard, so if the object is a type the manager cannot take, the hover
stays off and nothing breaks.

Note from the log: the retry clip exists only on mp_result_end.  On the verdict frame the
lookup finds nothing, which is why both are wired - only the end frame's wiring matters.
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

shutil.rmtree("/tmp/lpo_re", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_re", str(L / "lpo/patches/lib/lib.swf")], capture_output=True, text=True)
shutil.copy2(pathlib.Path("/tmp/lpo_re/scripts/PrinceOnline/UI_multiplay.as"), SRC)
src = SRC.read_text()

ANCHOR = 'Debug.addLog("\\\\tmp_diag: listener attached");'
assert ANCHOR in src, "anchor missing"
ADD = ANCHOR + '''
            try
            {
               this.mcBtnManager.addMCButton(rb,"SFX_drag",null,"SFX_drop");
               Debug.addLog("\\\\tmp_diag: hover/press effects restored");
            }
            catch(sfxErr:*)
            {
               Debug.addLog("\\\\tmp_diag: effects skipped " + sfxErr);
            }'''
src = src.replace(ANCHOR, ADD, 1)
SRC.write_text(src)
print("guarded addMCButton added back into mpWireRetry")

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print("\n".join(l for l in r.stdout.splitlines() if l.startswith(("new ", "base "))))
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer complained"); print(r.stdout[-400:]); sys.exit(1)

out = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as").read_text()
checks = [("mpFind once", out.count("function mpFind(") == 1),
          ("mpWireRetry once", out.count("function mpWireRetry") == 1),
          ("no bracket lookup", not re.search(r'this\["btnRetry', out)),
          ("effects call present", "addMCButton" in out),
          ("click listener present", "MouseEvent.CLICK" in out),
          ("play again present", "mpPlayAgain(" in out)]
for label, ok in checks:
    print("   %-24s %s" % (label, ok))
if not all(ok for _, ok in checks):
    print("!! check failed - NOT shipping"); sys.exit(1)

for p in sorted(L.rglob("lib.swf")):
    shutil.copy2(p, KEEP / (p.parent.relative_to(L).as_posix().replace("/", "_") + ".bak"))
    shutil.copy2("/tmp/lib_one.swf", p)
print("deployed ->", md5(L / "lpo/patches/lib/lib.swf"))
subprocess.run(["python3", str(TOOLS / "build_local.py")], capture_output=True, text=True, cwd=TOOLS)
r = subprocess.run(["python3", str(TOOLS / "ship_launcher_pack.py")],
                   capture_output=True, text=True, cwd=TOOLS)
for l in r.stdout.splitlines():
    if "drive after" in l or "VERIFIED" in l:
        print(l)
