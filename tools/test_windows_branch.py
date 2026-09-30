#!/usr/bin/env python3
"""Exercise the Windows-only detection branch with a stub winreg."""
import importlib.util, sys, types
from pathlib import Path

PKG = Path.home() / "Downloads" / "littleprince-patcher"
LPO = PKG / "lpo"

fake = Path("/tmp/p2/fakeclient/Little Prince Online")
fake.mkdir(parents=True, exist_ok=True)
(fake / "index.swf").write_bytes(b"FWS fake")
(fake / "login.swf").write_bytes(b"FWS fake")
dead = Path("/tmp/p2/fakeclient/GoneBroken")

UNINSTALL = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall"
WOW = "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall"

# what a real machine would hold: a prince install, an unrelated app, and a
# prince entry whose folder has been deleted
INSTALLS = {
    "LittlePrinceOnline_is1": {"DisplayName": "Little Prince Online", "InstallLocation": str(fake)},
    "NotAPrinceApp": {"DisplayName": "Some Other App", "InstallLocation": str(dead)},
    "GonePrinces_is1": {"DisplayName": "Old Prince Demo", "InstallLocation": str(dead)},
}


class FakeKey:
    def __init__(self, names=None, values=None):
        self.names = names or []
        self.values = values or {}
    def __enter__(self): return self
    def __exit__(self, *a): return False


class FakeWinReg(types.ModuleType):
    HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER = 1, 2
    def __init__(self):
        super().__init__("winreg")
        self.subkeys = {UNINSTALL: ["LittlePrinceOnline_is1", "NotAPrinceApp", "GonePrinces_is1"],
                        WOW: []}
    def OpenKey(self, root, sub):
        if sub in self.subkeys:
            return FakeKey(names=self.subkeys[sub])
        if sub in INSTALLS:                              # a subkey under Uninstall
            return FakeKey(values=INSTALLS[sub])
        return FakeKey()
    def QueryInfoKey(self, key): return (len(key.names), 0, 0)
    def EnumKey(self, key, i): return key.names[i]
    def QueryValueEx(self, key, name):
        if name in key.values:
            return (key.values[name], 1)
        raise OSError("no value")


stub = FakeWinReg()
sys.modules["winreg"] = stub
sys.path.insert(0, str(LPO))
spec = importlib.util.spec_from_file_location("lpo_srv_win", LPO / "server.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod._on_windows = lambda: True

found = [Path(d) for d in (mod._windows_game_dirs() or ())]
print("windows branch yielded :", [str(f) for f in found])
print("real client discovered :", fake in found)
print("dead paths skipped     :", dead not in found)
print("resolved GAME_DIR      :", mod._resolve_game_dir())
print("has the client         :", mod._has_swfs(mod._resolve_game_dir()))
