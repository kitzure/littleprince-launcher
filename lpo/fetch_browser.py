#!/usr/bin/env python3
"""Get the publisher's own cloud browser and point it at this machine.

The official route (see the publisher's install guide) is: download
`LittlePrinceBrowserHome.zip`, extract it, run `LittlePrinceBrowserHome.exe`, then
register an account, wait for an activation email and bind the product before any
game opens.  None of that is needed here: the browser is Electron with Pepper Flash
(real Flash, better than the bundled Ruffle), its `resources/app/main.js` is a plain
file, and all it does is load the portal URL.  Point that URL at the local server and
the full games run offline, with the local login.

    python fetch_browser.py --check      is a browser already here?
    python fetch_browser.py              download, extract and patch it
    python fetch_browser.py --local      show the portal URL it will use
"""
import argparse
import hashlib
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pack_download import PACK_UA, validate_pack_url, _PackRedirectHandler  # noqa: E402
try:
    from fetch_client import resolve_base                              # noqa: E402
except Exception:                                                      # noqa: BLE001
    resolve_base = None

BROWSER_URL = "http://www.little-prince.com.hk/littleprince/Download/LittlePrinceBrowserHome.zip"
BROWSER_SOURCES = (("catbox", "https://files.catbox.moe/0cdlki.zip"),
                   ("official", BROWSER_URL))
BROWSER_SIZE = 67022603
BROWSER_SHA256 = "c006afdde0443435b742e53c345b8f376ee2bf33af41924ec51f71e661e79871"
PORTAL = "http://www1.little-prince.com.hk/LP/personal/"
DEFAULT_DIR = HERE.parent / "browser"          # next to the package, deleted from the zip
EXE = "LittlePrinceBrowserHome.exe"
MAIN_JS = Path("LittlePrinceBrowserHome/resources/app/main.js")


def local_portal(port=8080) -> str:
    return "http://127.0.0.1:%d/LP/personal/" % port


def find(root: Path = None):
    """An installed or downloaded copy: (exe path, is ours)."""
    roots = [root] if root else []
    roots += [DEFAULT_DIR,
              Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
              / "LittlePrinceBrowserHome",
              Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "LittlePrinceBrowserHome",
              Path.home() / "Downloads" / "LittlePrinceBrowserHome"]
    for base in roots:
        if not base:
            continue
        base = Path(base)
        for exe in (base / EXE, base / "LittlePrinceBrowserHome" / EXE):
            if exe.exists():
                return exe, base == DEFAULT_DIR
        for exe in base.rglob(EXE):
            return exe, base == DEFAULT_DIR
    return None, False


def patch(browser_dir: Path, portal: str = None, log=print) -> bool:
    """Point the browser's main.js at the local portal.  Keeps a .orig copy.

    Also teaches it to take a page argument (the real-Flash player), which matters
    for copies downloaded by an earlier build.  Safe to run again and again.
    """
    portal = portal or local_portal()
    main = browser_dir / MAIN_JS
    if not main.exists():
        log("  no %s - nothing to patch" % MAIN_JS)
        return False
    text = main.read_text(encoding="utf-8", errors="replace")
    backup = main.with_suffix(".js.orig")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")

    changed = False
    if PORTAL in text:
        text = text.replace(PORTAL, portal)
        # a second flavour the menu uses
        text = text.replace("http://www1.little-prince.com.hk/LP/personal",
                            portal.rstrip("/"))
        changed = True

    # Let the launcher ask for one page (the real-Flash player) instead of the
    # portal: the launcher runs  LittlePrinceBrowserHome.exe <url>
    if "START_URL" not in text:
        loader = "loadURL('%s')" % portal
        if loader in text:
            text = text.replace(loader, "loadURL(START_URL)", 1)
            text = text.replace(
                "function createWindow() {",
                "// The launcher may ask for a single page instead of the portal,\n"
                "// e.g. the real-Flash player:\n"
                "//     LittlePrinceBrowserHome.exe http://127.0.0.1:8080/play-flash\n"
                "const PORTAL_URL = '%s'\n"
                "const START_URL = process.argv.slice(1).find(function (a) {\n"
                "  return /^https?:\\/\\//i.test(a)\n"
                "}) || PORTAL_URL\n\n"
                "function createWindow() {" % portal, 1)
            changed = True

    # The publisher's menu offers 選擇遊戲 / 主頁 / 離開.  The online game has its own
    # card on the portal now, so a copy patched by an earlier build gets our own menu
    # entry taken back out - an extra item in their browser is one more thing to
    # explain, and the card is where it belongs.
    marker = "label: '啟動 Little Prince Online',"
    if marker in text:
        at = text.find(marker)
        line_start = text.rfind("\n", 0, at) + 1
        open_brace = text.rfind("{", 0, line_start)
        close = text.find("},", at)
        if open_brace > 0 and close > at:
            text = text[:open_brace] + text[close + 2:].lstrip("\n")
            changed = True
            log("  removed our own menu entry from the publisher's browser")

    # A "Mods" entry in the browser's own menu bar, beside 星願小王子瀏覽器.  The mods
    # live on the local server (every game reads its progress from it), so the panel
    # is a page the browser can just open - and the menu bar is the one strip that
    # sits outside the game's canvas.
    if "MR_MODS_MENU" not in text and "Menu.buildFromTemplate(template)" in text:
        host = portal.split("//", 1)[-1].split("/", 1)[0]        # 127.0.0.1:8080
        base = "http://" + host + "/"
        block = (
            "// MR_MODS_MENU: the mods panel lives on the local server; add an entry\n"
            "// to the publisher's menu bar for it (idempotent, see fetch_browser.py).\n"
            "const MODS_URL = (function () {\n"
            "  try { return new URL('/mods', START_URL).href } catch (e) { return '%smods' }\n"
            "})()\n"
            "template.push({\n"
            "  label: '模組',\n"
            "  submenu: [\n"
            "    {\n"
            "      label: '開啟模組面板',\n"
            "      click: function () { mainWindow.loadURL(MODS_URL) }\n"
            "    },\n"
            "    {\n"
            "      label: '回到遊戲選擇',\n"
            "      click: function () { mainWindow.loadURL(PORTAL_URL) }\n"
            "    },\n"
            "    { type: 'separator' },\n"
            "    {\n"
            "      label: '重新載入這個遊戲',\n"
            "      click: function () { mainWindow.reload() }\n"
            "    }\n"
            "  ]\n"
            "})\n\n" % base
        )
        text = text.replace("const menu = Menu.buildFromTemplate(template)",
                            block + "const menu = Menu.buildFromTemplate(template)", 1)
        changed = True
        log("  added the Mods entry to the browser's menu bar")

    # The browser's own menu bar is Chinese, so ours is too.  An earlier build wrote
    # it in English; translate a copy that still has those labels.
    for old, new in (("label: 'Mods',", "label: '模組',"),
                     ("label: 'Open the mods panel',", "label: '開啟模組面板',"),
                     ("label: 'Back to the games',", "label: '回到遊戲選擇',"),
                     ("label: 'Reload this game',", "label: '重新載入這個遊戲',")):
        if old in text:
            text = text.replace(old, new)
            changed = True
            log("  translated the Mods menu into the browser's own language")

    if changed:
        main.write_text(text, encoding="utf-8")
        log("  patched main.js -> %s" % portal)
        return True
    log("  main.js is already set up for %s" % portal)
    return False


def _verified_archive(path: Path) -> bool:
    """Only the complete, archived publisher build may be extracted."""
    try:
        if path.stat().st_size != BROWSER_SIZE:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        if digest.hexdigest() != BROWSER_SHA256:
            return False
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                return False
            names = set(archive.namelist())
            required = ("LittlePrinceBrowserHome/" + EXE,
                        str(MAIN_JS).replace("\\", "/"),
                        "LittlePrinceBrowserHome/resources/app/Plugins/pepflashplayer.dll")
            if not all(name in names for name in required):
                return False
            for info in archive.infolist():
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ":" in name or ".." in name.split("/"):
                    return False
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    return False
        return True
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError):
        return False


def download(dest: Path, log=print, cancel=None) -> bool:
    """Catbox archive first, official fallback; verify bytes before extracting."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / "LittlePrinceBrowserHome.zip"
    if cancel is not None and cancel.is_set():
        return False
    ready = _verified_archive(zip_path)
    if ready:
        log("  using the verified cached browser archive")
    opener = urllib.request.build_opener(_PackRedirectHandler())
    for label, source in (() if ready else BROWSER_SOURCES):
        try:
            if cancel is not None and cancel.is_set():
                return False
            validate_pack_url(source)
            url, host_header = source, ""
            # A mirror must never inherit the publisher's hosts override.
            if label == "official" and resolve_base:
                url, host_header = resolve_base(source, log=log)
            part = zip_path.with_name("LittlePrinceBrowserHome.%s.part" % label)
            have = part.stat().st_size if part.is_file() else 0
            if have >= BROWSER_SIZE:
                if _verified_archive(part):
                    part.replace(zip_path)
                    ready = True
                    break
                part.unlink()
                have = 0
            headers = {"User-Agent": PACK_UA}
            if host_header:
                headers["Host"] = host_header
            if have:
                headers["Range"] = "bytes=%d-" % have
            log("  downloading browser from %s: %s" % (label, source))
            req = urllib.request.Request(validate_pack_url(url), headers=headers)
            with opener.open(req, timeout=90) as response:
                status = response.getcode()
                if status == 206:
                    content_range = response.headers.get("Content-Range", "")
                    if not (content_range.startswith("bytes %d-" % have)
                            and content_range.endswith("/%d" % BROWSER_SIZE)):
                        part.unlink(missing_ok=True)
                        raise ValueError("incorrect partial browser response")
                    mode = "ab" if have else "wb"
                elif status == 200:
                    # A host may ignore Range: never append its complete ZIP.
                    have = 0
                    mode = "wb"
                else:
                    raise ValueError("unexpected browser HTTP status %s" % status)
                done = have
                with part.open(mode) as fh:
                    while True:
                        if cancel is not None and cancel.is_set():
                            log("  cancelled")
                            return False
                        chunk = response.read(1 << 20)
                        if not chunk:
                            break
                        fh.write(chunk)
                        done += len(chunk)
                        log("  %.1f / %.1f MB" % (done / 1e6, BROWSER_SIZE / 1e6))
            if not _verified_archive(part):
                part.unlink(missing_ok=True)
                raise ValueError("browser archive size, SHA-256 or ZIP check failed")
            part.replace(zip_path)
            ready = True
            log("  verified browser archive from %s" % label)
            break
        except Exception as exc:
            log("  browser source %s failed: %s" % (label, exc))
    if not ready:
        return False
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(dest)
    log("  extracted into %s" % dest)
    patch(dest, log=log)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="fetch and patch the publisher's cloud browser")
    ap.add_argument("--dir", default=str(DEFAULT_DIR), help="where to keep it")
    ap.add_argument("--check", action="store_true", help="report only")
    ap.add_argument("--local", action="store_true", help="print the local portal URL")
    args = ap.parse_args()

    if args.local:
        print(local_portal())
        return 0
    exe, ours = find(Path(args.dir))
    if exe:
        print("browser found: %s%s" % (exe, "  (downloaded here, patched)" if ours else
                                       "  (installed copy)"))
        if args.check:
            return 0
    elif args.check:
        print("no browser found - run this without --check to download it")
        return 1
    if not exe:
        if not download(Path(args.dir)):
            return 1
        exe, ours = find(Path(args.dir))
    print("ready: %s" % exe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
