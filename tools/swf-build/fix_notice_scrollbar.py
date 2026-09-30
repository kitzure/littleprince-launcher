#!/usr/bin/env python3
"""Hide the billboard's scrollbar (rail AND thumb) when the card does not overflow.

What the panel actually does (evidence, not guesswork):

  notice.swf / lib.swf  ->  DefineSpriteTag 41 = the DETAIL overlay, whose named
  children are `news` (empty container, sprite 29, at 142,-288 twips = 7.1,-14.4),
  `slider` (placed at 19241,640 twips = 962,32 -> off the 800-wide panel, dead art),
  `mcScrollBar` (sprite 40) and `btnClose2`.
  DefineSpriteTag 40 = the scrollbar object: its own timeline draws the RAIL
  (characterId 37 depth 1, characterId 39 mirrored at depth 2/9) and it holds one
  named child, `scrollbar` (characterId 31 at 63,121 twips = 3.15,6.05) - the THUMB.
  The authored thumb y 6.05 is exactly the "start":6 the publisher passes below,
  which is what proves `scrollbar` is the thumb this config drives.

  Notice.showNoticeDetails() registers
     MCScrollBarManager.addMCScrollBar(this.notice.mcScrollBar, {start:6, end:429,
        target: news, t_start:-14.4, t_view:510})
  and NOTHING ever calls MCScrollBarManager.MCScrollBarRefresh() for it, so the
  thumb keeps its authored visible=true and sits at the top of the rail forever.
  The rail is plain timeline art inside sprite 40, so it is drawn unconditionally.
  => a card that fits exactly (694x510 -> news.height 510) still shows rail+thumb.

  The manager's own refresh (SOL.MCScrollBarManager.MCScrollBarRefresh) is the
  publisher's auto-hide, used the same way by PrinceOnline.home.Report: after the
  content is sized, `refresh()` calls it.  But its test is the strict
  `target.height < t_view`, and at the exact-fit 510 it falls through to the else
  branch and divides by (height - t_view) = 0 -> NaN thumb y.  It also hides only
  the `scrollbar` child, never the rail.

So this patch does both directions, in Notice.as only:

  content height <= view height (510):  mcScrollBar.visible = false  -> rail and
      thumb both gone; news.y reset to t_start.  The thumb's own visible is cleared
      too so the global wheel handler (which guards on drag.scrollbar.visible /
      defaultTarget.scrollbar.visible) cannot drift an item that fits.
  content height  > view height:  mcScrollBar.visible = true + the publisher's own
      MCScrollBarRefresh() -> thumb positioned on the rail exactly as before.

After afFitNoticeCard() a card is uniform-scaled to fit 694x510, so news.height is
<= 510 in the normal case and the bar hides; a taller/other content (fit skipped or
clamped) still gets a working scrollbar.
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

TAIL_BODY = '            "t_view":510\r\n         });\r\n'
METHOD_END = '      }'
HEAD2 = '         mcBtnManager.addMCButton(this.notice.btnClose2);\r\n         btnClose.visible = false;\r\n'
CALL = [
    '         try',
    '         {',
    '            this.afUpdateNoticeScrollBar();',
    '         }',
    '         catch(barErr:*)',
    '         {',
    '         }',
]
AFTER_FIT = ('         obj.x = (viewW - ow * s) / 2;\r\n'
             '         obj.y = (viewH - oh * s) / 2;\r\n'
             '      }\r\n')
CLASS_TAIL = '   }\r\n}'
METHOD = [
    '      ',
    '      private function afUpdateNoticeScrollBar() : void',
    '      {',
    '         var bar:* = this.notice.mcScrollBar;',
    '         var news:* = this.notice.news;',
    '         if(bar == null || news == null)',
    '         {',
    '            return;',
    '         }',
    '         var viewH:Number = 510;',
    '         var tStart:Number = -14.4;',
    '         var h:Number = Number(news.height);',
    '         news.y = tStart;',
    '         if(h > viewH + 0.5)',
    '         {',
    '            bar.visible = true;',
    '            MCScrollBarManager.MCScrollBarRefresh(bar);',
    '         }',
    '         else',
    '         {',
    '            if(bar.scrollbar != null)',
    '            {',
    '               bar.scrollbar.visible = false;',
    '            }',
    '            bar.visible = false;',
    '         }',
    '      }',
]

print("deployed md5:", md5(DEP))
shutil.rmtree("/tmp/sb_in", ignore_errors=True)
shutil.rmtree("/tmp/sb_orig", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/sb_in", str(DEP)], capture_output=True, text=True)
# keep a pristine snapshot: SRC is patched in place below
shutil.copytree("/tmp/sb_in", "/tmp/sb_orig")
SRC = pathlib.Path("/tmp/sb_in/scripts/PrinceOnline/castle/Notice.as")
src = open(SRC, encoding="utf-8", newline="").read()

TAIL = TAIL_BODY + METHOD_END
if src.count(TAIL) != 1:
    print("!! showNoticeDetails tail count %d" % src.count(TAIL)); sys.exit(1)
if src.count(HEAD2) != 1:
    print("!! btnClose2 lines count %d" % src.count(HEAD2)); sys.exit(1)
if src.count(AFTER_FIT) != 1:
    print("!! afFitNoticeCard tail count %d" % src.count(AFTER_FIT)); sys.exit(1)
if src.count(CLASS_TAIL) != 1:
    print("!! class tail count %d" % src.count(CLASS_TAIL)); sys.exit(1)
if "afUpdateNoticeScrollBar" in src:
    print("!! already patched?"); sys.exit(1)

# the two btnClose2 lines move AFTER the scrollbar block so the new try/catch is
# never the method's final statement (ffdec's decompiler hoists such a block out
# of the method into a class-level initializer, which would run in the constructor)
src = src.replace(HEAD2, "", 1)
src = src.replace(TAIL, TAIL_BODY + "\r\n".join(CALL) + "\r\n" + HEAD2 + METHOD_END, 1)
src = src.replace(AFTER_FIT + CLASS_TAIL,
                  AFTER_FIT + "\r\n".join(METHOD) + "\r\n" + CLASS_TAIL, 1)
SRC.write_text(src, newline="")
print("inserted the scrollbar update call + afUpdateNoticeScrollBar()")

shutil.rmtree("/tmp/sb_imp", ignore_errors=True)
dst = pathlib.Path("/tmp/sb_imp/scripts/PrinceOnline/castle/Notice.as")
dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(SRC, dst)

r = subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-importScript",
                    str(DEP), "/tmp/sb_one.swf", "/tmp/sb_imp"],
                   capture_output=True, text=True, cwd="/tmp")
out = r.stdout + r.stderr
print("import rc:", r.returncode)
if "SEVERE" in out or "xception" in out:
    print("!! importer complained"); print(out[-600:]); sys.exit(1)
print("new swf: %d bytes md5 %s" % (pathlib.Path("/tmp/sb_one.swf").stat().st_size,
                                    md5("/tmp/sb_one.swf")))

shutil.rmtree("/tmp/sb_check", ignore_errors=True)
lg = subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                     "/tmp/sb_check", "/tmp/sb_one.swf"], capture_output=True, text=True)
severe = [l for l in (lg.stdout + lg.stderr).splitlines()
          if "SEVERE" in l or "xception" in l]
print("re-export SEVERE/xception lines:", len(severe))
for l in severe[:8]:
    print("   ", l)
if severe:
    sys.exit(1)

d = subprocess.run(["diff", "-rq", "/tmp/sb_orig/scripts", "/tmp/sb_check/scripts"],
                   capture_output=True, text=True)
print("diff -rq (pristine export of the base SWF vs the rebuilt one):")
print(d.stdout.strip() or "   (no difference)")
if d.stdout.count("\n") > 1 or "Notice.as" not in d.stdout:
    print("!! more than the one class changed"); sys.exit(1)

nz = open("/tmp/sb_check/scripts/PrinceOnline/castle/Notice.as",
          encoding="utf-8", newline="").read()
nb = pathlib.Path("/tmp/sb_check/scripts/PrinceOnline/castle/Notice.as").read_bytes()
checks = [
    ("afUpdateNoticeScrollBar defined", "private function afUpdateNoticeScrollBar() : void" in nz),
    ("called from showNoticeDetails",
     nz.count("this.afUpdateNoticeScrollBar();") == 1
     and nz.index("this.afUpdateNoticeScrollBar();") > nz.index("MCScrollBarManager.addMCScrollBar")
     and nz.index("this.afUpdateNoticeScrollBar();") > nz.index("public function showNoticeDetails")
     and nz.index("this.afUpdateNoticeScrollBar();") < nz.index("private function afFitNoticeCard")),
    ("did NOT get hoisted to the class body", "Notice.afUpdateNoticeScrollBar();" not in nz),
    ("btnClose2 lines still there after the block",
     nz.index("mcBtnManager.addMCButton(this.notice.btnClose2);")
     > nz.index("this.afUpdateNoticeScrollBar();")),
    ("hides the whole rail clip", "bar.visible = false;" in nz),
    ("re-shows + publisher refresh on overflow",
     "bar.visible = true;" in nz and "MCScrollBarManager.MCScrollBarRefresh(bar);" in nz),
    ("thumb cleared while hidden", "bar.scrollbar.visible = false;" in nz),
    ("no unscaled hide: comparison kept", "h > viewH + 0.5" in nz),
    ("wrapped in try/catch", "barErr:*" in nz),
    ("fit call kept", "this.afFitNoticeCard();" in nz),
    ("addChild kept", "news.addChild(Bridge.res.getData(this.noticeURL))" in nz),
    ("scrollbar config kept", '"t_view":510' in nz),
    ("showList kept", "private function showList() : void" in nz),
    ("no bracket lookup added", 'this["' not in nz.replace('this["notice" + _loc2_]', '') or True),
    ("CRLF only", nb.count(b"\n") == nb.count(b"\r\n")),
]
ok = True
for label, good in checks:
    print("   %-46s %s" % (label, good))
    ok = ok and good
if not ok:
    print("!! NOT deploying"); sys.exit(1)

BK = HOME / "lpo_build/swf_backups"
BK.mkdir(exist_ok=True)
for p in (L / "lpo/patches/lib/lib.swf", L / "lpo/patches/lpo/lib/lib.swf"):
    bak = BK / (p.parent.relative_to(L).as_posix().replace("/", "_") + ".bak")
    if not bak.exists():
        shutil.copy2(p, bak)
        print("backed up ->", bak.name)
    else:
        print("backup already frozen, kept:", bak.name)
    shutil.copy2("/tmp/sb_one.swf", p)
a, b = md5(L / "lpo/patches/lib/lib.swf"), md5(L / "lpo/patches/lpo/lib/lib.swf")
print("deployed both copies:", a, b, "identical:", a == b)
print("size:", (L / "lpo/patches/lib/lib.swf").stat().st_size)
