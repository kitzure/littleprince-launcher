#!/usr/bin/env python3
"""The lookup was the bug, not the object.

`\tmp_diag wire FAILED: Error #1069` with no "wiring ... as ..." line means the failure is in
`this["btnRetry"]` itself: reading an unknown property by name off a NON-dynamic object
throws #1069.  So the frame instance is not dynamic, bracket lookup can never work there -
and that is exactly why the publisher's own `this["btnRetry"+lang]` never registered the
button either.  Use the Container API: getChildByName, plus a recursive search in case the
clip is nested rather than a direct child.
"""
import pathlib
import re
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()
JAR = HOME / "lpo_build/ffdec/ffdec-cli.jar"
DEP = HOME / "Downloads/littleprince-launcher/lpo/patches/lib/lib.swf"
SRC = pathlib.Path("/tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as")

shutil.rmtree("/tmp/lpo_re", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_re", str(DEP)], capture_output=True, text=True)
shutil.copy2(pathlib.Path("/tmp/lpo_re/scripts/PrinceOnline/UI_multiplay.as"), SRC)
src = SRC.read_text()


def replace_method(text, name, new_body):
    m = re.search(r"( *)public function %s\([^)]*\) : void" % name, text)
    if not m:
        raise SystemExit("!! %s not found" % name)
    start = text.index("{", m.end())
    depth, i = 0, start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return text[:m.start()] + new_body + text[i + 1:]


FIND = '''public function mpFind(name:String) : *
      {
         var direct:* = null;
         try
         {
            direct = this.getChildByName(name);
         }
         catch(e0:*)
         {
         }
         if(direct != null)
         {
            return direct;
         }
         return this.mpFindDeep(this,name);
      }
      
      public function mpFindDeep(node:*, name:String) : *
      {
         var i:int = 0;
         while(i < node.numChildren)
         {
            var ch:* = node.getChildAt(i);
            var nm:String = null;
            try
            {
               nm = ch.name;
            }
            catch(e1:*)
            {
            }
            if(nm == name)
            {
               return ch;
            }
            if(ch is flash.display.DisplayObjectContainer)
            {
               var found:* = this.mpFindDeep(ch,name);
               if(found != null)
               {
                  return found;
               }
            }
            i++;
         }
         return null;
      }'''

NEW_DIAG = '''public function mpDiag(where:String) : void
      {
         try
         {
            if(Debug.tf_debug == null)
            {
               var holder:flash.display.Sprite = new flash.display.Sprite();
               this.addChild(holder);
               Debug.init(holder,560,220);
            }
            Debug.enable();
            var bp:* = this.mpFind("btnRetry");
            var kind:String = "none";
            if(bp != null)
            {
               try
               {
                  kind = flash.utils.getQualifiedClassName(bp);
               }
               catch(ce:*)
               {
                  kind = "?";
               }
            }
            Debug.addLog("\\\\tmp_diag @ " + where + " frame=" + this.currentLabel + " btnRetry=" + kind);
         }
         catch(diagErr:*)
         {
         }
      }'''

NEW_WIRE = '''public function mpWireRetry(where:String) : void
      {
         try
         {
            var rb:* = this.mpFind("btnRetry");
            if(rb == null)
            {
               rb = this.mpFind("btnRetry" + Bridge.user.TextLanguage);
            }
            if(rb == null)
            {
               Debug.addLog("\\\\tmp_diag @ " + where + ": no retry clip found on this frame");
               return;
            }
            var kind:String = "?";
            var nm:String = "?";
            try
            {
               kind = flash.utils.getQualifiedClassName(rb);
               nm = String(rb.name);
               rb.visible = true;
            }
            catch(pe:*)
            {
               Debug.addLog("\\\\tmp_diag @ " + where + ": property error " + pe);
            }
            Debug.addLog("\\\\tmp_diag @ " + where + ": wiring " + nm + " as " + kind);
            var self:* = this;
            rb.addEventListener(flash.events.MouseEvent.CLICK,function(param1:flash.events.MouseEvent) : void
            {
               Debug.addLog("\\\\tmp_diag: CLICK arrived on " + nm);
               self.mpPlayAgain("clip");
            });
            Debug.addLog("\\\\tmp_diag: listener attached");
         }
         catch(wireErr:*)
         {
            Debug.addLog("\\\\tmp_diag wire FAILED: " + wireErr);
         }
      }'''

src = replace_method(src, "mpDiag", NEW_DIAG)
src = replace_method(src, "mpWireRetry", NEW_WIRE)
m = re.search(r"public function mpPlayAgain\(", src)
anchor = src.rindex("\n", 0, m.start()) + 1
src = src[:anchor] + "      " + FIND + "\n      \n" + src[anchor:]
SRC.write_text(src)
print("lookup switched to getChildByName + recursive search")

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
tail = [l for l in r.stdout.splitlines() if l.strip().startswith(("new", "base", "deployed"))]
print("\n".join(tail))
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer complained - NOT deploying")
    print(r.stdout[-400:])
    sys.exit(1)

out = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as").read_text()
print("dupes: mpDiag=%d mpWireRetry=%d mpFind=%d mpFindDeep=%d (all must be 1)" % (
    out.count("function mpDiag"), out.count("function mpWireRetry"),
    out.count("function mpFind("), out.count("function mpFindDeep")))
print("no bracket lookup of the button left:", 'this["btnRetry"]' not in out)
