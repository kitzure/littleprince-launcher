#!/usr/bin/env python3
"""Stage the ONE class this batch patches in lib.swf: PrinceOnline/castle/AddFriend.as.

- the "request sent" line, client-side (RemoteService only SENDS requestBeFriend)
- the page arrows are hidden whenever the panel has no second page (btnSFL/btnSFR are
  placed on frameset 34 "result_edit" by the timeline and nothing re-hides them after a
  replay; btnL/btnR are placed on frame 7 "friend_edit")
- the 共同朋友 count can no longer throw (flist is now sent by the mirror, but an
  undefined one must not kill the rest of showSearchResult)
- the on-screen diagnostic overlay and its Debug.addLog markers come OUT (the user asked
  for them to be removed from the shipped pack)
"""
import pathlib
import re
import shutil
import sys

BASE = pathlib.Path("/home/yoke/work_base/scripts/PrinceOnline/castle/AddFriend.as")
STAGE = pathlib.Path("/tmp/lpo_stage/scripts/PrinceOnline/castle/AddFriend.as")

text = open(BASE, encoding="utf-8", newline="").read()
original = text
report = []

# ── 1. the diagnostic overlay: drop the method and its call ──
start = text.index("      public function afDiag() : void")
end = text.index("      public function afHideEmptySlots() : void")
text = text[:start] + text[end:]
report.append(("afDiag() method removed", "public function afDiag" not in text))
text = text.replace("         this.afDiag();\r\n", "")
report.append(("afDiag() call removed", "this.afDiag();" not in text))

# ── 2. every Debug.addLog marker comes out ──
text, n_logs = re.subn(r"[ \t]*Debug\.addLog\([^\r\n]*\);\r\n", "", text)
report.append(("Debug.addLog lines removed (%d)" % n_logs, "Debug." not in text))
text = text.replace("   import SOL.Debug;\r\n", "")
report.append(("import SOL.Debug removed", "SOL.Debug" not in text))

# ── 3. fetchGroup().flist can no longer abort showSearchResult ──
OLD_CF = ('               _loc3_["btnCF" + Bridge.user.TextLanguage].btn.'
          'gotoAndStop(this.searchResult[_loc2_ + _loc1_].flist.length.toString().length);\r\n'
          '               Utils.setEmbedFont(_loc3_["btnCF" + Bridge.user.TextLanguage].btn.num,'
          '"Arial Rounded MT Bold",18,this.searchResult[_loc2_ + _loc1_].flist.length.toString());\r\n')
NEW_CF = ('               try\r\n'
          '               {\r\n'
          '                  _loc6_ = this.searchResult[_loc2_ + _loc1_].flist == null'
          ' ? 0 : this.searchResult[_loc2_ + _loc1_].flist.length;\r\n'
          '                  _loc3_["btnCF" + Bridge.user.TextLanguage].btn.gotoAndStop'
          '(_loc6_.toString().length);\r\n'
          '                  Utils.setEmbedFont(_loc3_["btnCF" + Bridge.user.TextLanguage].btn.num,'
          '"Arial Rounded MT Bold",18,_loc6_.toString());\r\n'
          '               }\r\n'
          '               catch(cfErr:*)\r\n'
          '               {\r\n'
          '               }\r\n')
assert OLD_CF in text, "the 共同朋友 lines moved - re-export and re-anchor"
text = text.replace(OLD_CF, NEW_CF, 1)
report.append(("flist access guarded", "flist == null" in text))

# ── 4. the arrow sync: an ENTER_FRAME keeper, registered in init ──
OLD_INIT_TAIL = ('         Bridge.utils.batchAddFrameScript(this.fanset,_loc1_);\r\n'
                 '         this.titleFriend.gotoAndStop("lan" + Bridge.user.TextLanguage);\r\n'
                 '      }\r\n')
NEW_INIT_TAIL = ('         Bridge.utils.batchAddFrameScript(this.fanset,_loc1_);\r\n'
                 '         this.titleFriend.gotoAndStop("lan" + Bridge.user.TextLanguage);\r\n'
                 '         this.removeEventListener(Event.ENTER_FRAME,this.afArrowsSync);\r\n'
                 '         this.addEventListener(Event.ENTER_FRAME,this.afArrowsSync);\r\n'
                 '      }\r\n')
assert OLD_INIT_TAIL in text, "init() moved - re-export and re-anchor"
text = text.replace(OLD_INIT_TAIL, NEW_INIT_TAIL, 1)

OLD_REMOVED = ('         IDEvent.removeListener(this);\r\n'
               '         super.eRemoved(param1);\r\n')
NEW_REMOVED = ('         IDEvent.removeListener(this);\r\n'
               '         this.removeEventListener(Event.ENTER_FRAME,this.afArrowsSync);\r\n'
               '         super.eRemoved(param1);\r\n')
assert OLD_REMOVED in text, "eRemoved() moved - re-export and re-anchor"
text = text.replace(OLD_REMOVED, NEW_REMOVED, 1)

ARROWS = '''      public function afArrowsSync(param1:Event = null) : void
      {
         var label:String;
         var size:int;
         var total:int;
         var pages:int;
         var clip:*;
         try
         {
            label = this.fanset.currentLabel;
         }
         catch(lblErr:*)
         {
            label = "";
         }
         try
         {
            size = 0;
            total = 0;
            if(label.indexOf("result") == 0)
            {
               size = 4;
               total = this.searchResult == null ? 0 : this.searchResult.length;
            }
            else if(label.indexOf("friend") == 0)
            {
               size = 8;
               total = this.myFriends == null ? 0 : this.myFriends.length;
            }
            pages = size > 0 ? int((total + size - 1) / size) : 1;
            clip = this.fanset["btnSFL"];
            if(clip != null)
            {
               clip.visible = size == 4 && this.page > 0;
            }
            clip = this.fanset["btnSFR"];
            if(clip != null)
            {
               clip.visible = size == 4 && this.page + 1 < pages;
            }
            clip = this.fanset["btnL"];
            if(clip != null)
            {
               clip.visible = size == 8 && this.page > 0;
            }
            clip = this.fanset["btnR"];
            if(clip != null)
            {
               clip.visible = size == 8 && this.page + 1 < pages;
            }
         }
         catch(arErr:*)
         {
         }
      }
      
      public function afHideEmptySlots() : void
'''
text = text.replace("      public function afHideEmptySlots() : void\r\n", ARROWS, 1)
report.append(("afArrowsSync() added", "afArrowsSync" in text))

# ── 5. the "request sent" confirmation (the client only SENDS requestBeFriend) ──
OLD_SEND = ('            RemoteService.requestBeFriend(this.selectIndex,this.fanset.msg.text);\r\n')
NEW_SEND = OLD_SEND + (
    '            try\r\n'
    '            {\r\n'
    '               if(Bridge.user.TextLanguage == 0)\r\n'
    '               {\r\n'
    '                  Bridge.utils.setEmbedFont(this.sysMesg.txtMesg,'
    '"Arial Rounded MT Bold",22,"Friend request sent - it is up to them to accept.");\r\n'
    '               }\r\n'
    '               else\r\n'
    '               {\r\n'
    '                  Bridge.utils.setEmbedFont(this.sysMesg.txtMesg,'
    '"華康儷特圓(P)",22,"朋友邀請已送出，等候對方確認。");\r\n'
    '               }\r\n'
    '            }\r\n'
    '            catch(reqErr:*)\r\n'
    '            {\r\n'
    '            }\r\n')
assert OLD_SEND in text, "the btnSend branch moved - re-export and re-anchor"
text = text.replace(OLD_SEND, NEW_SEND, 1)
report.append(("request-sent confirmation added", "Friend request sent" in text))

STAGE.parent.mkdir(parents=True, exist_ok=True)
with open(STAGE, "w", encoding="utf-8", newline="") as fh:
    fh.write(text)
report.append(("no Debug/diagnostic references left", "Debug" not in text))
report.append(("CRLF preserved", b"\r\n" in STAGE.read_bytes() and b"\n\n" not in
               STAGE.read_bytes().replace(b"\r\n", b"")))

for label, ok in report:
    print("  %-46s %s" % (label, "OK" if ok else "FAIL"))
bad = [l for l, ok in report if not ok]
print("%d lines before, %d after" % (original.count("\r\n"), text.count("\r\n")))
if bad:
    print("!! staging failed:", bad)
    sys.exit(1)
print("staged ->", STAGE)
