#!/usr/bin/env python3
"""Game 1: insert the auto-start into the form frame's SECOND action tag, and
prove the other frame-3 tag is untouched."""
import shutil, subprocess
from pathlib import Path

PKG = Path.home() / "Downloads" / "littleprince-patcher" / "games" / "1-Starwish-Legend" / "reg.swf"
FF = "/tmp/ffdec/ffdec.jar"
W = Path("/tmp/p2/g1fix"); shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)

def ffdec(*a):
    return subprocess.run(["java", "-jar", FF, *a], capture_output=True, text=True, timeout=600)

def export(swf, d):
    ffdec("-export", "script", str(d), str(swf))
    return d

# export the source-of-truth script
export(PKG, W / "before")
src_dir = W / "before" / "scripts" / "frame_3"
form = src_dir / "DoAction_2.as"
other = src_dir / "DoAction.as"
form_txt = form.read_text(encoding="utf-8")
other_before = other.read_text(encoding="utf-8")
assert "btn_activate.onRelease" in form_txt and form_txt.rstrip().endswith("stop();")
print("form script (DoAction_2) ends with:", form_txt.rstrip().splitlines()[-1])
print("other script (DoAction):", repr(other_before.strip()))

seed = ("\r\n// start the full version straight away - no button press needed\r\n"
        "if(_root.loadFullVersion)\r\n{\r\n   _root.loadFullVersion();\r\n}\r\n")
at = form_txt.rstrip().rfind("stop();")
form.write_text(form_txt.rstrip()[:at] + seed + form_txt.rstrip()[at:] + "\r\n", encoding="utf-8")

out = W / "reg-patched.swf"
r = ffdec("-replace", str(PKG), str(out), "/frame 3/DoAction_2", str(form))
print("replace rc:", r.returncode, "| out exists:", out.exists())
if not out.exists():
    # try the alternate spelling FFDec uses for the second tag
    r = ffdec("-replace", str(PKG), str(out), "/frame 3 (name: form)/DoAction_2", str(form))
    print("retry with frame name -> rc:", r.returncode, "| out exists:", out.exists())
    if not out.exists():
        print("STDOUT:", r.stdout[-600:]); print("STDERR:", r.stderr[-600:]); raise SystemExit(1)

export(out, W / "after")
a_form = (W / "after" / "scripts" / "frame_3" / "DoAction_2.as").read_text(encoding="utf-8")
a_other = (W / "after" / "scripts" / "frame_3" / "DoAction.as").read_text(encoding="utf-8")
print("\n--- after ---")
print("DoAction_2 has the seed      :", "loadFullVersion();" in a_form.split("btn_activate")[0])
print("DoAction_2 still has buttons :", "btn_activate.onRelease" in a_form)
print("DoAction unchanged           :", a_other == other_before)
print("script count same            :",
      len(list((W / "before").rglob("*.as"))), len(list((W / "after").rglob("*.as"))))
print("form script now ends with:")
print("   " + "\n   ".join(a_form.rstrip().splitlines()[-6:]))
if "loadFullVersion();" in a_form.split("btn_activate")[0] and a_other == other_before:
    shutil.copy(out, PKG)
    print("\nINSTALLED", PKG, PKG.stat().st_size, "bytes")
else:
    print("\nNOT installed - verification failed")
