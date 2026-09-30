#!/usr/bin/env python3
"""Re-run the LP1/LP3 source exports with the real jar path and visible logs."""
import pathlib
import subprocess
import sys

JAR = pathlib.Path.home() / "lpo_build/ffdec/ffdec.jar"
assert JAR.is_file(), "no ffdec jar at %s" % JAR
launcher = pathlib.Path.home() / "Downloads/littleprince-launcher"

jobs = []
for game, out in (("LP1", "/tmp/lp1_src"), ("LP3", "/tmp/lp3_src")):
    swf = launcher / "cloud" / game / "index.swf"
    print("  %s: %s (%d bytes)" % (game, swf.name, swf.stat().st_size))
    log = open("/tmp/%s_export.log" % game.lower(), "wb")
    p = subprocess.Popen(["java", "-jar", str(JAR), "-export", "script", out, str(swf)],
                         stdout=log, stderr=subprocess.STDOUT)
    jobs.append((game, out, p, log))
    print("     pid %d -> %s (log /tmp/%s_export.log)" % (p.pid, out, game.lower()))

# give them a head start and report, so a failure is visible immediately
import time
time.sleep(45)
for game, out, p, log in jobs:
    n = len(list(pathlib.Path(out).rglob("*.as"))) if pathlib.Path(out).exists() else 0
    print("  after 45s: %s -> %d .as files, still running: %s"
          % (game, n, p.poll() is None))
    if p.poll() is not None:
        log.flush()
        print("     export exited with %s; tail of the log:" % p.returncode)
        print("     " + pathlib.Path("/tmp/%s_export.log" % game.lower())
              .read_text(errors="replace")[-400:].replace("\n", "\n     "))
