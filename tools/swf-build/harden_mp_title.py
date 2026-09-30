#!/usr/bin/env python3
"""Harden UI_multiplay.label_mp_result_title (frame mp_result_title, 388).

That function is the win/lose split:
    mpIsPass() -> heading gotoAndStop("pass") + SFX_successgame
    else       -> heading gotoAndStop("fail") + SFX_failgame

The win branch works on the machine; the lose branch misbehaves. Every step of it can
throw (showLang is not null-safe, the heading clip may be absent, the SFX name may not
resolve) and a throw there means the rest of the frame script never runs. This rewrite
makes each concern separately fault-tolerant, logs what actually happened via
Debug.addLog (which mirrors to trace -> Ruffle console), and mirrors the single-player
path's popup close.
"""
import pathlib
import sys

P = pathlib.Path('/tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as')
src = P.read_text(encoding='utf-8', errors='replace')

OLD = '''      public function label_mp_result_title() : void
      {
         trace(">>>>>>>> label_mp_result_title");
         footer.mouseControlPanel.visible = false;
         this.showLang(["heading"],1);
         if(this.mpIsPass())
         {
            this["heading" + Bridge.user.TextLanguage].gotoAndStop("pass");
            Bridge.res.playSFX("SFX_successgame");
         }
         else
         {
            this["heading" + Bridge.user.TextLanguage].gotoAndStop("fail");
            Bridge.res.playSFX("SFX_failgame");
         }
      }'''

NEW = '''      public function label_mp_result_title() : void
      {
         var myLang:* = undefined;
         var pass:* = false;
         var idx:* = 0;
         var clip:MovieClip = null;
         trace(">>>>>>>> label_mp_result_title");
         Debug.addLog("\\tmp_title: enter");
         try
         {
            footer.mouseControlPanel.visible = false;
         }
         catch(footerErr:*)
         {
            Debug.addLog("\\tmp_title: footer error " + footerErr);
         }
         try
         {
            Bridge.popup.close();
         }
         catch(popupErr:*)
         {
            Debug.addLog("\\tmp_title: popup error " + popupErr);
         }
         myLang = Bridge.user.TextLanguage;
         idx = 0;
         while(idx <= 1)
         {
            clip = this["heading" + idx];
            if(clip != null)
            {
               clip.visible = idx == myLang;
            }
            else
            {
               Debug.addLog("\\tmp_title: heading" + idx + " missing on this frame");
            }
            idx++;
         }
         try
         {
            pass = this.mpIsPass();
         }
         catch(passErr:*)
         {
            Debug.addLog("\\tmp_title: mpIsPass error " + passErr);
            pass = false;
         }
         Debug.addLog("\\tmp_title: pass=" + pass + " lang=" + myLang);
         try
         {
            clip = this["heading" + myLang];
            if(clip != null)
            {
               clip.gotoAndStop(pass ? "pass" : "fail");
               Debug.addLog("\\tmp_title: heading gotoAndStop(" + (pass ? "pass" : "fail") + ") ok");
            }
            else
            {
               Debug.addLog("\\tmp_title: no heading clip for lang " + myLang);
            }
         }
         catch(headErr:*)
         {
            Debug.addLog("\\tmp_title: heading error " + headErr);
         }
         try
         {
            Bridge.res.playSFX(pass ? "SFX_successgame" : "SFX_failgame");
         }
         catch(sfxErr:*)
         {
            Debug.addLog("\\tmp_title: SFX error " + sfxErr);
         }
         Debug.addLog("\\tmp_title: done");
      }'''

def norm(s):
    return s.replace('\r\n', '\n')

if norm(OLD) not in norm(src):
    print("PATTERN NOT FOUND — aborting")
    sys.exit(1)

# rebuild with the file's own line endings
out = norm(src).replace(norm(OLD), NEW)
if '\r\n' in src:
    out = out.replace('\n', '\r\n')
P.write_text(out, encoding='utf-8')
print("patched:", P)
print("markers now present:", out.count('\\tmp_title:'))
