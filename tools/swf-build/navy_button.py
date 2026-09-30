import os, pathlib, re, shutil, signal, subprocess, time

W = pathlib.Path("/home/yoke/Downloads/littleprince-launcher/lpo/web.html")
src = W.read_text()

# the gold primary button -> navy, at rest and on hover
old = ".btn.primary{background:#f1592a;background:linear-gradient(180deg,#f6c85a 0,#e2a32c 55%,#c98a18 100%);"
new = ".btn.primary{background:#0d4d97;background:linear-gradient(180deg,#2a6fc4 0,#124f9e 55%,#0d4d97 100%);"
assert old in src, "primary rule shape changed - look before patching"
src = src.replace(old, new, 1)
src = re.sub(r"(\.btn\.primary[^{}]*\{[^}]*?)border:1px solid #a06f14", r"\1border:1px solid #0a3c78", src)
src = re.sub(r"(\.btn\.primary[^{}]*\{[^}]*?)color:#3f2a06", r"\1color:#ffffff", src)
src = re.sub(r"(\.btn\.primary[^{}]*text-shadow:)[^;]+;", r"\1none;", src)

# and any remaining gold on the primary/hover path
src = src.replace("#f1592a", "#0d4d97").replace("#f6c85a", "#2a6fc4")
src = src.replace("#e2a32c", "#124f9e").replace("#c98a18", "#0d4d97").replace("#a06f14", "#0a3c78")
W.write_text(src)
print("primary button is navy; gold hexes left:", len(re.findall(r"#f1592a|#f6c85a|#e2a32c|#c98a18|#a06f14", src)))

if os.environ.get("SHIP"):
    T = "/home/yoke/Downloads/littleprince-patcher-handoff/tools"
    for s in ("build_local.py", "ship_launcher_pack.py"):
        r = subprocess.run(["python3", s], cwd=T, capture_output=True, text=True)
        print(r.stdout[-400:])

    S = pathlib.Path("/tmp/tw3")
    shutil.rmtree(S, ignore_errors=True)
    (S / "lp").mkdir(parents=True)
    shutil.copytree("/home/yoke/Downloads/littleprince-launcher/lpo", S / "lp/lpo")
    os.symlink("/home/yoke/Downloads/littleprince-launcher/cloud", S / "lp/cloud")
    for d in ("patches", "macos"):
        (S / "lp" / d).mkdir(exist_ok=True)
    env = dict(os.environ, LPO_PORT="8993", LPO_GAME_DIR="/home/yoke/littleprince-online")
    srv = subprocess.Popen(["python3", "-u", "server.py"], cwd=S / "lp/lpo", env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1440, "height": 860})
            pg.goto("http://127.0.0.1:8993/web", wait_until="networkidle")
            time.sleep(1)
            print("primary bg:", pg.locator(".btn.primary").first.evaluate("e=>getComputedStyle(e).backgroundColor"))
            pg.screenshot(path="/tmp/bb_tweak/06-navy-button.png")
            print("saved /tmp/bb_tweak/06-navy-button.png")
            b.close()
    finally:
        srv.send_signal(signal.SIGTERM); time.sleep(1); srv.kill()
    shutil.rmtree(S, ignore_errors=True)
