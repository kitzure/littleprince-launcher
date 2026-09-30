#!/usr/bin/env python3
"""Fix the botched restore AND make the overlay mouse-transparent.

1. The bad lines: one landed in label_mp_result_end (live) and one inside the now-unused
   setupMpRetryButton (dead).  Both passed the manager itself as the button.  The retry
   button is registered by mpWireRetry, so remove them; keep a correct call only where it
   does not duplicate that.

2. The Ready button losing its hover: the diagnostic overlay adds a Sprite + TextField to
   the UI.  A TextField is mouse-interactive by default, so the overlay was eating hovers in
   its 560x220 corner.  Set mouseChildren/mouseEnabled false on the holder so the overlay is
   click-through - it only ever needed to display text.
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

# 1 - drop the bad lines (whole line, including the corrupted "Dethis..." one)
before = len(re.findall(r"addMCButton\(mcBtnManager", src))
src = re.sub(r"[^\n]*addMCButton\(mcBtnManager[^\n]*\n", "", src)
print("bad addMCButton lines removed:", before)
if before != 2:
    print("!! expected 2"); sys.exit(1)

# 2 - make the overlay click-through
n = 0
old = '''               this.addChild(holder);
               Debug.init(holder,560,220);'''
new = '''               holder.mouseEnabled = false;
               holder.mouseChildren = false;
               this.addChild(holder);
               Debug.init(holder,560,220);
               try
               {
                  Debug.tf_debug.mouseEnabled = false;
               }
               catch(mt:*)
               {
               }'''
if old in src:
    src = src.replace(old, new, 1)
    n += 1
src = src.replace('Debug.init(holder,560,220);\n            }\n            Debug.enable();',
                  'Debug.init(holder,560,220);\n               Debug.tf_debug.mouseEnabled = false;\n            }\n            Debug.enable();', 1)
print("click-through patch applied:", n)
SRC.write_text(src)

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print("\n".join(l for l in r.stdout.splitlines() if l.startswith(("new ", "base "))))
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer complained"); print(r.stdout[-400:]); sys.exit(1)

out = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as").read_text()
checks = [("bad lines gone", "addMCButton(mcBtnManager" not in out),
          ("no 'Dethis'", "Dethis" not in out),
          ("overlay click-through", "mouseChildren = false" in out or "mouseEnabled = false" in out),
          ("mpFind once", out.count("function mpFind(") == 1),
          ("no bracket lookup", not re.search(r'this\["btnRetry', out)),
          ("retry effects kept", "hover/press effects restored" in out)]
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
