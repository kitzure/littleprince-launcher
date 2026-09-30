#!/usr/bin/env python3
"""Same as patch_instant.py, with the reporting bugs fixed."""
import subprocess, shutil
from pathlib import Path

PKG = Path.home() / "Downloads" / "littleprince-patcher"
FFDEC = "/tmp/ffdec/ffdec.jar"
WORK = Path("/tmp/p2/auto")

def ffdec(*args, timeout=600):
    return subprocess.run(["java", "-jar", FFDEC, *args], capture_output=True,
                          text=True, timeout=timeout)

def export(swf, out):
    ffdec("-export", "script", str(out), str(swf))
    return sorted(str(p.relative_to(out)) for p in Path(out).rglob("*.as"))

def changed(before_dir, after_dir):
    r = subprocess.run(["diff", "-rq", str(before_dir), str(after_dir)],
                       capture_output=True, text=True)
    out = []
    for line in r.stdout.splitlines():
        if line.startswith("Files") and " differ" in line:
            parts = line.replace("Files ", "").replace(" and ", "|").split("|")
            out.append("/".join(Path(parts[0].strip()).parts[-2:]))
    return out

# ── game 1 ───────────────────────────────────────────────────────────────────
g1 = PKG / "games" / "1-Starwish-Legend" / "reg.swf"
b1, a1 = WORK / "g1-before", WORK / "g1-after"
shutil.rmtree(a1, ignore_errors=True)
before = export(g1, b1)
f3 = next(b1.rglob("frame_3/DoAction_2.as"))
src = f3.read_text(encoding="utf-8")
if "loadFullVersion()" not in src.split("btn_activate")[0]:
    edited = src.rstrip()
    seed = ('\r\n// start the full version straight away - no button press needed\r\n'
            'if(_root.loadFullVersion)\r\n{\r\n   _root.loadFullVersion();\r\n}\r\n')
    at = edited.rfind("stop();")
    edited = edited[:at] + seed + edited[at:] + "\r\n"
    f3.write_text(edited, encoding="utf-8")
    out1 = WORK / "g1-reg.swf"
    ffdec("-replace", str(g1), str(out1), "/frame 3 (name: form)/DoAction", str(f3))
    after = export(out1, a1)
    print("game 1: scripts", len(before), "->", len(after), "| changed:", changed(b1, a1))
    print("game 1: form frame now ends with:")
    for ln in next(a1.rglob("frame_3/DoAction_2.as")).read_text(encoding="utf-8").rstrip().splitlines()[-9:]:
        print("   ", ln)
    shutil.copy(out1, g1)
    print("game 1: installed", g1, g1.stat().st_size, "bytes\n")
else:
    print("game 1: already patched\n")

# ── game 3 ───────────────────────────────────────────────────────────────────
g3 = PKG / "games" / "3-Prince-Adventure" / "reg.swf"
b3, a3 = WORK / "g3-before", WORK / "g3-after"
shutil.rmtree(a3, ignore_errors=True)
before3 = export(g3, b3)
f1 = next(b3.rglob("frame_1/DoAction.as"))
src3 = f1.read_text(encoding="utf-8")
if "saveActivation" in src3:
    print("game 3: already patched")
else:
    old_block = ('if(_level0)\r\n{\r\n   _level0.activationSuccess = function(sn, hdkey, akey)\r\n'
                 '   {\r\n      return true;\r\n   };\r\n}')
    assert old_block in src3, "seed block not found"
    new_block = ('if(_level0)\r\n{\r\n   _level0.activationSuccess = function(sn, hdkey, akey)\r\n'
                 '   {\r\n      return true;\r\n   };\r\n'
                 '   if(_level0.saveActivation)\r\n   {\r\n      _level0.saveActivation("Player",'
                 '"12345678","a@b.com","P3-AAAA-BBBB-CCCC-DDDD",_level0.getHDKey(),"12345678");\r\n   }\r\n}')
    f1.write_text(src3.replace(old_block, new_block, 1), encoding="utf-8")
    out3 = WORK / "g3-reg.swf"
    ffdec("-replace", str(g3), str(out3), "/frame 1/DoAction", str(f1))
    after3 = export(out3, a3)
    print("game 3: scripts", len(before3), "->", len(after3), "| changed:", changed(b3, a3))
    print("game 3: frame 1 now ends with:")
    for ln in next(a3.rglob("frame_1/DoAction.as")).read_text(encoding="utf-8").rstrip().splitlines()[-13:]:
        print("   ", ln)
    shutil.copy(out3, g3)
    print("game 3: installed", g3, g3.stat().st_size, "bytes")
