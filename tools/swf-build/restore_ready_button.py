#!/usr/bin/env python3
"""Restore the addMCButton call I clobbered.

The sweep that neutralised addMCButton matched two calls. One was the retry button (now
registered properly through mpWireRetry, so it must stay out). The other belonged to another
button - the Ready button in the multiplayer room - which is why its hover effect vanished.

Find both stubs, keep the retry one out, restore the other with the manager's standard
arguments.  Print what each one was so the decision is visible, not assumed.
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

stubs = list(re.finditer(r'Debug\.addLog\("\\\\tmp_diag: skipped addMCButton for " \+ (\w+)\.name\);', src))
print("neutralised addMCButton stubs found:", len(stubs))
for m in stubs:
    var = m.group(1)
    line_no = src[:m.start()].count("\n") + 1
    ctx = src[max(0, m.start() - 420):m.start()]
    method = re.findall(r"function (\w+)\(", ctx)
    print("   line %-5d var=%-12s inside %s" % (line_no, var, method[-1] if method else "?"))

if len(stubs) != 2:
    print("!! expected 2 stubs"); sys.exit(1)

for m in stubs:
    var = m.group(1)
    if var.lower().find("retry") >= 0:
        print("   keeping %s out (mpWireRetry registers it)" % var)
        continue
    src = src[:m.start()] + 'this.mcBtnManager.addMCButton(%s,"SFX_drag",null,"SFX_drop");' % var \
        + src[m.end():]
    print("   restored the registration for %s" % var)

SRC.write_text(src)
print("stubs left:", len(re.findall(r"skipped addMCButton", src)),
      "| addMCButton calls now:", src.count("addMCButton("))

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print("\n".join(l for l in r.stdout.splitlines() if l.startswith(("new ", "base "))))
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer complained"); print(r.stdout[-400:]); sys.exit(1)

out = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as").read_text()
checks = [("mpFind once", out.count("function mpFind(") == 1),
          ("mpWireRetry once", out.count("function mpWireRetry") == 1),
          ("no bracket lookup", not re.search(r'this\["btnRetry', out)),
          ("effects call still there", "hover/press effects restored" in out)]
for label, ok in checks:
    print("   %-26s %s" % (label, ok))
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
