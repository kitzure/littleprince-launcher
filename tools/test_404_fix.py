#!/usr/bin/env python3
"""The user's bug: a game folder that has no web.html (a fresh official client).
The accounts site and admin page must still work, because they ship in the package."""
import importlib.util, subprocess, threading, urllib.request, urllib.error
from importlib.machinery import SourceFileLoader
from pathlib import Path

HOME = Path.home()
PKG = HOME / "Downloads" / "littleprince-patcher"
FRESH = HOME / "Downloads" / ".lpclient-test" / "game"

print("=== the fresh official client: has web.html? ===")
print("web.html  :", (FRESH / "web.html").exists())
print("admin.html:", (FRESH / "admin.html").exists())
print("index.swf :", (FRESH / "index.swf").exists(), (FRESH / "index.swf").stat().st_size, "bytes")

print("\n=== completeness of the download ===")
spec = importlib.util.spec_from_file_location("lpo_fetch", PKG / "lpo" / "fetch_client.py")
fetcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(fetcher)
res = fetcher.check(FRESH)
print("present %d / %d, missing %d, wrong size %d"
      % (res["present"], res["total"], len(res["missing"]), len(res["wrong"])))

print("\n=== run the server against it (no env override, like the user's machine) ===")
import os
os.environ["LPO_GAME_DIR"] = str(FRESH)
loader = SourceFileLoader("gui", str(PKG / "Start_Server_GUI.pyw"))
gui = importlib.util.module_from_spec(importlib.util.spec_from_loader("gui", loader))
loader.exec_module(gui)
srv = gui.Online(port=8093)
srv.start()
print("game_dir:", srv.game_dir, "| swfs:", srv.swfs)

checks = [("/web", 200), ("/admin", 200), ("/index.swf", 200),
          ("/web/api/profile", 404), ("/play", 200), ("/crossdomain.xml", 200)]
print("\nroute      status")
ok = True
for path, expect in checks:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8093" + path, timeout=10) as r:
            code, size = r.status, len(r.read())
    except urllib.error.HTTPError as e:
        code, size = e.code, 0
    good = code == expect or (path.endswith("api/profile") and code in (401, 404))
    ok &= good
    print(f"{path:18s} {code} ({size} bytes)  {'ok' if good else 'UNEXPECTED'}")

# the accounts page must be a real page, not an error
with urllib.request.urlopen("http://127.0.0.1:8093/web", timeout=10) as r:
    body = r.read().decode("utf-8", "replace")
print("\n/web looks like the accounts site:", "Sign in" in body or "sign" in body.lower())
print("/admin looks like the editor    :", "profile" in body.lower() or "world" in body.lower())
srv.stop()
print("\nVERDICT:", "PASS" if ok else "CHECK")
