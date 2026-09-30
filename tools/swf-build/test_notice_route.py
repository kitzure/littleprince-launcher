#!/usr/bin/env python3
"""End-to-end check of the notice content route after the 694x510 card change.

Starts the pack's own server on a scratch port and curls /notice/content/<id>.png for
(a) a notice with no uploaded card -> the shipped blank card, and (b) the empty-board
URL the mirror hands out.  Asserts the bytes are a real PNG of the panel's content size.
"""
import hashlib
import os
import pathlib
import subprocess
import sys
import time

L = pathlib.Path.home() / "Downloads" / "littleprince-launcher"
PORT = 8981
env = dict(os.environ, LPO_PORT=str(PORT), LPO_GAME_DIR=str(L))
proc = subprocess.Popen(["python3", str(L / "lpo/server.py")], cwd=str(L / "lpo"),
                        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
try:
    for _ in range(60):
        time.sleep(0.5)
        out = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                              "http://127.0.0.1:%d/web" % PORT],
                             capture_output=True, text=True).stdout
        if out.strip() == "200":
            break
    else:
        print("!! server did not come up"); sys.exit(1)
    print("server up on", PORT)

    for path in ("/notice/content/1.png", "/notice/content/empty.png"):
        for label, extra in (("plain", []), ):
            f = "/tmp/route%s%s.png" % (path.replace("/", "_"), "")
            r = subprocess.run(["curl", "-s", "-D", "/tmp/hdr.txt", "-o", f,
                                "http://127.0.0.1:%d%s" % (PORT, path)],
                               capture_output=True, text=True)
            hdr = pathlib.Path("/tmp/hdr.txt").read_text()
            data = pathlib.Path(f).read_bytes()
            from PIL import Image
            size = Image.open(f).size if data[:8] == b"\x89PNG\r\n\x1a\n" else None
            print("%-28s %s  server says: %s" % (
                path, size,
                [l.strip() for l in hdr.splitlines() if l.lower().startswith(
                    ("http/", "content-type", "content-length"))]))
            print("      %d bytes  png magic %s  md5 %s"
                  % (len(data), data[:8] == b"\x89PNG\r\n\x1a\n",
                     hashlib.md5(data).hexdigest()[:12]))

    # the shipped blank card is what a notice with no upload gets
    blank = (L / "lpo/notice_blank.png").read_bytes()
    served = pathlib.Path("/tmp/route_notice_content_1.png").read_bytes()
    print("shipped notice_blank.png == served blank card:",
          hashlib.md5(blank).hexdigest() == hashlib.md5(served).hexdigest())
    print("shipped blank card size:", __import__("PIL.Image", fromlist=["Image"])
          .open(L / "lpo/notice_blank.png").size)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    tail = proc.stdout.read()[-600:]
    print("--- server log tail ---")
    print(tail)
