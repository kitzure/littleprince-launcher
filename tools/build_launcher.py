#!/usr/bin/env python3
"""Build the Windows release: "Little Prince Launcher.exe" + bundled Python + the package.

    python tools/build_launcher.py [--out DIR] [--zip NAME] [--skip-exe]

1. builds launcher-app/ (Tauri) with cargo - needs Rust, and with the GNU toolchain
   a MinGW-w64 bin folder on PATH or in ~/.mingw64-winlibs/mingw64/bin (dlltool);
2. fetches the official embeddable Python (same version as the one running this
   script) and the Pillow wheel for it, into tools/.cache/ (kept between builds);
3. lays out DIR/littleprince-launcher/: every tracked file of the package (not
   docs/, tools/ or the exe's sources), the exe, and runtime/python/;
4. zips it.

Players unzip and run the exe - no Python install needed.
"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "tools" / ".cache"
APP = REPO / "launcher-app"
EXE_NAME = "Little Prince Launcher.exe"
SKIP_PREFIXES = ("docs/", "tools/", "launcher-app/")
SKIP_FILES = ("banner.jpeg",)


def fetch(url, dest):
    if dest.is_file() and dest.stat().st_size:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print("downloading", url)
    req = urllib.request.Request(url, headers={"User-Agent": "littleprince-launcher-build"})
    with urllib.request.urlopen(req, timeout=300) as r, open(str(dest) + ".part", "wb") as fh:
        shutil.copyfileobj(r, fh, 1 << 20)
    os.replace(str(dest) + ".part", dest)
    return dest


def build_exe():
    env = dict(os.environ)
    extra = [Path.home() / ".cargo" / "bin", Path.home() / ".mingw64-winlibs" / "mingw64" / "bin"]
    env["PATH"] = os.pathsep.join([str(p) for p in extra if p.is_dir()] + [env.get("PATH", "")])
    subprocess.run(["cargo", "build", "--release"], cwd=APP, env=env, check=True)
    exe = APP / "target" / "release" / "littleprince-launcher.exe"
    if not exe.is_file():
        sys.exit("the build did not produce %s" % exe)
    return exe


def python_runtime(dest):
    """The embeddable Python + Pillow, unpacked into dest (runtime/python)."""
    ver = platform.python_version()
    tag = "cp%d%d" % sys.version_info[:2]
    embed = fetch("https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip" % (ver, ver),
                  CACHE / ("python-%s-embed-amd64.zip" % ver))
    meta = json.load(urllib.request.urlopen("https://pypi.org/pypi/Pillow/json", timeout=60))
    wheel = next((f for f in meta["urls"]
                  if f["filename"].endswith("-%s-%s-win_amd64.whl" % (tag, tag))), None)
    if wheel is None:
        sys.exit("no Pillow wheel for %s on PyPI" % tag)
    whl = fetch(wheel["url"], CACHE / wheel["filename"])
    if hashlib.sha256(whl.read_bytes()).hexdigest() != wheel["digests"]["sha256"]:
        whl.unlink()
        sys.exit("the Pillow wheel's checksum does not match PyPI - deleted, run again")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    zipfile.ZipFile(embed).extractall(dest)
    site = dest / "Lib" / "site-packages"
    site.mkdir(parents=True)
    zipfile.ZipFile(whl).extractall(site)
    # the ._pth file is the embeddable Python's whole sys.path: add site-packages
    pth = next(dest.glob("python*._pth"))
    lines = [ln for ln in pth.read_text().splitlines() if ln.strip()]
    if "Lib\\site-packages" not in lines:
        lines.insert(1, "Lib\\site-packages")
    pth.write_text("\n".join(lines) + "\n")
    print("bundled Python %s + %s" % (ver, wheel["filename"]))


def webview2_loader():
    found = sorted((APP / "target" / "release" / "build").glob("webview2-com-sys-*/out/x64/WebView2Loader.dll"),
                   key=lambda p: p.stat().st_mtime)
    return found[-1] if found else None


def tracked_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True)
    files = [f for f in out.stdout.decode("utf-8").split("\0") if f]
    return [f for f in files if not f.startswith(SKIP_PREFIXES) and f not in SKIP_FILES]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "tools" / ".build"))
    ap.add_argument("--zip", default="littleprince-launcher.zip")
    ap.add_argument("--skip-exe", action="store_true", help="reuse the last built exe")
    ap.add_argument("--guide", help="a GUIDE.md to put in the zip")
    a = ap.parse_args()

    exe = (APP / "target" / "release" / "littleprince-launcher.exe") if a.skip_exe else build_exe()
    out = Path(a.out)
    root = out / "littleprince-launcher"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    for f in tracked_files():
        target = root / f
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / f, target)
    shutil.copy2(exe, root / EXE_NAME)
    # Built with the GNU toolchain, the exe loads WebView2Loader.dll at run time
    # (Microsoft's redistributable loader, shipped in the webview2-com-sys crate)
    loader = webview2_loader()
    if loader:
        shutil.copy2(loader, root / "WebView2Loader.dll")
    python_runtime(root / "runtime" / "python")
    if a.guide:
        shutil.copy2(a.guide, root / "GUIDE.md")

    zpath = out / a.zip
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                z.write(p, Path("littleprince-launcher") / p.relative_to(root))
    data = zpath.read_bytes()
    print("%s  %.1f MB  sha256 %s" % (zpath, len(data) / 1e6, hashlib.sha256(data).hexdigest()))


if __name__ == "__main__":
    main()
