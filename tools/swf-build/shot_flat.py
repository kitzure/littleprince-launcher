import os, pathlib, shutil, signal, subprocess, time

# what is the last orange hex?
L = pathlib.Path("/home/yoke/Downloads/littleprince-launcher/lpo/web.html").read_text().splitlines()
for n in range(792, 800):
    if n <= len(L):
        print("line %d: %s" % (n, L[n-1][:110]))

# minimal scratch: lpo/ only, cloud symlinked read-only.  Keeps /tmp small.
S = pathlib.Path("/tmp/tw")
shutil.rmtree(S, ignore_errors=True)
(S / "lp").mkdir(parents=True)
shutil.copytree("/home/yoke/Downloads/littleprince-launcher/lpo", S / "lp/lpo")
os.symlink("/home/yoke/Downloads/littleprince-launcher/cloud", S / "lp/cloud")
for d in ("patches", "macos"):
    (S / "lp" / d).mkdir(exist_ok=True)

env = dict(os.environ, LPO_PORT="8991", LPO_GAME_DIR="/home/yoke/littleprince-online")
srv = subprocess.Popen(["python3", "-u", "server.py"], cwd=S / "lp/lpo", env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(3)
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 860})
        pg.goto("http://127.0.0.1:8991/web", wait_until="networkidle")
        time.sleep(1)
        pg.screenshot(path="/tmp/bb_tweak/04-flat-navy.png")
        print("body bg:", pg.evaluate("getComputedStyle(document.body).backgroundColor"))
        print("bg-image layers:", pg.evaluate("(getComputedStyle(document.body).backgroundImage.match(/radial-gradient/g)||[]).length"))
        print("gradient present:", "gradient(" in pg.evaluate("getComputedStyle(document.body).backgroundImage").replace("radial-gradient", ""))
        print("a:hover colour (in CSS):", "see grep")
        print("saved /tmp/bb_tweak/04-flat-navy.png")
        b.close()
finally:
    srv.send_signal(signal.SIGTERM); time.sleep(1); srv.kill()
