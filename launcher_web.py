#!/usr/bin/env python3
"""The launcher without a Tk window - what "Little Prince Launcher.exe" runs.

The exe (launcher-app/, Tauri) shows a WebView window; this process is
everything behind it.  It drives the very same WindowsBackend the Tk window
(Start_Server_GUI.pyw) uses - the CD-games server on port 80, the hosts redirect,
Little Prince Online, the LAN relay, the publisher's browser - and serves:

    /                   launcher/ui/index.html  (the screens - plain HTML/CSS/JS,
    /ui/...             edited without rebuilding the exe)
    /banners/...        the key art
    /cards/...          the portal's card art (cloud/images)
    /api/...            the launcher's own JSON calls (state, play, open, ...)
    /game/...           forwarded to the game server's /web/api/... (download
                        state, downloads, 星夜重圓's licence and start)

on 127.0.0.1 only, on the port the exe picked (--ui-port).

Run by hand from a source checkout:  python launcher_web.py --ui-port 8099
and open http://127.0.0.1:8099/ in any browser.
"""

import ast
import collections
import itertools
import json
import os
import sys
import threading
import time
import types
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
UI_DIR = Path(HERE) / "launcher" / "ui"
LOG_KEEP = 400


# ─── Tk-free imports ─────────────────────────────────────────────────────────

def _stub_launcher_ui():
    """Start_Server_GUI imports launcher_ui (Tk) at the top.  Without tkinter - the
    bundled Python has none - give it a module with just what this process uses:
    the two language helpers, read straight out of launcher_ui.py so they stay
    the same functions."""
    try:
        import tkinter  # noqa: F401
        return
    except Exception:                                                 # noqa: BLE001
        pass
    src = (Path(HERE) / "launcher_ui.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef)
            and n.name in ("read_language", "write_language")]
    mod = types.ModuleType("launcher_ui")
    mod.__dict__.update({"json": json, "os": os})
    exec(compile(ast.Module(body=keep, type_ignores=[]), "launcher_ui.py", "exec"),
         mod.__dict__)
    sys.modules["launcher_ui"] = mod


def _load_backend_module():
    import importlib.machinery
    import importlib.util
    path = os.path.join(HERE, "Start_Server_GUI.pyw")
    loader = importlib.machinery.SourceFileLoader("lp_launcher", path)
    spec = importlib.util.spec_from_loader("lp_launcher", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lp_launcher"] = mod
    loader.exec_module(mod)
    return mod


# ─── what the backend calls "the window" ─────────────────────────────────────

class _Root:
    """ui.root for the backend: after() and destroy() without Tk."""

    def __init__(self, ui):
        self.ui = ui

    def after(self, ms, fn, *args):
        t = threading.Timer(ms / 1000.0, fn, args)
        t.daemon = True
        t.start()
        return t

    def destroy(self):
        self.ui.quit_requested = True

    def wait_window(self, *_a, **_k):
        return None


class Prompts:
    """Tk's messagebox, answered from the page: a question waits (on its own
    thread) until the player clicks, or until it times out as "no"."""

    def __init__(self):
        self.lock = threading.Lock()
        self.ids = itertools.count(1)
        self.open = {}            # id -> {"title", "text", "kind", "event", "answer"}
        self.toasts = collections.deque(maxlen=20)

    def _ask(self, kind, title, message, timeout=600):
        pid = next(self.ids)
        item = {"id": pid, "kind": kind, "title": str(title), "text": str(message),
                "event": threading.Event(), "answer": None}
        with self.lock:
            self.open[pid] = item
        item["event"].wait(timeout)
        with self.lock:
            self.open.pop(pid, None)
        return bool(item["answer"])

    def answer(self, pid, value):
        with self.lock:
            item = self.open.get(int(pid))
        if item:
            item["answer"] = bool(value)
            item["event"].set()
        return bool(item)

    def pending(self):
        with self.lock:
            return [{k: v for k, v in i.items() if k in ("id", "kind", "title", "text")}
                    for i in self.open.values()]

    def toast(self, kind, title, message):
        self.toasts.append({"id": next(self.ids), "kind": kind, "title": str(title),
                            "text": str(message), "at": time.time()})

    # the messagebox interface the backend uses
    def askyesno(self, title, message, **_k):
        return self._ask("yesno", title, message)

    def askokcancel(self, title, message, **_k):
        return self._ask("yesno", title, message)

    def showwarning(self, title, message, **_k):
        self.toast("warning", title, message)

    def showerror(self, title, message, **_k):
        self.toast("error", title, message)

    def showinfo(self, title, message, **_k):
        self.toast("info", title, message)


class WebUI:
    """The object the backend calls `ui`: notes go to the log the page shows and to
    logs/launcher.log (the same file the Tk window wrote)."""

    def __init__(self, backend):
        self.backend = backend
        self.root = _Root(self)
        self.lines = collections.deque(maxlen=LOG_KEEP)
        self.seq = 0
        self.lock = threading.Lock()
        self.quit_requested = False
        self.task = None              # {"label", "pct", "detail"} while something runs
        log_dir = os.path.join(HERE, "logs")
        os.makedirs(log_dir, exist_ok=True)
        self.log_path = os.path.join(log_dir, "launcher.log")
        try:
            if os.path.getsize(self.log_path) > 8 * 1024 * 1024:
                os.replace(self.log_path, os.path.join(
                    log_dir, "launcher-%s.log" % time.strftime("%Y%m%d-%H%M%S")))
        except OSError:
            pass
        self._fh = open(self.log_path, "a", encoding="utf-8", errors="replace")
        self._fh.write("\n=== launcher started %s (window: launcher exe) ===\n"
                       % time.strftime("%Y-%m-%d %H:%M:%S"))
        self._fh.flush()

    def _add(self, text):
        text = str(text).rstrip()
        if not text:
            return
        with self.lock:
            for line in text.splitlines():
                self.seq += 1
                self.lines.append((self.seq, line))
            try:
                self._fh.write(text + "\n")
                self._fh.flush()
            except Exception:                                         # noqa: BLE001
                pass

    # the page asks for the download state every couple of seconds; logging each
    # of those buried everything the log is for
    QUIET = ("/web/api/cloud_state",)

    def say(self, msg):                   # server output, already timestamped
        if any(q in str(msg) for q in self.QUIET):
            return
        self._add(msg)

    def note(self, msg):                  # the launcher's own remarks
        self._add("%s %s" % (time.strftime("%H:%M:%S"), msg))

    def refresh(self):
        pass                              # the page polls /api/state

    def test_clicked(self):
        self.note(self.backend.test())

    def start_clicked(self):
        self.backend.start()

    def stop_clicked(self):
        self.backend.stop()

    def revert_clicked(self):
        self.backend.revert_hosts()
        self.note("hosts file reverted")

    def log_since(self, after):
        with self.lock:
            return [{"n": n, "t": t} for n, t in self.lines if n > after]


# ─── the launcher's actions ──────────────────────────────────────────────────

class Launcher:
    def __init__(self, mod, backend, ui, prompts):
        self.mod, self.b, self.ui, self.prompts = mod, backend, ui, prompts
        self._play_lock = threading.Lock()
        self._browser_lock = threading.Lock()
        self.playing = set()              # games getting ready after a press of Play

    # where each game is played, once its files are here
    def game_url(self, code):
        port = self.b.online_srv.port if self.b.online_srv is not None else self.b.online_port
        base = "http://127.0.0.1:%d" % port
        return {"LP1": base + "/LP/personal/LP1/", "LP2": base + "/LP/personal/LP2/",
                "LP3": base + "/LP/personal/LP3/", "LP4": base + "/lp4/games/",
                "LPO": base + "/play-flash"}.get(code, self.b.portal_url())

    def game_api(self, method, path, body=None, timeout=30):
        """Forward to the game server's /web/api/<path> (never through a proxy)."""
        port = self.b.online_srv.port if self.b.online_srv is not None else self.b.online_port
        url = "http://127.0.0.1:%d/web/api/%s" % (port, path.lstrip("/"))
        req = urllib.request.Request(url, data=body, method=method,
                                     headers={"Content-Type": "application/json"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except Exception as e:                                        # noqa: BLE001
            return 502, json.dumps({"ok": False, "error": str(e)}).encode()

    def ensure_browser(self):
        """The publisher's browser (real Flash), fetched with progress if missing."""
        with self._browser_lock:          # one download, however many games wait for it
            return self._ensure_browser()

    def _ensure_browser(self):
        exe, _ours = self.b.browser_exe()
        if exe is not None:
            self.b.ensure_browser_patched()
            return exe
        fetcher = self.b._load_browser_fetcher()
        if fetcher is None:
            return None
        lang = self.mod.read_language()
        self.ui.task = {"label": "下載遊戲瀏覽器" if lang == "zh" else "Getting the game browser",
                        "pct": 0, "detail": ""}
        import re

        def say(msg):
            msg = str(msg).strip()
            self.ui.note(msg)
            m = re.search(r"([0-9.]+) / ([0-9.]+) MB", msg)
            if m and float(m.group(2)):
                self.ui.task["pct"] = round(100.0 * float(m.group(1)) / float(m.group(2)), 1)
            self.ui.task["detail"] = msg[:90]
        try:
            ok = fetcher.download(Path(os.path.join(HERE, "browser")), log=say)
        except BaseException as exc:                                  # noqa: BLE001
            self.ui.note("browser download failed: %s" % exc)
            ok = False
        finally:
            self.ui.task = None
        if not ok:
            self.prompts.toast("error", "Little Prince Launcher",
                               "The game browser could not be downloaded - see the log.")
            return None
        exe, _ = self.b.browser_exe()
        return exe

    def cloud_state(self):
        code, body = self.game_api("GET", "cloud_state")
        try:
            return (json.loads(body.decode("utf-8")) or {}).get("games") or {}
        except Exception:                                             # noqa: BLE001
            return {}

    def fetch_game(self, code):
        """Download one game's files and wait for them - True when they are here."""
        st = self.cloud_state().get(code) or {}
        if st.get("ready") and not st.get("downloading"):
            return True
        self.ui.note("%s is not on this PC yet - downloading it first" % code)
        if not st.get("downloading"):
            status, body = self.game_api("POST", "cloud_download",
                                         json.dumps({"code": code}).encode(), timeout=60)
            try:
                reply = json.loads(body.decode("utf-8"))
            except Exception:                                         # noqa: BLE001
                reply = {}
            if status >= 400 or reply.get("ok") is False:
                self.prompts.toast("error", code, reply.get("error") or "the download did not start")
                return False
        deadline = time.time() + 3 * 3600
        time.sleep(2)
        while time.time() < deadline:
            st = self.cloud_state().get(code) or {}
            if st.get("error"):
                self.prompts.toast("error", code, st["error"])
                return False
            if st.get("ready") and not st.get("downloading"):
                self.ui.note("%s downloaded" % code)
                return True
            time.sleep(1.5)
        return False

    def play(self, code):
        """One press: download the game if it is missing, fetch the publisher's
        browser (at the same time) if that is missing, then open the game in it."""
        b = self.b
        if b.online_srv is not None and not b.online_srv.running:
            b.online_srv.start()
        if b.online_srv is None or not b.online_srv.running:
            self.prompts.toast("error", "Little Prince Launcher",
                               "The local server is not running - see the log.")
            return
        with self._play_lock:
            if code in self.playing:
                return                    # a second press while it is still getting ready
            self.playing.add(code)
        try:
            browser = {}
            getter = threading.Thread(target=lambda: browser.update(exe=self.ensure_browser()),
                                      daemon=True)
            getter.start()
            if not self.fetch_game(code):
                return
            getter.join()
            self._launch(code, browser.get("exe"))
        finally:
            with self._play_lock:
                self.playing.discard(code)

    def _launch(self, code, exe):
        b = self.b
        url = self.game_url(code)
        if exe is None:
            self.ui.note("opening %s in your normal browser" % url)
            self.mod.open_url(url)
            return
        self.ui.note("opening %s in the publisher's browser (real Flash)" % code)
        b.launch_browser(exe, url)

    def open(self, what):
        b = self.b
        port = b.online_srv.port if b.online_srv is not None else b.online_port
        base = "http://127.0.0.1:%d" % port
        import webbrowser
        if what in ("accounts", "billboard"):
            webbrowser.open(base + "/web")
        elif what == "mods":
            webbrowser.open(base + "/mods")
        elif what == "portal":
            exe = self.ensure_browser()
            if exe is not None:
                b.launch_browser(exe, b.portal_url())
            else:
                webbrowser.open(b.portal_url())
        elif what == "log":
            b.open_log()
        elif what == "folder":
            b.open_folder(HERE)
        elif what == "patches":
            b.open_patch_files()
        else:
            return False
        return True

    def server(self, action):
        if action == "start":
            self.b.start()
        elif action == "stop":
            self.b.stop()
        elif action == "revert":
            self.ui.revert_clicked()
        elif action == "test":
            self.ui.test_clicked()
        else:
            return False
        return True

    def settings(self):
        try:
            with open(self.b._settings_file, encoding="utf-8") as fh:
                saved = json.load(fh)
        except Exception:                                             # noqa: BLE001
            saved = {}
        saved = self.mod.clean_download_settings(saved)
        return {"method": saved.get("method") or "auto", "custom": saved.get("custom") or {},
                "codes": ["LP1", "LP2", "LP3", "lpo", "browser"]}

    def save_settings(self, data):
        try:
            custom = {k: str(v).strip() for k, v in (data.get("custom") or {}).items()
                      if str(v).strip()}
            for url in custom.values():
                self.mod.validate_pack_url(url)
            clean = self.mod.clean_download_settings(
                {"method": data.get("method") or "auto", "custom": custom})
            with open(self.b._settings_file, "w", encoding="utf-8") as fh:
                json.dump(clean, fh, indent=2, ensure_ascii=False)
        except Exception as exc:                                      # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        self.ui.note("download method saved: %s" % clean.get("method"))
        return {"ok": True}

    def state(self, after=0):
        b, mod = self.b, self.mod
        lang = mod.read_language()
        running, = (bool(b.server.running),)
        online = b.online_srv is not None and b.online_srv.running
        games = []
        for code, name, sub in b.games():
            games.append({"code": code, "name": name, "sub": sub,
                          "banner": "/banners/hero_%s.png" % code.lower()})
        return {
            "version": getattr(mod, "VERSION", ""),
            "lang": lang,
            "admin": bool(mod.is_admin()),
            "running": running, "online": online,
            "hosts": bool(b.server.hosts_active),
            "stats": [[k, v] for k, v in b.stats()],
            "footer": b.footer(),
            "marquee": mod.last_log_line(),
            "games": games,
            "log": self.ui.log_since(after),
            "prompts": self.prompts.pending(),
            "toasts": list(self.prompts.toasts),
            "task": self.ui.task,
            "playing": sorted(self.playing),
        }

    def quit(self):
        """Stop everything the way closing the Tk window did - without asking."""
        b = self.b
        try:
            if b.server.running:
                b.server.stop()
            elif b.use_hosts:
                self.mod.srv.hosts_revert()
            if b.online_srv is not None and b.online_srv.running:
                b.online_srv.stop()
            if b.relay_srv is not None and b.relay_srv.running:
                b.relay_srv.stop()
        finally:
            self.ui.note("launcher closed - servers stopped")


# ─── HTTP ────────────────────────────────────────────────────────────────────

CTYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
          ".js": "text/javascript; charset=utf-8", ".png": "image/png",
          ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".woff": "font/woff",
          ".woff2": "font/woff2", ".ico": "image/x-icon", ".json": "application/json"}
STATIC = {"/ui/": UI_DIR, "/banners/": Path(HERE) / "banners",
          "/cards/": Path(HERE) / "cloud" / "images", "/fonts/": Path(HERE) / "cloud" / "css"}


def make_handler(app, httpd_box):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LittlePrinceLauncher"

        def log_message(self, *_a):
            pass

        def _send(self, code, body, ctype="application/json"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            try:
                return raw, (json.loads(raw.decode("utf-8")) if raw else {})
            except Exception:                                         # noqa: BLE001
                return raw, {}

        def _static(self, path):
            for prefix, root in STATIC.items():
                if path.startswith(prefix):
                    rel = path[len(prefix):]
                    target = (root / rel).resolve()
                    try:
                        target.relative_to(root.resolve())
                    except ValueError:
                        return self._send(403, {"error": "outside"})
                    if not target.is_file():
                        return self._send(404, {"error": "not found"})
                    return self._send(200, target.read_bytes(),
                                      CTYPES.get(target.suffix.lower(), "application/octet-stream"))
            return self._send(404, {"error": "not found"})

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            u = urlsplit(self.path)
            path = u.path
            if path in ("/", "/index.html"):
                return self._static("/ui/index.html")
            if path == "/api/ping":
                return self._send(200, {"ok": True})
            if path == "/api/state":
                after = 0
                for part in u.query.split("&"):
                    if part.startswith("after="):
                        try:
                            after = int(part[6:])
                        except ValueError:
                            pass
                return self._send(200, app.state(after))
            if path == "/api/settings":
                return self._send(200, app.settings())
            if path.startswith("/game/"):
                code, body = app.game_api("GET", path[len("/game/"):] +
                                          ("?" + u.query if u.query else ""))
                return self._send(code, body)
            return self._static(path)

        def do_POST(self):
            path = urlsplit(self.path).path
            raw, data = self._body()
            if path.startswith("/game/"):
                code, body = app.game_api("POST", path[len("/game/"):], raw or b"{}",
                                          timeout=60)
                return self._send(code, body)
            if path == "/api/play":
                threading.Thread(target=app.play, args=(str(data.get("code") or "LP1"),),
                                 daemon=True).start()
                return self._send(200, {"ok": True})
            if path == "/api/open":
                threading.Thread(target=app.open, args=(str(data.get("what") or ""),),
                                 daemon=True).start()
                return self._send(200, {"ok": True})
            if path == "/api/server":
                threading.Thread(target=app.server, args=(str(data.get("action") or ""),),
                                 daemon=True).start()
                return self._send(200, {"ok": True})
            if path == "/api/lang":
                which = "zh" if data.get("lang") == "zh" else "en"
                sys.modules["launcher_ui"].write_language(app.mod.profile_path(), which)
                return self._send(200, {"ok": True, "lang": which})
            if path == "/api/settings":
                return self._send(200, app.save_settings(data))
            if path == "/api/prompt":
                return self._send(200, {"ok": app.prompts.answer(data.get("id", 0),
                                                                 data.get("answer"))})
            if path == "/api/toast/clear":
                app.prompts.toasts.clear()
                return self._send(200, {"ok": True})
            if path == "/api/quit":
                app.quit()
                self._send(200, {"ok": True})
                threading.Thread(target=lambda: (time.sleep(0.2), os._exit(0)),
                                 daemon=True).start()
                return None
            return self._send(404, {"error": "unknown call"})

    return Handler


def main():
    args = sys.argv[1:]

    def opt(name, default):
        for i, a in enumerate(args):
            if a == name and i + 1 < len(args):
                return args[i + 1]
            if a.startswith(name + "="):
                return a.split("=", 1)[1]
        return default

    ui_port = int(opt("--ui-port", "8099"))
    port = int(opt("--port", "80"))
    online_port = int(opt("--online-port", "8080"))
    use_hosts = "--no-hosts" not in args
    online = "--no-online" not in args

    _stub_launcher_ui()
    mod = _load_backend_module()
    prompts = Prompts()
    mod._messagebox = lambda: prompts             # Tk's dialogs -> the page

    backend = mod.WindowsBackend(port=port, use_hosts=use_hosts,
                                 online_port=online_port, online=online)
    ui = WebUI(backend)
    backend.ui = ui
    backend.attach_log(ui.say)
    app = Launcher(mod, backend, ui, prompts)

    for line in backend.startup_lines():
        ui.note(line)
    box = {}
    httpd = ThreadingHTTPServer(("127.0.0.1", ui_port), make_handler(app, box))
    httpd.daemon_threads = True
    box["httpd"] = httpd
    ui.note("launcher window served on http://127.0.0.1:%d/" % ui_port)
    if backend.autostart():
        threading.Thread(target=backend.start, daemon=True).start()
    try:
        httpd.serve_forever(poll_interval=0.25)
    finally:
        app.quit()


if __name__ == "__main__":
    main()
