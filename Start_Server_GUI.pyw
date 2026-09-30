#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Little Prince Launcher — server window (Windows entry point)
============================================================

The Windows launcher: it shows whether the local server is running, which port it
is on, whether the hosts redirect is active, how many requests the games have
made, and the live log - and it stops the server and reverts the hosts file when
you close the window.

The WINDOW itself is launcher_ui.py at the root of the pack. This file contains
the Windows backend - the hosts file, the port-80 admin check and the servers -
plus the entry point Start.bat runs.

Run it by double-clicking  Start_Server_GUI.pyw  (or: python Start_Server_GUI.pyw)

    --port N        port to listen on (default 80, needs admin on Windows)
    --no-hosts      do not touch the hosts file (testing)
    --online-port N port for Little Prince Online (default 8080)
    --no-online     do not run the online server or the multiplayer relay
    --no-elevate    do not ask for administrator rights
    --selftest      start, self-check, stop - no window (used by the packager)
"""

import importlib.util
import json
from pathlib import Path
import logging
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import fake_server as srv          # the server itself (same folder)
import launcher_ui                 # the window both platforms draw  (same folder)
from lpo.pack_download import clean_download_settings, validate_pack_url, open_pack

APP_TITLE = "Little Prince Launcher — server"
VERSION = "1.1"


def _messagebox():
    """tkinter, imported where it is used so --selftest needs no display."""
    from tkinter import messagebox
    return messagebox


# ─────────────────────────── platform helpers ────────────────────────────────

def is_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    """Windows: restart this script elevated (UAC prompt)."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        params = " ".join('"%s"' % a for a in sys.argv)
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, HERE, 1)
        return rc > 32
    except Exception:
        return False


# ─────────────────────────── the server wrapper ──────────────────────────────

class Server:
    """Runs fake_server's socket loop in a thread and reports its state."""

    def __init__(self, port=80, use_hosts=True):
        self.port = port
        self.use_hosts = use_hosts
        self.running = False
        self.started_at = None
        self.requests = 0
        self.last_error = ""
        self.hosts_active = False
        self.redirect_was_present = False
        self._sock = None
        self._thread = None
        self.lines = []                       # captured log
        self.watchers = []                    # callbacks for new log lines

    # -- log capture --------------------------------------------------------
    def attach_log_capture(self):
        original = srv.log

        def capture(msg):
            line = time.strftime("%H:%M:%S") + " " + str(msg)
            if " POST " in line or " GET " in line:      # a real request from the game
                self.requests += 1
            self.lines.append(line)
            del self.lines[:-800]
            for cb in list(self.watchers):
                try:
                    cb(line)
                except Exception:
                    pass
            return original(msg)

        srv.log = capture

    # -- lifecycle ----------------------------------------------------------
    def start(self):
        if self.running:
            return True
        if self.use_hosts:
            before = srv.HOSTS_STATE.get('added')
            srv.hosts_ensure()
            self.hosts_active = bool(srv.HOSTS_STATE.get('added'))
            self.redirect_was_present = bool(srv.HOSTS_STATE.get('added')) and not before
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", self.port))
            sock.listen(8)
        except OSError as e:
            self.last_error = str(e)
            srv.log("Could not bind port %d: %s" % (self.port, e))
            if self.port == 80:
                srv.log("Port 80 needs administrator rights - "
                        "use the 'Run as admin' button.")
            if self.use_hosts:
                srv.hosts_revert()
                self.hosts_active = False
            return False
        self._sock = sock
        self.running = True
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._accept_loop, args=(sock,), daemon=True)
        self._thread.start()
        srv.log("listening on 0.0.0.0:%d  (all three games)" % self.port)
        srv.log("checkVersion -> 0.0,,   everything else -> e000 / valid=true")
        return True

    def _accept_loop(self, sock):
        while self.running:
            try:
                conn, addr = sock.accept()
            except OSError:
                break
            threading.Thread(target=srv.handle_client, args=(conn, addr), daemon=True).start()

    def stop(self, revert=True):
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self.running = False
        if revert and self.use_hosts:
            srv.hosts_revert()
            self.hosts_active = False
        srv.log("server stopped")

    def revert_hosts(self):
        srv.hosts_revert()
        self.hosts_active = False

    def uptime(self):
        if not self.running or not self.started_at:
            return "—"
        secs = int(time.time() - self.started_at)
        return "%02d:%02d:%02d" % (secs // 3600, (secs % 3600) // 60, secs % 60)

    def probe(self):
        """Is the port accepting connections? (a bare connect - no request, no log line)"""
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=1.0):
                pass
            return True
        except Exception as e:
            self.last_error = str(e)
            return False


class Relay:
    """LAN multiplayer relay for Little Prince Online (mp_relay.py, ws :8443)."""

    def __init__(self, port=8443):
        self.port = port
        self.running = False
        self.last_error = ""
        self._proc = None
        self._handler = None

    def start(self):
        if self.running:
            return True
        try:
            path = os.path.join(HERE, "lpo", "mp_relay.py")
            if not os.path.isfile(path):
                self.last_error = "lpo/mp_relay.py is missing"
                return False
            self._proc = subprocess.Popen(
                [sys.executable, "-u", path, "--port", str(self.port)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                cwd=os.path.dirname(path),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.running = True
            threading.Thread(target=self._pump, daemon=True).start()
            # the child binds asynchronously - wait until it answers, and fail
            # honestly when the port is already taken (e.g. a second launcher)
            for _ in range(20):
                time.sleep(0.15)
                if self.probe():
                    break
            else:
                self.last_error = "port %d did not open (already in use?)" % self.port
                self.running = False
        except Exception as e:
            self.last_error = str(e)
            self.running = False
        return self.running

    def _pump(self):
        try:
            for raw in iter(self._proc.stdout.readline, b""):
                line = raw.decode("utf-8", "replace").rstrip()
                if line and self._handler:
                    self._handler(line)
        except Exception:
            pass

    def stop(self):
        if self._proc is not None:
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=3)      # give it a moment to go
                except Exception:
                    self._proc.kill()               # ...then make sure it did
            except Exception:
                pass
            self._proc = None
        self.running = False

    def probe(self):
        if not self.running:
            return False
        try:
            import socket as _s
            c = _s.create_connection(("127.0.0.1", self.port), timeout=2)
            c.close()
            return True
        except Exception:
            return False


class Online:
    """Little Prince Online: game gateway + account website, on its own port."""

    def __init__(self, port=8080):
        self.port = port
        self.running = False
        self.last_error = ""
        self.game_dir = ""
        self.swfs = 0
        self._srv = None
        self._mod = None
        self._handler = None

    def _load(self):
        path = os.path.join(HERE, "lpo", "server.py")
        if not os.path.isfile(path):
            raise FileNotFoundError("lpo/server.py is missing")
        lpo_dir = os.path.dirname(path)          # its siblings: amf0.py, accounts.py
        if lpo_dir not in sys.path:
            sys.path.insert(0, lpo_dir)
        spec = importlib.util.spec_from_file_location("lpo_server", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def start(self):
        if self.running:
            return True
        try:
            mod = self._load()
            mod.PORT = self.port
            try:
                srv.ONLINE_PORT = self.port      # keep the relay pointing at us
            except Exception:
                pass
            self.game_dir = str(mod.GAME_DIR)
            self.swfs = len(list(mod.GAME_DIR.glob("**/*.swf")))

            class _Sink(logging.Handler):
                def emit(inner, record):
                    try:
                        (self._handler or (lambda m: None))(inner.format(record))
                    except Exception:
                        pass

            sink = _Sink()
            sink.setFormatter(logging.Formatter("%(message)s"))
            mod.log.addHandler(sink)
            self._srv = mod.ReusableTCPServer((mod.HOST, self.port), mod.LittlePrinceHandler)
            threading.Thread(target=self._srv.serve_forever, daemon=True).start()
            self._mod = mod
            self.running = True
            # Work out the game state once, in the background.  The check stats
            # every file in the mirror and took about ten seconds on a Windows
            # machine, and the portal asks for it the moment it opens.
            try:
                threading.Thread(target=lambda: mod.cloud_state_reply(fresh=True),
                                 daemon=True).start()
            except Exception:                                         # noqa: BLE001
                pass
        except OSError as e:
            self.last_error = "port %d is busy (%s)" % (self.port, e)
            self.running = False
        except Exception as e:
            self.last_error = str(e)
            self.running = False
        return self.running

    def stop(self):
        if self._srv is not None:
            try:
                self._srv.shutdown()
                self._srv.server_close()
            except Exception:
                pass
            self._srv = None
        self.running = False


ONLINE_GAME_URL = "http://www1.little-prince.com.hk/LP/Po/"


def browser_url(redirect_ready, port):
    """Where to send the browser: always the local address.

    Opening the publisher's own hostname only works when the browser honours the
    hosts redirect - and browsers that do their own DNS (DNS over HTTPS) do not,
    in which case the page is served by the real site and the game's login fails.
    The 127.0.0.1 page always comes from this machine, so that is what Play online
    opens; the game's own address stays available for anyone who wants it.

    The Flash page, not /play: the pack plays with real Flash in the publisher's
    browser, and the install-free Ruffle page is switched off.
    """
    return "http://127.0.0.1:%d/play-flash" % port


def open_url(url, dry_run=False):
    """Open a url in the default browser, with a Windows fallback."""
    if dry_run:
        return url
    try:
        import webbrowser
        if webbrowser.open(url):
            return url
    except Exception:
        pass
    try:
        os.startfile(url)
    except Exception:
        pass
    return url


def open_in_browser(redirect_ready, port, dry_run=False):
    url = browser_url(redirect_ready, port)
    if dry_run:
        return url
    try:
        import webbrowser
        if webbrowser.open(url):
            return url
    except Exception:
        pass
    try:                                    # Windows fallback when no browser is registered
        os.startfile(url)
    except Exception:
        pass
    return url


def cloud_row_state(codes, state_of):
    """(ready, message) for several cloud games shown as one row.

    Kept outside the dialog so it can be exercised without a display - the three
    cloud games are one choice now, and their counts are what the row reports.
    """
    states = [(c,) + tuple(state_of(c)) for c in codes]
    if all(r for _, r, _ in states):
        parts = []
        for c, _ready, message in states:
            num = re.search(r"([\d,]+) files?", message)
            parts.append("%s %s" % (c, num.group(1) if num else "?"))
        return True, "ready - %s files verified" % " · ".join(parts)
    return False, " · ".join("%s: %s" % (c, message)
                             for c, ready, message in states if not ready)


# Pack downloads use Catbox and Pixeldrain, with no Google Drive fallback.
# The server also supports HTTP(S) self-hosted pack URLs in download settings.
#
# catbox.moe takes 200 MB per file, so the two big packs (LP2 ~300 MB, LP3
# ~352 MB) cannot move there and stay on pixeldrain, whose links drop after 120
# days of no access.  Everything that fits is on catbox now.
PACK_SOURCES = {
    "LP1": ["https://files.catbox.moe/hqrqto.zip"],
    "LP2": ["https://pixeldrain.com/api/file/jirbPgbb"],
    "LP3": ["https://pixeldrain.com/api/file/jPAAE3e8"],
    "lpo": ["https://files.catbox.moe/1kdpb0.zip"],
    "browser": ["https://files.catbox.moe/epshu2.zip"],
}
PACK_MB = {"LP1": 94, "LP2": 300, "LP3": 352, "lpo": 10, "browser": 134}

# Anonymous hosts such as catbox.moe drop the connection when a request arrives
# with no User-Agent or with Python's default one, so the download says who it is.
# Without this a catbox link looks like a dead mirror and the next source is tried.
PACK_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) littleprince-launcher/1.0"


def fetch_pack(urls, dest, log=print, on_progress=None):
    """Download the first pack URL that works and unpack it into `dest`.

    The archives keep the package layout (`cloud/LP1/...`), so unpacking into the
    package root puts every file where the manifest expects it.  Returns the number
    of files written, or raises when every URL failed.
    """
    import tempfile
    import urllib.request
    import zipfile

    last = None
    for url in urls:
        try:
            log("downloading %s" % url)
            with open_pack(url, timeout=120) as r:
                total = int(r.headers.get("Content-Length") or 0)
                got = 0
                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                    tmp_name = tmp.name
                    while True:
                        chunk = r.read(262144)
                        if not chunk:
                            break
                        tmp.write(chunk)
                        got += len(chunk)
                        if on_progress is not None:
                            on_progress(got, total)
            log("unpacking into %s" % dest)
            with zipfile.ZipFile(tmp_name) as zf:
                members = [n for n in zf.namelist() if not n.endswith("/")]
                zf.extractall(str(dest))
            os.unlink(tmp_name)
            log("unpacked %d file(s)" % len(members))
            return len(members)
        except Exception as exc:                                      # noqa: BLE001
            last = exc
            log("%s failed: %s" % (url, str(exc)[:120]))
    raise last if last else RuntimeError("no download source")


# ──────────────────────── the launcher's own words ───────────────────────────
# Everything the Windows launcher draws is named here, so the language badge
# switches the whole window and not just the games behind it.
TR = {
    "en": {
        "play": "Play",
        "download": "Download",
        "menu": "Menu",
        "menu_play": "Play Little Prince",
        "admin_run": "Run as administrator",
        "sec_server": "SERVER",
        "server_start": "Start",
        "server_stop": "Stop",
        "server_revert": "Revert the hosts redirect",
        "sec_user": "USER",
        "user_site": "Accounts site",
        "user_billboard": "Billboard and game files (accounts page)",
        "user_folder": "Open the accounts folder",
        "user_profile": "Open the profile file",
        "sec_patches": "PATCHES",
        "patch_files": "SWF patch files (CD copy)",
        "sec_download": "DOWNLOAD METHOD",
        "settings_open": "Settings",
        "settings": "Settings",
        "settings_save": "Save",
        "settings_close": "Close",
        "settings_saved": "Saved - applies to the next download",
        "dl_auto": "Auto (default) - try each source in turn",
        "dl_official": "Official server (file by file)",
        "dl_pixeldrain": "Catbox / Pixeldrain mirrors",
        "dl_custom": "Self-hosted / custom URL",
        "dl_url_hint": "pack URL per game (used by 'A URL I give'):",
        "dl_save": "Save download settings",
        "sec_logs": "LOGS",
        "logs_open": "Server Logs",
        "brw_title": "Get the publisher's browser",
        "brw_ask": "The publisher's own browser plays these three games with real "
                   "Flash, which looks better than the built-in player.\n\n"
                   "Download it from the publisher (about 67 MB, once), then point "
                   "it at this machine?\n\nIt is stored in browser/ and can be "
                   "deleted at any time. There is no registration and no "
                   "activation email.",
        "brw_win": "Getting the publisher's browser",
        "brw_head": "Downloading the publisher's browser",
        "brw_first_title": "Download the publisher's browser first",
        "brw_first_ask": "The three games open in the publisher's own browser, "
                         "which has real Flash.\n\n"
                         "Download it now? (about 67 MB, once)\n\n"
                         "No  -  open the portal in your normal browser instead.  "
                         "Each game still downloads from the portal when you press "
                         "it.",
        "files_title": "Download the game files",
        "files_ask": "Download the official Little Prince Online files?\n\n"
                     "%d files, about %.0f MB, straight from the publisher's "
                     "server:\n    %s\n\n"
                     "They are stored in lpo\\game and only fetched once.%s",
        "LP1": ("Little Prince", "When happiness meets courage"),
        "LP2": ("Starwish Legend", "The vanishing constellation"),
        "LP3": ("Prince Adventure", "Farm adventure"),
        "LPO": ("Little Prince Online", "A new way to learn online"),
    },
    "zh": {
        "play": "進入遊戲",
        "download": "下載",
        "menu": "選單",
        "menu_play": "開始遊戲",
        "admin_run": "以管理員身分執行",
        "sec_server": "伺服器",
        "server_start": "啟動",
        "server_stop": "停止",
        "server_revert": "還原 hosts 轉向",
        "sec_user": "使用者",
        "user_site": "帳號網站",
        "user_billboard": "佈告欄與遊戲檔案（帳號網站）",
        "user_folder": "開啟帳號資料夾",
        "user_profile": "開啟個人檔案",
        "sec_patches": "修補檔",
        "patch_files": "SWF 修補檔（CD 版）",
        "sec_download": "下載方式",
        "settings_open": "設定",
        "settings": "設定",
        "settings_save": "儲存",
        "settings_close": "關閉",
        "settings_saved": "已儲存 － 下次下載時生效",
        "dl_auto": "自動（預設）－ 依次嘗試每個來源",
        "dl_official": "官方伺服器（逐個檔案）",
        "dl_pixeldrain": "Catbox / Pixeldrain 鏡像",
        "dl_custom": "自訂網址",
        "dl_url_hint": "每個遊戲的鏡像網址（供「自訂網址」使用）：",
        "dl_save": "儲存下載設定",
        "sec_logs": "記錄",
        "logs_open": "伺服器記錄",
        "brw_title": "取得官方瀏覽器",
        "brw_ask": "官方瀏覽器用真正的 Flash 執行這三個遊戲，畫面比內建的播放器好。"
                   "\n\n要從官方網站下載（約 67 MB，只需一次）並用它開啟這個網站嗎？"
                   "\n\n它會存放在 browser/ 資料夾，隨時可以刪除。不需要註冊，也不需要"
                   "驗證信。",
        "brw_win": "正在取得官方瀏覽器",
        "brw_head": "正在下載官方瀏覽器",
        "brw_first_title": "請先下載官方瀏覽器",
        "brw_first_ask": "這三個遊戲要在官方瀏覽器裡執行，才有真正的 Flash。"
                         "\n\n現在下載嗎？（約 67 MB，只需一次）\n\n"
                         "選「否」會用你平常的瀏覽器開啟遊戲選單，按下去時遊戲依然"
                         "會從選單下載。",
        "files_title": "下載遊戲檔案",
        "files_ask": "要下載星願小王子 ONLINE 的官方檔案嗎？\n\n"
                     "共 %d 個檔案，約 %.0f MB，直接從官方伺服器下載：\n    %s\n\n"
                     "檔案會存放在 lpo\\game，只會下載一次。%s",
        "LP1": ("星願小王子", "當幸福遇見勇氣"),
        "LP2": ("星願外傳", "星座消失之謎"),
        "LP3": ("星願歷奇", "農場大作戰"),
        "LPO": ("星願小王子 ONLINE", "網上學習新體驗"),
    },
}

GAME_CODES = ("LP1", "LP2", "LP3", "LPO")


def profile_path():
    """The player record the games read their TextLanguage from."""
    return Path(os.path.join(HERE, "lpo", "profile.json"))


def read_language():
    return launcher_ui.read_language(profile_path())


def tr(key):
    """The current language's wording for a key."""
    table = TR.get(read_language(), TR["en"])
    if key in table:
        return table[key]
    return TR["en"].get(key, key)


def name_sub(code):
    """The game's title and tagline, in the current language."""
    got = tr(code)
    return got if isinstance(got, tuple) else (code, "")


# the protocol chatter the games emit is meaningless to a player, so the marquee
# under the banner skips it and shows the last line that says something
CHATTY = ("checkVersion", "-> 0.0", "e000", "valid=", "getmonthscorerank",
          "canplaymaze", "mazerec", "getmyfriends", "getmonthmazerank",
          "checkupdateversion", "havenewemail", "login4", "totalitems", "checkmail")


def last_log_line():
    """The newest readable line of the server log - the launcher's marquee."""
    try:
        path = Path(srv.LOG_PATH)
        size = path.stat().st_size
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(max(0, size - 6000))
            lines = [ln.strip() for ln in fh.read().splitlines() if ln.strip()]
    except (OSError, AttributeError):
        return ""
    for line in reversed(lines):
        body = line.split(" ", 1)[-1] if line[:8].count(":") == 2 else line
        if not any(tag in body for tag in CHATTY):
            return line[:110]
    return lines[-1][:110] if lines else ""


# ─────────────────────────────── the window ──────────────────────────────────
# WindowsBackend is what Start_Server_GUI's window is: launcher_ui.py draws it and
# this class answers for the servers, the hosts file and the downloads.

class WindowsBackend:
    """The Windows side of the launcher: hosts redirect, port 80, in-process servers."""

    name = APP_TITLE
    title = APP_TITLE
    version = VERSION
    background_start = False        # the servers here run inside this process
    mono_font = ("Consolas", 9)

    def __init__(self, port=80, use_hosts=True, online_port=8080, online=True):
        self.port = port
        self.use_hosts = use_hosts
        self.online_port = online_port
        self.server = Server(port=port, use_hosts=use_hosts)
        self.server.attach_log_capture()
        self.online_srv = Online(port=online_port) if online else None
        self.relay_srv = Relay(port=8443) if online else None
        self.ui = None
        self._mp_value = "—"           # the multiplayer row only speaks when it runs
        self._verify = {"at": 0.0, "ready": {}, "note": "", "busy": False}
        self._settings_file = os.path.join(HERE, "lpo", "download-settings.json")

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def assets_dir(self):
        return HERE

    # ── the servers ─────────────────────────────────────────────────────────
    def running(self):
        return bool(self.server.running)

    def status(self):
        if self.server.running:
            return "Server running", True
        return ("Server stopped — see log" if self.server.last_error
                else "Server stopped"), False

    def start(self):
        """Start whatever is not running yet - the old Start button, unchanged."""
        ui = self.ui
        if not self.server.running:
            if not is_admin() and self.port == 80:
                ui.note("not elevated - port 80 will probably fail; "
                        "use 'Run as admin'")
            self.server.start()
        # the online game does not need the CD-box port: start it either way
        if self.online_srv is not None and not self.online_srv.running:
            if self.online_srv.start():
                self.online_srv._handler = lambda m: ui.say(m)
                ui.note("online server started on port %d (%d game files)"
                        % (self.online_srv.port, self.online_srv.swfs))
            else:
                ui.note("online server did NOT start: %s" % self.online_srv.last_error)
        # LAN multiplayer relay: auto-start with the server so two machines in
        # the same network can battle; it costs nothing when nobody uses it
        if self.relay_srv is not None and not self.relay_srv.running:
            if self.relay_srv.start():
                self.relay_srv._handler = ui.say
                ui.note("LAN multiplayer relay started on port %d" % self.relay_srv.port)
            else:
                ui.note("multiplayer relay did NOT start: %s" % self.relay_srv.last_error)
        ui.refresh()
        if self.server.running:
            ui.root.after(400, ui.test_clicked)
            ui.note("server started on port %d" % self.port)

    def stop(self):
        if self.server.running:
            self.server.stop()
        if self.online_srv is not None and self.online_srv.running:
            self.online_srv.stop()
            self.ui.note("online server stopped")
        if self.relay_srv is not None and self.relay_srv.running:
            self.relay_srv.stop()
            self.ui.note("LAN multiplayer relay stopped")
        self.ui.refresh()

    def test(self):
        if not self.server.running:
            return "the server is not running"
        ok = self.server.probe()
        return "connection test: %s" % ("ok - port %d answers" % self.port if ok
                                        else "failed - %s" % self.server.last_error)

    def revert_hosts(self):
        self.server.revert_hosts()

    def stats(self):
        rows = []
        if self.server.hosts_active and self.server.running:
            rows.append(("hosts", "active"))
        elif self.server.hosts_active:
            rows.append(("hosts", "stale"))
        else:
            rows.append(("hosts", "off"))
        rows.append(("requests", str(self.server.requests)))
        rows.append(("uptime", self.server.uptime()))
        rows.append(("user", "admin" if is_admin() else "not admin"))
        if self.online_srv is None:
            rows.append(("online", "not included"))
        elif self.online_srv.running:
            rows.append(("online", "%d game files" % self.online_srv.swfs))
        else:
            rows.append(("online", "stopped" + (" (%s)" % self.online_srv.last_error
                                                if self.online_srv.last_error else "")))
        if self.relay_srv is None:
            rows.append(("multiplayer", "not included"))
        else:
            if self.relay_srv.running:
                self._mp_value = ("on (:%d)" % self.relay_srv.port
                                  if self.relay_srv.probe() else "on (no answer)")
            rows.append(("multiplayer", self._mp_value))
        return rows

    def footer(self):
        if self.server.hosts_active:
            return "The game domains point at this PC while this window is open."
        if self.use_hosts:
            return ("The hosts redirect is off - run as administrator to turn it on.")
        return "Started with --no-hosts, so the redirect stays untouched."

    def close(self):
        """Ask before pulling the rug out; True lets the window go."""
        ui = self.ui
        busy = bool(self.server.running) or bool(self.online_srv is not None
                                                and self.online_srv.running)
        if busy:
            try:
                if not _messagebox().askyesno(
                        APP_TITLE,
                        "Closing this window stops the local server.\n\n"
                        "If you are in the middle of a game it will stop too.\n\n"
                        "Close anyway?"):
                    return False
            except Exception as exc:                                    # noqa: BLE001
                # never trap someone in the window because a dialog would not draw
                ui.note("could not show the close confirmation (%s) - closing" % exc)
        if self.server.running:
            self.server.stop()
        elif self.use_hosts:
            srv.hosts_revert()
        if self.online_srv is not None and self.online_srv.running:
            self.online_srv.stop()
        # The relay is the one child that is a real process (mp_relay.py), not an
        # in-process thread - without this it outlived the window and had to be
        # killed from Task Manager by hand.
        if self.relay_srv is not None and self.relay_srv.running:
            self.relay_srv.stop()
        return True

    def background(self):
        return False

    def error_log_path(self):
        return os.path.join(HERE, "lpo", "launcher-error.log")

    # ── the log, the marquee, the drawer ────────────────────────────────────
    def attach_log(self, sink):
        self.server.watchers.append(sink)

    def startup_lines(self):
        lines = []
        if self.online_srv is not None:
            lines.append("Little Prince Online will start on port %d "
                         "(accounts page /web)" % self.online_srv.port)
        if not self.use_hosts:
            lines.append("hosts file left untouched (--no-hosts)")
        if not is_admin():
            lines.append("not running as administrator - port 80 and the hosts "
                         "file need admin rights")
        lines.append("starting the server - this window can stay open while you play.")
        path = getattr(self.ui, "log_path", None)
        if path:
            lines.append("everything printed here is also saved to %s" % path)
        return lines

    def autostart(self):
        return "--no-autostart" not in sys.argv

    def tick(self):
        self.verify_snapshot()

    def status_line(self):
        return last_log_line()

    def menu_title(self):
        return tr("menu")

    def menu(self):
        """The hamburger's list, live: the rows grey out against the real state."""
        rows = [(tr("menu_play"), self.choose_game, True)]
        if not is_admin():
            rows.append((tr("admin_run"), self.run_as_admin, True))
        sections = [(None, rows)]
        sections.append((tr("sec_server"), [
            (tr("server_start"), self.ui.start_clicked, not self.server.running),
            (tr("server_stop"), self.ui.stop_clicked, bool(self.server.running)),
            (tr("server_revert"), self.ui.revert_clicked, bool(self.use_hosts)),
        ]))
        sections.append((tr("sec_user"), [
            (tr("user_site"), self.open_website, True),
            (tr("user_billboard"), self.open_billboard, True),
            (tr("user_folder"), lambda: self.open_folder(os.path.join(HERE, "lpo")),
             True),
            (tr("user_profile"),
             lambda: self.open_folder(os.path.join(HERE, "lpo", "profile.json")), True),
        ]))
        sections.append((tr("sec_patches"), [
            (tr("patch_files"), self.open_patch_files, True),
        ]))
        sections.append((None, [(tr("settings_open"), self.open_settings, True)]))
        sections.append((tr("sec_logs"), [
            (tr("logs_open"), self.open_log, True),
        ]))
        return sections

    def open_accounts(self):
        """The accounts page - what the user badge in the title strip opens."""
        import webbrowser
        port_used = self.online_srv.port if self.online_srv is not None else self.online_port
        url = "http://127.0.0.1:%d/web" % port_used
        self.ui.note("opening %s" % url)
        try:
            webbrowser.open(url)
        except Exception as e:                                          # noqa: BLE001
            self.ui.note("could not open a browser (%s) - the page is at %s" % (e, url))

    # ── the banner ──────────────────────────────────────────────────────────
    def games(self):
        out = []
        for code in GAME_CODES:
            name, sub = name_sub(code)
            out.append((code, name, sub))
        return out

    def default_game(self):
        return "LP1"

    def play_label(self, code):
        return tr("play")

    def play(self, code):
        """What the banner's button does: the 3-in-1 portal, for every tab.

        LP1/LP2/LP3 are one product and LPO plays through the same portal; the old
        route dived into find_client() and greeted a fresh machine with the 900 MB
        client dialog before anything else.
        """
        self.open_portal()

    # ── the language ────────────────────────────────────────────────────────
    def profile_path(self):
        return profile_path()

    def is_admin(self):
        return is_admin()

    def relaunch_as_admin(self):
        return relaunch_as_admin()

    def run_as_admin(self):
        if relaunch_as_admin():
            self.ui.root.destroy()

    # ── the drawer's other actions ──────────────────────────────────────────
    def choose_game(self):
        """Drawer entry: same as Play - the 3-in-1 portal, not a per-game picker."""
        self.open_portal()

    def open_billboard(self):
        """The accounts page - where the billboard and the client folder live.

        The old /admin page is gone: those settings are an ADMIN group on the
        accounts page now, and they need a signed-in account.  /admin still
        redirects there for anyone holding the old link.
        """
        import webbrowser
        port_used = self.online_srv.port if self.online_srv is not None else self.online_port
        url = "http://127.0.0.1:%d/web" % port_used
        self.ui.note("opening %s - the ADMIN group is in the list on the left" % url)
        try:
            webbrowser.open(url)
        except Exception as e:                                          # noqa: BLE001
            self.ui.note("could not open a browser (%s) - the page is at %s" % (e, url))

    def open_website(self):
        import webbrowser
        url = "http://127.0.0.1:%d/web" % (self.online_srv.port if self.online_srv
                                          else self.online_port)
        if self.online_srv is None or not self.online_srv.running:
            self.ui.note("start the server first - the accounts page is at %s" % url)
        else:
            self.ui.note("opening %s" % url)
        try:
            webbrowser.open(url)
        except Exception as e:
            self.ui.note("could not open a browser (%s)" % e)

    def open_log(self):
        # Everything the window prints is teed into one txt file (the pane trims
        # its backlog and clamps to the bottom, so the file is the full record).
        path = getattr(self.ui, "log_path", None) or srv.LOG_PATH
        try:
            os.startfile(path)                          # Windows only
        except Exception as e:
            self.ui.note("could not open the log file (%s) - it is at %s" % (e, path))

    def open_folder(self, path):
        """Reveal a file or folder in whatever the platform uses for that."""
        try:
            if os.name == "nt":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])
            self.ui.note("opened %s" % path)
        except Exception as e:                                          # noqa: BLE001
            self.ui.note("could not open %s (%s)" % (path, e))

    SWF_PACK_URL = "https://files.catbox.moe/lpzlzd.zip"

    def open_patch_files(self):
        """Open the download for the patched CD/web SWFs."""
        note = self.ui.note
        note("SWF patch files: %s" % self.SWF_PACK_URL)
        note("  only needed for a CD or website copy you already have - the games")
        note("  in this launcher need no CD files at all")
        try:
            import webbrowser
            webbrowser.open(self.SWF_PACK_URL)
        except Exception as exc:                                      # noqa: BLE001
            note("could not open a browser (%s)" % exc)
            note("open this link yourself: %s" % self.SWF_PACK_URL)

    # ── the settings page ───────────────────────────────────────────────────
    def open_settings(self):
        """Where the game files come from.

        The server reads this file on every download, so a change applies the next
        time the button is pressed - no restart needed.  The page itself is the
        shared one in launcher_ui.py.
        """
        try:
            with open(self._settings_file, encoding="utf-8") as fh:
                saved = json.load(fh)
        except Exception:                                             # noqa: BLE001
            saved = {}
        saved = clean_download_settings(saved)
        radios = [(tr("sec_download"),
                   [(tr("dl_auto"), "auto"),
                    (tr("dl_pixeldrain"), "pixeldrain"),
                    (tr("dl_custom"), "custom")])]
        entries = [(tr("dl_url_hint"),
                    [(code, 48) for code in ("LP1", "LP2", "LP3", "lpo", "browser")])]
        custom = saved.get("custom") or {}
        launcher_ui.open_settings_window(
            self.ui, tr("settings"), radios, entries, self._save_settings,
            values={"radio": {tr("sec_download"): str(saved.get("method") or "auto")},
                    "text": {code: str(custom.get(code) or "")
                             for code in ("LP1", "LP2", "LP3", "lpo", "browser")}},
            save_label=tr("settings_save"), close_label=tr("settings_close"))

    def _save_settings(self, chosen, text_vars):
        custom = {code: var.get().strip() for code, var in text_vars.items()
                  if var.get().strip()}
        method = list(chosen.values())[0] if chosen else "auto"
        try:
            for url in custom.values():
                validate_pack_url(url)
            settings = clean_download_settings({"method": method, "custom": custom})
            method, custom = settings["method"], settings["custom"]
            with open(self._settings_file, "w", encoding="utf-8") as fh:
                json.dump({"method": method, "custom": custom}, fh,
                          indent=2, ensure_ascii=False)
        except Exception as exc:                                      # noqa: BLE001
            return False, "could not save (%s)" % exc
        note = self.ui.note
        note("download method saved: %s" % method)
        for code in sorted(custom):
            note("  %s: %s" % (code, custom[code]))
        note("  takes effect on the next download - no restart needed")
        return True, tr("settings_saved")

    # ── the state of the game files ─────────────────────────────────────────
    def verify_snapshot(self, force=False):
        """The last verification result - never a fresh scan on this thread.

        It hashes every file in the mirror, which took seconds once a download was
        writing thousands of files - and it ran from the window's own refresh, so
        the launcher simply stopped responding.  The scan runs on its own thread
        and this reports whatever it last found.
        """
        now = time.time()
        stale = force or not self._verify["ready"] or now - self._verify["at"] > 15
        if stale and not self._verify["busy"]:
            self._verify["busy"] = True

            def work():
                ready, trouble = {}, []
                for code in ("LP1", "LP2", "LP3"):
                    try:
                        ok, msg = self.cloud_state(code)
                    except Exception as exc:                          # noqa: BLE001
                        ok, msg = False, "could not check %s (%s)" % (code, str(exc)[:40])
                    ready[code] = ok
                    if not ok:
                        trouble.append(msg)
                good = sum(1 for v in ready.values() if v)
                if good == 3:
                    note = "all three games verified on this machine"
                elif trouble:
                    note = trouble[0]
                else:
                    note = "%d of 3 games ready" % good
                self._verify.update({"ready": ready, "note": note, "at": time.time()})
                self._verify["busy"] = False

            threading.Thread(target=work, daemon=True).start()
        return self._verify

    def _load_cloud_fetcher(self):
        """The cloud mirror fetcher, loaded from lpo/fetch_cloud.py."""
        path = os.path.join(HERE, "lpo", "fetch_cloud.py")
        if not os.path.exists(path):
            return None
        spec = importlib.util.spec_from_file_location("lpo_cloud", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def cloud_state(self, code):
        """(ready, message) for a mirrored game, checked against the manifest."""
        cloud = Path(os.path.join(HERE, "cloud"))
        folder = cloud / code
        if not folder.is_dir():
            return False, "not mirrored - cloud/%s is missing from the package" % code
        mod = self._load_cloud_fetcher()
        if mod is None:
            files = len([f for f in os.listdir(folder) if f.lower().endswith(".swf")])
            return bool(files), ("ready - %d files on this machine" % files) if files else \
                                "nothing in cloud/%s" % code
        try:
            missing, wrong = mod.check(cloud)          # the manifest lives at cloud/files.txt
            total = len([r for r, _ in mod.read_manifest(cloud) if r.startswith(code + "/")])
            # The CD's client files are exactly the manifest's sizes, so the check
            # above cannot see them - but they are the ones that ask for a serial
            # number.  Count them as missing, or the launcher offers "Play" for a
            # game that cannot be played.
            try:
                stale = mod.client_bad(cloud, code)
            except Exception:                                         # noqa: BLE001
                stale = []
        except Exception as exc:                                     # noqa: BLE001
            return True, "ready - could not verify (%s)" % str(exc)[:30]
        bad = len([r for r in missing + wrong if r.startswith(code + "/")]) + len(stale)
        if total and not bad:
            return True, "ready - all %d files verified" % total
        if stale:
            return False, ("the CD's client files are in cloud/%s (%s) - Play replaces "
                           "them with the publisher's" % (code, ", ".join(stale)))
        if bad:
            return False, "%d of %d files missing - Play fetches them" % (bad, total)
        files = len([f for f in os.listdir(folder) if f.lower().endswith(".swf")])
        return bool(files), ("ready - %d files on this machine" % files) if files else \
                            "nothing in cloud/%s" % code

    def game_ready(self, code):
        """Is this one game already here?  Cheap - the snapshot is cached."""
        if code == "LPO":
            return bool(self.online_srv is not None and self.online_srv.swfs)
        return bool(self.verify_snapshot()["ready"].get(code))

    # ── the downloads ───────────────────────────────────────────────────────
    def _load_fetcher(self):
        path = os.path.join(HERE, "lpo", "fetch_client.py")
        spec = importlib.util.spec_from_file_location("lpo_fetch", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _load_browser_fetcher(self):
        """The publisher's browser fetcher, loaded from lpo/fetch_browser.py."""
        path = os.path.join(HERE, "lpo", "fetch_browser.py")
        if not os.path.exists(path):
            return None
        spec = importlib.util.spec_from_file_location("lpo_browser", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def download_client_dialog(self, when_done=None):
        """Fetch the official client with a progress window.  True when the files are
        in place afterwards."""
        ui = self.ui
        mb = _messagebox()
        try:
            fetcher = self._load_fetcher()
        except Exception as e:                                   # noqa: BLE001
            mb.showerror(APP_TITLE, "Could not load the downloader:\n%s" % e)
            return False
        dest = os.path.join(HERE, "lpo", "game")
        rows = fetcher.read_manifest()
        size_mb = sum(s for _, s in rows) / 1e6
        warning = ""
        if self.server.hosts_active:
            warning = ("\n\nNote: the hosts redirect is active, so the game's own "
                       "address currently points at this computer and cannot serve a "
                       "download.\n\nThe download goes straight to the publisher's real "
                       "address instead. If it cannot work that out, press 'Revert "
                       "hosts', restart the server, and try again.")
        elif self.use_hosts and os.name == "nt":
            warning = ("\n\nIf you later turn the hosts redirect on, note that the "
                       "publisher's address then points at this computer - turn it off "
                       "again before downloading more files.")
        if not mb.askyesno(
                tr("files_title"),
                tr("files_ask") % (len(rows), size_mb, fetcher.DEFAULT_BASE, warning)):
            return False

        cancel = threading.Event()
        updates = queue.Queue()
        state = {"done": False, "result": None, "error": ""}
        holder = {}

        def on_cancel():
            cancel.set()
            if holder.get("dlg") is not None:
                holder["dlg"].detail.set("cancelling ...")

        dlg = launcher_ui.ProgressDialog(ui, "Downloading the game files",
                                        "Downloading the official game files",
                                        cancel=on_cancel, warn=True)
        holder["dlg"] = dlg

        def worker():
            try:
                state["result"] = fetcher.fetch(
                    dest=dest, workers=6, cancel=cancel,
                    progress=lambda st: updates.put(st),
                    log=lambda m: ui.note(m.strip()))
            except BaseException as e:                            # noqa: BLE001
                state["error"] = str(e)
            state["done"] = True

        def tick():
            last = None
            while True:
                try:
                    last = updates.get_nowait()
                except queue.Empty:
                    break
            if last:
                pct = 100.0 * last["bytes"] / max(1, last["total_bytes"])
                detail = ("%d / %d files   %.0f / %.0f MB   %s"
                          % (last["files"], last["total"], last["bytes"] / 1e6,
                             last["total_bytes"] / 1e6, last["current"][:34]))
                notes = [n.strip() for n in last.get("notes", []) if n.strip()]
                dlg.set(pct, detail, notes[-1] if notes else None)
            if state["done"]:
                dlg.close()
                return
            dlg.win.after(150, tick)

        threading.Thread(target=worker, daemon=True).start()
        dlg.win.after(150, tick)
        ui.root.wait_window(dlg.win)

        res = state["result"]
        if state["error"]:
            mb.showwarning(APP_TITLE, "The download stopped:\n\n%s" % state["error"])
            return False
        if not res:
            return False
        if res["failed"]:
            mb.showwarning(
                APP_TITLE,
                "%d of %d files could not be downloaded.\n\n"
                "Run it again - it continues where it stopped."
                % (len(res["failed"]), res["total"]))
        done = res["ok"] + res["skipped"]
        ui.note("game files: %d of %d in place (%s)" % (done, res["total"], dest))
        if done and when_done is not None:
            when_done()
        return bool(done) and not res["failed"]

    # ── the publisher's browser ─────────────────────────────────────────────
    def browser_exe(self):
        """(exe, is_our_copy) for the publisher's browser, if it is on this machine."""
        mod = self._load_browser_fetcher()
        if mod is None:
            return None, False
        try:
            return mod.find(Path(os.path.join(HERE, "browser")))
        except Exception as exc:                                     # noqa: BLE001
            self.ui.note("could not look for the browser (%s)" % exc)
            return None, False

    def browser_here(self):
        """(exe path, is_our_patched_copy); (None, False) when it is not here."""
        try:
            exe, ours = self.browser_exe()
            return exe, bool(ours)
        except Exception as exc:                                          # noqa: BLE001
            self.ui.note("could not look for the publisher's browser (%s)" % exc)
            return None, False

    def ensure_browser_patched(self):
        """Keep our copy able to take a page argument, even if it was fetched earlier.

        Idempotent, and it never touches an install that is not ours.
        """
        mod = self._load_browser_fetcher()
        if mod is None:
            return
        try:
            mod.patch(Path(os.path.join(HERE, "browser")), log=lambda m: None)
        except Exception as exc:                                          # noqa: BLE001
            self.ui.note("could not update the publisher's browser (%s)" % exc)

    def auto_get_browser(self):
        """Fetch the publisher's browser without asking, once the game is here.

        It plays the game with real Flash instead of Ruffle, and the request was
        explicitly for this to happen by itself after the game files download.
        """
        if self.browser_here()[0]:
            return True
        mod = self._load_browser_fetcher()
        if mod is None:
            return False
        self.ui.note("the publisher's browser is not here - fetching it now "
                     "(real Flash)")
        return self.download_browser_dialog(mod, ask=False)

    def background_get_browser(self):
        """Fetch the publisher's browser on a thread, no questions, no window.

        For the case where the game files were already there: the publisher's browser
        is fetched now so the next press of Play can hand the game to real Flash.
        """
        if self.browser_here()[0] or getattr(self, "_bg_browser", False):
            return
        mod = self._load_browser_fetcher()
        if mod is None:
            return
        dest = Path(os.path.join(HERE, "browser"))
        self._bg_browser = True
        ui = self.ui

        def worker():
            try:
                ui.note("fetching the publisher's browser in the background "
                        "(real Flash for the next Play)")
                ok = mod.download(dest, log=lambda m: ui.note(str(m).strip()))
                ui.note("publisher's browser ready - Play will use real Flash"
                        if ok else "could not fetch the publisher's browser")
            except BaseException as exc:                                  # noqa: BLE001
                ui.note("browser fetch failed: %s" % exc)
            finally:
                self._bg_browser = False

        threading.Thread(target=worker, daemon=True).start()

    def launch_browser(self, exe, url=None):
        """Start the publisher's browser, optionally straight at `url`.

        With no argument it opens our portal page; the game passes the real-Flash
        player's address instead (main.js takes the first http(s) argument).
        """
        cmd = [str(exe)] + ([str(url)] if url else [])
        try:
            subprocess.Popen(cmd, cwd=str(Path(exe).parent))
            return True
        except Exception as exc:                                     # noqa: BLE001
            try:
                os.startfile(str(exe))
                return True
            except Exception:                                        # noqa: BLE001
                self.ui.note("could not start the browser (%s)" % exc)
                return False

    def download_browser_dialog(self, mod, ask=True):
        """Download and patch the publisher's browser, with a progress window.

        `ask=False` skips the question: the launcher fetches it by itself once the
        game files are in, which is what was asked for.
        """
        ui = self.ui
        dest = Path(os.path.join(HERE, "browser"))
        if ask and not _messagebox().askyesno(tr("brw_title"), tr("brw_ask")):
            return False
        dlg = launcher_ui.ProgressDialog(ui, tr("brw_win"), tr("brw_head"), length=440)
        state = {"done": False, "ok": False}
        seen = queue.Queue()

        def worker():
            def say(message):
                ui.note(message.strip())
                seen.put(message.strip())
            try:
                state["ok"] = mod.download(dest, log=say)
            except BaseException as exc:                             # noqa: BLE001
                ui.note("browser download failed: %s" % exc)
            state["done"] = True

        def tick():
            while True:
                try:
                    line = seen.get_nowait()
                except queue.Empty:
                    break
                value = None
                m = re.search(r"([0-9.]+) / ([0-9.]+) MB", line)
                if m:
                    done_mb, total_mb = float(m.group(1)), float(m.group(2))
                    if total_mb:
                        value = 100.0 * done_mb / total_mb
                dlg.set(value if value is not None else dlg.meter["value"], line)
            if state["done"]:
                dlg.close()
                return
            dlg.win.after(300, tick)

        threading.Thread(target=worker, daemon=True).start()
        dlg.win.after(300, tick)
        ui.root.wait_window(dlg.win)
        if state["ok"]:
            ui.note("publisher's browser ready in browser/ (patched to this machine)")
        else:
            _messagebox().showwarning(APP_TITLE, "The browser could not be downloaded.")
        return bool(state["ok"])

    # ── the three CD games' mirrors ─────────────────────────────────────────
    def download_pack_dialog(self, code):
        """Fetch one game as a single archive instead of file-by-file.

        True when cloud/<code> verifies complete afterwards; False when the pack
        could not be fetched, so the caller falls back to the per-file fetch.
        """
        ui = self.ui
        urls = PACK_SOURCES.get(code) or []
        mod = self._load_cloud_fetcher()
        if not urls or mod is None:
            return False
        cloud = Path(os.path.join(HERE, "cloud"))
        if not _messagebox().askyesno(
                "Download %s" % code,
                "Fetch %s as one archive (about %d MB) and unpack it into the "
                "package?\n\nQuicker than pulling the files one by one.\n\n%s"
                % (code, PACK_MB.get(code, 0), urls[0])):
            return False

        dlg = launcher_ui.ProgressDialog(ui, "Downloading %s" % code,
                                         "Downloading %s" % code, length=440)
        state = {"done": False}

        def on_progress(got, total):
            if total:
                dlg.set(100.0 * got / total, "%.1f of %.1f MB" % (got / 1e6, total / 1e6))
            else:
                dlg.set(0, "%.1f MB" % (got / 1e6))

        def worker():
            try:
                n = fetch_pack(urls, HERE, log=lambda m: ui.note(m),
                               on_progress=on_progress)
                ui.note("%s: unpacked %d file(s)" % (code, n))
            except BaseException as exc:                             # noqa: BLE001
                ui.note("%s: pack download failed (%s)" % (code, str(exc)[:120]))
            state["done"] = True

        threading.Thread(target=worker, daemon=True).start()

        def tick():
            if state["done"]:
                dlg.close()
                return
            dlg.win.after(200, tick)

        dlg.win.after(200, tick)
        ui.root.wait_window(dlg.win)

        left_missing, left_wrong = mod.check(cloud)
        left = [r for r in left_missing + left_wrong if r.startswith(code + "/")]
        ui.refresh()
        if left:
            ui.note("%s: %d file(s) still missing after the pack" % (code, len(left)))
            return False
        ui.note("%s: complete" % code)
        return True

    def download_cloud_dialog(self, code, when_done=None):
        """Fetch the missing files of one mirrored game.  True when it ended complete."""
        ui = self.ui
        mod = self._load_cloud_fetcher()
        if mod is None:
            _messagebox().showerror(APP_TITLE, "Could not load lpo\\fetch_cloud.py")
            return False
        cloud = Path(os.path.join(HERE, "cloud"))
        missing, wrong = mod.check(cloud)
        wanted = set(r for r in missing + wrong if r.startswith(code + "/"))
        if not wanted:
            return True
        sizes = dict(mod.read_manifest(cloud))
        mb = sum(sizes.get(rel, 0) for rel in wanted) / 1e6
        warning = ""
        if self.server.hosts_active:
            warning = ("\n\nThe hosts redirect is active, so the publisher's name points at "
                       "this computer. The download goes to the real address instead; if it "
                       "cannot, press 'Revert hosts', restart the server, and try again.")
        if not _messagebox().askyesno(
                "Download the game files",
                "Fetch the %d missing file(s) of %s from the publisher's server?\n\n"
                "About %.0f MB, stored in cloud\\%s and fetched only once.%s"
                % (len(wanted), code, mb, code, warning)):
            return False

        dlg = launcher_ui.ProgressDialog(ui, "Downloading %s" % code,
                                         "Downloading the %s files" % code, length=440)
        state = {"done": False, "ok": 0, "failed": []}

        def worker():
            try:
                done, failed = mod.fetch(cloud, only=wanted,
                                         log=lambda m: ui.say(m.strip()))
                state["ok"], state["failed"] = done, failed
            except BaseException as exc:                             # noqa: BLE001
                state["failed"] = [("", str(exc))]
            state["done"] = True

        def tick():
            missing_now, wrong_now = mod.check(cloud)
            left = len([r for r in wanted if r not in set(missing_now + wrong_now)])
            dlg.set(100.0 * left / max(1, len(wanted)),
                    "%d of %d files in place" % (left, len(wanted)))
            if state["done"]:
                dlg.close()
                return
            dlg.win.after(200, tick)

        threading.Thread(target=worker, daemon=True).start()
        dlg.win.after(200, tick)
        ui.root.wait_window(dlg.win)

        left_missing, left_wrong = mod.check(cloud)
        left = [r for r in left_missing + left_wrong if r.startswith(code + "/")]
        if left:
            _messagebox().showwarning(
                APP_TITLE,
                "%d file(s) still missing.\n\nRun it again - it continues where it stopped."
                % len(left))
            return False
        ui.note("%s: files complete (%d fetched)" % (code, state["ok"]))
        ui.refresh()
        if when_done is not None:
            when_done()
        return True

    # ── the online client ───────────────────────────────────────────────────
    def client_looks_complete(self):
        """Do the game's own entry movies sit in the folder the server is serving?

        Counting .swf files was not enough: half a client folder passed, and the player
        then met the browser's download page with no explanation of what was missing.
        """
        root = str(getattr(self.online_srv, "game_dir", "") or "")
        if not root:
            return False
        try:
            return all(os.path.isfile(os.path.join(root, name))
                       for name in ("index.swf", "login.swf"))
        except Exception:                                             # noqa: BLE001
            return False

    def find_client(self):
        """The client files are missing: let the user point at the folder instead of
        just telling them about it.  Remembers the choice for next time."""
        from tkinter import filedialog
        ui = self.ui
        mb = _messagebox()
        online_srv = self.online_srv
        if online_srv is not None and online_srv.swfs and self.client_looks_complete():
            return True
        answer = mb.askyesnocancel(
            APP_TITLE,
            "This package does not include the Little Prince Online game files.\n\n"
            "Yes  -  download the official files now (about 900 MB, once)\n"
            "No  -  I already have the game, let me point at its folder\n"
            "Cancel  -  not now")
        if answer is None:
            ui.note("no game files - cancelled")
            return False
        if answer:
            if not self.download_client_dialog():
                return False
            os.environ.pop("LPO_GAME_DIR", None)          # lpo/game is the destination
            if online_srv is not None:
                online_srv.stop()
                for _ in range(3):
                    if online_srv.start():
                        break
                    time.sleep(0.5)
                ui.note("online server: port %d, %d game files"
                        % (online_srv.port, online_srv.swfs))
                ui.refresh()
            ready = bool(online_srv is not None and online_srv.swfs)
            if ready:
                # the game files are in, so now the browser that plays them with
                # real Flash - fetched by itself, without a question
                self.auto_get_browser()
            return ready
        start_at = os.path.expanduser("~")
        for probe in (os.environ.get("LPO_GAME_DIR"), os.environ.get("LOCALAPPDATA"),
                      os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                      start_at):
            if probe and os.path.isdir(probe):
                start_at = probe
                break
        chosen = filedialog.askdirectory(title="Find the Little Prince Online folder",
                                         initialdir=start_at, mustexist=True)
        if not chosen:
            ui.note("no folder chosen - cancelled")
            return False

        def has_swf(d):
            try:
                return any(f.lower().endswith(".swf") for f in os.listdir(d)[:500])
            except OSError:
                return False
        if not has_swf(chosen):                      # maybe they picked the folder above it
            try:
                for d in sorted(os.listdir(chosen)):
                    sub = os.path.join(chosen, d)
                    if os.path.isdir(sub) and has_swf(sub):
                        chosen = sub
                        break
            except OSError:
                pass
        if not has_swf(chosen):
            mb.showwarning(
                APP_TITLE,
                "No .swf files in that folder.\n\n"
                "Pick the folder that contains index.swf and login.swf.")
            return False
        os.environ["LPO_GAME_DIR"] = chosen
        try:
            online_srv._mod.save_game_dir(chosen)
        except Exception:
            pass
        ui.note("game folder: %s" % chosen)
        if online_srv is not None:
            online_srv.stop()
            for _ in range(3):
                if online_srv.start():
                    break
                time.sleep(0.5)
            if not online_srv.running:
                mb.showwarning(APP_TITLE, "Could not start the game server: %s"
                               % online_srv.last_error)
                return False
            ui.note("online server: port %d, %d game files"
                    % (online_srv.port, online_srv.swfs))
            ui.refresh()
        return bool(online_srv is not None and online_srv.swfs)

    def play_clicked(self):
        """Start the server if needed, make sure the game files are there, then open
        the game in the browser."""
        ui = self.ui
        online_srv = self.online_srv
        if online_srv is None or not online_srv.running:
            if online_srv is not None and online_srv.start():
                ui.note("online server started on port %d (%d game files)"
                        % (online_srv.port, online_srv.swfs))
                ui.refresh()
        if online_srv is None or not online_srv.running:
            _messagebox().showwarning(
                APP_TITLE, "The Little Prince Online server is not running yet.")
            return
        if not self.find_client():
            return
        # Real Flash beats Ruffle.  The publisher's browser is Electron 4 carrying
        # Pepper Flash, so the game runs the way it was made - use it when it is
        # here, and quietly fetch it in the background when it is not.
        exe, ours = self.browser_here()
        if exe and ours:
            self.ensure_browser_patched()      # a copy fetched earlier may not take a URL
            # Open it on the publisher's OWN name when the hosts redirect is on.
            # A page served from 127.0.0.1 makes Flash put the movie in a local
            # sandbox, and the game's gateway lives on www1.little-prince.com.hk -
            # the redirect points that name straight back here, so on the real name
            # the movie and the gateway are on the same host and nothing is blocked.
            if getattr(self.server, "hosts_active", False):
                target = "http://www1.little-prince.com.hk/play-flash"
            else:
                target = "http://127.0.0.1:%d/play-flash" % online_srv.port
                ui.note("the hosts redirect is off, so the game opens on 127.0.0.1 - "
                        "if the login hangs, start the server from this window first")
            ui.note("opening Little Prince Online in the publisher's browser")
            ui.note("  real Flash: %s" % target)
            if self.launch_browser(exe, target):
                return
            ui.note("could not start it - the publisher's browser is needed to play;")
            ui.note("  if it is still downloading, press Play online again when it is done")
        else:
            if exe:
                ui.note("the publisher's browser here is an official install, not our "
                        "patched copy, so it cannot be pointed at this machine")
            self.background_get_browser()
        redirect_ready = bool(self.server.running and self.server.hosts_active)
        url = open_in_browser(redirect_ready, online_srv.port)
        if redirect_ready:
            ui.note("opened %s - the game's own address, served by the local server"
                    % url)
            ui.note("if the browser shows the official site instead, switch off its "
                    "DNS-over-HTTPS setting (Firefox: Settings > Privacy & Security > "
                    "DNS over HTTPS > Off) - the hosts file is ignored while it is on")
        elif self.server.hosts_active:
            ui.note("the hosts file still sends the game domains to this PC, but the "
                    "server that answers them is not running - press 'Start server' "
                    "(as administrator) or 'Revert hosts', then press Play online again")
            ui.note("opened %s in the meantime" % url)
        else:
            ui.note("opened %s - the hosts redirect is off, so the browser may ask to "
                    "allow local-network access" % url)

    def portal_url(self):
        port = self.online_srv.port if self.online_srv is not None else self.online_port
        return "http://127.0.0.1:%d/LP/personal/" % port

    def open_portal(self):
        """The 3-in-1: publisher's browser first, then the portal that lists all
        three games.  LP1/LP2/LP3 are fetched from the greyed cards on that page,
        never from this window.
        """
        ui = self.ui
        online_srv = self.online_srv
        if online_srv is None or not online_srv.running:
            if online_srv is not None:
                online_srv.start()
                ui.refresh()
        if online_srv is None or not online_srv.running:
            _messagebox().showwarning(APP_TITLE, "The local server is not running yet.")
            return
        exe, _ours = self.browser_exe()
        if exe is None:
            mod = self._load_browser_fetcher()
            if mod is not None and _messagebox().askyesno(tr("brw_first_title"),
                                                          tr("brw_first_ask")):
                if self.download_browser_dialog(mod):
                    exe, _ = self.browser_exe()
        url = self.portal_url()
        if exe is not None:
            ui.note("opening the game portal in the publisher's browser (real Flash)")
            if not self.launch_browser(exe):
                ui.note("falling back to your normal browser at %s" % url)
                open_url(url)
            return
        ui.note("opening %s" % url)
        open_url(url)


def run_gui(port=80, use_hosts=True, online_port=8080, online=True):
    """Open the launcher window - the shared one, with the Windows backend."""
    return launcher_ui.run(WindowsBackend(port=port, use_hosts=use_hosts,
                                          online_port=online_port, online=online))


# ─────────────────────────────── self test ───────────────────────────────────

def selftest(port=8080, use_hosts=False):
    print("selftest: starting the server on port %d (hosts %s)"
          % (port, "on" if use_hosts else "off"))
    server = Server(port=port, use_hosts=use_hosts)
    server.attach_log_capture()
    assert server.start(), "server did not start"
    assert server.running, "running flag not set"
    time.sleep(0.3)
    ok = server.probe()
    print("selftest: probe ->", ok, "| requests seen:", server.requests,
          "| uptime:", server.uptime(), "| hosts active:", server.hosts_active)
    assert ok, "could not connect to the listener"
    assert server.requests == 0, "a bare connect must not count as a game request"
    import urllib.request
    urllib.request.urlopen("http://127.0.0.1:%d/health.php" % port, timeout=3).read()
    time.sleep(0.3)
    print("selftest: after one real request, counter =", server.requests)
    assert server.requests == 1, "a real request should be counted once"
    log_text = "\n".join(server.lines)
    for needle in ("listening on 0.0.0.0", "checkVersion ->", "e000"):
        assert needle in log_text, "log line missing: %s" % needle
    server.stop()
    assert not server.running, "still running after stop()"
    assert "server stopped" in "\n".join(server.lines), "stop was not logged"
    print("selftest: OK - log tail:")
    for line in server.lines[-8:]:
        print("   ", line)
    return 0


def main():
    port = 80
    use_hosts = True
    online_port = 8080
    online = True
    no_elevate = False
    for i, a in enumerate(sys.argv):
        if a == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
        elif a.startswith("--port="):
            port = int(a.split("=", 1)[1])
        elif a == "--no-hosts":
            use_hosts = False
        elif a == "--online-port" and i + 1 < len(sys.argv):
            online_port = int(sys.argv[i + 1])
        elif a.startswith("--online-port="):
            online_port = int(a.split("=", 1)[1])
        elif a == "--no-online":
            online = False
        elif a == "--no-autostart":
            pass                                   # handled by the backend
        elif a == "--no-elevate":
            no_elevate = True

    # Windows: ask for administrator rights before anything opens, so the window
    # never appears without them and nothing has to be pressed by hand.  The UAC
    # prompt is Windows' own - declining it just continues unelevated.
    if (os.name == "nt" and not no_elevate and not is_admin()
            and "--selftest" not in sys.argv):
        if relaunch_as_admin():
            return 0                               # the elevated copy takes over
        print("administrator rights declined - continuing without them")

    if "--selftest" in sys.argv:
        return selftest(port, use_hosts)
    run_gui(port, use_hosts, online_port, online)
    return 0


if __name__ == "__main__":
    sys.exit(main())
