#!/usr/bin/env python3
"""Size the billboard card to the panel's real content area, client side.

The notice panel does `news.addChild(<the loaded card>)` with no sizing at all, so the
card appears at whatever pixel size the operator uploaded.  The panel's content viewport
(read out of notice.swf - see the geometry notes below) is 694 x 510, and the admin page
now draws the card at exactly that size - so for a fresh upload this helper does nothing
(s is 1.0 and the offsets are 0).  It is here for everything else:

  * a card uploaded BEFORE the admin page drew at 694x510 (520x360, the old size) is
    scaled UNIFORMLY (never one axis only - that is the stretching the user complained
    about) and centred, so it fills the board instead of sitting in a cream border
  * a card bigger than the viewport is scaled DOWN to fit rather than spilling out of
    the panel

Geometry it is built on (notice.swf, PrinceOnline.castle.Notice):
  sprite 54 = the `Notice` panel, 800 x 600 in its own coordinates
  sprite 41 = the detail overlay, placed at (35.2, 94.5) inside it, and inside the
              overlay the empty container `news` sits at (7.1, -14.4)
     -> the card is addChild'ed at panel coordinates (42.3, 80.1)
  the overlay's scrollbar rail starts at panel x 737, and the publisher's own scroll
  config says t_view = 510 -> the content viewport is 694.7 x 510.
  (twips/20 confirmed by the placement of `news`: 142,-288 -> 7.1,-14.4, which is exactly
  the t_start -14.4 the publisher passes to MCScrollBarManager.)
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()
JAR = HOME / "lpo_build/ffdec/ffdec-cli.jar"
L = HOME / "Downloads/littleprince-launcher"
DEP = L / "lpo/patches/lib/lib.swf"
md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

ANCHOR = "         this.notice.news.addChild(Bridge.res.getData(this.noticeURL));"
CALL = [
    '         try',
    '         {',
    '            this.afFitNoticeCard();',
    '         }',
    '         catch(fitErr:*)',
    '         {',
    '         }',
]
METHOD = [
    '      ',
    '      private function afFitNoticeCard() : void',
    '      {',
    '         var obj:* = Bridge.res.getData(this.noticeURL);',
    '         if(obj == null)',
    '         {',
    '            return;',
    '         }',
    '         var ow:Number = obj.width;',
    '         var oh:Number = obj.height;',
    '         if(!(ow > 0) || !(oh > 0))',
    '         {',
    '            return;',
    '         }',
    '         var viewW:Number = 694;',
    '         var viewH:Number = 510;',
    '         var s:Number = Math.min(viewW / ow,viewH / oh);',
    '         if(s > 4)',
    '         {',
    '            s = 4;',
    '         }',
    '         if(s < 0.995 || s > 1.005)',
    '         {',
    '            obj.scaleX = s;',
    '            obj.scaleY = s;',
    '         }',
    '         obj.x = (viewW - ow * s) / 2;',
    '         obj.y = (viewH - oh * s) / 2;',
    '      }',
]

print("deployed md5:", md5(DEP))
shutil.rmtree("/tmp/nfit_in", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/nfit_in", str(DEP)], capture_output=True, text=True)
SRC = pathlib.Path("/tmp/nfit_in/scripts/PrinceOnline/castle/Notice.as")
src = open(SRC, encoding="utf-8", newline="").read()

if src.count(ANCHOR) != 1:
    print("!! anchor count %d" % src.count(ANCHOR)); sys.exit(1)
if "afFitNoticeCard" in src:
    print("!! already patched?"); sys.exit(1)

src = src.replace(ANCHOR, ANCHOR + "\r\n" + "\r\n".join(CALL), 1)
# the method goes in right after showNoticeDetails() closes
tail = '            "t_view":510\r\n         });\r\n      }'
if src.count(tail) != 1:
    print("!! showNoticeDetails tail count %d" % src.count(tail)); sys.exit(1)
src = src.replace(tail, tail + "\r\n" + "\r\n".join(METHOD), 1)
SRC.write_text(src, newline="")
print("inserted the fit call + afFitNoticeCard()")

shutil.rmtree("/tmp/nfit_imp", ignore_errors=True)
dst = pathlib.Path("/tmp/nfit_imp/scripts/PrinceOnline/castle/Notice.as")
dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(SRC, dst)

r = subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-importScript",
                    str(DEP), "/tmp/nt_one.swf", "/tmp/nfit_imp"],
                   capture_output=True, text=True, cwd="/tmp")
out = r.stdout + r.stderr
print("import rc:", r.returncode)
if "SEVERE" in out or "xception" in out:
    print("!! importer complained"); print(out[-400:]); sys.exit(1)
print("new swf: %d bytes md5 %s" % (pathlib.Path("/tmp/nt_one.swf").stat().st_size,
                                    md5("/tmp/nt_one.swf")))

shutil.rmtree("/tmp/nfit_check", ignore_errors=True)
lg = subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                     "/tmp/nfit_check", "/tmp/nt_one.swf"], capture_output=True, text=True)
severe = [l for l in (lg.stdout + lg.stderr).splitlines()
          if "SEVERE" in l or "xception" in l]
print("re-export SEVERE/xception lines:", len(severe))
for l in severe[:5]:
    print("   ", l)
if severe:
    sys.exit(1)

nz = open("/tmp/nfit_check/scripts/PrinceOnline/castle/Notice.as", encoding="utf-8", newline="").read()
nb = pathlib.Path("/tmp/nfit_check/scripts/PrinceOnline/castle/Notice.as").read_bytes()
checks = [
    ("afFitNoticeCard defined", "private function afFitNoticeCard() : void" in nz),
    ("called from showNoticeDetails",
     "this.afFitNoticeCard();" in nz and nz.index("this.afFitNoticeCard();")
     > nz.index("addChild(Bridge.res.getData")),
    ("uniform scale only (one factor for both axes)",
     "obj.scaleX = s;" in nz and "obj.scaleY = s;" in nz),
    ("viewport 694 x 510", "viewW:Number = 694" in nz and "viewH:Number = 510" in nz),
    ("wrapped in try/catch", "fitErr:*" in nz),
    ("addChild kept", "news.addChild(Bridge.res.getData(this.noticeURL))" in nz),
    ("scrollbar config kept", '"t_view":510' in nz),
    ("showList kept", "private function showList() : void" in nz),
    ("CRLF only", nb.count(b"\n") == nb.count(b"\r\n")),
]
ok = True
for label, good in checks:
    print("   %-46s %s" % (label, good))
    ok = ok and good
if not ok:
    print("!! NOT deploying"); sys.exit(1)

for p in (L / "lpo/patches/lib/lib.swf", L / "lpo/patches/lpo/lib/lib.swf"):
    shutil.copy2(p, HOME / "lpo_build/swf_backups" /
                 (p.parent.relative_to(L).as_posix().replace("/", "_") + ".bak"))
    shutil.copy2("/tmp/nt_one.swf", p)
a, b = md5(L / "lpo/patches/lib/lib.swf"), md5(L / "lpo/patches/lpo/lib/lib.swf")
print("deployed both copies:", a, b, "identical:", a == b)
print("size:", (L / "lpo/patches/lib/lib.swf").stat().st_size)
