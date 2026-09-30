#!/usr/bin/env python3
"""Close the last way to reach the Ruffle player, then verify every entry point.

The /web/ static prefix mirrors the package's web folder, so /web/play.html served the
Ruffle page even after /play was switched to the notice.
"""
import pathlib
import subprocess
import time

ROOT = pathlib.Path.home() / "Downloads/littleprince-launcher"
S = ROOT / "lpo/server.py"
src = S.read_text()

OLD = '''        if clean_path.startswith("/web/") and not clean_path.startswith("/web/api"):
            self.serve_package_file(clean_path[len("/web/"):])
            return'''
NEW = '''        if clean_path.startswith("/web/") and not clean_path.startswith("/web/api"):
            # This prefix mirrors the whole web folder, which is how the Ruffle page
            # stayed reachable at /web/play.html after /play was switched off.
            if clean_path[len("/web/"):].lstrip("/") in ("play.html", "play"):
                self.serve_package_file("play_off.html")
                return
            self.serve_package_file(clean_path[len("/web/"):])
            return'''

if OLD in src:
    src = src.replace(OLD, NEW, 1)
    S.write_text(src)
    print("server.py: /web/ guard added")
else:
    print("!! /web/ anchor not found")

# stale header comment on the Flash page
P = ROOT / "lpo/web/play_flash.html"
p = P.read_text()
OLD_C = """  The real-Flash player: the publisher's browser is Electron 4 with Pepper Flash
  (resources/app/Plugins/pepflashplayer.dll), so a plain <object>/<embed> plays the
  game natively at its own 800x600.  Ruffle is the fallback for ordinary browsers,
  at /play."""
NEW_C = """  The real-Flash player: the publisher's browser is Electron 4 with Pepper Flash
  (resources/app/Plugins/pepflashplayer.dll), so a plain <object>/<embed> plays the
  game natively at its own 800x600.  This is the only player the pack uses; the
  install-free page that used to be the fallback at /play is switched off."""
if OLD_C in p:
    p = p.replace(OLD_C, NEW_C, 1)
    P.write_text(p)
    print("play_flash.html: header comment updated")
else:
    print("!! header comment anchor not found")

print("\n=== probing every entry point ===")
subprocess.run("pkill -f 'python3 lpo/server[.]py'", shell=True, check=False)
time.sleep(0.5)
log = open("/tmp/p3.log", "wb")
srv = subprocess.Popen(["python3", "lpo/server.py"], cwd=ROOT, stdout=log, stderr=log)
for _ in range(20):
    time.sleep(1)
    if subprocess.run("ss -ltn | grep -q :8080", shell=True).returncode == 0:
        break

def probe(path):
    r = subprocess.run(["curl", "-s", "-o", "/tmp/probe.html", "-w", "%{http_code}",
                        f"http://127.0.0.1:8080{path}"], capture_output=True, text=True)
    body = pathlib.Path("/tmp/probe.html").read_text(errors="ignore") if pathlib.Path("/tmp/probe.html").exists() else ""
    low = body.lower()
    player = ("ruffleplayer" in low) or ("ruffle.js" in low) or ("createplayer" in low)
    return r.stdout.strip(), len(body), player, ("runs in the publisher's flash browser" in low)

for path in ("/play", "/play.html", "/web/play.html", "/LP/Po", "/LP/Po/play.html", "/",
             "/play-flash", "/web/play_flash.html"):
    code, size, player, notice = probe(path)
    kind = "NOTICE" if notice else ("PLAYER" if player else "other")
    flag = "PLAYER!!" if (player and "flash" not in path) else ""
    print(f"  {path:22} http={code:3} bytes={size:6} {kind:7} {flag}")

srv.terminate()
time.sleep(1)
print("\ntest server stopped:",
      subprocess.run("pgrep -f 'python3 lpo/server[.]py' >/dev/null", shell=True).returncode != 0)
