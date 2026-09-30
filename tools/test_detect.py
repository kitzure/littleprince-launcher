#!/usr/bin/env python3
"""Check the client-folder detection and the not-found page."""
import importlib.util, os, sys, urllib.request
from pathlib import Path

PKG = Path.home() / "Downloads" / "littleprince-patcher"
LPO = PKG / "lpo"

def load(env=None, kill_swfs=False):
    if env is None:
        os.environ.pop("LPO_GAME_DIR", None)
    else:
        os.environ["LPO_GAME_DIR"] = env
    sys.path.insert(0, str(LPO))
    for m in ("lpo_srv_test",):
        sys.modules.pop(m, None)
    spec = importlib.util.spec_from_file_location("lpo_srv_test", LPO / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if kill_swfs:                      # pretend this machine has no client anywhere
        mod._has_swfs = lambda p: False
        mod.GAME_DIR = mod._resolve_game_dir()
    return mod

print("=== 1. the shipped case: game_dir.txt holds a foreign path ===")
(LPO / "game_dir.txt").write_text(os.path.expanduser("~/littleprince-online") + "\n", encoding="utf-8")
txt = LPO / "game_dir.txt"
txt.write_text("D:\\Nope\\Not\\Here\n", encoding="utf-8")          # a Windows path that doesn't exist
m1 = load()
print("   GAME_DIR :", m1.GAME_DIR)
print("   swf count:", len(list(m1.GAME_DIR.glob('**/*.swf'))), "->",
      "ok (found the client anyway)" if m1.GAME_DIR != LPO else "FAILED")

print("\n=== 2. no saved path at all ===")
txt.unlink(missing_ok=True)
m2 = load()
print("   GAME_DIR :", m2.GAME_DIR, "| swfs:", len(list(m2.GAME_DIR.glob('*.swf'))))

print("\n=== 3. an explicit folder wins (what the picker sets) ===")
m3 = load(env=str(Path.home() / "littleprince-online"))
print("   GAME_DIR :", m3.GAME_DIR, "| swfs:", len(list(m3.GAME_DIR.glob('*.swf'))))

print("\n=== 4. no client anywhere -> players get the help page, not a broken player ===")
m4 = load(kill_swfs=True)
print("   resolves to:", m4.GAME_DIR, "(package folder)")
m4.PORT = 8099
srv = m4.ReusableTCPServer((m4.HOST, 8099), m4.LittlePrinceHandler)
import threading
threading.Thread(target=srv.serve_forever, daemon=True).start()
for path in ("/play", "/LP/Po/"):
    with urllib.request.urlopen("http://127.0.0.1:8099" + path, timeout=10) as r:
        body = r.read().decode("utf-8", "replace")
    print(f"   {path:9s} -> {r.status} | help page: {'Game files not found' in body}")
srv.shutdown(); srv.server_close()

print("\n=== 5. save_game_dir writes the file the resolver reads ===")
p = m4.save_game_dir("/tmp/somewhere/Little Prince Online")
print("   wrote:", (LPO / "game_dir.txt").read_text(encoding="utf-8").strip())
(LPO / "game_dir.txt").unlink(missing_ok=True)
print("   cleaned up:", not (LPO / "game_dir.txt").exists())
