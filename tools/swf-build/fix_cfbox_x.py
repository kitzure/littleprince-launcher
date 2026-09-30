#!/usr/bin/env python3
"""Restore the click handling of the mutual-friends box (cfbox) in AddFriend.as.

Regression being fixed: an earlier pass removed the mcBtnManager.addMCButton calls for
`fanset.sr<i>.cfbox.btnCFL`, `btnCFR` and `btnCFClose` (fix_cf_buttons.py dropped every
line matching addMCButton(... "SFX_drag" ... btn(CF|SFL|SFR))).  Those clips are only
reachable through the manager, so the X (and the two arrows) stopped responding.

Restored with the FULL argument list - mcBtnManager.addMCButton(clip, hoverSfx, pressSfx,
releaseSfx) - and wrapped in try/catch, and each clip is pinned to its `_up` label after
registration.  Pinning is what keeps the clip from free-running its own timeline
(`_up` -> `_down` -> `_over` -> ... with no stop() on any frame) and sitting in a hover
pose, which is exactly how the 共同朋友 badge was fixed.

Clip frames read out of `-swf2xml addfriend.swf` first:
  sprite 179 = btnCFL / btnCFR   : labels _up(1) _down(5) _over(7)   - 8 frames
  sprite 166 = btnCFClose        : labels _up(1) _over(6) _down(13)  - 19 frames
  sprite 127/153 = btnCF badge   : labels _up(1) _over(5) _down(8)   - 10 frames
All three carry `_up` on frame 1, so gotoAndStop("_up") is valid for all of them.
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()
JAR = HOME / "lpo_build/ffdec/ffdec-cli.jar"
L = HOME / "Downloads/littleprince-launcher"
TOOLS = HOME / "Downloads/littleprince-patcher-handoff/tools"
DEP = L / "lpo/patches/lib/lib.swf"
md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

ANCHOR = ('         Bridge.utils.setEmbedFont(_loc1_.total,"Arial Rounded MT Bold",16,'
          'this.sameFriends.length.toString());')

BLOCK = [
    '         try',
    '         {',
    '            this.mcBtnManager.addMCButton(_loc1_.btnCFL,"SFX_drag",null,"SFX_drop");',
    '            _loc1_.btnCFL.gotoAndStop("_up");',
    '            this.mcBtnManager.addMCButton(_loc1_.btnCFR,"SFX_drag",null,"SFX_drop");',
    '            _loc1_.btnCFR.gotoAndStop("_up");',
    '            this.mcBtnManager.addMCButton(_loc1_.btnCFClose,"SFX_drag",null,"SFX_drop");',
    '            _loc1_.btnCFClose.gotoAndStop("_up");',
    '         }',
    '         catch(cfBoxErr:*)',
    '         {',
    '         }',
]

print("deployed md5:", md5(DEP))

shutil.rmtree("/tmp/xcf_in", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/xcf_in", str(DEP)], capture_output=True, text=True)
SRC = pathlib.Path("/tmp/xcf_in/scripts/PrinceOnline/castle/AddFriend.as")
src = SRC.read_text()

if ANCHOR not in src:
    print("!! anchor not found in showCF"); sys.exit(1)
if src.count(ANCHOR) != 1:
    print("!! anchor is not unique (%d)" % src.count(ANCHOR)); sys.exit(1)
if 'addMCButton(_loc1_.btnCFClose' in src:
    print("!! already patched?"); sys.exit(1)

insert = "\r\n".join(BLOCK)
src = src.replace(ANCHOR, ANCHOR + "\r\n" + insert, 1)
SRC.write_text(src)
print("inserted %d lines after the showCF anchor" % len(BLOCK))

# only THIS class goes back in
shutil.rmtree("/tmp/xcf_imp", ignore_errors=True)
dst = pathlib.Path("/tmp/xcf_imp/scripts/PrinceOnline/castle/AddFriend.as")
dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(SRC, dst)

r = subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-importScript",
                    str(DEP), "/tmp/af_one.swf", "/tmp/xcf_imp"],
                   capture_output=True, text=True, cwd="/tmp")
out = r.stdout + r.stderr
print("import rc:", r.returncode)
if "SEVERE" in out or "xception" in out:
    print("!! importer complained"); print(out[-400:]); sys.exit(1)
print("new swf: %d bytes md5 %s" % (pathlib.Path("/tmp/af_one.swf").stat().st_size,
                                    md5("/tmp/af_one.swf")))

# validate: re-export and diff -rq against the source-of-truth export
shutil.rmtree("/tmp/xcf_check", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/xcf_check", "/tmp/af_one.swf"], capture_output=True, text=True)
log = subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                      "/tmp/xcf_check", "/tmp/af_one.swf"], capture_output=True, text=True)
severe = [l for l in (log.stdout + log.stderr).splitlines()
          if "SEVERE" in l or "xception" in l]
print("re-export SEVERE/xception lines:", len(severe))
for l in severe[:5]:
    print("   ", l)
if severe:
    sys.exit(1)

af = pathlib.Path("/tmp/xcf_check/scripts/PrinceOnline/castle/AddFriend.as").read_text()
af_b = pathlib.Path("/tmp/xcf_check/scripts/PrinceOnline/castle/AddFriend.as").read_bytes()
before = len(pathlib.Path("/tmp/xcf_in/scripts/PrinceOnline/castle/AddFriend.as")
             .read_text().split("\n"))
after = len(af.split("\n"))
checks = [
    ("btnCFClose registered with full args",
     'addMCButton(_loc1_.btnCFClose,"SFX_drag",null,"SFX_drop")' in af),
    ("btnCFL registered with full args",
     'addMCButton(_loc1_.btnCFL,"SFX_drag",null,"SFX_drop")' in af),
    ("btnCFR registered with full args",
     'addMCButton(_loc1_.btnCFR,"SFX_drag",null,"SFX_drop")' in af),
    ("all three pinned to _up",
     af.count('gotoAndStop("_up")') >= 3),
    ("the registration is inside try/catch",
     "cfBoxErr:*" in af),
    ("badge registration from the last pass kept",
     'addMCButton(_loc6_,"SFX_drag",null,"SFX_drop")' in af),
    ("btnCFL/btnCFR/btnCFClose release handlers kept",
     af.count('param1.name == "btnCFL"') == 1 and af.count('param1.name == "btnCFR"') == 1
     and af.count('param1.name == "btnCFClose"') == 1),
    ("CRLF only", af_b.count(b"\n") == af_b.count(b"\r\n")),
]
ok = True
for label, good in checks:
    print("   %-46s %s" % (label, good))
    ok = ok and good
before = len(pathlib.Path("/tmp/xcf_in/scripts/PrinceOnline/castle/AddFriend.as")
             .read_text().split("\n"))
after = len(af.split("\n"))
print("   lines before/after: %d -> %d" % (before, after))
if not ok:
    print("!! NOT deploying"); sys.exit(1)

for p in (L / "lpo/patches/lib/lib.swf", L / "lpo/patches/lpo/lib/lib.swf"):
    shutil.copy2(p, HOME / "lpo_build/swf_backups" /
                 (p.parent.relative_to(L).as_posix().replace("/", "_") + ".bak"))
    shutil.copy2("/tmp/af_one.swf", p)
a, b = md5(L / "lpo/patches/lib/lib.swf"), md5(L / "lpo/patches/lpo/lib/lib.swf")
print("deployed both copies:", a, b, "identical:", a == b)
print("size:", (L / "lpo/patches/lib/lib.swf").stat().st_size)
