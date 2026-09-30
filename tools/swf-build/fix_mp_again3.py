#!/usr/bin/env python3
"""Redo the play-again patch on a clean source export, with valid AS3."""
import pathlib
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()
JAR = HOME / "lpo_build/ffdec/ffdec-cli.jar"
DEP = HOME / "Downloads/littleprince-launcher/lpo/patches/lib/lib.swf"
SRC = pathlib.Path("/tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as")

md5 = lambda p: subprocess.run(["md5sum", str(p)], capture_output=True,
                               text=True).stdout.split()[0]
print("deployed lib.swf: %s  md5 %s" % (DEP.stat().st_size, md5(DEP)))

# ── 1. clean re-export of the deployed (already-fixed) class ─────────────────
shutil.rmtree("/tmp/lpo_re", ignore_errors=True)
r = subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                    "/tmp/lpo_re", str(DEP)], capture_output=True, text=True)
clean = pathlib.Path("/tmp/lpo_re/scripts/PrinceOnline/UI_multiplay.as")
print("re-exported class: %d chars" % (len(clean.read_text()) if clean.is_file() else -1))
if not clean.is_file():
    print("!! re-export produced no class")
    sys.exit(1)
shutil.copy2(clean, SRC)
src = SRC.read_text()
print("restored %s from the deployed SWF" % SRC.name)

# sanity: the first fix must be in there
assert 'substr(0,8) == "btnRetry"' in src, "the first fix is missing from the export"
assert "closed a leftover popup" in src, "the popup close is missing from the export"

# ── 2. the btnRetry branch calls a shared method ─────────────────────────────
OLD = '''         else if(_loc4_.substr(0,8) == "btnRetry")
         {
            // The result screen's play-again.  UI_base only matches the button for the
            // CURRENT language ("btnRetry" + Bridge.user.TextLanguage), but
            // label_mp_result_end shows the other language's button when the current
            // one is missing - and that press fell straight through to the base, which
            // matched nothing and did nothing.  Same action as the base's multiplayer
            // branch: back to the game room for another round.
            Debug.addLog("\\tmp_result: play again (" + _loc4_ + ")");
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
         }'''
NEW = '''         else if(_loc4_.substr(0,8) == "btnRetry")
         {
            this.mpPlayAgain(_loc4_);
         }'''
assert OLD in src, "the btnRetry branch differs from what was written earlier"
src = src.replace(OLD, NEW, 1)

# ── 3. the shared method, before btnExit_click_end ───────────────────────────
ANCHOR = '''      override protected function btnExit_click_end() : void'''
METHOD = '''      // The multiplayer result screen's play-again: exactly what UI_base does for a
      // gameMode other than "single" - back to the game room for another round.
      public function mpPlayAgain(where:String = "?") : void
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
assert ANCHOR in src, "btnExit_click_end anchor not found"
src = src.replace(ANCHOR, METHOD + ANCHOR, 1)

# ── 4. the clip's own onRelease, so the press cannot be swallowed ────────────
OLD = '''               retryBtn.visible = true;
               this.mcBtnManager.addMCButton(retryBtn,"SFX_drag",null,"SFX_drop");'''
NEW = '''               retryBtn.visible = true;
               this.mcBtnManager.addMCButton(retryBtn,"SFX_drag",null,"SFX_drop");
               // Belt and braces: MCBtnManager dispatches a release only when the
               // mouse-up target is below-or-same as the pressed clip, and on this frame
               // that test fails - the button hovered, the press never arrived, and the
               // client log stayed empty.  A MovieClip can carry its own onRelease,
               // which fires on a release over the clip whatever the manager decides.
               // The action is idempotent, so if both fire it is still one trip back.
               var self:* = this;
               retryBtn.onRelease = function() : void
               {
                  self.mpPlayAgain("clip");
               };'''
assert OLD in src, "the retry registration block differs"
src = src.replace(OLD, NEW, 1)

SRC.write_text(src)
print("applied 3 edits")

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
out = r.stdout
print(out[-900:])
if "SEVERE" in out or "expected but" in out:
    print("!! the importer complained - not shipping this")
    sys.exit(1)
