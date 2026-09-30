import os, pathlib, re, shutil, signal, subprocess, time

W = pathlib.Path("/home/yoke/Downloads/littleprince-launcher/lpo/web.html")
src = W.read_text()
NAVY, NAVY_DK = "#0d4d97", "#0a3c78"

# every hover/active/focus rule that leans on the amber (orange) palette -> navy
hits = 0
def fix(m):
    global hits
    sel, body = m.group(1), m.group(2)
    if not re.search(r"var\(--amber[\w-]*\)|#8a5a0b|#c98a18|#e2a32c|#f6c85a|#f1592a", body, re.I):
        return m.group(0)
    nb = re.sub(r"var\(--amber[\w-]*\)", NAVY, body, flags=re.I)
    nb = re.sub(r"#8a5a0b|#c98a18|#e2a32c|#f6c85a|#f1592a", NAVY_DK, nb, flags=re.I)
    nb = re.sub(r"color:\s*#5d2a2c", "color:#ffffff", nb)
    nb = re.sub(r"color:\s*#3f2a06", "color:#ffffff", nb)
    hits += 1
    return sel + "{" + nb + "}"

src = re.sub(r"([^{}]*:(?:hover|focus|active|focus-visible)[^{}]*)\{([^}]*)\}", fix, src, flags=re.I)
print("hover rules repainted navy:", hits)
assert hits > 0, "nothing matched"
W.write_text(src)

# anything amber left in a hover context?
left = [m.group(0)[:80] for m in re.finditer(r"[^{}]*:hover[^{}]*\{[^}]*\}", src, re.I)
        if re.search(r"amber|#f1592a|#e2a32c|#c98a18", m.group(0), re.I)]
print("hover rules still amber:", len(left))
for l in left[:3]:
    print("   ", l)

if os.environ.get("SHIP"):
    T = "/home/yoke/Downloads/littleprince-patcher-handoff/tools"
    for s in ("build_local.py", "ship_launcher_pack.py"):
        r = subprocess.run(["python3", s], cwd=T, capture_output=True, text=True)
        for l in r.stdout.splitlines():
            if "ALL CHECKS" in l or "VERIFIED" in l or "local :" in l:
                print("   ", l.strip()[:130])

    S = pathlib.Path("/tmp/tw2")
    shutil.rmtree(S, ignore_errors=True)
    (S / "lp").mkdir(parents=True)
    shutil.copytree("/home/yoke/Downloads/littleprince-launcher/lpo", S / "lp/lpo")
    os.symlink("/home/yoke/Downloads/littleprince-launcher/cloud", S / "lp/cloud")
    for d in ("patches", "macos"):
        (S / "lp" / d).mkdir(exist_ok=True)
    env = dict(os.environ, LPO_PORT="8992", LPO_GAME_DIR="/home/yoke/littleprince-online")
    srv = subprocess.Popen(["python3", "-u", "server.py"], cwd=S / "lp/lpo", env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1440, "height": 860})
            pg.goto("http://127.0.0.1:8992/web", wait_until="networkidle")
            time.sleep(1)
            pg.screenshot(path="/tmp/bb_tweak/05-final.png")
            btn = pg.locator("button.btn.primary, .btn.primary").first
            before = btn.evaluate("e=>getComputedStyle(e).backgroundColor") if btn.count() else "n/a"
            if btn.count():
                btn.hover(); time.sleep(0.4)
                after = btn.evaluate("e=>getComputedStyle(e).backgroundColor")
                print("   primary button bg: normal=%s hover=%s" % (before, after))
            print("   body bg:", pg.evaluate("getComputedStyle(document.body).backgroundColor"))
            print("   saved /tmp/bb_tweak/05-final.png")
            b.close()
    finally:
        srv.send_signal(signal.SIGTERM); time.sleep(1); srv.kill()
    shutil.rmtree(S, ignore_errors=True)
