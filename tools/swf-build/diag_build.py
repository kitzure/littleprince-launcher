#!/usr/bin/env python3
"""Diagnostic build: revert the title-frame registration, and make the log VISIBLE.

The client's Debug class owns a TextField that nothing ever initialises, and addLog()
also calls trace() - which the publisher's player discards.  That is why no log line could
ever be seen.  This build initialises and enables that TextField so the markers appear on
screen, and logs the facts we have been guessing at: which result frame is showing, which
retry clips exist on it, and whether a press arrives.

The registration on the verdict frame uses ONLY a click listener - no addMCButton - because
addMCButton calls gotoAndStop on the clip, which is my suspect for the blank panel.
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

shutil.rmtree("/tmp/lpo_re", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_re", str(DEP)], capture_output=True, text=True)
shutil.copy2(pathlib.Path("/tmp/lpo_re/scripts/PrinceOnline/UI_multiplay.as"), SRC)
src = SRC.read_text()
print("base: %d chars, helpers=%d calls=%d" % (len(src),
      src.count("function setupMpRetryButton"), src.count("setupMpRetryButton();")))

DIAG = '''public function mpDiag(where:String) : void
      {
         try
         {
            if(Debug.tf_debug == null)
            {
               var holder:flash.display.Sprite = new flash.display.Sprite();
               this.addChild(holder);
               Debug.init(holder,560,220);
            }
            Debug.enable();
            var b0:* = this["btnRetry0"];
            var b1:* = this["btnRetry1"];
            var bp:* = this["btnRetry"];
            Debug.addLog("\\\\tmp_diag @ " + where + " frame=" + this.currentLabel);
            Debug.addLog("\\\\tmp_diag btnRetry=" + (bp == null ? "none" : bp.name + " f" + bp.currentFrame) + " btnRetry0=" + (b0 == null ? "no" : "yes") + " btnRetry1=" + (b1 == null ? "no" : "yes"));
         }
         catch(diagErr:*)
         {
         }
      }
      
      public function mpWireRetry(where:String) : void
      {
         try
         {
            var rb:MovieClip = this["btnRetry"];
            if(rb == null)
            {
               rb = this["btnRetry" + Bridge.user.TextLanguage];
            }
            if(rb == null)
            {
               Debug.addLog("\\\\tmp_diag @ " + where + ": no retry clip at all");
               return;
            }
            rb.visible = true;
            Debug.addLog("\\\\tmp_diag @ " + where + ": wiring " + rb.name);
            var self:* = this;
            rb.addEventListener(flash.events.MouseEvent.CLICK,function(param1:flash.events.MouseEvent) : void
            {
               Debug.addLog("\\\\tmp_diag: CLICK arrived on " + rb.name);
               self.mpPlayAgain("clip");
            });
         }
         catch(wireErr:*)
         {
            Debug.addLog("\\\\tmp_diag wire error: " + wireErr);
         }
      }
      
      '''

# put both helpers before mpPlayAgain
anchor = src.index("public function mpPlayAgain(")
anchor = src.rindex("\n", 0, anchor) + 1
src = src[:anchor] + "      " + DIAG + src[anchor:]

# the verdict frame: revert the old call, add diagnostics + the click-only wiring
old_call = "this.setupMpRetryButton();"
if old_call not in src:
    print("!! the title-frame call is not there")
    sys.exit(1)
title = re.search(r"function label_mp_result_title\(\) : void", src)
start = src.index("{", title.end())
depth, i = 0, start
while i < len(src):
    if src[i] == "{":
        depth += 1
    elif src[i] == "}":
        depth -= 1
        if depth == 0:
            break
    i += 1
body = src[start:i]
if old_call in body:
    body2 = body.replace(old_call,
                         'this.mpDiag("verdict");\n         this.mpWireRetry("verdict");')
    src = src[:start] + body2 + src[i:]
    print("verdict frame: call replaced by the diagnostic + click-only wiring")
else:
    print("!! the call is not inside the title handler")
    sys.exit(1)

# the end frame: same diagnostics, keeping its existing registration
end = re.search(r"function label_mp_result_end\(\) : void", src)
s2 = src.index("{", end.end())
depth, j = 0, s2
while j < len(src):
    if src[j] == "{":
        depth += 1
    elif src[j] == "}":
        depth -= 1
        if depth == 0:
            break
    j += 1
src = src[:s2] + "{\n         this.mpDiag(\"end\");\n         this.mpWireRetry(\"end\");" + src[s2 + 1:]

# mpPlayAgain announces itself on screen
src = src.replace('public function mpPlayAgain(where:String = "?") : void\n      {\n',
                  'public function mpPlayAgain(where:String = "?") : void\n      {\n'
                  '         Debug.addLog("\\\\tmp_diag: play again running (" + where + ")");\n', 1)

SRC.write_text(src)
print("helpers=%d diagCalls=%d wireCalls=%d" % (src.count("function mpDiag"),
                                                 src.count("mpDiag("), src.count("mpWireRetry(")))

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print(r.stdout[-600:])
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer complained - NOT deploying")
    sys.exit(1)
