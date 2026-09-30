#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
launcher_ui.py - the Windows Little Prince launcher window.
==================================================================

This is the launcher's presentation layer. The Windows entry point builds its
window from here:

    Start_Server_GUI.pyw          WindowsBackend   hosts redirect, port 80, admin

Everything the user sees - the title strip (hamburger, status dot, the URL, the
account badge, the ZH badge), the hero banner (the game's key art beside the
starfield panel with the title, the tagline and the game tabs), the gold hairline,
the live status line, the stats row with "Test the connection", the monospace log
console with its scrollbar, the footer, the sliding hamburger drawer, the settings
page and the download progress windows - lives in this file and nowhere else, so a
window changes remain separate from server and game logic.

A platform file supplies a BACKEND object with the interface below and calls
``launcher_ui.run(backend)``.  The window never touches a server, a port or a
subprocess itself; the backend never draws a widget.

BACKEND INTERFACE
-----------------
Identity
    name                str    window title
    title               str    short name dialogs are headed with (default: name)
    version             str    printed in the first log line
    url                 str    the address shown in the title strip
    assets_dir()        str    folder holding banners/backdrop.png, hero_<code>.png
    mono_font           tuple  the log console's font (default ("Consolas", 9))

Servers
    status()            (text, running: bool)   the dot and the word beside it
    start()             start everything (see background_start)
    stop()              stop everything
    running()           bool
    test()              str    the line "Test the connection" logs
    revert_hosts()      bool | None   None when the platform has no hosts redirect
    stats()             [(label, value), ...]   the stats row, left to right
    footer()            str    the line under the log
    close()             bool   True lets the window go (stop what you must first)
    background_start    bool   True: run start()/stop() on a worker thread
                               (Windows startup is in-process)

Menu, language, admin
    menu()              [(section_label_or_None, [(label, callable, enabled)])]
    menu_title()        str    the drawer's heading (default "Menu")
    profile_path()      path | None   the player record the EN/ZH badge writes
    is_admin()          bool
    relaunch_as_admin() bool   False -> the entry is never offered
    language_changed(lang)     optional hook, after the profile was written

The banner and the actions row
    games()             [(code, name, subtitle), ...]   one tab per game
    play(code)          what the banner's button does
    play_label(code)    str    the button's wording
    default_game()      code shown first (default: the first game)
    actions()           [(label, callable, accent), ...]  [] -> no extra row
    actions_summary()   str    the right-hand side of that row
    status_line()       str    the marquee under the banner

The log
    attach_log(sink)    hand the window's sink(text) to the servers
    startup_lines()     [str, ...]  the lines the window logs as it opens
    autostart()         bool   press Start once, by itself, after 300 ms
    tick()              optional, called on every refresh (every 0.5 s)
    error_log_path()    str    where an unhandled error is recorded

What the window's own two badges do
    open_accounts()     the account badge at the right of the title strip
    open_settings()     the settings page (see open_settings_window below)

The window sets ``backend.ui`` before anything is drawn, so a backend can use
``ui.note()`` (stamped + logged + queued for drawing), ``ui.say()`` (queue only),
``ui.refresh()`` and ``ui.button()`` from its own dialogs and worker threads.
"""

import json
import os
import queue
import sys
import threading
import time

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ──────────────────────────────── the palette ─────────────────────────────────
# One dark theme, drawn with plain tk widgets on Windows and the X11 test host.

BG, FG, DIM = "#101014", "#f2f2f2", "#9a9aa5"
PANEL, LINE = "#0b0b0b", "#26262c"
GREEN, RED, AMBER = "#3ddc84", "#ff5c5c", "#ffb020"
GOLD, GOLD_DIM = "#e8c98a", "#3a3325"      # the launcher's accent, after the portal
DRAWER_BG, DRAWER_LINE = "#15151c", "#3a3325"
ROW_ON, ROW_OFF = "#e8e8ee", "#55555f"

LOG_PER_TICK = 150        # lines drawn per refresh
LOG_MAX_LINES = 1500      # the pane is a view of the log; the log itself is on disk
LOG_QUEUE_MAX = 4000      # the pane cannot draw as fast as a download can talk


# ─────────────────────── the player record / the language ─────────────────────

def read_language(path):
    """'en' or 'zh', from the player record the games themselves read."""
    try:
        with open(path, encoding="utf-8") as fh:
            prof = json.load(fh)
    except Exception:                                                 # noqa: BLE001
        return "en"
    val = str(prof.get("textLanguage", prof.get("language", "0"))).strip().lower()
    return "zh" if val in ("1", "chi", "zh", "zh-tw", "tw", "big5") else "en"


def write_language(path, which):
    """Store the language where the game and the served pages look for it."""
    try:
        with open(path, encoding="utf-8") as fh:
            prof = json.load(fh)
    except Exception:                                                 # noqa: BLE001
        prof = {}
    val = "1" if which == "zh" else "0"
    prof["textLanguage"] = val
    prof["language"] = val
    try:
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(prof, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:                                                 # noqa: BLE001
        return False


def set_button_state(btn, enabled):
    """Grey a drawer row or an action button out, or put it back.

    Keep the disabled appearance consistent across drawer rows and action buttons.
    """
    try:
        btn.configure(state="normal" if enabled else "disabled",
                      fg=ROW_ON if enabled else ROW_OFF)
    except Exception:                                                 # noqa: BLE001
        pass


def set_button_text(btn, text):
    try:
        btn.configure(text=text)
    except Exception:                                                 # noqa: BLE001
        pass


# ───────────────────────── the shared progress window ─────────────────────────
# The Windows launcher shows one of these for each download it makes.

class ProgressDialog:
    def __init__(self, ui, title, heading, length=460, cancel=None, warn=False):
        self.ui = ui
        win = self.win = tk.Toplevel(ui.root)
        win.title(title)
        win.configure(bg=BG)
        win.transient(ui.root)
        win.resizable(False, False)
        tk.Label(win, text=heading, bg=BG, fg=FG,
                 font=(ui.font, 11, "bold")).pack(padx=18, pady=(16, 2), anchor="w")
        self.detail = tk.StringVar(value="starting ...")
        tk.Label(win, textvariable=self.detail, bg=BG, fg=DIM,
                 font=(ui.font, 9)).pack(padx=18, anchor="w")
        self.warn_var = tk.StringVar(value="")
        if warn:
            tk.Label(win, textvariable=self.warn_var, bg=BG, fg=AMBER, justify="left",
                     font=(ui.font, 8)).pack(padx=18, pady=(6, 0), anchor="w")
        self.meter = ttk.Progressbar(win, length=length, mode="determinate",
                                     maximum=100)
        self.meter.pack(padx=18, pady=10)
        if cancel is not None:
            ui.button(win, text="Cancel", command=cancel).pack(pady=(0, 16))
        win.protocol("WM_DELETE_WINDOW", lambda: None)     # no closing mid-download

    def set(self, value, detail=None, note=None):
        try:
            self.meter["value"] = value
        except Exception:                                             # noqa: BLE001
            pass
        if detail is not None:
            self.detail.set(detail)
        if note is not None:
            self.warn_var.set(note)

    def close(self):
        try:
            self.win.destroy()
        except Exception:                                             # noqa: BLE001
            pass


# ───────────────────────────── the settings page ─────────────────────────────

def open_settings_window(ui, title, radios, entries, on_save, values=None,
                         save_label=None, close_label=None):
    """The settings page, built from the Windows backend's description.

    `radios`  [(heading, [(label, value), ...])] - one group of radio buttons.
    `entries` [(heading, [(label, width), ...])] | None - one group of text fields.
    `values`  {"radio": {heading: chosen}, "text": {label: text}} | None - what is
              already saved, so the page opens on the current settings.
    `on_save(radio_values, text_vars)` -> (ok: bool, message: str); the radio
              values are the chosen ones and the text ones are StringVars.
    """
    win = tk.Toplevel(ui.root)
    win.title(title)
    win.configure(bg=BG)
    win.resizable(False, False)
    win.transient(ui.root)

    saved_radios = (values or {}).get("radio") or {}
    saved_text = (values or {}).get("text") or {}

    tk.Label(win, text=title, bg=BG, fg=FG, anchor="w",
             font=(ui.font, 15, "bold")).pack(fill="x", padx=22, pady=(18, 2))

    groups = {}
    for heading, options in radios:
        group = tk.Frame(win, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        group.pack(fill="x", padx=22, pady=(10, 0))
        tk.Label(group, text=heading, bg=PANEL, fg="#6a6a7c", anchor="w",
                 font=(ui.font, 9, "bold"), padx=16).pack(fill="x", pady=(10, 3))
        var = tk.StringVar(value=str(saved_radios.get(heading)
                                     or (options[0][1] if options else "")))
        groups[heading] = var
        for label, value in options:
            tk.Radiobutton(group, text="  " + label, value=value, variable=var,
                           bg=PANEL, fg=FG, selectcolor="#22222e", activebackground=PANEL,
                           activeforeground=GOLD, relief="flat", bd=0,
                           font=(ui.font, 10), anchor="w", padx=16, pady=2,
                           cursor="hand2", highlightthickness=0).pack(fill="x")

    text_vars = {}
    if entries:
        for heading, fields in entries:
            box = tk.Frame(win, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
            box.pack(fill="x", padx=22, pady=(8, 0))
            tk.Label(box, text=heading, bg=PANEL, fg="#6a6a7c", anchor="w",
                     font=(ui.font, 9), padx=16).pack(fill="x", pady=(10, 5))
            for label, width in fields:
                line = tk.Frame(box, bg=PANEL)
                line.pack(fill="x", padx=16, pady=2)
                tk.Label(line, text=label, bg=PANEL, fg=DIM, width=8, anchor="w",
                         font=(ui.font, 10)).pack(side="left")
                var = tk.StringVar(value=str(saved_text.get(label) or ""))
                text_vars[label] = var
                tk.Entry(line, textvariable=var, bg="#0e0e14", fg=FG,
                         insertbackground=GOLD, relief="flat", bd=0,
                         font=(ui.font, 10), width=width).pack(
                    side="left", fill="x", expand=True, ipady=3)

    row = tk.Frame(win, bg=BG)
    row.pack(fill="x", padx=22, pady=(16, 18))
    status = tk.Label(row, text="", bg=BG, fg=DIM, anchor="w", font=(ui.font, 9))

    def save():
        chosen = {h: v.get() for h, v in groups.items()}
        ok, message = on_save(chosen, text_vars)
        status.configure(text=message, fg=GOLD if ok else "#e07a7a")

    ui.button(row, text=save_label or ui.chrome("save"), command=save,
              accent=True).pack(side="left")
    ui.button(row, text=close_label or ui.chrome("close"), command=win.destroy,
              bg=PANEL, fg=FG, font=(ui.font, 10), padx=18, pady=7,
              activebackground="#22222e", activeforeground=GOLD).pack(side="left",
                                                                     padx=(8, 0))
    status.pack(side="left", padx=12)
    win.bind("<Escape>", lambda _e: win.destroy())
    win.focus_force()
    return win


# ───────────────────────────────── the window ─────────────────────────────────

class Window:
    """The launcher window, built from the Windows backend."""

    def __init__(self, root, backend):
        self.root = root
        self.backend = backend
        backend.ui = self

        tk.messagebox = messagebox
        for option, default in (("mono_font", ("Consolas", 9)),
                                ("version", ""), ("title", None)):
            if not hasattr(backend, option):
                setattr(backend, option, default)
        if backend.title is None:
            backend.title = backend.name

        self.log_queue = queue.Queue()
        self.say = self._say             # what the backend's servers call
        backend.attach_log(self.say)

        self.font = self._pick_font()
        self._build_root()
        self._build_header()
        self._build_banner()
        self._build_status_line()
        self._build_stats()
        self._build_actions()
        self._build_log()
        self._build_footer()
        self._build_drawer()
        self._size_window()

    # ── fonts, colours, the shell ───────────────────────────────────────────
    def _pick_font(self):
        """A font that really has the Chinese glyphs, used everywhere.

        Tk does not fall back per glyph: a missing glyph is a box, and a
        Latin-only font on a Chinese label looks broken.
        """
        import tkinter.font as tkfont
        present = set(tkfont.families(self.root))
        if os.name == "nt":
            first = ["Microsoft JhengHei", "Microsoft YaHei", "MingLiU"]
        else:
            first = ["Noto Sans CJK TC", "Noto Sans CJK SC", "WenQuanYi Micro Hei",
                     "AR PL UMing TW"]
        candidates = first + ["Microsoft JhengHei"]
        for name in candidates:
            if name in present:
                return name
        # Tk on X11 sometimes lists only a placeholder family, so when the list
        # looks uninformative, trust the preference order rather than fall back to
        # something that cannot draw Chinese at all
        return candidates[0] if len(present) <= 1 else "Segoe UI"

    def button(self, parent, text="", command=None, accent=False, **kw):
        """A native Tk button with the Windows launcher's appearance."""
        kw = dict(kw)
        kw.setdefault("font", (self.font, 10, "bold" if accent else "normal"))
        kw.setdefault("padx", 12)
        kw.setdefault("pady", 6)
        if accent:
            kw.setdefault("bg", GOLD)
            kw.setdefault("fg", "#1a1a1a")
            kw.setdefault("activebackground", "#f2dcae")
            kw.setdefault("activeforeground", "#1a1a1a")
        else:
            kw.setdefault("bg", "#1d1d24")
            kw.setdefault("fg", FG)
            kw.setdefault("activebackground", GOLD_DIM)
            kw.setdefault("activeforeground", GOLD)
        kw.setdefault("relief", "flat")
        kw.setdefault("bd", 0)
        # deliberately NOT highlightthickness: Tk's own default (1 on a Button) is
        # what the Windows window has always drawn, and the ring is part of its look
        kw.setdefault("cursor", "hand2")
        return tk.Button(parent, text=text, command=command, **kw)

    def chrome(self, key):
        """The window's own few words (not the platform's)."""
        return CHROME.get(key, key)

    def _build_root(self):
        root = self.root
        root.title(self.backend.name)
        root.configure(bg=BG)
        root.geometry("1060x620")          # replaced below with a width that fits
        root.resizable(False, False)       # a fixed-size launcher: nothing squashes it

        # ── never die silently ────────────────────────────────────────────────
        # Under pythonw.exe there is no console, so an unhandled error in a Tk
        # callback or on a background thread only makes the window vanish - which
        # is what "it crashes when I close the server" looks like from outside.
        def crash(kind, exc, tb=None):
            import traceback
            try:
                text = "".join(traceback.format_exception(type(exc), exc,
                                                          tb or exc.__traceback__))
            except Exception:                                         # noqa: BLE001
                text = repr(exc)
            try:
                path = self.backend.error_log_path()
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write("\n=== %s  (%s) ===\n%s\n"
                             % (time.strftime("%Y-%m-%d %H:%M:%S"), kind, text))
            except Exception:                                         # noqa: BLE001
                pass
            # The log pane is Tk, and Tk may only be touched from the thread that
            # owns it - a crash handler that calls into Tk from a worker thread is
            # a second crash waiting to happen.
            try:
                if threading.current_thread() is threading.main_thread():
                    self.note("PROBLEM (%s): %s" % (kind, exc))
                    for line in text.strip().splitlines()[-6:]:
                        self.note("   " + line)
                else:
                    self.log_queue.put("PROBLEM (%s): %s - see %s"
                                       % (kind, exc, self.backend.error_log_path()))
            except Exception:                                         # noqa: BLE001
                pass

        root.report_callback_exception = lambda t, e, tb: crash("window", e, tb)
        sys.excepthook = lambda t, e, tb: crash("launcher", e, tb)
        try:
            threading.excepthook = lambda args: crash("background", args.exc,
                                                      args.exc.__traceback__)
        except Exception:                                             # noqa: BLE001
            pass

        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:                                             # noqa: BLE001
            pass
        style.configure("TButton", padding=(10, 6))
        style.configure("Go.TButton", padding=(10, 6), font=(self.font, 10, "bold"))

    # ── the title strip ─────────────────────────────────────────────────────
    def _build_header(self):
        root = self.root
        head = self.head = tk.Frame(root, bg=BG)
        head.pack(fill="x", padx=14, pady=(12, 4))

        # a hamburger at the top left, drawn rather than typed so no font can turn
        # it into a missing-glyph box.  Its list is built when it is pressed, so it
        # always shows the live state.
        burger = tk.Canvas(head, width=26, height=22, bg=BG, highlightthickness=0,
                           cursor="hand2")
        for y in (4, 11, 18):
            burger.create_line(3, y, 23, y, fill=FG, width=2, capstyle="round")
        burger.pack(side="left", padx=(0, 10))
        burger.bind("<Button-1>", lambda _e: self.toggle_drawer())
        self.burger = burger

        dot = tk.Canvas(head, width=16, height=16, bg=BG, highlightthickness=0)
        dot.pack(side="left", padx=(0, 8))
        self.dot_id = dot.create_oval(2, 2, 14, 14, fill=RED, outline="")
        self.dot = dot

        self.status_var = tk.StringVar(value="Server stopped")
        tk.Label(head, textvariable=self.status_var, bg=BG, fg=FG,
                 font=(self.font, 13, "bold")).pack(side="left")

        # a language badge at the far right, beside the account badge
        self.lang_path = None
        try:
            self.lang_path = self.backend.profile_path()
        except Exception:                                             # noqa: BLE001
            self.lang_path = None
        if self.lang_path:
            self.lang_var = tk.StringVar(value=self._lang_badge())
            self.lang_btn = tk.Button(head, textvariable=self.lang_var,
                                      command=self.toggle_language,
                                      bg=BG, fg=GOLD, activebackground=BG,
                                      activeforeground=FG, relief="flat", bd=0,
                                      highlightthickness=0, cursor="hand2",
                                      font=(self.font, 10, "bold"), padx=6)
            self.lang_btn.pack(side="right", padx=(12, 0))

        # a user badge at the far right: it opens the accounts admin page
        badge = tk.Canvas(head, width=28, height=26, bg=BG, highlightthickness=0,
                          cursor="hand2")
        badge.create_oval(9, 3, 19, 13, outline=FG, width=2)          # head
        badge.create_arc(4, 15, 24, 30, start=0, extent=180, style="arc",
                         outline=FG, width=2)                         # shoulders
        badge.bind("<Button-1>", lambda _e: self.backend.open_accounts())
        badge.pack(side="right", padx=(12, 0))

        self.addr_var = tk.StringVar(value=self.backend.url)
        tk.Label(head, textvariable=self.addr_var, bg=BG, fg=DIM,
                 font=(self.font, 10)).pack(side="right")

    def _lang_badge(self):
        return "EN" if read_language(self.lang_path) == "en" else "ZH"

    def toggle_language(self):
        new = "en" if read_language(self.lang_path) == "zh" else "zh"
        if not write_language(self.lang_path, new):
            self.note("could not save the language")
            return
        self.lang_var.set("EN" if new == "en" else "ZH")
        self.note("language: %s" % ("English" if new == "en" else "Chinese"))
        self.note("  the games, the download page and the portal follow it from the "
                  "next game login")
        # and the launcher's own words follow it straight away
        self.reload_games()
        self.draw_words(self.selected["code"])
        self.refresh_play()
        self.rebuild_drawer()
        try:
            self.backend.language_changed(new)
        except AttributeError:
            pass

    # ── the hero banner ─────────────────────────────────────────────────────
    def _build_banner(self):
        root = self.root
        here = self.backend.assets_dir()
        hero = tk.Frame(root, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        hero.pack(fill="x", padx=14, pady=(8, 10))
        tk.Frame(hero, bg=GOLD, height=2).pack(fill="x")   # a hairline of gold

        # the starfield behind the art and the words.  A Label can carry its
        # children, which is how Tk gives a frame an image background.
        backdrop = None
        path = os.path.join(here, "banners", "backdrop.png")
        if os.path.exists(path):
            try:
                backdrop = tk.PhotoImage(file=path)
            except Exception:                                         # noqa: BLE001
                backdrop = None
        self.backdrop = backdrop
        if backdrop is not None:
            sky = tk.Label(hero, image=backdrop, bd=0, bg=PANEL)
            sky.image = backdrop                   # a reference, or Tk drops it
        else:
            sky = tk.Frame(hero, bg=PANEL)
        sky.pack(fill="both", expand=True)
        self.sky = sky

        art_holder = tk.Frame(sky, bg=PANEL)
        art_holder.pack(side="left", padx=(12, 16), pady=(0, 46))
        self.art_label = tk.Label(art_holder, bg=PANEL, bd=0)
        self.art_label.pack()

        self.art = {}
        self.reload_games()

        # ── the banner's words ─────────────────────────────────────────────────
        # The title and the tabs are drawn on a Canvas over the starfield rather
        # than packed into a panel - Tk widgets cannot be transparent, and a flat
        # panel showed as a box over the picture.  The glow is offset copies of
        # the same words, so nothing has to be installed for it to work.
        self.WORDS_W, self.WORDS_H = 452, 320
        self.WORDS_X, self.WORDS_Y = 700, 46       # which slice of the starfield shows
        words = tk.Canvas(sky, width=self.WORDS_W, height=self.WORDS_H, bg=PANEL,
                          bd=0, highlightthickness=0, cursor="hand2")
        if backdrop is not None:
            # the starfield is bigger than the column: park it so the right slice shows
            words.create_image(-self.WORDS_X, -self.WORDS_Y, image=backdrop,
                               anchor="nw")
        words.pack(side="left", anchor="center", pady=(0, 46))
        self.words = words

        # the way in.  It speaks for the tab that is showing.
        self.play_btn = self.button(sky, text=self.backend.play_label(self.game_code()),
                                    command=lambda: self.backend.play(self.game_code()),
                                    bg=GOLD, fg="#1a1a1a",
                                    activebackground="#f2dcae",
                                    activeforeground="#1a1a1a",
                                    relief="flat", bd=0,
                                    font=(self.font, 13, "bold"),
                                    padx=26, pady=9)
        # placed, not packed: it lies along the foot of the banner, so the
        # starfield carries all the way down to the button
        self.play_btn.place(relx=0.5, rely=1.0, anchor="s", relwidth=1.0, height=38)
        self.show_art(self.game_code())

    def reload_games(self):
        """(Re-)read the game list and the key art - the language can change it."""
        here = self.backend.assets_dir()
        self.GAMES = [tuple(g) for g in self.backend.games()]
        for code, _name, _sub in self.GAMES:
            path = os.path.join(here, "banners", "hero_%s.png" % code.lower())
            if code not in self.art and os.path.exists(path):
                try:
                    self.art[code] = tk.PhotoImage(file=path)
                except Exception:                                     # noqa: BLE001
                    pass
        self.selected = getattr(self, "selected", None) or {"code": None}
        codes = [c for c, _n, _s in self.GAMES]
        if self.selected["code"] not in codes:
            first = None
            try:
                first = self.backend.default_game()
            except Exception:                                         # noqa: BLE001
                first = None
            self.selected["code"] = first if first in codes else (codes[0] if codes else "")

    def game_code(self):
        return self.selected["code"]

    def name_sub(self, code):
        """The game's title and tagline, as the backend words them."""
        for c, name, sub in self.GAMES:
            if c == code:
                return name, sub
        return code, ""

    def draw_words(self, code):
        """Paint the column: the glowing title, the subtitle and the tab row.

        They are one group, centred in the column, and the tabs are measured before
        they are drawn - measuring after is how the last one runs off the edge.
        """
        import tkinter.font as tkfont
        words = self.words
        words.delete("paint")
        name, sub = self.name_sub(code)
        f_name, f_sub, f_tab = ((self.font, 22, "bold"), (self.font, 11),
                                (self.font, 10))
        glow = ((4, "#2f2a1e"), (3, "#4a3f28"), (2, "#6d5c37"), (1, "#96804a"))
        measure = tkfont.Font(family=self.font, size=10)
        for text, font, x, y, face, halo in ((name, f_name, 26, 104, "#f8f5ee", glow),
                                            (sub, f_sub, 26, 142, "#d6d6e2", glow[:2])):
            for step, colour in halo:          # the halo: offset copies of the words
                for ox, oy in ((step, 0), (-step, 0), (0, step), (0, -step),
                               (step, step), (-step, -step)):
                    words.create_text(x + ox, y + oy, text=text, font=font,
                                      fill=colour, anchor="w", tags="paint")
            words.create_text(x, y, text=text, font=font, fill=face, anchor="w",
                              tags="paint")
        # the tabs follow the words.  They stay on one line if they fit; in English
        # they do not, so they go into two columns of two - a wrapped row of 3 + 1
        # leaves a lone tab hanging, which reads as a mistake.
        labels = [(c, self.name_sub(c)[0]) for c, _n, _s in self.GAMES]
        gap = 24
        widths = [measure.measure(label) for _c, label in labels]
        one_row = sum(widths) + gap * (len(labels) - 1) <= self.WORDS_W - 52
        col_w = max(widths) + gap if widths else gap
        for i, (c, label) in enumerate(labels):
            if one_row:
                x = 26 + sum(w + gap for w in widths[:i])
                y = 262
            else:
                x = 26 + (i % 2) * col_w
                y = 248 + (i // 2) * 32
            width = widths[i]
            words.create_text(x, y, text=label, font=f_tab, anchor="w",
                              fill=GOLD if c == code else DIM,
                              tags=("paint", "tab", c))
            if c == code:
                words.create_line(x, y + 22, x + width, y + 22, fill=GOLD, width=2,
                                  tags=("paint", "tab", c))
            # each tab is its own canvas item, so the click can be bound to it
            words.tag_bind(c, "<Button-1>",
                           lambda _e, cc=c: (self.show_art(cc), self.refresh_play()))

    def show_art(self, code):
        self.selected["code"] = code
        img = self.art.get(code)
        if img is not None:
            self.art_label.configure(image=img)
            self.art_label.image = img        # keep a reference or Tk drops the image
        self.draw_words(code)

    def refresh_play(self):
        """The button says what pressing it will do for the game on screen."""
        code = self.game_code()
        text = self.backend.play_label(code)
        if getattr(self, "_play_text", None) != text:
            self._play_text = text
            self.play_btn.configure(text=text)
        self.play_btn.configure(command=lambda c=code: self.backend.play(c))

    # ── the strip under the banner: what is happening right now ──────────────
    def _build_status_line(self):
        self.state_var = tk.StringVar(value="starting up")
        stripbar = tk.Frame(self.root, bg=BG)
        stripbar.pack(fill="x", padx=14, pady=(0, 9))
        tk.Label(stripbar, textvariable=self.state_var, bg=PANEL, fg=FG,
                 font=(self.font, 9), padx=12, pady=8, anchor="w",
                 cursor="arrow").pack(side="left", fill="x", expand=True)

    # ── one quiet status line, instead of a grid of developer counters ───────
    def _build_stats(self):
        info = tk.Frame(self.root, bg=BG)
        info.pack(fill="x", padx=14, pady=(0, 7))
        self.stat_labels, self.stat_vars = [], []
        for i, (label, value) in enumerate(self.backend.stats()):
            if i:
                tk.Label(info, text="\u00b7", bg=BG, fg="#5a5a6c",
                         font=(self.font, 10)).pack(side="left", padx=8)
            lab = tk.Label(info, text=label, bg=BG, fg="#8a8a9c",
                           font=(self.font, 9))
            lab.pack(side="left", padx=(0, 5))
            var = tk.StringVar(value=value or "\u2014")
            tk.Label(info, textvariable=var, bg=BG, fg="#d8d8e2",
                     font=(self.font, 9, "bold")).pack(side="left")
            self.stat_labels.append(lab)
            self.stat_vars.append(var)

        # the one control that earns its place on this line.  Bound lazily, since
        # it is only clicked long after startup.
        self.test_btn = self.button(info, text="Test the connection", bg=PANEL, fg=DIM,
                                    font=(self.font, 8), padx=10, pady=3,
                                    activebackground=GOLD_DIM, activeforeground=GOLD,
                                    command=self.test_clicked)
        self.test_btn.pack(side="right")           # hard right of the status line

    # ── an optional extra row of the backend's own actions ───────────────────
    def _build_actions(self):
        """Only built when the backend has actions of its own.

        The row is a parameter, not a second window: with no actions there is no
        row at all and the window is the one it has always been.
        """
        self.action_buttons = {}
        actions = []
        try:
            actions = list(self.backend.actions() or [])
        except Exception:                                             # noqa: BLE001
            actions = []
        self.actions_summary_var = None
        if not actions:
            return
        row = tk.Frame(self.root, bg=BG)
        row.pack(fill="x", padx=14, pady=(0, 7))
        for label, command, accent in actions:
            btn = self.button(row, text=label, command=command, accent=accent)
            btn.pack(side="left", padx=(0, 8))
            self.action_buttons[label] = btn
        self.actions_summary_var = tk.StringVar(value="")
        tk.Label(row, textvariable=self.actions_summary_var, bg=BG, fg=DIM,
                 font=(self.font, 9)).pack(side="right")

    def set_action_text(self, label, text):
        """Re-word one of the backend's own action buttons (e.g. while it works)."""
        btn = self.action_buttons.get(label)
        if btn is not None:
            set_button_text(btn, text)

    # ── the log console ─────────────────────────────────────────────────────
    def _build_log(self):
        log_frame = tk.Frame(self.root, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        box = self.box = tk.Text(log_frame, bg="#0a0a0c", fg="#d8d8de",
                                 insertbackground=FG, font=self.backend.mono_font,
                                 relief="flat", height=7, wrap="char",
                                 state="disabled", cursor="arrow", takefocus=0,
                                 highlightthickness=0, selectbackground="#0a0a0c")
        scroll = tk.Scrollbar(log_frame, command=box.yview)
        box.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        box.pack(side="left", fill="both", expand=True)
        # open the txt file now, so the startup lines can name its path
        self._open_log_file()

    def _build_footer(self):
        self.foot_var = tk.StringVar()
        tk.Label(self.root, bg=BG, fg=DIM, justify="left", font=(self.font, 8),
                 textvariable=self.foot_var).pack(fill="x", padx=14, pady=(0, 10))

    def _size_window(self):
        # A narrow window used to clip the button labels (Windows font metrics
        # differ, and a small screen makes the window manager shrink it).  Never
        # allow less than the content.
        root = self.root
        root.update_idletasks()
        need_w = max(1180, root.winfo_reqwidth() + 8)      # the banner needs the room
        screen_w = root.winfo_screenwidth()
        win_w = min(need_w, max(760, screen_w - 80))
        win_h = 690                                        # taller, so the log and the
        root.geometry("%dx%d" % (win_w, win_h))            # status line are not clipped
        # geometry() and minsize() both clear the min=max lock that resizable(False,
        # False) sets, so the lock has to be re-applied AFTER them.
        root.minsize(win_w, win_h)
        root.maxsize(win_w, win_h)
        root.resizable(False, False)

    # ── the log, and the window's own messages ──────────────────────────────
    def _say(self, text):
        """Queue a log line for the window, without letting the backlog grow."""
        try:
            if self.log_queue.qsize() > LOG_QUEUE_MAX:
                return
        except Exception:                                             # noqa: BLE001
            pass
        self.log_queue.put(text)

    # ── the log file: the pane trims itself and clamps to the bottom, so the
    #    file is the only complete record (and can be scrolled freely) ───────
    def _open_log_file(self):
        try:
            import os
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
            os.makedirs(log_dir, exist_ok=True)
            path = os.path.join(log_dir, "launcher.log")
            try:                                  # keep one older run aside
                if os.path.getsize(path) > 8 * 1024 * 1024:
                    os.replace(path, os.path.join(
                        log_dir, "launcher-%s.log" % time.strftime("%Y%m%d-%H%M%S")))
            except OSError:
                pass
            self.log_path = path
            self._log_fh = open(path, "a", encoding="utf-8", errors="replace")
            self._log_fh.write("\n=== launcher started %s ===\n"
                               % time.strftime("%Y-%m-%d %H:%M:%S"))
            self._log_fh.flush()
        except Exception:                                             # noqa: BLE001
            self.log_path = None
            self._log_fh = None

    def _log_to_file(self, text):
        if not hasattr(self, "_log_fh"):
            self._open_log_file()
        fh = getattr(self, "_log_fh", None)
        if fh is None:
            return
        try:
            fh.write(text + "\n")
            fh.flush()
        except Exception:                                             # noqa: BLE001
            self._log_fh = None

    def _at_bottom(self):
        """True when the pane is scrolled to the end - only then follow the tail,
        so scrolling up to read does not get yanked back to the bottom."""
        try:
            return self.box.yview()[1] >= 0.999
        except Exception:                                             # noqa: BLE001
            return True

    def note(self, text):
        """Window-level message: stamped like the server's own lines."""
        self._say(time.strftime("%H:%M:%S") + " " + text)

    def log_line(self, text):
        # the log is a record, not an editor: a disabled Text has no caret, no
        # selection and does not react to a click, which is what it should be
        self._log_to_file(text)
        box = self.box
        follow = self._at_bottom()
        box.configure(state="normal")
        box.insert("end", text + "\n")
        if follow:
            box.see("end")
        box.configure(state="disabled")

    def drain_log(self):
        """Draw what the queue has, but never the whole backlog in one go.

        Draining everything in one pass is what stops the window responding: a
        download logs thousands of lines, and each one is three Tk calls plus a
        scroll.  Take a slice per tick instead, one scroll for the batch, and drop
        the oldest lines once the pane is long enough - a huge Text is slow too.
        """
        lines = []
        try:
            while len(lines) < LOG_PER_TICK:
                lines.append(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        if lines:
            for line in lines:
                self._log_to_file(str(line))
            try:
                box = self.box
                follow = self._at_bottom()
                box.configure(state="normal")
                box.insert("end", "\n".join(str(x) for x in lines) + "\n")
                if follow:
                    box.see("end")
                box.configure(state="disabled")
                total = int(str(box.index("end-1c")).split(".")[0])
                if total > LOG_MAX_LINES:
                    box.configure(state="normal")
                    box.delete("1.0", "%d.0" % (total - LOG_MAX_LINES))
                    box.configure(state="disabled")
            except Exception:                                         # noqa: BLE001
                pass
        self.root.after(250, self.drain_log)

    # ── the buttons that drive the servers ──────────────────────────────────
    def start_clicked(self):
        if getattr(self.backend, "background_start", False):
            # Slow backend operations run off-thread; refresh shows the result.
            threading.Thread(target=self._guard(self.backend.start),
                             daemon=True).start()
            return
        self._guard(self.backend.start)()
        self.refresh()

    def stop_clicked(self):
        if getattr(self.backend, "background_start", False):
            threading.Thread(target=self._guard(self.backend.stop),
                             daemon=True).start()
            return
        self._guard(self.backend.stop)()
        self.refresh()

    def _guard(self, fn):
        """Never let a backend failure take the window down with it."""
        def run():
            try:
                fn()
            except Exception as exc:                                  # noqa: BLE001
                self.note("could not do that: %s" % exc)
        return run

    def test_clicked(self):
        try:
            self.note(self.backend.test())
        except Exception as exc:                                      # noqa: BLE001
            self.note("connection test failed: %s" % exc)

    def revert_clicked(self):
        try:
            self.backend.revert_hosts()
        except Exception as exc:                                      # noqa: BLE001
            self.note("could not revert the hosts file: %s" % exc)
        self.refresh()
        self.note("hosts file reverted by request")

    def open_settings(self):
        """The settings page, whenever a backend offers one."""
        try:
            self.backend.open_settings()
        except Exception as exc:                                      # noqa: BLE001
            self.note("could not open the settings (%s)" % exc)

    # ── the drawer the hamburger slides out ─────────────────────────────────
    def _build_drawer(self):
        """The hamburger's list is its own borderless window, not a placed frame.

        A placed child that overlaps its parent leaves Windows holding stale paint
        once it goes away - the banner and headings came back only piece by piece.
        A separate window never overlaps the launcher, so closing it cannot damage
        it, and it is rebuilt on every open so the entries show the live state.
        """
        self.draw_w = 288
        drawer = self.drawer = tk.Toplevel(self.root)
        drawer.overrideredirect(True)          # no title bar, no decorations
        # Deliberately NOT the launcher's own name: this window has no title bar,
        # but it still carries a WM_NAME, and a search for the launcher (a window
        # manager, a screen recorder, "xdotool search --name") must find one window,
        # not two - the second one 1x1.
        drawer.title("launcher drawer")
        drawer.transient(self.root)
        drawer.configure(bg=DRAWER_BG, highlightbackground=DRAWER_LINE,
                         highlightthickness=1)
        drawer.withdraw()
        self.drawer_state = {"on": False, "x": -self.draw_w}
        self.draw_rows = {}
        self.rebuild_drawer()

        self.root.bind("<Configure>", self._drawer_follow)
        self.root.bind("<Button-1>", self.maybe_close_drawer, add="+")
        self.root.bind("<Escape>", self.close_drawer)

    def rebuild_drawer(self):
        """Build (or rebuild) the list from the backend, showing what can be done now."""
        drawer = self.drawer
        for child in drawer.winfo_children():
            child.destroy()
        self.draw_rows = {}

        top = tk.Frame(drawer, bg=DRAWER_BG)
        top.pack(fill="x", pady=(10, 2))
        self.menu_label = tk.Label(top, text=self.backend.menu_title(), bg=DRAWER_BG,
                                   fg=FG, font=(self.font, 12, "bold"), anchor="w")
        self.menu_label.pack(side="left", padx=(18, 0))
        xmark = tk.Canvas(top, width=20, height=20, bg=DRAWER_BG,
                          highlightthickness=0, cursor="hand2")
        xmark.create_line(6, 6, 14, 14, fill=DIM, width=2, capstyle="round")
        xmark.create_line(14, 6, 6, 14, fill=DIM, width=2, capstyle="round")
        xmark.pack(side="right", padx=(0, 14))
        xmark.bind("<Button-1>", lambda _e: self.close_drawer())

        for section, rows in self.backend.menu():
            if section is not None:
                tk.Label(drawer, text=section, bg=DRAWER_BG, fg="#6a6a7c", anchor="w",
                         font=(self.font, 8, "bold"), padx=18).pack(fill="x",
                                                                    pady=(11, 2))
            for label, command, enabled in rows:
                action = self._drawer_action(command, enabled) if command else None
                btn = self.button(drawer, text="  " + label, command=action,
                                  bg=DRAWER_BG, fg=ROW_ON if enabled else ROW_OFF,
                                  font=(self.font, 10), anchor="w", padx=18, pady=6,
                                  activebackground="#22222e", activeforeground=GOLD)
                btn.pack(fill="x")
                set_button_state(btn, enabled)
                self.draw_rows[label] = btn

    def _drawer_action(self, command, enabled):
        def run():
            if not enabled:
                return
            self.close_drawer()
            try:
                command()
            except Exception as exc:                                  # noqa: BLE001
                self.note("could not do that: %s" % exc)
        return run

    def _drawer_move(self, x):
        """Put the drawer at screen offset x, spanning from below the header down.

        It is a real window, so x is a screen coordinate and a negative value just
        parks it off to the left - harmless now that it overlaps nothing.
        """
        self.drawer_state["x"] = x
        top = self.head.winfo_height() or 48
        height = max(1, self.root.winfo_height() - top)
        self.drawer.geometry("%dx%d+%d+%d" % (
            self.draw_w, height, self.root.winfo_rootx() + int(x),
            self.root.winfo_rooty() + top))

    def _drawer_follow(self, event=None):
        """Keep the drawer glued to the launcher when the launcher is moved.

        A separate window does not travel with its parent, so dragging the launcher
        left the open drawer behind - hanging outside the window on its own.
        """
        if event is not None and event.widget is not self.root:
            return
        if self.drawer_state["on"]:
            self._drawer_move(self.drawer_state["x"])

    def _drawer_alpha(self, a):
        """Fade the drawer in and out.

        Sliding it in from a negative x meant a separate window visibly travelled
        across the desktop from outside the launcher.  Fading means it is always in
        place and never appears outside the window.
        """
        try:
            self.drawer.attributes("-alpha", max(0.0, min(1.0, a)))
        except tk.TclError:
            pass                          # some platforms refuse; it still works

    def close_drawer(self, *_e):
        # Driven by a flag, never by winfo_ismapped(): those two can disagree and
        # the close then runs out early, leaving it stuck flagged as open so the
        # hamburger stops working.
        if not self.drawer_state["on"]:
            return
        self.drawer_state["on"] = False
        for step in range(1, 7):
            self.root.after(step * 12, lambda s=step: self._drawer_alpha(1.0 - s / 6.0))
        self.root.after(12 * 7, self._hide_drawer)

    def _hide_drawer(self):
        self.drawer.withdraw()
        self.drawer_state["on"] = False

    def toggle_drawer(self):
        if self.drawer_state["on"]:
            self.close_drawer()
            return
        self.rebuild_drawer()              # the entries show the state right now
        self.drawer_state["on"] = True
        self._drawer_move(0)               # already in place: never outside the window
        self.drawer.deiconify()
        self._drawer_alpha(0.0)
        try:
            self.drawer.lift()
        except tk.TclError:
            pass
        for step in range(1, 7):
            self.root.after(step * 14, lambda s=step: self._drawer_alpha(s / 6.0))

    def maybe_close_drawer(self, event):
        """Clicking anywhere outside the drawer (and off the burger) puts it away.

        Geometric, because the drawer is its own window: walking the widget tree
        would never reach it, so every click inside would look like an outside one.
        """
        if not self.drawer_state["on"]:
            return
        x0, y0 = self.drawer.winfo_rootx(), self.drawer.winfo_rooty()
        if (x0 <= event.x_root <= x0 + self.drawer.winfo_width()
                and y0 <= event.y_root <= y0 + self.drawer.winfo_height()):
            return                                    # inside the drawer
        bx, by = self.burger.winfo_rootx(), self.burger.winfo_rooty()
        if (bx <= event.x_root <= bx + self.burger.winfo_width()
                and by <= event.y_root <= by + self.burger.winfo_height()):
            return                                    # the hamburger toggles it
        self.close_drawer()

    # ── the refresh loop ────────────────────────────────────────────────────
    def _call(self, label, fn, default=None):
        """Run one backend hook, and *say so* the first time one fails.

        Swallowing a broken hook silently is how a window keeps drawing while a
        panel quietly freezes - the failure belongs in the log pane, once.
        """
        try:
            return fn()
        except Exception as exc:                                      # noqa: BLE001
            self._warned = getattr(self, "_warned", set())
            if label not in self._warned:
                self._warned.add(label)
                self.note("%s failed: %s: %s" % (label, type(exc).__name__, exc))
            return default

    def refresh(self):
        """One pass of the live state - the dot, the rows, the footer, the marquee."""
        backend = self.backend
        status = self._call("backend.status()", backend.status,
                            ("state unknown", False))
        text, running = status if isinstance(status, tuple) else ("state unknown", False)
        self.dot.itemconfig(self.dot_id, fill=GREEN if running else RED)
        self.status_var.set(text)

        rows = self._call("backend.stats()", backend.stats, []) or []
        for i, row in enumerate(rows):
            if i >= len(self.stat_vars):
                break
            label, value = row
            self.stat_labels[i].configure(text=label)
            self.stat_vars[i].set(value if value else "\u2014")

        line = self._call("backend.status_line()", backend.status_line, "")
        self.state_var.set(line or "idle")
        foot = self._call("backend.footer()", backend.footer, "")
        if foot:
            self.foot_var.set(foot)
        if self.actions_summary_var is not None:
            summary = self._call("backend.actions_summary()",
                                 backend.actions_summary, "")
            self.actions_summary_var.set(summary or "")
        if hasattr(backend, "tick"):
            self._call("backend.tick()", backend.tick)
        self._call("backend.play_label()", self.refresh_play)
        self.root.after(500, self.refresh)

    # ── the way out ─────────────────────────────────────────────────────────
    def on_close(self):
        try:
            if self.backend.close() is False:
                return
        except Exception:                                             # noqa: BLE001
            pass
        try:
            self.root.destroy()
        except Exception:                                             # noqa: BLE001
            pass

    # ── start it ────────────────────────────────────────────────────────────
    def main(self):
        backend = self.backend
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.note("%s v%s" % (backend.title, backend.version))
        for line in backend.startup_lines():
            self.note(line)
        self.drain_log()
        self.refresh()
        if backend.autostart():
            self.root.after(300, self.start_clicked)   # one double-click and it runs
        self.root.mainloop()
        return 0


# The window's own few words. The Windows backend uses its own tr() table.
CHROME = {
    "save": "Save",
    "close": "Close",
}


def run(backend):
    """Build the window for the Windows `backend` and run it."""
    root = tk.Tk()
    window = Window(root, backend)
    return window.main()
