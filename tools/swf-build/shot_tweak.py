import hashlib
import os
import pathlib
import shutil
import signal
import subprocess
import time

PACK = pathlib.Path("/home/yoke/Downloads/littleprince-launcher")
SCRATCH = pathlib.Path("/tmp/tweakshot")
PORT = 8987

# md5 of the pack the ship tool just uploaded
zips = list(pathlib.Path("/home/yoke/Downloads/littleprince-patcher-handoff").rglob("*.zip"))
for z in zips[:3]:
    print("zip:", z, hashlib.md5(z.read_bytes()).hexdigest(), z.stat().st_size)

shutil.rmtree(SCRATCH, ignore_errors=True)
shutil.copytree(PACK, SCRATCH / "littleprince-launcher")
os.makedirs("/tmp/bb_tweak", exist_ok=True)

env = dict(os.environ, LPO_PORT=str(PORT), LPO_GAME_DIR="/home/yoke/littleprince-online")
srv = subprocess.Popen(["python3", "-u", "server.py"], cwd=SCRATCH / "littleprince-launcher/lpo",
                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(3)
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.goto("http://127.0.0.1:%d/web" % PORT, wait_until="networkidle")
        time.sleep(1)
        pg.screenshot(path="/tmp/bb_tweak/01-signin.png", full_page=True)
        # is the banner gone and the star field present?
        print("cover block present:", pg.locator(".lp-cover").count())
        print("bg.jpg requested:", "bg.jpg" in pg.content())
        bg = pg.evaluate("getComputedStyle(document.body).backgroundImage")
        print("body background-imag e layers:", bg.count("radial-gradient"))
        print("saved /tmp/bb_tweak/01-signin.png")
        b.close()
finally:
    srv.send_signal(signal.SIGTERM)
    time.sleep(1)
    srv.kill()
