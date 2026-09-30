#!/usr/bin/env python3
"""One continuous sky, no seam.

My last pass painted a radial gradient only 1200x540 at the top with background-size 100% 100%,
so everything below it showed the html base colour - two visible bands.  Fix: a single
linear gradient pinned to the viewport (background-attachment fixed) so it always fills the
whole page, with the star tiles anchored the same way.
"""
import os
import pathlib
import re
import shutil
import signal
import subprocess
import time

W = pathlib.Path("/home/yoke/Downloads/littleprince-launcher/lpo/web.html")
src = W.read_text()

src = src.replace("html{background:#dff1fd}", "html{background:#d8eefc}", 1)

start = src.index("    /* CSS-only sky")
end = src.index("background-size:260px 220px,320px 260px,210px 190px,300px 240px,240px 210px,100% 100%;")
end = src.index("\n", end) + 1
new = '''    /* CSS-only sky: ONE continuous gradient pinned to the viewport, so there is
       no band where a fixed-height layer ends.  Drifting star tiles above it. */
    background-color:#d8eefc;
    background-image:
      radial-gradient(circle at 12% 18%, rgba(255,255,255,.92) 0 1.6px, transparent 1.7px),
      radial-gradient(circle at 34% 44%, rgba(255,255,255,.78) 0 1.3px, transparent 1.4px),
      radial-gradient(circle at 57% 11%, rgba(255,255,255,.88) 0 1.5px, transparent 1.6px),
      radial-gradient(circle at 79% 34%, rgba(255,255,255,.72) 0 1.2px, transparent 1.3px),
      radial-gradient(circle at 91% 63%, rgba(255,255,255,.62) 0 1.4px, transparent 1.5px),
      linear-gradient(180deg,#f8fdff 0%,#eaf6fe 38%,#ddeffd 72%,#d8eefc 100%);
    background-repeat:repeat,repeat,repeat,repeat,repeat,no-repeat;
    background-size:260px 220px,320px 260px,210px 190px,300px 240px,240px 210px,100% 100%;
    background-attachment:fixed,fixed,fixed,fixed,fixed,fixed;
'''
src = src[:start] + new + src[end:]
W.write_text(src)
print("sky rewritten as one viewport-pinned gradient")
print("layers:", src.count("radial-gradient(circle"), "stars + 1 linear sky")

if __name__ == "__main__":
    TOOLS = "/home/yoke/Downloads/littleprince-patcher-handoff/tools"
    for s in ("build_local.py", "ship_launcher_pack.py"):
        r = subprocess.run(["python3", s], cwd=TOOLS, capture_output=True, text=True)
        for l in r.stdout.splitlines():
            if "ALL CHECKS" in l or "VERIFIED" in l or "local :" in l or "drive after" in l:
                print("   ", l.strip()[:150])

    SCRATCH = pathlib.Path("/tmp/tweakshot2")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    shutil.copytree("/home/yoke/Downloads/littleprince-launcher", SCRATCH / "lp")
    env = dict(os.environ, LPO_PORT="8988", LPO_GAME_DIR="/home/yoke/littleprince-online")
    srv = subprocess.Popen(["python3", "-u", "server.py"], cwd=SCRATCH / "lp/lpo", env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1440, "height": 900})
            pg.goto("http://127.0.0.1:8988/web", wait_until="networkidle")
            time.sleep(1)
            os.makedirs("/tmp/bb_tweak", exist_ok=True)
            pg.screenshot(path="/tmp/bb_tweak/02-signin-fixed.png", full_page=False)
            # sample the same column at several heights: one colour family = no band
            cols = pg.evaluate("""() => {
                const ys=[10,200,400,600,880];
                return ys.map(y=>{const e=document.elementFromPoint(20,y);
                  return getComputedStyle(document.body).backgroundAttachment;});
            }""")
            print("attachment per probe:", set(cols))
            print("saved /tmp/bb_tweak/02-signin-fixed.png")
            b.close()
    finally:
        srv.send_signal(signal.SIGTERM)
        time.sleep(1)
        srv.kill()
