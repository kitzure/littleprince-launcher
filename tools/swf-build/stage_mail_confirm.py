#!/usr/bin/env python3
"""Mail panel: make the friend-request letter's 確認朋友 (btnAddF) actually click.

The read-mail screen's confirm button lives in `PrinceOnline.home.Mail` (code in
lib.swf) and its art in `mail.swf` (sprite 149 -> class Mail, mailSet 109 holds
btnAddF 87, a 3-frame sprite labelled lan0/lan1 with no _up/_over/_down labels).

What is wrong with the publisher's handler (updateView, section == "reading"):

  * `mcBtnManager.addMCButton(this.mailSet.btnAddF);` - the publisher's truncated
    registration the other panels already had to fix.  It is wrapped here in a
    try/catch so a failure there can never abort the rest of updateView (which is
    what "the panel stops dead half way" looks like).
  * btnAddF carries only the language labels, so mcBtnManager's `if(!_up) _up=1`
    decides the button's state frame for it; the publisher's own code then does
    gotoAndStop("lan"+lang).  Pin _up/_over/_down/_hit to the language frame after
    registering, so the manager's frame bookkeeping and the drawn button agree
    (that is the "register, then pin to _up" rule).
  * the click path is the manager's stage MOUSE_UP -> onRelease only.  Give the
    button its own MouseEvent.CLICK listener as a second, independent path.  Both
    funnel through one guarded action (afConfirmFriendLetter), so the two paths
    cannot double-fire, and the action is idempotent on the server anyway.
  * raise the button above its mailSet siblings (btnGetItem/msg/scrollbar/select
    sit at higher depths) so a higher sibling cannot swallow the click.

Only PrinceOnline/home/Mail.as is staged; the import must change that class alone.
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()
JAR = HOME / "lpo_build/ffdec/ffdec-cli.jar"
L = HOME / "Downloads/littleprince-launcher"
md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

DEP = L / "lpo/patches/lib/lib.swf"
REL = "PrinceOnline/home/Mail.as"
WORK = pathlib.Path("/home/yoke/lpo_build/work/mail_patch")
EXPORT = WORK / "export"
ONECLASS = WORK / "oneclass"

shutil.rmtree(WORK, ignore_errors=True)
EXPORT.mkdir(parents=True)
r = subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                    str(EXPORT), str(DEP)], capture_output=True, text=True)
if r.returncode != 0:
    print("!! export failed:", r.stdout[-400:], r.stderr[-400:]); sys.exit(1)
SRC = EXPORT / "scripts" / REL
text = open(SRC, encoding="utf-8", newline="").read()
original = text
print("Mail.as %d chars, CRLF %s" % (len(text), "\r\n" in text))

report = []


def sub(old, new, label):
    global text
    n = text.count(old)
    if n != 1:
        print("!! %s: expected 1 anchor, found %d" % (label, n)); sys.exit(1)
    text = text.replace(old, new, 1)
    report.append(label)


# ── 1. the guard field ────────────────────────────────────────────────────────
sub("      private var checkInMailAgain:Boolean = false;\r\n",
    "      private var checkInMailAgain:Boolean = false;\r\n"
    "      \r\n"
    "      private var afConfirmBusy:Boolean = false;\r\n",
    "afConfirmBusy field added")

# ── 2. the registration: full args, pinned state frames, own click listener ───
sub("            if(this.mailSet.btnAddF)\r\n"
    "            {\r\n"
    "               mcBtnManager.addMCButton(this.mailSet.btnAddF);\r\n"
    "            }\r\n",
    "            if(this.mailSet.btnAddF)\r\n"
    "            {\r\n"
    "               try\r\n"
    "               {\r\n"
    "                  var afBtn:MovieClip = this.mailSet.btnAddF;\r\n"
    "                  mcBtnManager.addMCButton(afBtn,\"SFX_drag\",null,\"SFX_drop\");\r\n"
    "                  var afUpFrame:* = afBtn[\"lan\" + Bridge.user.TextLanguage];\r\n"
    "                  if(afUpFrame == null)\r\n"
    "                  {\r\n"
    "                     afUpFrame = 1;\r\n"
    "                  }\r\n"
    "                  afBtn[\"_up\"] = afUpFrame;\r\n"
    "                  afBtn[\"_over\"] = afUpFrame;\r\n"
    "                  afBtn[\"_down\"] = afUpFrame;\r\n"
    "                  afBtn[\"_hit\"] = afUpFrame;\r\n"
    "                  afBtn.gotoAndStop(afUpFrame);\r\n"
    "                  afBtn.buttonMode = true;\r\n"
    "                  afBtn.mouseEnabled = true;\r\n"
    "                  afBtn.addEventListener(MouseEvent.CLICK,this.afConfirmClick);\r\n"
    "                  this.mailSet.setChildIndex(afBtn,this.mailSet.numChildren - 1);\r\n"
    "               }\r\n"
    "               catch(afBtnErr:*)\r\n"
    "               {\r\n"
    "               }\r\n"
    "            }\r\n",
    "btnAddF registered with full args + pinned + CLICK listener")

# ── 3. one action, used by both click paths ───────────────────────────────────
sub("      private function eMotionFinish(param1:*) : void\r\n",
    "      private function afConfirmFriendLetter() : void\r\n"
    "      {\r\n"
    "         if(this.afConfirmBusy)\r\n"
    "         {\r\n"
    "            return;\r\n"
    "         }\r\n"
    "         this.afConfirmBusy = true;\r\n"
    "         trace(\"mail: confirmBeFriend uid=\" + this.mails[this.page].user.uid);\r\n"
    "         try\r\n"
    "         {\r\n"
    "            this.RemoteService.confirmBeFriend(this.mails[this.page].user.uid);\r\n"
    "         }\r\n"
    "         catch(afSendErr:*)\r\n"
    "         {\r\n"
    "            trace(\"mail: confirmBeFriend threw \" + afSendErr);\r\n"
    "         }\r\n"
    "         this.mailSet.play();\r\n"
    "         this.section = this.endTo = \"read\";\r\n"
    "         this.checkInMailAgain = true;\r\n"
    "      }\r\n"
    "      \r\n"
    "      private function afConfirmClick(param1:MouseEvent) : void\r\n"
    "      {\r\n"
    "         this.afConfirmFriendLetter();\r\n"
    "      }\r\n"
    "      \r\n"
    "      private function eMotionFinish(param1:*) : void\r\n",
    "afConfirmFriendLetter + afConfirmClick added")

# ── 4. the manager path routes through the same action ────────────────────────
sub("         else if(param1.name == \"btnAddF\")\r\n"
    "         {\r\n"
    "            this.RemoteService.confirmBeFriend(this.mails[this.page].user.uid);\r\n"
    "            this.mailSet.play();\r\n"
    "            this.section = this.endTo = \"read\";\r\n"
    "            this.checkInMailAgain = true;\r\n"
    "         }\r\n",
    "         else if(param1.name == \"btnAddF\")\r\n"
    "         {\r\n"
    "            this.afConfirmFriendLetter();\r\n"
    "         }\r\n",
    "eBtnOnRelease btnAddF branch -> afConfirmFriendLetter")

# ── 5. opening a letter re-arms the guard ─────────────────────────────────────
sub("      private function initReadMail() : void\r\n"
    "      {\r\n"
    "         this.pageSize = 1;\r\n",
    "      private function initReadMail() : void\r\n"
    "      {\r\n"
    "         this.afConfirmBusy = false;\r\n"
    "         this.pageSize = 1;\r\n",
    "initReadMail re-arms afConfirmBusy")
sub("      private function initShowMails() : void\r\n"
    "      {\r\n"
    "         this.page = 0;\r\n",
    "      private function initShowMails() : void\r\n"
    "      {\r\n"
    "         this.afConfirmBusy = false;\r\n"
    "         this.page = 0;\r\n",
    "initShowMails re-arms afConfirmBusy")

# ── the staged tree holds THIS class only ─────────────────────────────────────
dst = ONECLASS / "scripts" / REL
dst.parent.mkdir(parents=True, exist_ok=True)
with open(dst, "w", encoding="utf-8", newline="") as fh:
    fh.write(text)

checks = [
    ("one definition of afConfirmFriendLetter", text.count("function afConfirmFriendLetter") == 1),
    ("one definition of afConfirmClick", text.count("function afConfirmClick") == 1),
    ("one CLICK listener", text.count("addEventListener(MouseEvent.CLICK,this.afConfirmClick)") == 1),
    ("no truncated addMCButton for btnAddF",
     "addMCButton(this.mailSet.btnAddF)" not in text),
    ("manager branch routes through the action",
     "else if(param1.name == \"btnAddF\")\r\n         {\r\n            this.afConfirmFriendLetter();" in text),
    ("both paths guarded", text.count("afConfirmBusy") == 5),
    ("CRLF preserved", b"\r\n" in dst.read_bytes()
     and b"\n\n" not in dst.read_bytes().replace(b"\r\n", b"")),
    ("no stray Debug overlay", "SOL.Debug" not in text),
]
for label, ok in checks:
    print("   %-46s %s" % (label, "OK" if ok else "FAIL"))
if not all(ok for _, ok in checks):
    print("!! staging failed"); sys.exit(1)

# ── import the one class ──────────────────────────────────────────────────────
OUT = WORK / "lib_patched.swf"
r = subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-importScript",
                    str(DEP), str(OUT), str(ONECLASS)],
                   capture_output=True, text=True, cwd=str(WORK))
print("import rc:", r.returncode)
if "SEVERE" in r.stdout + r.stderr or "expected but" in r.stdout + r.stderr:
    print("!! importer complained:"); print((r.stdout + r.stderr)[-500:]); sys.exit(1)
print("new SWF: %d bytes  md5 %s" % (OUT.stat().st_size, md5(OUT)))
print("old SWF: %d bytes  md5 %s" % (DEP.stat().st_size, md5(DEP)))

# ── prove ONLY Mail.as changed (full re-export, both SWFs) ────────────────────
def export_all(swf, outdir):
    shutil.rmtree(outdir, ignore_errors=True)
    subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                    str(outdir), str(swf)], capture_output=True, text=True)
    return outdir / "scripts"


e_old = export_all(DEP, WORK / "re_old")
e_new = export_all(OUT, WORK / "re_new")
files = sorted({p.relative_to(root).as_posix()
                for root in (e_old, e_new) for p in root.rglob("*") if p.is_file()})
differ = []
for rel in files:
    a, b = e_old / rel, e_new / rel
    if not a.is_file() or not b.is_file():
        differ.append(rel + " (only one side)")
    elif a.read_bytes() != b.read_bytes():
        differ.append(rel)
print("scripts old/new: %d/%d" % (len(list(e_old.rglob('*.as'))), len(list(e_new.rglob('*.as')))))
print("classes that differ:", differ)
if differ != [REL]:
    print("!! expected exactly [%s]" % REL); sys.exit(1)

new_mail = (e_new / REL).read_text(encoding="utf-8")
for label, ok in (("patched Mail re-exports with the action", "afConfirmFriendLetter" in new_mail),
                  ("re-export still has one eMotionFinish",
                   new_mail.count("function eMotionFinish") == 1),
                  ("re-export has no duplicated methods",
                   all(new_mail.count("function " + m + "(") == 1 for m in
                       ("updateView", "eBtnOnRelease", "initReadMail", "initShowMails", "edit")))):
    print("   %-46s %s" % (label, "OK" if ok else "FAIL"))
    if not ok:
        print("!! verify failed"); sys.exit(1)

print("\nSTAGED OK ->", OUT)
