#!/usr/bin/env python3
"""Build and verify the combined Windows/macOS package locally, without uploads.

Run against the full packaging tree in ~/Downloads/littleprince-launcher.
The source-only repository omits runtime and game-art payloads. The previous ZIP
is kept as littleprince-patcher-before-<date>.zip.
"""
import datetime
import hashlib
import subprocess
import zipfile
from pathlib import Path

HOME = Path.home()
PKG = HOME / "Downloads" / "littleprince-launcher"
ZIP = HOME / "Downloads" / "littleprince-patcher.zip"

for junk in PKG.rglob("__pycache__"):
    subprocess.run(["rm", "-rf", str(junk)])
for f in list(PKG.glob("*.log")) + list(PKG.glob("**/*.log")) \
        + list(PKG.glob("**/*.part")) + list(PKG.glob("**/*.bak")):
    if f.is_file():
        f.unlink()

if ZIP.exists():
    stamp = datetime.date.today().strftime("%Y%m%d")
    keep = ZIP.with_name("littleprince-patcher-before-%s.zip" % stamp)
    keep.write_bytes(ZIP.read_bytes())
    print("previous zip kept at", keep.name)
    ZIP.unlink()

subprocess.run(["zip", "-r", "-q", ZIP.name, PKG.name,
                "-x", "*/__pycache__/*", "-x", "*.log", "-x", "*.part", "-x", "*.bak",
                "-x", "*/lpo/accounts.json", "-x", "*/lpo/notices.json",
                "-x", "*/lpo/level_scores.json", "-x", "*/lpo/friends.json",
                "-x", "*/lpo/mails.json", "-x", "*/lpo/pending.json",
                "-x", "*/lpo/notice_content/*", "-x", "*/lpo/game/*",
                "-x", "*/lpo/game_dir.txt", "-x", "*/browser/*",
                "-x", "*/cloud/LP1/*", "-x", "*/cloud/LP2/*", "-x", "*/cloud/LP3/*",
                "-x", "*/games/*",
                "-x", "*/lpo/gone-pack.zip", "-x", "*.DS_Store",
                "-x", "*/lpo/captures/unreadable/*",
                "-x", "*/lpo/download-settings.json", "-x", "*/lpo/web/avatars/*",
                "-x", "*/.git/*",
                # macos/ stays IN: LittlePrinceLauncher.command execs
                # macos/launcher_gui.py, so a Windows zip without it breaks the Mac
                # side of the very same download (the pack is meant to work on both).
                # It carries the 27 MB Pepper Flash plugin, which is the price of
                # one combined download instead of two.
                ],
               cwd=str(HOME / "Downloads"), check=True)

# Keep the shipped default avatar, but not per-player cached avatar renders.
if (PKG / "lpo/web/avatars/default.png").is_file():
    subprocess.run(["zip", "-q", str(ZIP), PKG.name + "/lpo/web/avatars/default.png"],
                   cwd=str(HOME / "Downloads"), check=True)

md5 = hashlib.md5(ZIP.read_bytes()).hexdigest()
names = zipfile.ZipFile(ZIP).namelist()
print("zip: %.1f MB, %d entries, md5 %s" % (ZIP.stat().st_size / 1e6, len(names), md5))

in_zip = hashlib.sha256(
    zipfile.ZipFile(ZIP).read("littleprince-launcher/lpo/server.py")).hexdigest()
tree = hashlib.sha256((PKG / "lpo/server.py").read_bytes()).hexdigest()
checks = {
    "fixed Start_Server_GUI": any(n.endswith("Start_Server_GUI.pyw") for n in names),
    "pack download policy present": "littleprince-launcher/lpo/pack_download.py" in names,
    "no personal download settings": not any(n.endswith("lpo/download-settings.json") for n in names),
    "no user avatar cache": all(n.endswith("/default.png") or n.endswith("/")
                               for n in names if "/lpo/web/avatars/" in n),
    "no Drive fallback IDs": not any(b"https://drive.google.com/uc?export=download&id=" in
                                     zipfile.ZipFile(ZIP).read(n)
                                     for n in names if n.endswith((".py", ".pyw", ".html", ".js", ".md"))),
    "accounts.json excluded": not any(n.endswith("lpo/accounts.json") for n in names),
    "friends.json excluded": not any(n.endswith("lpo/friends.json") for n in names),
    "mails.json excluded": not any(n.endswith("lpo/mails.json") for n in names),
    "no bundled client": not any("/lpo/game/" in n for n in names),
    "no bundled browser": not any("/browser/" in n for n in names),
    "no cloud LP data": not any((("/cloud/LP%d/" % i) in n and not n.endswith("start.exe"))
                                for i in (1, 2, 3) for n in names),
    "no bytecode": not any("__pycache__" in n for n in names),
    "mac launcher entry": any(n.endswith("LittlePrinceLauncher.command") for n in names),
    "mac gui present": any(n.endswith("macos/launcher_gui.py") for n in names),
    "pepper flash present": any(n.endswith("PepperFlashPlayer.plugin/Contents/Info.plist")
                                for n in names),
    "no user notices": not any(n.endswith("lpo/notices.json") for n in names),
    "no user pending requests": not any(n.endswith("lpo/pending.json") for n in names),
    "no user notice cards": not any("/lpo/notice_content/" in n for n in names),
    "no user scores": not any(n.endswith("lpo/level_scores.json") for n in names),
    "one launcher bat": sorted(n.split("/")[-1] for n in names if n.endswith(".bat")),
    "fetch_browser.py": any(n.endswith("lpo/fetch_browser.py") for n in names),
    "client manifest": any(n.endswith("lpo/client_files.txt") for n in names),
    "cloud manifest": any(n.endswith("cloud/files.txt") for n in names),
    "server.py matches tree": in_zip == tree,
    "shared launcher UI": any(n.endswith("littleprince-launcher/launcher_ui.py") for n in names),
    "README has known-faults section": any(
        b"Faults in the publisher's own client" in zipfile.ZipFile(ZIP).read(n)
        for n in names if n.endswith("littleprince-launcher/README.md")),
}
for k, v in checks.items():
    print("    %-32s %s" % (k, v))
bad = [k for k, v in checks.items() if v is False]
print("\nCHECKS FAILED:" if bad else "\nALL CHECKS PASSED", bad or "")
if bad:
    raise SystemExit("CHECKS FAILED - do not upload this archive")
