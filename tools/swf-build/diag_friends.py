#!/usr/bin/env python3
"""Diagnostic build for the AddFriend result list.

The reply arrives (server log: 1 match, 425 bytes) and getFindFriendResult is reached, so the
failure is inside the render: either pageSize/page are 0 when it runs, or the first row throws
part way.  Put the client's own on-screen log back (it worked on the retry button) and mark
the exact values, so one screenshot names the cause instead of another guess.

Uses SOL.Debug fully qualified - no imports needed in this class.
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
DEP = L / "lpo/patches/lib/lib.swf"
md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

shutil.rmtree("/tmp/lpo_re2", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_re2", str(DEP)], capture_output=True, text=True)
SRC = pathlib.Path("/tmp/lpo_re2/scripts/PrinceOnline/castle/AddFriend.as")
src = SRC.read_text()
print("AddFriend.as: %d chars" % len(src))


def replace_method(text, name, new_body):
    m = re.search(r"( *)public function %s\(" % name, text)
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


DIAG_FN = '''public function afDiag() : void
      {
         try
         {
            if(SOL.Debug.tf_debug == null)
            {
               var holder:flash.display.Sprite = new flash.display.Sprite();
               holder.mouseEnabled = false;
               holder.mouseChildren = false;
               this.addChild(holder);
               SOL.Debug.init(holder,520,230);
               SOL.Debug.tf_debug.mouseEnabled = false;
            }
            SOL.Debug.enable();
         }
         catch(afdErr:*)
         {
         }
      }
      
      public function getFindFriendResult(param1:Array) : void
      {
         this.afDiag();
         this.searchResult = param1;
         SOL.Debug.addLog("\\\\tmp_friends: reply len=" + (param1 == null ? -1 : param1.length) + " page=" + this.page + " pageSize=" + this.pageSize);
         if(this.searchResult.length > 0)
         {
            this.sysMesg.txtMesg.text = "";
         }
         else if(Bridge.user.TextLanguage == 0)
         {
            Bridge.utils.setEmbedFont(this.sysMesg.txtMesg,"Arial Rounded MT Bold",22,"No record found. Please search again.");
         }
         else
         {
            Bridge.utils.setEmbedFont(this.sysMesg.txtMesg,"\\u83ef\\u5eb7\\u5137\\u7279\\u5713(P)",22,"\\u6c92\\u6709\\u7b26\\u5408\\u7684\\u7d00\\u9304\\uff0c\\u8acb\\u91cd\\u65b0\\u641c\\u5c0b\\u3002");
         }
         SOL.Debug.addLog("\\\\tmp_friends: calling showSearchResult");
         try
         {
            this.showSearchResult();
         }
         catch(srErr:*)
         {
            SOL.Debug.addLog("\\\\tmp_friends: showSearchResult FAILED " + srErr);
         }
         this.fanset.play();
      }'''
src = replace_method(src, "getFindFriendResult", DIAG_FN)

# mark the render loop
n1 = src.count("         _loc3_.visible = true;")
if n1 != 1:
    n1 = src.count("_loc3_.visible = true;")
src = src.replace("_loc3_.visible = true;",
                  'SOL.Debug.addLog("\\\\tmp_friends: row " + _loc2_ + " slot=" + _loc3_.name);\n            _loc3_.visible = true;\n            SOL.Debug.addLog("\\\\tmp_friends: rendering row " + _loc2_);', 1)
src = src.replace("            _loc5_ = new Character(_loc4_,\"right\",false);",
                  '            try\n            {\n               _loc5_ = new Character(_loc4_,"right",false);', 1)
src = src.replace("            _loc3_.photo.char.addChild(_loc5_);",
                  '               _loc3_.photo.char.addChild(_loc5_);\n            }\n            catch(rowErr:*)\n            {\n               SOL.Debug.addLog("\\\\tmp_friends: row " + _loc2_ + " FAILED " + rowErr);\n            }', 1)
print("row markers inserted:", 'tmp_friends: rendering row' in src, '| anchor hits:', n1)
SRC.write_text(src)

shutil.rmtree("/tmp/lpo_one", ignore_errors=True)
dst = pathlib.Path("/tmp/lpo_one/scripts/PrinceOnline/castle/AddFriend.as")
dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(SRC, dst)

r = subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-importScript",
                    str(DEP), "/tmp/lib_one.swf", "/tmp/lpo_one"],
                   capture_output=True, text=True, cwd="/tmp")
print("import rc:", r.returncode)
if "SEVERE" in r.stdout + r.stderr or "expected but" in r.stdout + r.stderr:
    print("!! importer complained"); print((r.stdout + r.stderr)[-400:]); sys.exit(1)
print("new SWF:", pathlib.Path("/tmp/lib_one.swf").stat().st_size, md5("/tmp/lib_one.swf"))

shutil.rmtree("/tmp/lpo_verify2", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_verify2", "/tmp/lib_one.swf"], capture_output=True, text=True)
af = pathlib.Path("/tmp/lpo_verify2/scripts/PrinceOnline/castle/AddFriend.as").read_text()
checks = [("diag initialiser", "afDiag" in af),
          ("reply marker", "tmp_friends: reply len=" in af),
          ("rows hopefully rendered", "tmp_friends: rendering row" in af or "rendering row" in af),
          ("render guarded", "showSearchResult FAILED" in af)]
for label, ok in checks:
    print("   %-24s %s" % (label, ok))
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
