#!/usr/bin/env python3
"""Two fixes from the GIF, both grounded in the code.

1. The screen-edge left/right arrows are the search's page buttons (btnSFL/btnSFR).  The
   publisher hides them according to the page count, but that block is guarded by
   `if(this.fanset.btnSFL)` and runs before `fanset.play()` - so anything the entry animation
   re-shows stays shown, and with one result you get paging arrows you cannot use.  Re-assert
   their visibility in the same post-play pass that already fixed the empty tiles.

2. The card's 共同朋友 button (btnCF<lang>) sits in its hover state without being hovered.
   Its state comes from the publisher's own per-language visibility logic; handing the same
   clip to mcBtnManager as well pins it into the manager's frame.  Stop handing the manager
   the clips whose state the publisher already owns: btnCF<lang> and btnSFL/btnSFR.
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

shutil.rmtree("/tmp/lpo_re4", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_re4", str(DEP)], capture_output=True, text=True)
SRC = pathlib.Path("/tmp/lpo_re4/scripts/PrinceOnline/castle/AddFriend.as")
src = SRC.read_text()

# 1 - stop the manager owning clips the publisher's own logic drives
lines = src.split("\n")
kept, dropped = [], []
for ln in lines:
    if ("addMCButton(" in ln and "SFX_drag" in ln
            and re.search(r"btn(CF|SFL|SFR)", ln)):
        dropped.append(ln.strip()[:96])
        continue
    kept.append(ln)
src = "\n".join(kept)
print("manager registrations removed:", len(dropped))
for d in dropped:
    print("   " + d)

# 2 - re-assert the paging arrows in the post-play pass
OLD = '''            SOL.Debug.addLog("\\\\tmp_friends: slots synced to " + this.searchResult.length);'''
NEW = '''            var pages:int = int((this.searchResult.length + this.pageSize - 1) / this.pageSize);
            if(this.fanset["btnSFL"] != null)
            {
               this.fanset["btnSFL"].visible = this.page > 0;
            }
            if(this.fanset["btnSFR"] != null)
            {
               this.fanset["btnSFR"].visible = this.page + 1 < pages;
            }
            SOL.Debug.addLog("\\\\tmp_friends: slots synced to " + this.searchResult.length + " pages=" + pages);'''
if OLD not in src:
    # the escape rendering may differ; fall back to a positional anchor
    k = src.find("slots synced to")
    if k < 0:
        print("!! slot-sync anchor not found"); sys.exit(1)
    j = src.index("\n", k)
    src = src[:j] + "\n" + NEW.replace('\\\\tmp_friends', '\\tmp_friends') + src[j:]
    print("arrow sync added by positional anchor")
else:
    src = src.replace(OLD, NEW, 1)
    print("arrow sync added by anchor")
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

shutil.rmtree("/tmp/lpo_verify4", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_verify4", "/tmp/lib_one.swf"], capture_output=True, text=True)
af = pathlib.Path("/tmp/lpo_verify4/scripts/PrinceOnline/castle/AddFriend.as").read_text()
checks = [("no manager on btnCF/btnSFL/btnSFR",
           not any(("addMCButton(" in l and "SFX_drag" in l and re.search(r"btn(CF|SFL|SFR)", l))
                   for l in af.split("\n"))),
          ("arrows synced", "btnSFR" in af and "pages=" in af),
          ("slot sync kept", "slots synced to" in af),
          ("friend search still renders", "showSearchResult" in af),
          ("full args kept elsewhere", af.count('"SFX_drag",null,"SFX_drop"') >= 3)]
for label, ok in checks:
    print("   %-34s %s" % (label, ok))
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
