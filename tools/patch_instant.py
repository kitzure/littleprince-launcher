#!/usr/bin/env python3
"""Make Starwish Legend and Prince Adventure start the full version by themselves,
the way Little Prince already does.

  game 1 (Starwish Legend, AS2 form frame): the form's frame script calls
      _root.loadFullVersion() itself, instead of waiting for the button.
  game 3 (Prince Adventure): frame 1 seeds the same activation record that makes
      game 2 instant, so Application.checkActivation() finds it and calls
      PrinceSystem.loadOpening() straight away.
"""
import re, subprocess, shutil
from pathlib import Path

PKG = Path.home() / "Downloads" / "littleprince-patcher"
FFDEC = "/tmp/ffdec/ffdec.jar"
WORK = Path("/tmp/p2/auto")
shutil.rmtree(WORK, ignore_errors=True)
WORK.mkdir(parents=True)

def ffdec(*args, timeout=500):
    return subprocess.run(["java", "-jar", FFDEC, *args], capture_output=True,
                          text=True, timeout=timeout)

def export(swf, out):
    ffdec("-export", "script", str(out), str(swf))
    return sorted(str(p.relative_to(out)) for p in Path(out).rglob("*.as"))

def replace(src, dst, spec, as_file):
    r = ffdec("-replace", str(src), str(dst), spec, str(as_file))
    if not Path(dst).exists():
        raise SystemExit(f"replace failed for {spec}: {r.stdout[-400:]} {r.stderr[-400:]}")
    return r

# ── game 1: act on the form frame ─────────────────────────────────────────────
g1_in = PKG / "games" / "1-Starwish-Legend" / "reg.swf"
g1_out = WORK / "g1-reg.swf"
before = export(g1_in, WORK / "g1-before")
f3 = next(WORK.glob("g1-before/**/frame_3/DoAction_2.as"))
src = f3.read_text(encoding="utf-8")
assert "btn_activate.onRelease" in src and src.rstrip().endswith("stop();"), "unexpected form frame"

seed = ('// start the full version straight away - no button press needed\r\n'
        'if(_root.loadFullVersion)\r\n'
        '{\r\n'
        '   _root.loadFullVersion();\r\n'
        '}\r\n')
edited = src.rstrip()
stop_at = edited.rfind("stop();")
edited = edited[:stop_at] + seed + edited[stop_at:] + "\r\n"
f3.write_text(edited, encoding="utf-8")
replace(g1_in, g1_out, "/frame 3 (name: form)/DoAction", f3)

after = export(g1_out, WORK / "g1-after")
print("game 1: scripts before/after =", len(before), len(after))
diff = subprocess.run(["diff", "-rq", str(WORK / "g1-before"), str(WORK / "g1-after")],
                      capture_output=True, text=True)
print("game 1: changed files ->", [l.split()[-1].split("/")[-2] + "/" + l.split()[-1].split("/")[-1]
                                   for l in diff.stdout.splitlines() if l.startswith("Files")])
print("game 1: tail of the rebuilt form frame:")
print("   " + "\n   ".join(Path(after[0] and (WORK / "g1-after")).rglob("frame_3/DoAction_2.as")
                           .__next__().read_text(encoding="utf-8").strip().splitlines()[-8:]))

# ── game 3: extend the frame-1 seed ───────────────────────────────────────────
g3_in = PKG / "games" / "3-Prince-Adventure" / "reg.swf"
g3_out = WORK / "g3-reg.swf"
before3 = export(g3_in, WORK / "g3-before")
f1 = next(WORK.glob("g3-before/**/frame_1/DoAction.as"))
src3 = f1.read_text(encoding="utf-8")
assert "activationSuccess" in src3, "frame 1 seed missing"

old_block = '''if(_level0)\r\n{\r\n   _level0.activationSuccess = function(sn, hdkey, akey)\r\n   {\r\n      return true;\r\n   };\r\n}'''
assert old_block in src3, "seed block not found verbatim"
new_block = old_block[:-2] + '''   if(_level0.saveActivation)\r\n   {\r\n      _level0.saveActivation("Player","12345678","a@b.com","P3-AAAA-BBBB-CCCC-DDDD",_level0.getHDKey(),"12345678");\r\n   }\r\n}'''
f1.write_text(src3.replace(old_block, new_block, 1), encoding="utf-8")
replace(g3_in, g3_out, "/frame 1/DoAction", f1)

after3 = export(g3_out, WORK / "g3-after")
print("\ngame 3: scripts before/after =", len(before3), len(after3))
diff3 = subprocess.run(["diff", "-rq", str(WORK / "g3-before"), str(WORK / "g3-after")],
                       capture_output=True, text=True)
print("game 3: changed files ->", [l.split()[-1].split("/")[-2] + "/" + l.split()[-1].split("/")[-1]
                                    for l in diff3.stdout.splitlines() if l.startswith("Files")])
tail = next((WORK / "g3-after").rglob("frame_1/DoAction.as")).read_text(encoding="utf-8").strip().splitlines()
print("game 3: frame 1 now ends with:")
print("   " + "\n   ".join(tail[-12:]))

for src_swf, dst_swf in ((g1_out, g1_in), (g3_out, g3_in)):
    shutil.copy(g1_out if src_swf == g1_out else src_swf, dst_swf)
    print(f"\ninstalled -> {dst_swf}  ({dst_swf.stat().st_size} bytes)")
