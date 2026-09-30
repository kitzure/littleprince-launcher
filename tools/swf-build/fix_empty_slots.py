#!/usr/bin/env python3
"""Hide the empty result slots, after the panel's entry animation.

showSearchResult() does hide unused slots (the else branch sets visible=false), but
getFindFriendResult() calls fanset.play() AFTER it, and that replays the panel's entry
animation, which brings the placeholder tiles back - the publisher's own test text ("friend",
A0X061101, 共 8888 位).  With a full page of results from the official server, every slot was
populated, so this never showed.

Re-assert the visibility once the animation has been kicked off, and keep the on-screen log
for this round so the result is visible rather than inferred.
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

shutil.rmtree("/tmp/lpo_re3", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_re3", str(DEP)], capture_output=True, text=True)
SRC = pathlib.Path("/tmp/lpo_re3/scripts/PrinceOnline/castle/AddFriend.as")
src = SRC.read_text()

HELPER = '''public function afHideEmptySlots() : void
      {
         try
         {
            var i:int = 0;
            while(i < 8)
            {
               var slot:* = this.fanset["sr" + i];
               if(slot != null)
               {
                  slot.visible = i < this.searchResult.length;
               }
               i++;
            }
            SOL.Debug.addLog("\\\\tmp_friends: slots synced to " + this.searchResult.length);
         }
         catch(hsErr:*)
         {
            SOL.Debug.addLog("\\\\tmp_friends: slot sync FAILED " + hsErr);
         }
      }
      
      '''
m = re.search(r"public function getFindFriendResult\(", src)
anchor = src.rindex("\n", 0, m.start()) + 1
src = src[:anchor] + "      " + HELPER + src[anchor:]

n = src.count("this.fanset.play();")
print("fanset.play() calls:", n)
k = src.find("srErr")
j = src.find("this.fanset.play();", k) if k > 0 else -1
if j < 0:
    print("!! could not locate the play() that follows the render call"); sys.exit(1)
print("patching the play() at offset", j, "which follows the render call")
src = (src[:j] + "this.fanset.play();\n         this.afHideEmptySlots();"
       + src[j + len("this.fanset.play();"):])
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
    print("!! importer complained"); print((r.stdout + r.stderr)[-350:]); sys.exit(1)
print("new SWF:", pathlib.Path("/tmp/lib_one.swf").stat().st_size, md5("/tmp/lib_one.swf"))

shutil.rmtree("/tmp/lpo_verify3", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_verify3", "/tmp/lib_one.swf"], capture_output=True, text=True)
af = pathlib.Path("/tmp/lpo_verify3/scripts/PrinceOnline/castle/AddFriend.as").read_text()
checks = [("hide helper present", "afHideEmptySlots" in af),
          ("called after play()", "afHideEmptySlots();" in af),
          ("diag still on", "tmp_friends: reply len=" in af),
          ("full args kept", af.count('"SFX_drag",null,"SFX_drop"') >= 5)]
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
