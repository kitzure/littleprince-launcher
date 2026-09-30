#!/usr/bin/env python3
"""Patch the re-exported class by structure (not by comment text): decompilers drop
comments, so the earlier block text cannot be matched verbatim."""
import pathlib
import re
import subprocess
import sys

HOME = pathlib.Path.home()
SRC = pathlib.Path("/tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as")
src = SRC.read_text()

# ── 1. replace the btnRetry branch wholesale, by brace matching ──────────────
m = re.search(r'else if\(_loc4_\.substr\(0,8\) == "btnRetry"\)', src)
if not m:
    print("!! no btnRetry branch in the export")
    sys.exit(1)
brace = src.index("{", m.end())
depth, i = 0, brace
while i < len(src):
    if src[i] == "{":
        depth += 1
    elif src[i] == "}":
        depth -= 1
        if depth == 0:
            break
    i += 1
old_block = src[m.start():i + 1]
print("=== the branch as exported (%d chars) ===" % len(old_block))
print("\n".join(old_block.splitlines()[:14]))
src = src[:m.start()] + 'else if(_loc4_.substr(0,8) == "btnRetry")\n         {\n            this.mpPlayAgain(_loc4_);\n         }' + src[i + 1:]

# ── 2. the shared method ─────────────────────────────────────────────────────
ANCHOR = "override protected function btnExit_click_end() : void"
if ANCHOR not in src:
    print("!! btnExit_click_end anchor missing")
    sys.exit(1)
METHOD = '''public function mpPlayAgain(where:String = "?") : void
      {
         Debug.addLog("\\tmp_result: play again (" + where + ")");
         this.returnGameSelectLevel();
         if(this.footer.currentFrame == 1)
         {
            this.footer.gotoAndStop(1);
         }
         else
         {
            this.footer.play();
         }
         this.footerRemove();
         Bridge.flow.toGameRoom();
      }
      
      '''
line_start = src.rindex("\n", 0, src.index(ANCHOR)) + 1
indent = src[line_start:src.index(ANCHOR)]
src = src[:line_start] + "\n".join(indent + l if l.strip() else l for l in METHOD.splitlines()) + src[line_start:]

# ── 3. the clip's own onRelease ──────────────────────────────────────────────
reg = re.search(r'( *)this\.mcBtnManager\.addMCButton\(retryBtn,\s*"SFX_drag",\s*null,\s*"SFX_drop"\);', src)
if not reg:
    print("!! the retry registration line was not found")
    sys.exit(1)
print("\n=== registration line as exported ===")
print(reg.group(0))
extra = (reg.group(1) + "// the manager's dispatch can be swallowed on this frame, so the clip carries\n"
         + reg.group(1) + "// its own release too; the action is idempotent\n"
         + reg.group(1) + "var self:* = this;\n"
         + reg.group(1) + "retryBtn.onRelease = function() : void\n"
         + reg.group(1) + "{\n"
         + reg.group(1) + "   self.mpPlayAgain(\"clip\");\n"
         + reg.group(1) + "};")
src = src.replace(reg.group(0), reg.group(0) + "\n" + extra, 1)

SRC.write_text(src)
r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print(r.stdout[-800:])
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer complained - not shipping")
    sys.exit(1)
