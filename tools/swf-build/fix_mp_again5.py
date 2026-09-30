#!/usr/bin/env python3
"""Replace the AS2-style onRelease with a real AS3 CLICK listener.

`MovieClip.onRelease` is an AS2 idiom: assigning it in an AS3 movie silently creates a
dynamic property and no handler, which is exactly "the button keeps animating and nothing
happens".  MouseEvent.CLICK is dispatched by Flash when a press and a release land on the
same interactive object, independently of MCBtnManager's target test.
"""
import pathlib
import re
import subprocess
import sys

HOME = pathlib.Path.home()
SRC = pathlib.Path("/tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as")
src = SRC.read_text()

m = re.search(r'( *)var self:\* = this;\s*\n\s*retryBtn\.onRelease = function\(\) : void\s*\n\s*\{\s*\n'
              r'\s*self\.mpPlayAgain\("clip"\);\s*\n\s*\};', src)
if not m:
    print("!! the onRelease block was not found; showing what is there")
    i = src.find("mpPlayAgain(\"clip\")")
    print(src[max(0, i - 700):i + 200] if i > 0 else "(no mpPlayAgain(\"clip\") either)")
    sys.exit(1)

indent = m.group(1)
print("=== replacing (%d chars) ===" % len(m.group(0)))
print(m.group(0))

NEW = (indent + "// A real AS3 listener: an assigned onRelease is an AS2 idiom and does\n"
       + indent + "// nothing in an AS3 movie - which is why the button animated and never\n"
       + indent + "// acted.  CLICK fires when the press and release land on this clip.\n"
       + indent + "var self:* = this;\n"
       + indent + "retryBtn.addEventListener(flash.events.MouseEvent.CLICK,"
       + "function(param1:flash.events.MouseEvent) : void\n"
       + indent + "{\n"
       + indent + "   self.mpPlayAgain(\"clip\");\n"
       + indent + "});")
src = src.replace(m.group(0), NEW, 1)
SRC.write_text(src)
print("\npatched with a flash.events.MouseEvent.CLICK listener")

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print(r.stdout[-900:])
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer complained - NOT deploying this")
    sys.exit(1)
