#!/usr/bin/env python3
"""The overlay says it: ReferenceError #1069 in mpWireRetry, which is a property read that
does not exist on the object.  The verdict panel is back (reverting the title-frame
registration fixed the blank stage), so the only thing left is the wiring - which must not
assume the retry object is a MovieClip (currentFrame/typed coercion throw on anything else,
e.g. a SimpleButton).

Rewrite both helpers to be class-agnostic: untyped lookup, guarded property reads, report
the real class name on screen, and attach the click listener to whatever it is.
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
print("base: %d chars  mpDiag=%d mpWireRetry=%d" % (len(src), src.count("function mpDiag"),
                                                    src.count("function mpWireRetry")))


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
            var bp:* = this["btnRetry"];
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
            var rb:* = this["btnRetry"];
            if(rb == null)
            {
               rb = this["btnRetry" + Bridge.user.TextLanguage];
            }
            if(rb == null)
            {
               Debug.addLog("\\\\tmp_diag @ " + where + ": no retry clip at all");
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
SRC.write_text(src)
print("rewrote mpDiag + mpWireRetry as class-agnostic")

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print(r.stdout[-500:])
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer complained - NOT deploying")
    sys.exit(1)

out = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as").read_text()
print("dupes:", out.count("function mpDiag"), out.count("function mpWireRetry"), "(1 1)")
print("class-agnostic:", "getQualifiedClassName" in out, "| untyped lookup:",
      'var rb:* = this["btnRetry"]' in out)
