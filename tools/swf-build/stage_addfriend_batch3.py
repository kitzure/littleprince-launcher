#!/usr/bin/env python3
"""Stage the ONE class this round patches: PrinceOnline/castle/AddFriend.as.

1) The 共同朋友 badge (fanset.sr<i>.btnCF<lang>) free-runs: the art (sprites 153/127)
   is a 10-frame button with _up/_over/_down labels and NO stop() anywhere, and it is
   registered with nothing, so its timeline loops up->over->down->up forever (the
   "pop-in animation" the user sees).  Register it with mcBtnManager, which pins it
   with gotoAndStop(_up) and uses gotoAndStop on hover too (setMotion -> gotoAndStop
   because there is no _over_end label), i.e. a static button that pops on hover.

2) After the friend request is sent, hide the result rows: btnSend -> play() lands on
   result_edit, whose frame script calls showSearchResult() and re-shows sr0..sr3 over
   the confirmation text.  A flag set on a successful send makes resultEdit keep them
   hidden.
"""
import pathlib
import sys

BASE = pathlib.Path("/home/yoke/lpo_build/cur_export/scripts/PrinceOnline/castle/AddFriend.as")
STAGE_ROOT = pathlib.Path("/home/yoke/lpo_build/stage3")
STAGE = STAGE_ROOT / "scripts/PrinceOnline/castle/AddFriend.as"

text = open(BASE, encoding="utf-8", newline="").read()
original = text
report = []


def sub(old, new, label, count=1):
    global text
    n = text.count(old)
    assert n == count, "%s: expected %d occurrence(s), found %d - re-anchor" % (label, count, n)
    text = text.replace(old, new, 1)
    report.append((label, True))


# ── 1. the flag field ──────────────────────────────────────────────────────────
sub(
    "      private var searchData:Object;\r\n",
    "      private var searchData:Object;\r\n"
    "      \r\n"
    "      private var afCardHidden:Boolean;\r\n",
    "afCardHidden field added")

# ── 2. reset the flag wherever a fresh search starts ───────────────────────────
sub(
    "      private function initResult() : void\r\n"
    "      {\r\n"
    "         this.page = 0;\r\n"
    "         this.pageSize = 4;\r\n",
    "      private function initResult() : void\r\n"
    "      {\r\n"
    "         this.page = 0;\r\n"
    "         this.pageSize = 4;\r\n"
    "         this.afCardHidden = false;\r\n",
    "initResult resets afCardHidden")

sub(
    "      private function findEdit() : void\r\n"
    "      {\r\n"
    "         this.fanset.stop();\r\n",
    "      private function findEdit() : void\r\n"
    "      {\r\n"
    "         this.fanset.stop();\r\n"
    "         this.afCardHidden = false;\r\n",
    "findEdit resets afCardHidden")

# ── 3. the hide helper, inserted before afArrowsSync ───────────────────────────
HELPER = (
    "      public function afHideResultCards() : void\r\n"
    "      {\r\n"
    "         var i:int;\r\n"
    "         var slot:*;\r\n"
    "         try\r\n"
    "         {\r\n"
    "            i = 0;\r\n"
    "            while(i < 8)\r\n"
    "            {\r\n"
    "               slot = this.fanset[\"sr\" + i];\r\n"
    "               if(slot != null)\r\n"
    "               {\r\n"
    "                  slot.visible = false;\r\n"
    "               }\r\n"
    "               i++;\r\n"
    "            }\r\n"
    "         }\r\n"
    "         catch(hcErr:*)\r\n"
    "         {\r\n"
    "         }\r\n"
    "      }\r\n"
    "      \r\n")
sub("      public function afArrowsSync(param1:Event = null) : void\r\n",
    HELPER + "      public function afArrowsSync(param1:Event = null) : void\r\n",
    "afHideResultCards() added")

# ── 4. resultEdit must not re-show the rows once a request went out ────────────
sub(
    "      private function resultEdit() : void\r\n"
    "      {\r\n"
    "         this.fanset.btnFindFriend.gotoAndPlay(\"enter\");\r\n"
    "         this.fanset.btnFindFriend.visible = false;\r\n"
    "         this.showSearchResult();\r\n"
    "         this.fanset.stop();\r\n"
    "      }\r\n",
    "      private function resultEdit() : void\r\n"
    "      {\r\n"
    "         this.fanset.btnFindFriend.gotoAndPlay(\"enter\");\r\n"
    "         this.fanset.btnFindFriend.visible = false;\r\n"
    "         this.showSearchResult();\r\n"
    "         if(this.afCardHidden)\r\n"
    "         {\r\n"
    "            this.afHideResultCards();\r\n"
    "         }\r\n"
    "         this.fanset.stop();\r\n"
    "      }\r\n",
    "resultEdit honours afCardHidden")

# ── 5. showSearchResult: register + pin the 共同朋友 badge per row ─────────────
sub(
    "               catch(cfErr:*)\r\n"
    "               {\r\n"
    "               }\r\n"
    "            }\r\n"
    "            else\r\n",
    "               catch(cfErr:*)\r\n"
    "               {\r\n"
    "               }\r\n"
    "               try\r\n"
    "               {\r\n"
    "                  _loc6_ = _loc3_[\"btnCF\" + Bridge.user.TextLanguage];\r\n"
    "                  if(_loc6_ != null)\r\n"
    "                  {\r\n"
    "                     this.mcBtnManager.addMCButton(_loc6_,\"SFX_drag\",null,\"SFX_drop\");\r\n"
    "                     _loc6_.gotoAndStop(\"_up\");\r\n"
    "                  }\r\n"
    "               }\r\n"
    "               catch(cfBtnErr:*)\r\n"
    "               {\r\n"
    "               }\r\n"
    "            }\r\n"
    "            else\r\n",
    "共同朋友 badge registered + pinned to _up")

# ── 6. btnAddF: the card goes as soon as add is pressed ────────────────────────
sub(
    "         else if(param1.name == \"btnAddF\")\r\n"
    "         {\r\n"
    "            this.selectIndex = this.searchResult[this.page * this.pageSize + int(param1.parent.name.substr(2))].user.uid;\r\n"
    "            this.fanset.play();\r\n"
    "         }\r\n",
    "         else if(param1.name == \"btnAddF\")\r\n"
    "         {\r\n"
    "            this.selectIndex = this.searchResult[this.page * this.pageSize + int(param1.parent.name.substr(2))].user.uid;\r\n"
    "            this.afHideResultCards();\r\n"
    "            this.fanset.play();\r\n"
    "         }\r\n",
    "btnAddF hides the result card")

# ── 7. btnSend: keep the card hidden behind the confirmation ───────────────────
sub(
    "               else\r\n"
    "               {\r\n"
    "                  Bridge.utils.setEmbedFont(this.sysMesg.txtMesg,\"華康儷特圓(P)\",22,\"朋友邀請已送出，等候對方確認。\");\r\n"
    "               }\r\n"
    "            }\r\n"
    "            catch(reqErr:*)\r\n",
    "               else\r\n"
    "               {\r\n"
    "                  Bridge.utils.setEmbedFont(this.sysMesg.txtMesg,\"華康儷特圓(P)\",22,\"朋友邀請已送出，等候對方確認。\");\r\n"
    "               }\r\n"
    "               this.afCardHidden = true;\r\n"
    "               this.afHideResultCards();\r\n"
    "            }\r\n"
    "            catch(reqErr:*)\r\n",
    "btnSend hides the result card for good")

# ── 8. the badge's click branch becomes reachable again: a null flist must not throw ──
sub(
    "            this.sameFriends = this.searchResult[this.page * this.pageSize + this.selectIndex].flist;\r\n",
    "            this.sameFriends = this.searchResult[this.page * this.pageSize + this.selectIndex].flist == null ? [] : this.searchResult[this.page * this.pageSize + this.selectIndex].flist;\r\n",
    "btnCF branch tolerates a null flist")

# ── checks ─────────────────────────────────────────────────────────────────────
for name in ("afHideResultCards", "afCardHidden"):
    report.append(("%s appears exactly once per function/field" % name,
                   text.count("function afHideResultCards") == 1))
assert text.count("function afHideResultCards") == 1
assert text.count("afCardHidden") == 5, text.count("afCardHidden")
assert "afDiag" not in text and "Debug" not in text, "diagnostics must not return"
assert "addMCButton(_loc6_" in text

STAGE.parent.mkdir(parents=True, exist_ok=True)
with open(STAGE, "w", encoding="utf-8", newline="") as fh:
    fh.write(text)

report.append(("CRLF only", b"\r\n" in STAGE.read_bytes()
               and b"\n\n" not in STAGE.read_bytes().replace(b"\r\n", b"")))
for label, ok in report:
    print("  %-52s %s" % (label, "OK" if ok else "FAIL"))
print("%d lines before, %d after" % (original.count("\r\n"), text.count("\r\n")))
bad = [l for l, ok in report if not ok]
if bad:
    print("!! staging failed:", bad)
    sys.exit(1)
print("staged ->", STAGE)
