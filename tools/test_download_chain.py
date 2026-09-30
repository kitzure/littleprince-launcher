#!/usr/bin/env python3
"""Prove the chain: downloader -> lpo/game -> the online server serves those files.
Downloads a subset, then removes it so nothing partial ships."""
import importlib.util, shutil, urllib.request
from importlib.machinery import SourceFileLoader
from pathlib import Path

PKG = Path.home() / "Downloads" / "littleprince-patcher"
GAME = PKG / "lpo" / "game"

spec = importlib.util.spec_from_file_location("lpo_fetch", PKG / "lpo" / "fetch_client.py")
fetcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetcher)
rows = fetcher.read_manifest()
print("manifest:", len(rows), "files,", round(sum(s for _, s in rows) / 1e6), "MB")

subset = [r for r in rows if r[0].startswith(("index.swf", "login.swf", "settings.cxd",
                                             "lib/lib.swf", "interface.swf"))]
shutil.rmtree(GAME, ignore_errors=True)
GAME.mkdir(parents=True)
for rel, size in subset:
    kind, _ = fetcher.fetch_file(fetcher.DEFAULT_BASE, GAME, rel, size)
    print("   ", kind, rel)
print("subset bytes:", sum(f.stat().st_size for f in GAME.rglob("*") if f.is_file()) // 1024, "KB")

loader = SourceFileLoader("gui", str(PKG / "Start_Server_GUI.pyw"))
gui = importlib.util.module_from_spec(importlib.util.spec_from_loader("gui", loader))
loader.exec_module(gui)
srv = gui.Online(port=8094)
srv.start()
print("online server game_dir:", srv.game_dir)
print("swfs:", srv.swfs, "| running:", srv.running)
code = urllib.request.urlopen("http://127.0.0.1:8094/index.swf", timeout=10).status
with urllib.request.urlopen("http://127.0.0.1:8094/play", timeout=10) as r:
    body = r.read().decode("utf-8", "replace")
print("index.swf served:", code, "| /play is the player:", "RufflePlayer" in body)
verdict = (str(GAME) == srv.game_dir and srv.swfs >= 5 and "RufflePlayer" in body)
srv.stop()

shutil.rmtree(GAME, ignore_errors=True)
print("cleaned lpo/game:", not GAME.exists())
print("VERDICT:", "PASS" if verdict else "CHECK")
