#!/usr/bin/env python3
"""Add a failure path to the multiplayer entry (PrinceOnline.flow.MultiplayFlow).

Why: the 多人連線模式 button does `Bridge.flow.connectServer(); gotoAndStop("connectserver")`,
and the ONLY thing that ever leaves that screen is the relay's `welcome` reply (SERVER_CONNECTED
-> connectGameLobby -> LOBBY_CONNECTED -> gotoAndStop("lobby")).  `eP2PStatus` had no branch for
NetEvent.SERVER_CONNECT_FAIL, which P2P dispatches on IOError/SecurityError and when the XMLSocket
cannot even be constructed - so any relay that is down, refused or unreachable leaves the player on
'connecting' for ever, with no message and no way on.  This adds:

  * a 10 s watchdog started with the connect attempt (covers a relay that answers nothing at all)
  * a SERVER_CONNECT_FAIL branch
  * one shared recovery: leave the connecting screen, then show the client's own
    `connecterror` alert (a string that already exists in settings.cxd, EN + ZH)
  * screen-first ordering on success, so a throw inside introMySelf() can no longer strand the
    player on the connecting screen (introMySelf is our own addition to that branch)

Only this one class is staged, so the import cannot touch anything else.
"""
import hashlib
import pathlib
import re
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()
JAR = HOME / "lpo_build/ffdec/ffdec-cli.jar"
PACK = HOME / "Downloads/littleprince-launcher"
SRC_LIB = PACK / "lpo/patches/lib/lib.swf"
WORK = HOME / "lpo_build/mpfix"
KEEP = HOME / "lpo_build/swf_backups"
CLASS = "PrinceOnline/flow/MultiplayFlow.as"

md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

shutil.rmtree(WORK, ignore_errors=True)
WORK.mkdir(parents=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                str(WORK / "base"), str(SRC_LIB)], capture_output=True, text=True)
src = WORK / "base/scripts" / CLASS
if not src.is_file():
    sys.exit("export failed: %s missing" % src)
s = src.read_text(encoding="utf-8", errors="replace")
nl = "\r\n" if "\r\n" in s else "\n"
print("exported %d chars, newline %r, fields=%d methods=%d"
      % (len(s), nl, s.count("private var"), s.count("function ")))

FIELDS = "      private var readDataMC:MovieClip;"
TIMER_FIELD = ("      public var mpConnectTimer:*;" + nl + nl + FIELDS)

CONNECT_OLD = (
    '         trace("<><>2");' + nl +
    '         this.p2p = new MultiPlayLobby({' + nl +
    '            "name":Bridge.user.name,' + nl +
    '            "cloth":Bridge.user.clothSetting2Array()' + nl +
    '         },Bridge.gameFile.substring(4,Bridge.gameFile.lastIndexOf(".")),"127.0.0.1");' + nl +
    '         trace("<><>3");' + nl +
    '         this.p2p.addEventListener(NetEvent.P2P_STATUS,this.eP2PStatus);' + nl +
    '         trace("<><>4");')
CONNECT_NEW = (
    '         trace("<><>2");' + nl +
    '         try' + nl +
    '         {' + nl +
    '            this.mpConnectTimer = new flash.utils.Timer(10000,1);' + nl +
    '            this.mpConnectTimer.addEventListener(flash.events.TimerEvent.TIMER_COMPLETE,this.mpConnectTimeout);' + nl +
    '            this.mpConnectTimer.start();' + nl +
    '         }' + nl +
    '         catch(afWatchErr:*)' + nl +
    '         {' + nl +
    '            Debug.addLog("multiplay: connect watchdog unavailable " + afWatchErr);' + nl +
    '         }' + nl +
    '         this.p2p = new MultiPlayLobby({' + nl +
    '            "name":Bridge.user.name,' + nl +
    '            "cloth":Bridge.user.clothSetting2Array()' + nl +
    '         },Bridge.gameFile.substring(4,Bridge.gameFile.lastIndexOf(".")),"127.0.0.1");' + nl +
    '         trace("<><>3");' + nl +
    '         this.p2p.addEventListener(NetEvent.P2P_STATUS,this.eP2PStatus);' + nl +
    '         trace("<><>4");')

SWITCH_OLD = ('         switch(param1.code)' + nl +
              '         {' + nl +
              '            case NetEvent.SERVER_CONNECTED:')
SWITCH_NEW = ('         switch(param1.code)' + nl +
              '         {' + nl +
              '            case NetEvent.SERVER_CONNECT_FAIL:' + nl +
              '               Debug.addLog("multiplay: the relay refused or dropped the connection");' + nl +
              '               this.mpConnectFailed("relay refused the connection");' + nl +
              '               break;' + nl +
              '            case NetEvent.SERVER_CONNECTED:')

LOBBY_OLD = ('            case NetEvent.LOBBY_CONNECTED:' + nl +
             '               trace("大廳連接成功");' + nl +
             '               this.p2p.introMySelf();' + nl +
             '               uiLayer.gotoAndStop("lobby");' + nl +
             '               break;')
LOBBY_NEW = ('            case NetEvent.LOBBY_CONNECTED:' + nl +
             '               trace("大廳連接成功");' + nl +
             '               try' + nl +
             '               {' + nl +
             '                  if(this.mpConnectTimer != null)' + nl +
             '                  {' + nl +
             '                     this.mpConnectTimer.stop();' + nl +
             '                     this.mpConnectTimer = null;' + nl +
             '                  }' + nl +
             '               }' + nl +
             '               catch(afWatchStopErr:*)' + nl +
             '               {' + nl +
             '                  Debug.addLog("multiplay: watchdog stop failed " + afWatchStopErr);' + nl +
             '               }' + nl +
             '               uiLayer.gotoAndStop("lobby");' + nl +
             '               try' + nl +
             '               {' + nl +
             '                  this.p2p.introMySelf();' + nl +
             '               }' + nl +
             '               catch(afIntroErr:*)' + nl +
             '               {' + nl +
             '                  Debug.addLog("multiplay: introMySelf failed " + afIntroErr);' + nl +
             '               }' + nl +
             '               break;')

METHODS_OLD = '      public function showFooterMultiRank() : void'
METHODS_NEW = '''      private function mpConnectTimeout(param1:flash.events.TimerEvent = null) : void
      {
         this.mpConnectFailed("no answer from the relay");
      }
      
      private function mpConnectFailed(reason:String) : void
      {
         var onConnecting:* = false;
         try
         {
            onConnecting = this.uiLayer != null && this.uiLayer.currentLabel == "connectserver";
         }
         catch(afLabelErr:*)
         {
            onConnecting = false;
         }
         try
         {
            Debug.addLog("multiplay: connect failed - " + reason + " (on connecting screen: " + onConnecting + ")");
         }
         catch(afLogErr:*)
         {
         }
         if(!onConnecting)
         {
            return;
         }
         try
         {
            if(this.mpConnectTimer != null)
            {
               this.mpConnectTimer.stop();
               this.mpConnectTimer = null;
            }
         }
         catch(afStopErr:*)
         {
         }
         try
         {
            if(Bridge.popup.isShow())
            {
               Bridge.popup.close();
            }
         }
         catch(afPopupErr:*)
         {
            Debug.addLog("multiplay: popup not closed " + afPopupErr);
         }
         try
         {
            var ui:* = this.uiLayer;
            ui.stopTimer();
         }
         catch(afUiTimerErr:*)
         {
         }
         try
         {
            this.returnGameSelectLevel();
         }
         catch(afReturnErr:*)
         {
            Debug.addLog("multiplay: could not leave the connecting screen " + afReturnErr);
         }
         try
         {
            if(this.p2p != null)
            {
               this.p2p.iLeaveLobby();
            }
         }
         catch(afLeaveErr:*)
         {
         }
         try
         {
            Bridge.popup.show("MSGalert",[this.mpConnectAck],Strings.value("connecterror" + Bridge.user.TextLanguage),Bridge.user.TextLanguage);
         }
         catch(afShowErr:*)
         {
            Debug.addLog("multiplay: connect alert could not be shown " + afShowErr);
         }
      }
      
      public function mpConnectAck() : void
      {
         try
         {
            Debug.addLog("multiplay: connect alert acknowledged");
         }
         catch(afAckErr:*)
         {
         }
      }
      
''' + METHODS_OLD
METHODS_NEW = METHODS_NEW.replace("\n", nl)

for name, old, new in (("timer field", FIELDS, TIMER_FIELD),
                       ("connectServer watchdog", CONNECT_OLD, CONNECT_NEW),
                       ("SERVER_CONNECT_FAIL case", SWITCH_OLD, SWITCH_NEW),
                       ("LOBBY_CONNECTED ordering", LOBBY_OLD, LOBBY_NEW),
                       ("recovery methods", METHODS_OLD, METHODS_NEW)):
    n = s.count(old)
    if n != 1:
        sys.exit("anchor %r matched %d times (must be 1)" % (name, n))
    s = s.replace(old, new)

out = WORK / "stage/scripts" / CLASS
out.parent.mkdir(parents=True)
out.write_text(s, encoding="utf-8")
print("staged %s (%d chars)" % (out, len(s)))

new_lib = WORK / "lib_mpfix.swf"
r = subprocess.run(["java", "-jar", str(JAR), "-importScript", str(SRC_LIB), str(new_lib),
                    str(WORK / "stage")], capture_output=True, text=True)
bad = [l for l in (r.stdout + r.stderr).splitlines()
       if "SEVERE" in l or "expected but" in l or "xception" in l]
print("import rc=%s  errors=%s" % (r.returncode, bad or "none"))
if bad or not new_lib.is_file():
    sys.exit("import failed - nothing written")
print("md5  %s -> %s" % (md5(SRC_LIB), md5(new_lib)))
if md5(SRC_LIB) == md5(new_lib):
    sys.exit("output is byte-identical to the input - the class did not compile")

# re-read the produced SWF and diff its script tree against the unpatched export
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                str(WORK / "out"), str(new_lib)], capture_output=True, text=True)
d = subprocess.run(["diff", "-rq", str(WORK / "base/scripts"), str(WORK / "out/scripts")],
                   capture_output=True, text=True)
print("=== changed classes (must be exactly this one) ===")
print(d.stdout.strip() or "(none!)")
again = (WORK / "out/scripts" / CLASS).read_text(encoding="utf-8", errors="replace")
for probe, label in (("function mpConnectFailed", "mpConnectFailed defined"),
                     ("function mpConnectTimeout", "mpConnectTimeout defined"),
                     ("function mpConnectAck", "mpConnectAck defined"),
                     ("SERVER_CONNECT_FAIL:", "fail branch present"),
                     ("Timer(10000", "watchdog armed"),
                     ("this.p2p.introMySelf();", "introMySelf kept")):
    print("   %-28s %s" % (label, probe in again))
print("   duplicate helpers:", again.count("function mpConnectFailed"),
      again.count("function mpConnectTimeout"), again.count("function mpConnectAck"),
      "(each must be 1)")
print("   duplicate definitions anywhere:",
      [p for p in ("introMySelf()", "connectServer()", "eP2PStatus(")
       if len(re.findall(r"function %s" % re.escape(p), again)) != 1])
