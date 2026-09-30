#!/usr/bin/env python3
"""Let the billboard's detail card ANIMATE, by playing a PNG sprite sheet.

Why this and not an animated SWF (route a): the loader accepts swf, but nothing on
this machine can AUTHOR a timeline SWF - ffdec edits and re-imports assets, it is
not a Flash authoring compiler - and there is no Flash runtime here to prove a
generated SWF plays.  Route (b) is verifiable from the bytecode and adds no new
dependency, so the sheet lives inside the resource the panel already fetches.

The trick is that the animation needs NO protocol change and NO new metadata:

  * the editor publishes a sheet that is exactly N frames of 694x510 side by side,
    i.e. (694*N) x 510 - the very same /notice/content/<id>.png URL the panel
    already loads;
  * Notice/afAnimateNoticeCard() reads the loaded object's size, and if it is
    height 510 and a whole number N>=2 of 694-wide tiles, shows ONLY the first tile
    via `scrollRect` and advances the window on Event.ENTER_FRAME;
  * anything else - a plain 694x510 card - falls straight through to the existing
    afFitNoticeCard() path, so a static card and a notice with no card at all render
    exactly as before.

Pacing is fixed client-side (about 1.5 s per cycle, clamped 70..400 ms/frame), which
is why the editor's own statement of what the board will do is a statement about the
strip, not about an fps box the client would ignore.

Same house rules as the scrollbar patch: ONE class imported, the new try/catch blocks
are never a method's last statement (ffdec hoists those into a class-body initializer,
which would run them in the constructor), the existing addMCButton registration is
kept, and every new call site is wrapped so a failure cannot abort the handler.
"""
import os
import hashlib
import pathlib
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()
JAR = HOME / "lpo_build/ffdec/ffdec-cli.jar"
L = HOME / "Downloads/littleprince-launcher"
DEP = pathlib.Path(os.environ.get("LPO_MOTION_DEP",
                                  str(L / "lpo/patches/lib/lib.swf")))
DRY = os.environ.get("LPO_MOTION_DRY") == "1"
md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

CRLF = "\r\n"


def join(lines):
    return CRLF.join(lines) + CRLF


# ── anchors in the CURRENT (already scrollbar-patched) Notice.as ─────────────
FIELD_ANCHOR = "   public var yoffset:Number;" + CRLF
FIELDS = join([
    "      ",
    "      public var afMotionObj:*;",
    "      ",
    "      public var afMotionFrames:int;",
    "      ",
    "      public var afMotionFrameW:Number;",
    "      ",
    "      public var afMotionFrameH:Number;",
    "      ",
    "      public var afMotionIndex:int;",
    "      ",
    "      public var afMotionLast:Number;",
])

ADDCHILD_FIT = join([
    '         this.notice.news.addChild(Bridge.res.getData(this.noticeURL));',
    "         try",
    "         {",
    "            this.afFitNoticeCard();",
    "         }",
])
ADDCHILD_FIT_NEW = join([
    '         this.notice.news.addChild(Bridge.res.getData(this.noticeURL));',
    "         try",
    "         {",
    "            this.afAnimateNoticeCard(Bridge.res.getData(this.noticeURL));",
    "         }",
    "         catch(animErr:*)",
    "         {",
    "         }",
    "         try",
    "         {",
    "            this.afFitNoticeCard();",
    "         }",
])

FIT_HEAD = join([
    "         var obj:* = Bridge.res.getData(this.noticeURL);",
    "         if(obj == null)",
    "         {",
    "            return;",
    "         }",
])
FIT_HEAD_NEW = FIT_HEAD + join([
    "         if(this.afMotionObj != null)",
    "         {",
    "            obj.x = 0;",
    "            obj.y = 0;",
    "            return;",
    "         }",
])

LOAD_HEAD = join([
    "      public function loadNoticeContent(param1:String) : void",
    "      {",
])
LOAD_HEAD_NEW = LOAD_HEAD + join([
    "         this.afStopNoticeMotion();",
])

EDIT_STOP = join([
    "         this.notice.visible = false;",
    "         this.notice.stop();",
])
EDIT_STOP_NEW = EDIT_STOP + CRLF + join(["         this.afStopNoticeMotion();"])

CLOSE_HEAD = join([
    '         else if(param1.name == "btnClose2")',
    "         {",
    "            btnClose.visible = true;",
])
CLOSE_HEAD_NEW = CLOSE_HEAD + join([
    "            this.afStopNoticeMotion();",
])

CLASS_TAIL = "   }" + CRLF + "}"

METHODS = join([
    "      ",
    "      private function afAnimateNoticeCard(param1:*) : void",
    "      {",
    "         this.afStopNoticeMotion();",
    "         if(param1 == null)",
    "         {",
    "            return;",
    "         }",
    "         var ow:Number = Number(param1.width);",
    "         var oh:Number = Number(param1.height);",
    "         var fw:Number = 694;",
    "         var fh:Number = 510;",
    "         if(!(oh > fh - 2 && oh < fh + 2))",
    "         {",
    "            return;",
    "         }",
    "         var n:int = Math.round(ow / fw);",
    "         if(n < 2 || n > 24)",
    "         {",
    "            return;",
    "         }",
    "         if(Math.abs(ow - n * fw) > 2)",
    "         {",
    "            return;",
    "         }",
    "         param1.scrollRect = new flash.geom.Rectangle(0,0,fw,fh);",
    "         param1.x = 0;",
    "         param1.y = 0;",
    "         param1.scaleX = 1;",
    "         param1.scaleY = 1;",
    "         this.afMotionObj = param1;",
    "         this.afMotionFrames = n;",
    "         this.afMotionFrameW = fw;",
    "         this.afMotionFrameH = fh;",
    "         this.afMotionIndex = 0;",
    "         this.afMotionLast = Number(getTimer());",
    "         param1.addEventListener(Event.ENTER_FRAME,this.afNoticeMotionTick);",
    "      }",
    "      ",
    "      private function afStopNoticeMotion() : void",
    "      {",
    "         var s:* = this.afMotionObj;",
    "         this.afMotionObj = null;",
    "         this.afMotionFrames = 0;",
    "         this.afMotionIndex = 0;",
    "         if(s == null)",
    "         {",
    "            return;",
    "         }",
    "         try",
    "         {",
    "            s.removeEventListener(Event.ENTER_FRAME,this.afNoticeMotionTick);",
    "         }",
    "         catch(offErr:*)",
    "         {",
    "         }",
    "         try",
    "         {",
    "            s.scrollRect = null;",
    "         }",
    "         catch(rectErr:*)",
    "         {",
    "         }",
    "         if(this.afMotionObj != null)",
    "         {",
    "            return;",
    "         }",
    "      }",
    "      ",
    "      private function afNoticeMotionTick(param1:Event) : void",
    "      {",
    "         var s:* = this.afMotionObj;",
    "         if(s == null)",
    "         {",
    "            return;",
    "         }",
    "         try",
    "         {",
    "            var iv:Number = 1500 / Number(this.afMotionFrames);",
    "            if(iv < 70)",
    "            {",
    "               iv = 70;",
    "            }",
    "            else if(iv > 400)",
    "            {",
    "               iv = 400;",
    "            }",
    "            var now:Number = Number(getTimer());",
    "            if(now - Number(this.afMotionLast) < iv)",
    "            {",
    "               return;",
    "            }",
    "            this.afMotionLast = now;",
    "            var i:int = (int(this.afMotionIndex) + 1) % int(this.afMotionFrames);",
    "            this.afMotionIndex = i;",
    "            s.scrollRect = new flash.geom.Rectangle(i * Number(this.afMotionFrameW),0,this.afMotionFrameW,this.afMotionFrameH);",
    "         }",
    "         catch(tickErr:*)",
    "         {",
    "         }",
    "         if(this.afMotionObj == null)",
    "         {",
    "            return;",
    "         }",
    "      }",
])

print("deployed md5:", md5(DEP))
shutil.rmtree("/tmp/mo_in", ignore_errors=True)
shutil.rmtree("/tmp/mo_orig", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/mo_in", str(DEP)], capture_output=True, text=True)
shutil.copytree("/tmp/mo_in", "/tmp/mo_orig")
SRC = pathlib.Path("/tmp/mo_in/scripts/PrinceOnline/castle/Notice.as")
src = open(SRC, encoding="utf-8", newline="").read()

pairs = [
    ("field anchor", FIELD_ANCHOR, FIELD_ANCHOR + FIELDS),
    ("showNoticeDetails fit call", ADDCHILD_FIT, ADDCHILD_FIT_NEW),
    ("afFitNoticeCard head", FIT_HEAD, FIT_HEAD_NEW),
    ("loadNoticeContent head", LOAD_HEAD, LOAD_HEAD_NEW),
    ("edit() stop", EDIT_STOP, EDIT_STOP_NEW),
    ("btnClose2 head", CLOSE_HEAD, CLOSE_HEAD_NEW),
    ("class tail", CLASS_TAIL, METHODS + CLASS_TAIL),
]
for label, old, new in pairs:
    c = src.count(old)
    if c != 1:
        print("!! anchor %r count %d" % (label, c))
        sys.exit(1)
    src = src.replace(old, new, 1)
if "afAnimateNoticeCard" in open("/tmp/mo_orig/scripts/PrinceOnline/castle/Notice.as",
                                 encoding="utf-8", newline="").read():
    print("!! already patched?")
    sys.exit(1)
SRC.write_text(src, newline="")
print("inserted the motion fields, the tick/stop methods and their call sites")

shutil.rmtree("/tmp/mo_imp", ignore_errors=True)
dst = pathlib.Path("/tmp/mo_imp/scripts/PrinceOnline/castle/Notice.as")
dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(SRC, dst)

r = subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-importScript",
                    str(DEP), "/tmp/mo_one.swf", "/tmp/mo_imp"],
                   capture_output=True, text=True, cwd="/tmp")
out = r.stdout + r.stderr
print("import rc:", r.returncode)
if "SEVERE" in out or "xception" in out or r.returncode != 0:
    print("!! importer complained")
    print(out[-1200:])
    sys.exit(1)
print("new swf: %d bytes md5 %s" % (pathlib.Path("/tmp/mo_one.swf").stat().st_size,
                                    md5("/tmp/mo_one.swf")))

shutil.rmtree("/tmp/mo_check", ignore_errors=True)
lg = subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                     "/tmp/mo_check", "/tmp/mo_one.swf"], capture_output=True, text=True)
severe = [l for l in (lg.stdout + lg.stderr).splitlines()
          if "SEVERE" in l or "xception" in l]
print("re-export SEVERE/xception lines:", len(severe))
for l in severe[:8]:
    print("   ", l)
if severe:
    sys.exit(1)

d = subprocess.run(["diff", "-rq", "/tmp/mo_orig/scripts", "/tmp/mo_check/scripts"],
                   capture_output=True, text=True)
print("diff -rq (pristine export of the base SWF vs the rebuilt one):")
print(d.stdout.strip() or "   (no difference)")
if d.stdout.count("\n") > 1 or "Notice.as" not in d.stdout:
    print("!! more than the one class changed")
    sys.exit(1)

nz = open("/tmp/mo_check/scripts/PrinceOnline/castle/Notice.as",
          encoding="utf-8", newline="").read()
nb = pathlib.Path("/tmp/mo_check/scripts/PrinceOnline/castle/Notice.as").read_bytes()
checks = [
    ("afAnimateNoticeCard defined",
     "private function afAnimateNoticeCard(param1:*) : void" in nz),
    ("afNoticeMotionTick defined", "private function afNoticeMotionTick" in nz),
    ("afStopNoticeMotion defined", "private function afStopNoticeMotion() : void" in nz),
    ("animate called from showNoticeDetails, before the fit",
     nz.count("this.afAnimateNoticeCard(Bridge.res.getData(this.noticeURL));") == 1
     and nz.index("this.afAnimateNoticeCard(Bridge.res.getData(this.noticeURL));")
     > nz.index("public function showNoticeDetails")
     and nz.index("this.afAnimateNoticeCard(Bridge.res.getData(this.noticeURL));")
     < nz.index("this.afFitNoticeCard();")),
    ("the fit SKIPS a strip instead of scaling it",
     "if(this.afMotionObj != null)" in nz
     and nz.index("if(this.afMotionObj != null)")
     > nz.index("private function afFitNoticeCard")),
    ("scrollRect window advanced on ENTER_FRAME",
     "s.addEventListener" not in nz
     and "param1.addEventListener(Event.ENTER_FRAME,this.afNoticeMotionTick);" in nz
     and ("flash.geom.Rectangle(i * this.afMotionFrameW" in nz
          or "Rectangle(i * this.afMotionFrameW" in nz)
     and "import flash.geom.Rectangle;" in nz),
    ("detection: 510 tall, whole 694-wide tiles, at least 2",
     "var fw:Number = 694;" in nz and "var fh:Number = 510;" in nz
     and "var n:int = Math.round(ow / fw);" in nz and "if(n < 2 || n > 24)" in nz),
    ("motion stopped when the panel closes / reloads content / edits",
     nz.count("this.afStopNoticeMotion();") == 4),
    ("did NOT get hoisted to the class body",
     "Notice.afNoticeMotionTick(" not in nz and "Notice.afStopNoticeMotion(" not in nz
     and "Notice.afAnimateNoticeCard(" not in nz),
    ("btnClose2 registration kept",
     "mcBtnManager.addMCButton(this.notice.btnClose2);" in nz),
    ("scrollbar patch survived", "afUpdateNoticeScrollBar" in nz),
    ("scrollbar config kept", '"t_view":510' in nz),
    ("addChild kept", "news.addChild(Bridge.res.getData(this.noticeURL))" in nz),
    ("stat card fit kept", "obj.x = (viewW - ow * s) / 2;" in nz),
    ("showList kept", "private function showList() : void" in nz),
    ("CRLF only", nb.count(b"\n") == nb.count(b"\r\n")),
]
ok = True
for label, good in checks:
    print("   %-52s %s" % (label, good))
    ok = ok and good
if not ok:
    print("!! NOT deploying")
    sys.exit(1)

BK = HOME / "lpo_build/swf_backups"
BK.mkdir(exist_ok=True)
TARGETS = (L / "lpo/patches/lib/lib.swf", L / "lpo/patches/lpo/lib/lib.swf",
           HOME / "littleprince-online/lib/lib.swf")
if DRY:
    print("DRY RUN - nothing deployed")
    sys.exit(0)
for p in TARGETS:
    bak = BK / (p.parent.relative_to(HOME).as_posix().replace("/", "_") + ".motion.bak")
    if not bak.exists():
        shutil.copy2(p, bak)
    shutil.copy2("/tmp/mo_one.swf", p)
for p in TARGETS:
    print("deployed %-52s %s" % (p, md5(p)))
print("size:", (L / "lpo/patches/lib/lib.swf").stat().st_size)
