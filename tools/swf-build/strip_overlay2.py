#!/usr/bin/env python3
"""Strip the overlay properly: replace the whole mpDiag body.

The line-by-line regex only matched 2 of 8 patterns (the re-exported code differs from what
I wrote), and my own guard then correctly refused to deploy.  Replacing the method body by
brace matching is reliable - the same technique that worked for the other helpers.

mpDiag keeps logging, but no longer creates or enables the on-screen text field, so the
overlay disappears while the addLog calls stay inert (they only trace()).
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
TOOLS = HOME / "Downloads/littleprince-patcher-handoff/tools"
SRC = pathlib.Path("/tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as")
md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

shutil.rmtree("/tmp/lpo_re", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_re", str(L / "lpo/patches/lib/lib.swf")], capture_output=True, text=True)
shutil.copy2(pathlib.Path("/tmp/lpo_re/scripts/PrinceOnline/UI_multiplay.as"), SRC)
src = SRC.read_text()
print("before: Debug.init=%d Debug.enable=%d" % (src.count("Debug.init("), src.count("Debug.enable()")))


def replace_method(text, name, new_body):
    m = re.search(r"( *)public function %s\([^)]*\) : void" % name, text)
    if not m:
        raise SystemExit("!! %s not found" % name)
    start = text.index("{", m.end())
    depth, i = 0, start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return text[:m.start()] + new_body + text[i + 1:]


NEW = '''public function mpDiag(where:String) : void
      {
         try
         {
            Debug.addLog("\\\\tmp_diag @ " + where + " frame=" + this.currentLabel);
         }
         catch(diagErr:*)
         {
         }
      }'''
src = replace_method(src, "mpDiag", NEW)
# and any stray enable/init calls outside it
src = re.sub(r"[ \t]*Debug\.enable\(\);[ \t]*\n", "", src)
src = re.sub(r"[ \t]*Debug\.init\([^;]*\);[ \t]*\n", "", src)
print("after : Debug.init=%d Debug.enable=%d" % (src.count("Debug.init("), src.count("Debug.enable()")))
if "Debug.init(" in src or "Debug.enable()" in src:
    print("!! remnants"); sys.exit(1)
SRC.write_text(src)

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print("\n".join(l for l in r.stdout.splitlines() if l.startswith(("new ", "base "))))
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer error"); print(r.stdout[-300:]); sys.exit(1)
out = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as").read_text()
checks = [("overlay gone", "Debug.init(" not in out and "Debug.enable()" not in out),
          ("ready fix kept", 'btnMultiplayReady,"SFX_drag",null,"SFX_drop"' in out),
          ("ready guard kept", "ready registration FAILED" in out),
          ("mpFind once", out.count("function mpFind(") == 1),
          ("retry listener kept", "MouseEvent.CLICK" in out),
          ("mpDiag once", out.count("function mpDiag") == 1)]
for label, ok in checks:
    print("   %-22s %s" % (label, ok))
if not all(ok for _, ok in checks):
    print("!! NOT shipping"); sys.exit(1)

for p in sorted(L.rglob("lib.swf")):
    shutil.copy2(p, HOME / "lpo_build/swf_backups" /
                 (p.parent.relative_to(L).as_posix().replace("/", "_") + ".bak"))
    shutil.copy2("/tmp/lib_one.swf", p)
print("deployed ->", md5(L / "lpo/patches/lib/lib.swf"))
subprocess.run(["python3", str(TOOLS / "build_local.py")], capture_output=True, text=True, cwd=TOOLS)
rr = subprocess.run(["python3", str(TOOLS / "ship_launcher_pack.py")],
                    capture_output=True, text=True, cwd=TOOLS)
for l in rr.stdout.splitlines():
    if "drive after" in l or "VERIFIED" in l:
        print(l)
