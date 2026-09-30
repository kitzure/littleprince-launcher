#!/usr/bin/env python3
"""LPO multiplayer: give the play-again button a second, direct press path.

MCBtnManager dispatches a release only when the mouse-up target is below-or-same as the
clip that was pressed.  On the multiplayer result frame that check fails - the button
hovers but the press never dispatches (nothing in the client log).  The button is a
MovieClip, so it can carry its own onRelease, which fires on release-over-clip regardless
of the manager's target test.  Both paths run the same idempotent action
(returnGameSelectLevel + toGameRoom = a gotoAndStop), so a double fire is harmless.
"""
import pathlib
import subprocess
import sys

AS = pathlib.Path("/tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as")
src = AS.read_text()
applied = []

# ── 1. factor the play-again action into one method ──────────────────────────
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
         }
      }
      
      // The multiplayer result screen's play-again: exactly what UI_base does for a
      // non-single gameMode (back to the game room for another round).
      public function mpPlayAgain(from where:String = "?") : void
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
         Bridge.flow.toGameRoom();'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("play-again action is one method now")
else:
    print("!! the retry branch anchor was not found")
    sys.exit(1)

# ── 2. the direct press path on the clip itself ──────────────────────────────
OLD = '''            if(retryBtn != null)
            {
               retryBtn.visible = true;
               this.mcBtnManager.addMCButton(retryBtn,"SFX_drag",null,"SFX_drop");
            }'''
NEW = '''            if(retryBtn != null)
            {
               retryBtn.visible = true;
               this.mcBtnManager.addMCButton(retryBtn,"SFX_drag",null,"SFX_drop");
               // Belt and braces: MCBtnManager only dispatches a release when the
               // mouse-up target is below-or-same as the pressed clip, and on this
               // frame that test fails - the button hovered, the press never arrived,
               // and the client log showed nothing at all.  A MovieClip can carry its
               // own onRelease, which fires on a release over the clip whatever the
               // manager decides.  The action is idempotent, so if both fire it is
               // still one trip back to the room.
               var self:* = this;
               retryBtn.onRelease = function() : void
               {
                  self.mpPlayAgain("clip");
               };
               retryBtn.onReleaseOutside = function() : void
               {
                  retryBtn.gotoAndStop(retryBtn._up);
               };
            }'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("the clip carries its own onRelease too")
else:
    print("!! the retry registration anchor was not found")
    sys.exit(1)

AS.write_text(src)
print("applied to UI_multiplay.as:")
for a in applied:
    print("  -", a)

r = subprocess.run(["bash", str(pathlib.Path.home() / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print(r.stdout[-1200:])
if r.returncode != 0:
    print("rebuild stderr:", r.stderr[-500:])
