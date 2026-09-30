#!/usr/bin/env python3
"""Import the clean class into the GOOD build (not the broken one), then verify."""
import hashlib
import pathlib
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()
JAR = HOME / "lpo_build/ffdec/ffdec-cli.jar"
KEEP = HOME / "lpo_build/swf_backups"
GOOD = "d0c547407d39e99cc8ff915099fc393f"
md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

good = next(b for b in sorted(KEEP.glob("*.bak*")) if md5(b) == GOOD)
shutil.copy2(good, "/tmp/lib_good.swf")
print("base (the last build whose panel rendered): %s  %d bytes" % (md5(good),
                                                                  good.stat().st_size))

r = subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-importScript",
                    "/tmp/lib_good.swf", "/tmp/lib_one.swf", "/tmp/lpo_one"],
                   capture_output=True, text=True, cwd="/tmp")
print("import rc:", r.returncode)
if "SEVERE" in r.stdout + r.stderr or "expected but" in r.stdout + r.stderr:
    print("!! importer complained:")
    print((r.stdout + r.stderr)[-500:])
    sys.exit(1)
print("new SWF: %d bytes  md5 %s" % (pathlib.Path("/tmp/lib_one.swf").stat().st_size,
                                     md5("/tmp/lib_one.swf")))

# verify by re-exporting the new SWF
shutil.rmtree("/tmp/lpo_verify", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_verify", "/tmp/lib_one.swf"], capture_output=True, text=True)
out = pathlib.Path("/tmp/lpo_verify/scripts/PrinceOnline/UI_multiplay.as").read_text()
print("\n=== verified in the new SWF ===")
print("   helper definitions : %d (must be 1)" % out.count("function setupMpRetryButton"))
print("   calls              : %d (must be 1)" % out.count("setupMpRetryButton();"))
print("   plain btnRetry look:", 'this["btnRetry"]' in out)
print("   mpPlayAgain        :", "function mpPlayAgain" in out)
print("   one method table?  :", out.count("public function setupMpRetryButton") == 1)

# and compare the whole class set against the good build, to be sure nothing else moved
shutil.rmtree("/tmp/lpo_good_exp", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_good_exp", "/tmp/lib_good.swf"], capture_output=True, text=True)
d = subprocess.run(["diff", "-rq", "/tmp/lpo_good_exp", "/tmp/lpo_verify"],
                   capture_output=True, text=True)
print("\n=== diff against the good build (expect only UI_multiplay.as) ===")
print(d.stdout.strip() or "(no differences at all)")
