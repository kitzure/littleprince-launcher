#!/usr/bin/env python3
"""LPO multiplayer: make the result screen's play-again actually work.

Two causes, both pinned from the client:

1. MCBtnManager only dispatches a release when the mouse-up target is below-or-same as
   the pressed clip (`belowOrSame(param1.target, this.press)`), so a leftover alert popup
   over the result frame makes the button hoverable but unpressable.  The flow shows
   MSGalert when a player leaves and multi_gameretryfail when a retry fails, and nothing
   on this frame ever closed it.  The single-player result does exactly this check.
2. UI_base's release handler matches `"btnRetry" + Bridge.user.TextLanguage` only, while
   label_mp_result_end falls back to the OTHER language's button when the current one is
   missing - so that visible button was ignored.
"""
import pathlib
import subprocess
import sys

AS = pathlib.Path("/tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as")
src = AS.read_text()
applied = []

# ── 1. close a leftover popup on the result frame ────────────────────────────
OLD = '''         trace(">>>>>>>> label_mp_result_end");
         try
         {
            showCoinBarChg(currentScore);'''
NEW = '''         trace(">>>>>>>> label_mp_result_end");
         try
         {
            // A leftover alert (MSGalert when a player leaves, multi_gameretryfail when a
            // retry fails) sits over this frame and eats the mouse-up: MCBtnManager only
            // dispatches a release when the mouse-up target is the pressed clip, so the
            // play-again button hovered but could never be pressed.  The single-player
            // result screen does the same check.
            if(Bridge.popup.isShow())
            {
               Bridge.popup.close();
               Debug.addLog("\\tmp_result: closed a leftover popup");
            }
            showCoinBarChg(currentScore);'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("result frame closes a leftover popup")
else:
    print("!! result-frame anchor not found")
    sys.exit(1)

# ── 2. accept the fallback language's retry button too ───────────────────────
OLD = '''         else
         {
            super.eBtnOnRelease(param1,param2,param3);
         }
      }
      
      override protected function btnExit_click_end() : void'''
NEW = '''         else if(_loc4_.substr(0,8) == "btnRetry")
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
         }
         else
         {
            super.eBtnOnRelease(param1,param2,param3);
         }
      }
      
      override protected function btnExit_click_end() : void'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("any btnRetry* now plays again")
else:
    print("!! release-handler anchor not found")
    sys.exit(1)

AS.write_text(src)
print("applied to UI_multiplay.as:")
for a in applied:
    print("  -", a)

r = subprocess.run(["bash", str(pathlib.Path.home() / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print(r.stdout[-1500:])
if r.returncode != 0:
    print("rebuild stderr:", r.stderr[-600:])
