#!/usr/bin/env python3
"""The real fix: the multiplayer result screen's button is named `btnRetry`, with no
language suffix.

Pinned from interface.xml: the `mp_result_end` symbol owns one clip named exactly
`btnRetry` (plus mp_ranking), while `btnRetry0`/`btnRetry1` sit with `btnNext0/1` and
`btnLevel0/1` on the SINGLE-PLAYER result frame.  So every `this["btnRetry" + lang]`
lookup on the multiplayer screen returned null - the button was never registered with the
manager, never given a listener, and never matched by UI_base's handler.  It just played
its own idle animation, which is exactly what was reported.
"""
import pathlib
import re
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()
JAR = HOME / "lpo_build/ffdec/ffdec-cli.jar"
DEP = HOME / "Downloads/littleprince-launcher/lpo/patches/lib/lib.swf"
SRC = pathlib.Path("/tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as")

md5 = lambda p: subprocess.run(["md5sum", str(p)], capture_output=True,
                               text=True).stdout.split()[0]
print("deployed md5:", md5(DEP))
shutil.rmtree("/tmp/lpo_re", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_re", str(DEP)], capture_output=True, text=True)
shutil.copy2(pathlib.Path("/tmp/lpo_re/scripts/PrinceOnline/UI_multiplay.as"), SRC)
src = SRC.read_text()
print("clean base: %d chars" % len(src))

# ── 1. the helper: look up btnRetry first ────────────────────────────────────
HELPER = '''public function setupMpRetryButton() : void
      {
         var retryBtn:MovieClip = this["btnRetry"];
         if(retryBtn == null)
         {
            retryBtn = this["btnRetry" + Bridge.user.TextLanguage];
         }
         if(retryBtn == null)
         {
            retryBtn = this["btnRetry" + (Bridge.user.TextLanguage == 0 ? 1 : 0)];
         }
         if(retryBtn != null)
         {
            retryBtn.visible = true;
            this.mcBtnManager.addMCButton(retryBtn,"SFX_drag",null,"SFX_drop");
            var self:* = this;
            retryBtn.addEventListener(flash.events.MouseEvent.CLICK,function(param1:flash.events.MouseEvent) : void
            {
               self.mpPlayAgain("clip");
            });
            Debug.addLog("\\\\tmp_result: retry ready (" + retryBtn.name + ")");
         }
         else
         {
            Debug.addLog("\\\\tmp_result: no retry button on this frame");
         }
      }
      
      '''
anchor = src.index("public function mpPlayAgain(")
anchor = src.rindex("\n", 0, anchor) + 1
src = src[:anchor] + "      " + HELPER + src[anchor:]

# ── 2. call it from the verdict frame ───────────────────────────────────────
m = re.search(r"public function label_mp_result_title\(\) : void", src)
start = src.index("{", m.end())
depth, i = 0, start
while i < len(src):
    if src[i] == "{":
        depth += 1
    elif src[i] == "}":
        depth -= 1
        if depth == 0:
            break
    i += 1
src = src[:i] + "\n         this.setupMpRetryButton();\n      " + src[i:]

# ── 3. the manager dispatch must accept the plain name too ──────────────────
if '"btnRetry"' not in src:
    OLD = 'else if(_loc4_.substr(0,8) == "btnRetry")'
    NEW = 'else if(_loc4_ == "btnRetry" || _loc4_.substr(0,8) == "btnRetry")'
    assert OLD in src, "the retry dispatch branch is missing"
    src = src.replace(OLD, NEW, 1)

SRC.write_text(src)
print("applied: btnRetry lookup + the verdict-frame call + the dispatch branch")

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print(r.stdout[-700:])
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer complained - NOT deploying")
    sys.exit(1)

out = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as").read_text()
print("\n=== after the round trip ===")
mm = re.search(r"function label_mp_result_title\(\) : void", out)
s = out.index("{", mm.end())
depth, j = 0, s
while j < len(out):
    if out[j] == "{":
        depth += 1
    elif out[j] == "}":
        depth -= 1
        if depth == 0:
            break
    j += 1
for probe, label in (('this["btnRetry"]', "looks up the plain btnRetry first"),
                     ("function setupMpRetryButton", "the helper exists"),
                     ("mouseEvent", "a real click listener"),
                     ("setupMpRetryButton();", "called exactly once")):
    print("   %-36s %s" % (label, out.lower().count(probe.lower())))
print("   called from the title frame:", "setupMpRetryButton();" in out[s:j])
