#!/usr/bin/env python3
"""Redo: helper + the call inside label_mp_result_title, by brace matching."""
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
print("deployed md5:", md5(DEP), "(unchanged - nothing was deployed)")

shutil.rmtree("/tmp/lpo_re", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_re", str(DEP)], capture_output=True, text=True)
clean = pathlib.Path("/tmp/lpo_re/scripts/PrinceOnline/UI_multiplay.as")
shutil.copy2(clean, SRC)
src = SRC.read_text()
print("clean base restored (%d chars)" % len(src))
assert "mpPlayAgain" in src

indent = "      "
HELPER = '''public function setupMpRetryButton() : void
      {
         var retryBtn:MovieClip = this["btnRetry" + Bridge.user.TextLanguage];
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

# put the helper immediately before mpPlayAgain
anchor = src.index("public function mpPlayAgain(")
anchor = src.rindex("\n", 0, anchor) + 1
src = src[:anchor] + indent + HELPER + src[anchor:]

# brace-match label_mp_result_title to insert the call at its very end
m = re.search(r"public function label_mp_result_title\(\) : void", src)
assert m, "title handler not found"
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
body = src[start:i]
print("=== title handler: %d chars, last 200 before the insertion point ===" % len(body))
print(body[-200:])
src = src[:i] + "\n" + indent + "   this.setupMpRetryButton();\n" + indent + src[i:]
SRC.write_text(src)
print("\ninserted: helper + the call at the end of label_mp_result_title")

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print(r.stdout[-700:])
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer complained - NOT deploying")
    sys.exit(1)

# confirm it landed in the right method
out = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as").read_text()
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
print("\n=== after the round trip ===")
print("   helper present            :", "function setupMpRetryButton" in out)
print("   called from the title frame:", "setupMpRetryButton();" in out[s:j])
print("   called from the end frame  :", out.count("setupMpRetryButton();"))
