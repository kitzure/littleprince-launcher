#!/usr/bin/env python3
"""Add the missing helper definitions, then verify and ship in one pass."""
import hashlib
import pathlib
import re
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()
L = HOME / "Downloads/littleprince-launcher"
KEEP = HOME / "lpo_build/swf_backups"
TOOLS = HOME / "Downloads/littleprince-patcher-handoff/tools"
SRC = pathlib.Path("/tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as")
md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

src = SRC.read_text()
if "function mpFind(" not in src:
    FIND = '''public function mpFind(name:String) : *
      {
         var direct:* = null;
         try
         {
            direct = this.getChildByName(name);
         }
         catch(e0:*)
         {
         }
         if(direct != null)
         {
            return direct;
         }
         return this.mpFindDeep(this,name);
      }
      
      public function mpFindDeep(node:*, name:String) : *
      {
         var i:int = 0;
         while(i < node.numChildren)
         {
            var ch:* = node.getChildAt(i);
            var nm:String = null;
            try
            {
               nm = ch.name;
            }
            catch(e1:*)
            {
            }
            if(nm == name)
            {
               return ch;
            }
            if(ch is flash.display.DisplayObjectContainer)
            {
               var found:* = this.mpFindDeep(ch,name);
               if(found != null)
               {
                  return found;
               }
            }
            i++;
         }
         return null;
      }
      
      '''
    m = re.search(r"public function mpPlayAgain\(", src)
    anchor = src.rindex("\n", 0, m.start()) + 1
    src = src[:anchor] + "      " + FIND + src[anchor:]
    SRC.write_text(src)
    print("inserted mpFind + mpFindDeep")

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print("\n".join(l for l in r.stdout.splitlines() if l.startswith(("new ", "base "))))
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer complained"); print(r.stdout[-400:]); sys.exit(1)

out = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as").read_text()
checks = [("mpFind defined", out.count("function mpFind(") == 1),
          ("mpFindDeep defined", out.count("function mpFindDeep") == 1),
          ("mpDiag once", out.count("function mpDiag") == 1),
          ("mpWireRetry once", out.count("function mpWireRetry") == 1),
          ("no bracket lookup", not re.search(r'this\["btnRetry', out)),
          ("wiring logs the class", "wiring " in out),
          ("getChildByName used", "getChildByName" in out)]
for label, ok in checks:
    print("   %-24s %s" % (label, ok))
if not all(ok for _, ok in checks):
    print("!! a check failed - NOT shipping"); sys.exit(1)

for p in sorted(L.rglob("lib.swf")):
    shutil.copy2(p, KEEP / (p.parent.relative_to(L).as_posix().replace("/", "_") + ".bak"))
    shutil.copy2("/tmp/lib_one.swf", p)
print("deployed ->", md5(L / "lpo/patches/lib/lib.swf"), md5(L / "lpo/patches/lpo/lib/lib.swf"))
r = subprocess.run(["python3", str(TOOLS / "build_local.py")], capture_output=True, text=True, cwd=TOOLS)
print([l for l in r.stdout.splitlines() if "PASSED" in l])
r = subprocess.run(["python3", str(TOOLS / "ship_launcher_pack.py")], capture_output=True, text=True, cwd=TOOLS)
for l in r.stdout.splitlines():
    if "drive after" in l or "VERIFIED" in l:
        print(l)
print("pack md5:", md5(TOOLS / "littleprince-patcher.zip"))
