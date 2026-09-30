#!/usr/bin/env python3
"""Hide the arrows the player actually sees (fanset.btnL / fanset.btnR).

The last round synced fanset.btnSFL/btnSFR - the publisher's search paging clips - but the
overlay showed `pages=1` with the arrows still on screen, and fanset.btnSFL/btnSFR are not on
this panel at all (that is why the publisher guards that block).  The visible edge arrows are
fanset.btnL / fanset.btnR, which the class uses for its own paging.  During a search result
they are the result paging, so hide them when there is no second page.
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

shutil.rmtree("/tmp/lpo_re5", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_re5", str(DEP)], capture_output=True, text=True)
SRC = pathlib.Path("/tmp/lpo_re5/scripts/PrinceOnline/castle/AddFriend.as")
src = SRC.read_text()

OLD = 'this.fanset["btnSFR"].visible = this.page + 1 < pages;'
if OLD not in src:
    print("!! anchor not found"); sys.exit(1)
NEW = OLD + '''
            if(this.fanset["btnL"] != null)
            {
               this.fanset["btnL"].visible = this.page > 0;
            }
            if(this.fanset["btnR"] != null)
            {
               this.fanset["btnR"].visible = this.page + 1 < pages;
            }'''
src = src.replace(OLD, NEW, 1)
print("btnL/btnR sync added")

shutil.rmtree("/tmp/lpo_one", ignore_errors=True)
dst = pathlib.Path("/tmp/lpo_one/scripts/PrinceOnline/castle/AddFriend.as")
dst.parent.mkdir(parents=True, exist_ok=True)
SRC.write_text(src)
shutil.copy2(SRC, dst)

r = subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-importScript",
                    str(DEP), "/tmp/lib_one.swf", "/tmp/lpo_one"],
                   capture_output=True, text=True, cwd="/tmp")
print("import rc:", r.returncode)
if "SEVERE" in r.stdout + r.stderr or "expected but" in r.stdout + r.stderr:
    print("!! importer complained"); print((r.stdout + r.stderr)[-300:]); sys.exit(1)
print("new SWF:", pathlib.Path("/tmp/lib_one.swf").stat().st_size, md5("/tmp/lib_one.swf"))

shutil.rmtree("/tmp/lpo_verify5", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_verify5", "/tmp/lib_one.swf"], capture_output=True, text=True)
af = pathlib.Path("/tmp/lpo_verify5/scripts/PrinceOnline/castle/AddFriend.as").read_text()
checks = [("btnL hidden with 1 page", 'this.fanset["btnL"].visible = this.page > 0' in af),
          ("btnR hidden with 1 page", 'this.fanset["btnR"].visible' in af),
          ("slot sync kept", "slots synced to" in af),
          ("no manager on btnCF/btnSFL/btnSFR",
           not any(("addMCButton(" in l and "SFX_drag" in l and re.search(r"btn(CF|SFL|SFR)", l))
                   for l in af.split("\n")))]
for label, ok in checks:
    print("   %-30s %s" % (label, ok))
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
