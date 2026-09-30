#!/usr/bin/env python3
"""Install the verified game-1 build, then patch game 3 (exact script path this
time) and verify both."""
import shutil, subprocess
from pathlib import Path

PKG = Path.home() / "Downloads" / "littleprince-patcher"
FF = "/tmp/ffdec/ffdec.jar"
W = Path("/tmp/p2/g1fix")

def ffdec(*a):
    return subprocess.run(["java", "-jar", FF, *a], capture_output=True, text=True, timeout=700)

def export(swf, d):
    ffdec("-export", "script", str(d), str(swf)); return d

# ── game 1: validate the build produced last run, then install ───────────────
out, after, before = W / "reg-patched.swf", W / "after", W / "before"
a_form = (after / "scripts" / "frame_3" / "DoAction_2.as").read_text(encoding="utf-8")
a_other = (after / "scripts" / "frame_3" / "DoAction.as").read_text(encoding="utf-8")
b_other = (before / "scripts" / "frame_3" / "DoAction.as").read_text(encoding="utf-8")
ok1 = ("if(_root.loadFullVersion)" in a_form and a_form.rstrip().splitlines()[-1] == "stop();"
       and a_form.index("if(_root.loadFullVersion)") < a_form.rindex("stop();")
       and "btn_activate.onRelease" in a_form and a_other == b_other
       and len(list(after.rglob("*.as"))) == len(list(before.rglob("*.as"))))
print("game 1 checks:", "PASS" if ok1 else "FAIL")
if ok1:
    shutil.copy(out, PKG / "games" / "1-Starwish-Legend" / "reg.swf")
    print("game 1 INSTALLED ->",
          (PKG / "games" / "1-Starwish-Legend" / "reg.swf").stat().st_size, "bytes")

# ── game 3: seed the activation record in the ROOT frame 1 ───────────────────
g3 = PKG / "games" / "3-Prince-Adventure" / "reg.swf"
W3 = Path("/tmp/p2/g3fix"); shutil.rmtree(W3, ignore_errors=True); W3.mkdir(parents=True)
export(g3, W3 / "before")
f1 = W3 / "before" / "scripts" / "frame_1" / "DoAction.as"
txt = f1.read_text(encoding="utf-8")
tail = txt.rstrip()
assert tail.endswith("}") and "activationSuccess" in tail, "unexpected frame 1"
block = ("\r\nif(_level0)\r\n{\r\n"
         "   _level0.activationSuccess = function(sn, hdkey, akey)\r\n   {\r\n      return true;\r\n   };\r\n"
         "   if(_level0.saveActivation)\r\n   {\r\n"
         '      _level0.saveActivation("Player","12345678","a@b.com",'
         '"P3-AAAA-BBBB-CCCC-DDDD",_level0.getHDKey(),"12345678");\r\n'
         "   }\r\n}\r\n")
# drop the existing (shorter) seed block, then append the extended one
start = tail.rindex("if(_level0)")
f1.write_text(tail[:start] + block.lstrip("\r\n"), encoding="utf-8")
out3 = W3 / "reg-patched.swf"
r = ffdec("-replace", str(g3), str(out3), "/frame 1/DoAction", str(f1))
print("\ngame 3 replace rc:", r.returncode, "| out exists:", out3.exists())
if not out3.exists():
    print(r.stdout[-500:], r.stderr[-500:]); raise SystemExit(1)

export(out3, W3 / "after")
a1 = (W3 / "after" / "scripts" / "frame_1" / "DoAction.as").read_text(encoding="utf-8")
ok3 = ("saveActivation" in a1 and "activationSuccess" in a1
       and len(list((W3 / "after").rglob("*.as"))) == len(list((W3 / "before").rglob("*.as"))))
print("game 3 checks:", "PASS" if ok3 else "FAIL")
print("frame 1 now ends with:")
print("   " + "\n   ".join(a1.rstrip().splitlines()[-12:]))
if ok3:
    shutil.copy(out3, g3)
    print("game 3 INSTALLED ->", g3.stat().st_size, "bytes")
else:
    print("game 3 NOT installed")
