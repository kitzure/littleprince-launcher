#!/usr/bin/env python3
"""Smoke-test the accounts page after the card-size change: load /web in real Chromium
through the pack's own server and report any JS console error, then confirm the billboard
canvas is the new size.  No session is used, so the ADMIN panes stay closed - this is a
syntax/render check of the page, not a login test."""
import os
import pathlib
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

L = pathlib.Path.home() / "Downloads" / "littleprince-launcher"
PORT = 8982
env = dict(os.environ, LPO_PORT=str(PORT), LPO_GAME_DIR=str(L))
proc = subprocess.Popen(["python3", str(L / "lpo/server.py")], cwd=str(L / "lpo"),
                        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
try:
    for _ in range(60):
        time.sleep(0.5)
        code = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                               "http://127.0.0.1:%d/web" % PORT],
                              capture_output=True, text=True).stdout.strip()
        if code == "200":
            break
    else:
        print("!! server did not come up"); sys.exit(1)
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1200, "height": 900})
        errs = []
        page.on("console", lambda m: errs.append((m.type, m.text)) if m.type == "error" else None)
        page.on("pageerror", lambda e: errs.append(("pageerror", str(e))))
        page.goto("http://127.0.0.1:%d/web" % PORT)
        page.wait_for_timeout(1200)
        print("title:", page.title())
        print("canvas count:", page.locator("#bb-canvas").count())
        print("size attr:", page.evaluate(
            "(()=>{const c=document.getElementById('bb-canvas');"
            "return c?[c.width,c.height,c.style.maxWidth]:null})()"))
        print("CARD_W/CARD_H in page:", page.evaluate(
            "(()=>{try{return [CARD_W,CARD_H]}catch(e){return String(e)}})()"))
        page.screenshot(path="/tmp/webpage.png", full_page=False)
        print("console errors:", errs if errs else "none")
        b.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
