#!/usr/bin/env python3
"""Point the overlay's help button at the notice route that actually exists, then
verify the whole Flash-only behaviour end to end."""
import pathlib
import re
import subprocess
import time

ROOT = pathlib.Path.home() / "Downloads/littleprince-launcher"

# fix the help button: /play-off is not a route, /play serves the notice
P = ROOT / "lpo/web/play_flash.html"
p = P.read_text()
if 'href="/play-off"' in p:
    p = p.replace('href="/play-off"', 'href="/play"', 1)
    P.write_text(p)
    print("play_flash.html: help button -> /play (the notice route)")

print("\n=== the other /play mentions in the launcher ===")
G = ROOT / "Start_Server_GUI.pyw"
lines = G.read_text().splitlines()
for n in (480, 538, 887):
    lo, hi = max(0, n - 4), min(len(lines), n + 2)
    print(f"--- around line {n} ---")
    for i in range(lo, hi):
        print(f"  {i+1}: {lines[i]}")

print("\n=== cloud pages / fetch_cloud ===")
for f, n in ((ROOT / "cloud/index.html", 208), (ROOT / "lpo/fetch_cloud.py", 46)):
    try:
        ls = f.read_text(errors="ignore").splitlines()
        print(f"--- {f.relative_to(ROOT)}:{n} ---")
        for i in range(max(0, n - 3), min(len(ls), n + 2)):
            print(f"  {i+1}: {ls[i]}")
    except Exception as e:
        print("  could not read:", e)

print("\n=== verifying the server ===")
subprocess.run("pkill -f 'python3 lpo/server[.]py'", shell=True, check=False)
time.sleep(0.5)
log = open("/tmp/flash_only_srv.log", "wb")
srv = subprocess.Popen(["python3", "lpo/server.py"], cwd=ROOT, stdout=log, stderr=log)
ready = False
for _ in range(20):
    time.sleep(1)
    if subprocess.run("ss -ltn | grep -q :8080", shell=True).returncode == 0:
        ready = True
        break
print("server up:", ready)

def probe(path):
    r = subprocess.run(["curl", "-s", "-o", "/tmp/probe.html", "-w", "%{http_code}",
                        f"http://127.0.0.1:8080{path}"], capture_output=True, text=True)
    body = pathlib.Path("/tmp/probe.html").read_text(errors="ignore") if pathlib.Path("/tmp/probe.html").exists() else ""
    ruffle = ("ruffle" in body.lower())
    return r.stdout.strip(), len(body), ruffle

for path in ("/play", "/play.html", "/LP/Po", "/", "/play-flash"):
    code, size, ruffle = probe(path)
    print(f"  {path:14} http={code:3} bytes={size:6} mentions_ruffle={ruffle}")

srv.terminate()
time.sleep(1)
print("test server stopped:", subprocess.run("pgrep -f 'python3 lpo/server[.]py' >/dev/null",
                                             shell=True).returncode != 0)
