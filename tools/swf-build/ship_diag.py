import hashlib
import pathlib
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()
L = HOME / "Downloads/littleprince-launcher"
KEEP = HOME / "lpo_build/swf_backups"
TOOLS = HOME / "Downloads/littleprince-patcher-handoff/tools"
md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

out = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as").read_text()
print("=== the diagnostic build, after the round trip ===")
for probe, label in (("function mpDiag", "mpDiag defined"),
                     ('mpDiag("verdict")', "runs on the verdict frame"),
                     ('mpDiag("end")', "runs on the end frame"),
                     ("function mpWireRetry", "mpWireRetry defined"),
                     ("Debug.init(", "the on-screen log is initialised"),
                     ("Debug.enable()", "and enabled"),
                     ("play again running", "the action announces itself")):
    print("   %-34s %s" % (label, probe in out))
print("   duplicate helpers:",
      out.count("function mpDiag"), out.count("function mpWireRetry"), "(both must be 1)")

d = subprocess.run(["diff", "-rq", "/tmp/lpo_good_exp", "/tmp/lpo_one_out"],
                   capture_output=True, text=True)
print("\n=== vs the good build ===")
print(d.stdout.strip() or "(no differences)")

for p in sorted(L.rglob("lib.swf")):
    shutil.copy2(p, KEEP / (p.parent.relative_to(L).as_posix().replace("/", "_") + ".bak"))
    shutil.copy2("/tmp/lib_one.swf", p)
    print("\ndeployed %s -> %s" % (p.relative_to(L), md5(p)))

for script in ("build_local.py", "ship_launcher_pack.py"):
    r = subprocess.run(["python3", str(TOOLS / script)], capture_output=True, text=True, cwd=TOOLS)
    for line in [l for l in r.stdout.splitlines() if l.strip()][-2:]:
        print(line)
