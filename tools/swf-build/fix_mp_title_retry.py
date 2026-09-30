#!/usr/bin/env python3
"""Register the play-again button on the frame the player is actually looking at.

The verdict panel (對不起，你未能成功過關 / 恭喜你，你已成功過關) is `mp_result_title`
(frame 388) - it has no rank footer, which `mp_result_end` (401) always draws.  Only
`label_mp_result_end` ever wired the retry button, so on the verdict screen the button was
a dead clip: it animates on hover (its own listeners), and nothing handles the press.
This adds one helper and calls it from the title frame as well.
"""
import pathlib
import re
import subprocess
import sys

HOME = pathlib.Path.home()
JAR = HOME / "lpo_build/ffdec/ffdec-cli.jar"
DEP = HOME / "Downloads/littleprince-launcher/lpo/patches/lib/lib.swf"
SRC = pathlib.Path("/tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as")

# ── canonical base: re-export the deployed SWF ───────────────────────────────
print("deployed md5:", subprocess.run(["md5sum", str(DEP)], capture_output=True,
                                      text=True).stdout.split()[0])
import shutil
shutil.rmtree("/tmp/lpo_re", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_re", str(DEP)], capture_output=True, text=True)
clean = pathlib.Path("/tmp/lpo_re/scripts/PrinceOnline/UI_multiplay.as")
assert clean.is_file(), "re-export failed"
shutil.copy2(clean, SRC)
src = SRC.read_text()
assert "mpPlayAgain" in src, "the shipped fix is missing from the export"
print("clean base restored (%d chars)" % len(src))

# ── 1. the helper ────────────────────────────────────────────────────────────
ANCHOR = "public function mpPlayAgain("
if ANCHOR not in src:
    print("!! mpPlayAgain not in the export")
    sys.exit(1)
line_start = src.rindex("\n", 0, src.index(ANCHOR)) + 1
indent = src[line_start:src.index(ANCHOR)]
HELPER = (indent + "// Wires the verdict screen's play-again button.  It lives on the\n"
          + indent + "// mp_result_title frame, which is the one the player sees - the old\n"
          + indent + "// code only wired the button on mp_result_end, so here it was a dead\n"
          + indent + "// clip that animated on hover and did nothing on release.\n"
          + indent + "public function setupMpRetryButton() : void\n"
          + indent + "{\n"
          + indent + "   var retryBtn:MovieClip = this[\"btnRetry\" + Bridge.user.TextLanguage];\n"
          + indent + "   if(retryBtn == null)\n"
          + indent + "   {\n"
          + indent + "      retryBtn = this[\"btnRetry\" + (Bridge.user.TextLanguage == 0 ? 1 : 0)];\n"
          + indent + "   }\n"
          + indent + "   if(retryBtn != null)\n"
          + indent + "   {\n"
          + indent + "      retryBtn.visible = true;\n"
          + indent + "      this.mcBtnManager.addMCButton(retryBtn,\"SFX_drag\",null,\"SFX_drop\");\n"
          + indent + "      var self:* = this;\n"
          + indent + "      retryBtn.addEventListener(flash.events.MouseEvent.CLICK,"
          + "function(param1:flash.events.MouseEvent) : void\n"
          + indent + "      {\n"
          + indent + "         self.mpPlayAgain(\"clip\");\n"
          + indent + "      });\n"
          + indent + "      Debug.addLog(\"\\\\tmp_result: retry ready (\" + retryBtn.name + \")\");\n"
          + indent + "   }\n"
          + indent + "   else\n"
          + indent + "   {\n"
          + indent + "      Debug.addLog(\"\\\\tmp_result: no retry button on this frame\");\n"
          + indent + "   }\n"
          + indent + "}\n"
          + indent + "\n")
src = src[:line_start] + HELPER + src[line_start:]

# ── 2. call it from the title frame ──────────────────────────────────────────
NEXT = "public function label_mp_result_end()"
i = src.index(NEXT)
# the closing brace of the title handler is the last "}" before it
close = src.rindex("}", 0, i)
print("=== title handler tail ===")
print(src[max(0, close - 220):close + 40])
src = src[:close] + indent + "   this.setupMpRetryButton();\n" + indent + src[close:]
SRC.write_text(src)
print("\ninserted the helper and the title-frame call")

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print(r.stdout[-900:])
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer complained - NOT deploying")
    sys.exit(1)
