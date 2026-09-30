#!/usr/bin/env python3
"""Ready button (multiplayer room) - the publisher's own call is missing its arguments.

    mcBtnManager.addMCButton(this.slotsUI.ui.btnMultiplayReady);

Every other registration in the client passes the hover/press sounds - the retry button,
which hovers correctly, uses ("SFX_drag", null, "SFX_drop").  With the argument list
truncated the manager cannot set the clip's hover frames, so the button only shows its idle
animation.  It is also unguarded, so a failure there kills the rest of label_room (the level
frame scripts that follow).

Give it the full, proven argument list and wrap it so the rest of the room handler always
runs.  Initialise the on-screen overlay on this frame too so the result is visible.
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

pat = re.compile(r"[ \t]*\w*\.?mcBtnManager\.addMCButton\(this\.slotsUI\.ui\.btnMultiplayReady\);[ \t]*")
n = len(pat.findall(src))
print("truncated Ready registrations found:", n)
if n != 1:
    print("!! expected exactly 1"); sys.exit(1)

REPL = '''this.mpDiag("room");
         try
         {
            this.mcBtnManager.addMCButton(this.slotsUI.ui.btnMultiplayReady,"SFX_drag",null,"SFX_drop");
            Debug.addLog("\\\\tmp_diag room: ready button registered");
         }
         catch(rbErr:*)
         {
            Debug.addLog("\\\\tmp_diag room: ready registration FAILED " + rbErr);
         }'''
src = pat.sub(REPL, src, 1)
SRC.write_text(src)

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print("\n".join(l for l in r.stdout.splitlines() if l.startswith(("new ", "base "))))
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer complained"); print(r.stdout[-400:]); sys.exit(1)

out = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as").read_text()
checks = [("full args now", 'btnMultiplayReady,"SFX_drag",null,"SFX_drop"' in out),
          ("guarded", "ready registration FAILED" in out),
          ("room diag present", 'mpDiag("room")' in out),
          ("mpFind once", out.count("function mpFind(") == 1),
          ("overlay click-through", "mouseChildren = false" in out),
          ("no bracket lookup", not re.search(r'this\["btnRetry', out))]
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
