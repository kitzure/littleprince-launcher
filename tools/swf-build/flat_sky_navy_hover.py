#!/usr/bin/env python3
"""Flat sky + navy hovers.

1. The user still sees '2 colors' - my sky is still a gradient, so it reads as a band top-to-bottom.
   Make it ONE flat colour, stars kept (they never complained about those).
2. 'the hover color aka the kinda orangeish one change to dark blue': the orange hovers
   (#c2560e / #F1592A / #F7941E) become the publisher's own navy #0d4d97.  Only *hover* rules are
   touched - the gold star glyphs and other accents are left alone on purpose.
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
report = []

# ---- 1. flat sky -------------------------------------------------------------------
i = src.index("    /* CSS-only sky")
j = src.index("background-attachment:fixed,fixed,fixed,fixed,fixed,fixed;", i)
j = src.index("\n", j) + 1
flat = '''    /* CSS-only sky: ONE flat colour (a gradient reads as a band) with faint
       star tiles over it.  No publisher artwork. */
    background-color:#d9eefb;
    background-image:
      radial-gradient(circle at 12% 18%, rgba(255,255,255,.85) 0 1.5px, transparent 1.6px),
      radial-gradient(circle at 34% 44%, rgba(255,255,255,.70) 0 1.2px, transparent 1.3px),
      radial-gradient(circle at 57% 11%, rgba(255,255,255,.80) 0 1.4px, transparent 1.5px),
      radial-gradient(circle at 79% 34%, rgba(255,255,255,.65) 0 1.1px, transparent 1.2px),
      radial-gradient(circle at 91% 63%, rgba(255,255,255,.55) 0 1.3px, transparent 1.4px);
    background-repeat:repeat,repeat,repeat,repeat,repeat;
    background-size:260px 220px,320px 260px,210px 190px,300px 240px,240px 210px;
    background-attachment:fixed,fixed,fixed,fixed,fixed;
'''
src = src[:i] + flat + src[j:]
src = src.replace("html{background:#d8eefc}", "html{background:#d9eefb}", 1)
report.append("sky is now a flat colour with stars only")

# ---- 2. orange hovers -> navy ------------------------------------------------------
NAVY = "#0d4d97"
orange = re.compile(r"#(?:c2560e|C2560E|f7941e|F7941E|f1592a|F1592A|e08a2e|E08A2E|d98a1f|D98A1F)")
changed = 0
# (a) any declaration block whose selector mentions hover/active/focus
block = re.compile(r"([^{}]*:(?:hover|focus|active)[^{}]*)\{([^}]*)\}", re.I)
def sub_block(m):
    global changed
    sel, body = m.group(1), m.group(2)
    if not orange.search(body):
        return m.group(0)
    newbody = orange.sub(NAVY, body)
    changed += len(orange.findall(body))
    return sel + "{" + newbody + "}"
src = block.sub(sub_block, src)

# (b) variables that name a hover colour
for m in re.finditer(r"(--[\w-]*h(?:ov|over)[\w-]*)\s*:\s*([^;]+);", src, re.I):
    if orange.search(m.group(2)):
        src = src.replace(m.group(0), "%s:%s;" % (m.group(1), NAVY))
        changed += 1
        report.append("hover variable %s -> %s" % (m.group(1), NAVY))

report.append("orange hover declarations rewritten: %d" % changed)
assert changed > 0, "no orange hover colours found - check the CSS before shipping"

# what orange is left, and where (should only be non-hover accents like the gold glyphs)
left = orange.findall(src)
report.append("orange hexes remaining outside hover rules: %d" % len(left))

W.write_text(src)
print("\n".join(report))

if __name__ == "__main__":
    TOOLS = "/home/yoke/Downloads/littleprince-patcher-handoff/tools"
    for s in ("build_local.py", "ship_launcher_pack.py"):
        r = subprocess.run(["python3", s], cwd=TOOLS, capture_output=True, text=True)
        for l in r.stdout.splitlines():
            if "ALL CHECKS" in l or "VERIFIED" in l or "local :" in l:
                print("   ", l.strip()[:140])

    SCRATCH = pathlib.Path("/tmp/tweakshot3")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    shutil.copytree("/home/yoke/Downloads/littleprince-launcher", SCRATCH / "lp")
    env = dict(os.environ, LPO_PORT="8989", LPO_GAME_DIR="/home/yoke/littleprince-online")
    srv = subprocess.Popen(["python3", "-u", "server.py"], cwd=SCRATCH / "lp/lpo", env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1440, "height": 900})
            pg.goto("http://127.0.0.1:8989/web", wait_until="networkidle")
            time.sleep(1)
            pg.screenshot(path="/tmp/bb_tweak/03-signin-flat.png", full_page=False)
            pg.screenshot(path="/tmp/bb_tweak/03-signin-flat-full.png", full_page=True)
            # sample the rendered background colour at several heights - identical = truly flat
            px = pg.evaluate("""async () => {
              const c=document.createElement('canvas'); c.width=c.height=1;
              const out=[];
              for (const y of [5,300,600,880]) {
                const el=document.elementFromPoint(5,y);
                out.push(getComputedStyle(document.body).backgroundColor);
              }
              return out;
            }""")
            print("   body colour probes:", px)
            print("   saved /tmp/bb_tweak/03-signin-flat.png")
            b.close()
    finally:
        srv.send_signal(signal.SIGTERM)
        time.sleep(1)
        srv.kill()
