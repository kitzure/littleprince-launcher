import hashlib
import pathlib
import shutil
import subprocess

HOME = pathlib.Path.home()
NEW = pathlib.Path("/tmp/lib_one.swf")
L = HOME / "Downloads/littleprince-launcher"
KEEP = HOME / "lpo_build/swf_backups"
TOOLS = HOME / "Downloads/littleprince-patcher-handoff/tools"
md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

print("new lib.swf: %d bytes  md5 %s" % (pathlib.Path(NEW).stat().st_size, md5(NEW)))
for p in sorted(L.rglob("lib.swf")):
    shutil.copy2(p, KEEP / (p.parent.relative_to(L).as_posix().replace("/", "_") + ".bak"))
    shutil.copy2(NEW, p)
    print("   %-42s -> %s %s" % (p.relative_to(L), md5(p),
                                 "OK" if md5(p) == md5(NEW) else "MISMATCH"))

print("=== build + ship ===")
for script in ("build_local.py", "ship_launcher_pack.py"):
    r = subprocess.run(["python3", str(TOOLS / script)], capture_output=True, text=True, cwd=TOOLS)
    print("   %s: rc=%d" % (script, r.returncode))
    for line in [l for l in r.stdout.splitlines() if l.strip()][-3:]:
        print("      " + line)
