#!/usr/bin/env python3
"""Prove the animated billboard's CLIENT side from the bytes that ship.

Three questions, three answers:

A. Is the motion code really in the lib.swf the relay serves?
   - decompress the CWS body and find the new method names in the ABC constant pool;
   - re-export the class from the SHIPPED swf and diff it against the pre-patch
     backup's export: exactly Notice.as may differ;
   - fetch /lib/lib.swf from the running mirror and compare md5 with the patch file.

B. Does the class's DETECTION/STEP logic actually classify real sheet sizes right?
   There is no Flash runtime here, so the AS3 bytecode cannot be executed.  What
   this does instead, honestly: read the constants OUT of the shipped decompiled
   source, then run a faithful port of `afAnimateNoticeCard`/`afNoticeMotionTick`
   (same arithmetic, same guards) over real PNGs of the sizes the editor publishes
   and over a simulated 60 fps clock.  It proves the LOGIC, not that Flash renders
   it - the port is a re-implementation, and it is labelled as one.

C. Does the served content route still hand the panel what it expects?
   - notices_reply's positional row must be unchanged (no motion field, all 12
     indices present) and the content URL must still end in .png (the only four
     extensions SOL::ResLoader turns into a display object);
   - a real strip served over HTTP must come back byte-identical, image/png;
   - notice_motion_clean must drop every malformed strip.

    python3 verify_notice_motion_swf.py [port] [scratch-lpo]
"""
import hashlib
import importlib
import json
import pathlib
import re
import struct
import subprocess
import sys
import urllib.request
import zlib

HOME = pathlib.Path.home()
JAR = HOME / "lpo_build/ffdec/ffdec-cli.jar"
PACK = HOME / "Downloads/littleprince-launcher"
SHIPPED = PACK / "lpo/patches/lib/lib.swf"
SIBLING = PACK / "lpo/patches/lpo/lib/lib.swf"
MIRROR = HOME / "littleprince-online/lib/lib.swf"
BASE_SWFs = sorted((HOME / "lpo_build/swf_backups").glob("*_lpo_patches_lib.motion.bak")) \
    or sorted((HOME / "lpo_build/swf_backups").glob("*lib.swf.motion.bak")) \
    or sorted((HOME / "lpo_build/swf_backups").glob("*lib.swf.bak"))
PORT = sys.argv[1] if len(sys.argv) > 1 else "8977"
SCRATCH = sys.argv[2] if len(sys.argv) > 2 else "/tmp/lpo_scratch/lpo"
BASE = "http://127.0.0.1:%s" % PORT
md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

RESULT = []


def check(name, ok, detail=""):
    RESULT.append((name, bool(ok), str(detail)[:300]))
    print(("PASS " if ok else "FAIL ") + name + ("  | " + str(detail)[:260] if detail else ""))


# ── A1. the method names are in the shipped SWF's constant pool ──────────────
raw = SHIPPED.read_bytes()
sig = raw[:3].decode("ascii")
body = raw[8:] if sig == "CWS" else raw
if sig == "CWS":
    body = zlib.decompress(body)
print("shipped lib.swf: %s %d bytes (packed) md5 %s" % (sig, len(raw), md5(SHIPPED)))
check("the shipped lib.swf is a zlib-compressed CWS", sig == "CWS", sig)
NEW_NAMES = ["afAnimateNoticeCard", "afNoticeMotionTick", "afStopNoticeMotion",
             "afMotionObj", "afMotionFrames", "afMotionFrameW", "afMotionFrameH",
             "afMotionIndex", "afMotionLast"]
missing = [n for n in NEW_NAMES if n.encode() not in body]
check("every new method/field name is in the SHIPPED swf's constant pool",
      not missing, missing or "all present")
check("the earlier scrollbar patch is still in the shipped swf",
      b"afUpdateNoticeScrollBar" in body and b"afFitNoticeCard" in body)

# ── A2. re-export the class from the shipped swf; diff against the backup ────
check("a pre-patch backup of lib.swf exists to diff against", bool(BASE_SWFs),
      [p.name for p in BASE_SWFs])
if not BASE_SWFs:
    sys.exit(1)
BASE_SWF = BASE_SWFs[0]


def export(swf, out):
    subprocess.run(["rm", "-rf", out], check=False)
    subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                    out, str(swf)], capture_output=True, text=True, check=False)
    return pathlib.Path(out) / "scripts"


base_scripts = export(BASE_SWF, "/tmp/verify_base")
new_scripts = export(SHIPPED, "/tmp/verify_new")
d = subprocess.run(["diff", "-rq", str(base_scripts), str(new_scripts)],
                   capture_output=True, text=True)
changed = [l for l in d.stdout.splitlines() if l.strip()]
check("re-exporting the shipped swf differs from the PRE-PATCH backup in Notice.as only",
      len(changed) == 1 and "Notice.as" in changed[0], changed)

nz = (new_scripts / "PrinceOnline/castle/Notice.as").read_text("utf-8")
bz = (base_scripts / "PrinceOnline/castle/Notice.as").read_text("utf-8")
check("the shipped class defines the three motion methods",
      all(("private function " + n) in nz for n in
          ("afAnimateNoticeCard", "afNoticeMotionTick", "afStopNoticeMotion")))
check("nothing was hoisted into a class-body initializer (AS3 would run it in the constructor)",
      "Notice.afAnimateNoticeCard(" not in nz and "Notice.afNoticeMotionTick(" not in nz
      and "Notice.afStopNoticeMotion(" not in nz)
check("the pre-patch class had no motion code at all (this really is the new behaviour)",
      "afAnimateNoticeCard" not in bz and "afNoticeMotionTick" not in bz)
check("the call sites are in the handlers that can abort the panel",
      nz.count("this.afAnimateNoticeCard(Bridge.res.getData(this.noticeURL));") == 1
      and nz.count("this.afStopNoticeMotion();") == 4
      and "animErr:*" in nz and "tickErr:*" in nz and "barErr:*" in nz)
check("the existing registrations/scrollbar work are untouched",
      "mcBtnManager.addMCButton(this.notice.btnClose2);" in nz
      and "afUpdateNoticeScrollBar" in nz and '"t_view":510' in nz
      and "news.addChild(Bridge.res.getData(this.noticeURL))" in nz)

# ── A3. the mirror really serves those bytes ────────────────────────────────
try:
    with urllib.request.urlopen(BASE + "/lib/lib.swf", timeout=20) as r:
        served = r.read()
    check("the running mirror serves the patched lib.swf byte for byte",
          hashlib.md5(served).hexdigest() == md5(SHIPPED),
          "%s vs %s" % (hashlib.md5(served).hexdigest(), md5(SHIPPED)))
except Exception as e:                                                # noqa: BLE001
    check("the running mirror serves the patched lib.swf byte for byte", False, e)
check("all three installed copies are identical",
      md5(SHIPPED) == md5(SIBLING) == md5(MIRROR) and md5(SHIPPED) != md5(BASE_SWF),
      "%s (before %s)" % (md5(SHIPPED), md5(BASE_SWF)))

# ── B. the shipped constants + a faithful port of the detection/step ────────
def lit(name):
    m = re.search(name + r":Number = ([\d.]+);", nz)
    if m:
        return float(m.group(1))
    m = re.search(name + r"\s*=\s*(-?[\d.]+)", nz)
    return float(m.group(1)) if m else None


FW, FH = lit("fw"), lit("fh")
check("the shipped frame size is read out of the decompiled class",
      FW == 694.0 and FH == 510.0, "fw=%s fh=%s" % (FW, FH))
check("the shipped guard is 2..24 frames and the height tolerance is +-2",
      "if(n < 2 || n > 24)" in nz and "if(!(oh > fh - 2 && oh < fh + 2))" in nz
      and "if(Math.abs(ow - n * fw) > 2)" in nz)
m = re.search(r"iv = ([\d.]+) / this\.afMotionFrames;", nz)
check("the shipped pace is derived from the frame count", bool(m), m.group(0) if m else "")
LOOP_MS = float(m.group(1)) if m else 1500.0


def afAnimateNoticeCard(ow, oh):
    """Port of the shipped decision: which sizes become an animation."""
    if not (FH - 2 < oh < FH + 2):
        return None
    n = round(ow / FW)
    if n < 2 or n > 24:
        return None
    if abs(ow - n * FW) > 2:
        return None
    return n


def afNoticeMotionTick(frames, fps=60.0, seconds=3.0):
    """Port of the shipped step: which frame is shown, at which times."""
    iv = LOOP_MS / frames
    iv = 70.0 if iv < 70 else (400.0 if iv > 400 else iv)
    seen, cur, last = [], 0, 0.0
    for k in range(int(fps * seconds)):
        now = k * 1000.0 / fps
        if now - last >= iv:
            last = now
            cur = (cur + 1) % frames
        seen.append(cur)
    return iv, seen


cases = [(694, 510, None), (1388, 510, 2), (2082, 510, 3), (2776, 510, 4),
         (1388, 1000, None), (700, 510, None), (5000, 510, None),
         (694 * 25, 510, None), (2100, 510, None), (694, 509, None), (694, 509.5, None)]
bad = [(w, h, want, afAnimateNoticeCard(w, h)) for w, h, want in cases
       if afAnimateNoticeCard(w, h) != want]
check("the ported detection classifies every size the editor can publish - and the "
      "near-misses it must refuse - exactly as intended",
      not bad, bad or "11/11")
check("a plain 694x510 card is NOT treated as an animation (the static path is untouched)",
      afAnimateNoticeCard(694, 510) is None)
check("the height tolerance accepts the 509.5..510.5 a real PNG can report",
      afAnimateNoticeCard(1388, 509.5) == 2 and afAnimateNoticeCard(1388, 510.5) == 2)

paces = {}
for n in (2, 3, 4, 6, 8):
    iv, seen = afNoticeMotionTick(n)
    paces[n] = (round(iv, 1), sorted(set(seen)))
check("every frame is shown and the window wraps (no frame is skipped)",
      all(fr == list(range(n)) for n, (_, fr) in paces.items()), paces)
check("a strip loops in about 1.5 s, whatever its frame count (the pace the editor quotes)",
      all(abs(iv * n - 1500.0) < 1.0 or (iv in (70.0, 400.0)) for n, (iv, _) in paces.items()),
      {n: iv for n, (iv, _) in paces.items()})

# ── C. the served content route ─────────────────────────────────────────────
sys.path.insert(0, SCRATCH)
srv = importlib.import_module("server")

# a real PNG at each size, made by the server's own writer
card = srv._plain_card_png(694, 510)
strip = srv._plain_card_png(694 * 4, 510)
w0, h0 = struct.unpack(">II", card[16:24])
w1, h1 = struct.unpack(">II", strip[16:24])
check("a real 694x510 card and a real 4-frame strip decode to the sizes the port expects",
      (w0, h0) == (694, 510) and (w1, h1) == (2776, 510)
      and afAnimateNoticeCard(w0, h0) is None and afAnimateNoticeCard(w1, h1) == 4)

saved = srv.save_notice_image(1, strip)
check("the server stores a 10:1-wide strip without complaint",
      saved.get("bytes") == len(strip), saved)
with urllib.request.urlopen(BASE + "/notice/content/1.png", timeout=20) as r:
    got, ctype = r.read(), r.headers.get("Content-Type")
check("the route the panel fetches serves that strip byte for byte, as image/png",
      got == strip and ctype == "image/png",
      "%s %d bytes %s" % (ctype, len(got), struct.unpack(">II", got[16:24])))

# the AMF row the panel actually reads must be untouched
payload = srv.notices_reply("getnotices")
decoded = srv.amf0.decode(payload)
rows = decoded[0] if isinstance(decoded, list) else decoded
row = (rows.get("list") or [{}])[0]
check("getNotices still answers a POSITIONAL row (slots 0..11 all present, no motion key)",
      all(str(i) in row for i in range(12)) and "motion" not in row,
      {"slots_0_11": all(str(i) in row for i in range(12)), "keys": len(row)})
check("the reply still points the panel at a .png (the only extensions ResLoader "
      "turns into a display object are swf/jpg/png/gif)",
      str(rows.get("url", "")).endswith(".png"), rows.get("url"))
rd = srv.amf0.decode(srv.notices_reply("readnotice"))
rd = rd[0] if isinstance(rd, list) else rd
check("readNotice points at the same .png route too (opening a card fetches it)",
      str(rd.get("url", "")).endswith(".png") and rd.get("response") == "readNotice",
      rd.get("url"))
check("neither reply carries a motion field (the client is not told about the strip)",
      "motion" not in rd and "motion" not in rows,
      [k for k in rd.keys()])
check("the row's body still rides as `content` (a reader that reads `body` gets nothing)",
      "content" in row and "body" not in row, [k for k in row.keys()][:12])

# malformed strips never reach the class
mclean = srv.notice_motion_clean
check("motion with fewer than 2 frames is refused",
      mclean({"on": True, "frames": ["data:image/png;base64,AA"]}) is None)
check("motion whose frames are not images is refused",
      mclean({"on": True, "frames": ["http://x/a.png", "http://x/b.png"]}) is None)
check("motion with more than 8 frames is clamped to 8",
      (mclean({"on": True, "frames": ["data:image/png;base64,AA"] * 20}) or {}).get("count") == 8)
check("an oversized frame source is dropped, not stored",
      mclean({"on": True, "frames": ["data:image/png;base64," + "A" * srv.LAYOUT_MAX_FRAME_SRC + "B"] * 2}) is None)
check("a layout with no motion keeps motion = None (old notices are unchanged)",
      srv.notice_layout_clean({"card": {"bg": "#fff"}})["motion"] is None
      and srv.notice_layout_clean(None) is None)
ok_motion = mclean({"on": True, "frames": ["data:image/png;base64,AA"] * 3})
check("a well-formed strip survives with its count",
      ok_motion == {"on": True, "count": 3, "frames": ["data:image/png;base64,AA"] * 3}, ok_motion)

bad = [r for r in RESULT if not r[1]]
print("\n==== %d checks, %d failed ====" % (len(RESULT), len(bad)))
sys.exit(1 if bad else 0)
