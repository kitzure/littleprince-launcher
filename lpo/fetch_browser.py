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
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    from fetch_client import resolve_base                              # noqa: E402
except Exception:                                                      # noqa: BLE001
    resolve_base = None

BROWSER_URL = "http://www.little-prince.com.hk/littleprince/Download/LittlePrinceBrowserHome.zip"
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


def download(dest: Path, log=print, cancel=None) -> bool:
    """Fetch and unpack the browser into dest."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / "LittlePrinceBrowserHome.zip"
    url = BROWSER_URL
    host_header = ""
    if resolve_base:
        url, host_header = resolve_base(BROWSER_URL, log=log)
    part = zip_path.with_suffix(".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {}
    if host_header:
        headers["Host"] = host_header
    if have:
        headers["Range"] = "bytes=%d-" % have
        log("  resuming at %.1f MB" % (have / 1e6))
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r, open(part, "ab" if have else "wb") as fh:
        total = int(r.headers.get("Content-Length", 0)) + have
        done = have
        while True:
            if cancel is not None and cancel.is_set():
                log("  cancelled")
                return False
            chunk = r.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if total:
                log("  %.1f / %.1f MB" % (done / 1e6, total / 1e6))
    part.replace(zip_path)
    log("  downloaded %.1f MB" % (zip_path.stat().st_size / 1e6))
    with zipfile.ZipFile(zip_path) as z:
        bad = z.testzip()
        if bad:
            log("  the zip is damaged at %s" % bad)
            return False
        z.extractall(dest)
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
