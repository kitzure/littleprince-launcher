#!/usr/bin/env python3
"""Make the pack Flash-only: the publisher's own browser plays the game, the
install-free Ruffle page is switched off.

Edits (all reversible):
  1. server.py   - /play (and its aliases) serves a notice instead of the Ruffle page
  2. web/play_off.html - the notice (new file, English only)
  3. web/play_flash.html - drop the automatic hand-over to Ruffle
  4. Start_Server_GUI.pyw - "Play online" opens /play-flash, not /play
  5. web.html - the portal's "Open the game" button points at /play-flash
"""
import pathlib

ROOT = pathlib.Path.home() / "Downloads/littleprince-launcher"
changed = []

# ── 1. server.py: route /play to the notice ────────────────────────────────────
S = ROOT / "lpo/server.py"
src = S.read_text()

OLD_COMMENT = """        # ── the browser player (Ruffle web build, install-free) ──
        #    /play, and the game's own URL /LP/Po/ - the latter keeps the page on
        #    the same origin as the gateway, so the client's calls are not
        #    cross-site from the browser's point of view."""
NEW_COMMENT = """        # ── the browser player ──
        #    /play and the game's own URL /LP/Po/ used to serve the install-free
        #    Ruffle page.  The pack is Flash-only now: the game runs in the
        #    publisher's own Flash browser and the Ruffle page is OFF, because the
        #    client misbehaves under Ruffle (the multiplayer result screen among
        #    others) and users were seeing those bugs.  Swap the serve below back to
        #    play.html to bring the Ruffle player back.
        #    The URL keeps the page on the same origin as the gateway, so a
        #    Flash player's calls are not cross-site from the browser's point of view."""

OLD_ROUTE = """        if clean_path.rstrip("/") in ("/play", "/play.html", "/LP/Po", "/LP/Po/index.html", ""):
            if not next(GAME_DIR.glob("*.swf"), None):
                self.serve_package_file("no_game_files.html")
                return
            self.serve_package_file("play.html")
            return"""
NEW_ROUTE = """        if clean_path.rstrip("/") in ("/play", "/play.html", "/LP/Po", "/LP/Po/index.html", ""):
            if not next(GAME_DIR.glob("*.swf"), None):
                self.serve_package_file("no_game_files.html")
                return
            self.serve_package_file("play_off.html")
            return"""

for old, new, label in ((OLD_COMMENT, NEW_COMMENT, "comment"), (OLD_ROUTE, NEW_ROUTE, "route")):
    if old in src:
        src = src.replace(old, new, 1)
        changed.append(f"server.py {label}")
    else:
        print(f"  !! {label} anchor not found")
S.write_text(src)

# ── 2. the notice page ────────────────────────────────────────────────────────
(ROOT / "lpo/web/play_off.html").write_text("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Little Prince Online</title>
<style>
  html, body { margin: 0; height: 100%; background: #0b0b0b; color: #e8e8ee;
               font: 14px/1.9 "Segoe UI", "Microsoft JhengHei", system-ui, sans-serif; }
  .wrap { display: flex; align-items: center; justify-content: center; height: 100%;
          padding: 6vh 6vw; text-align: center; }
  b { color: #f0c96a; font-weight: normal; }
  ol { display: inline-block; text-align: left; margin: 14px 0 0; padding-left: 22px;
       color: #b9b9c6; }
  .btn { display: inline-block; margin-top: 20px; padding: 10px 20px; border-radius: 8px;
         border: 1px solid #6d5c37; background: #1b1b22; color: #f0c96a;
         text-decoration: none; font-size: 15px; }
  .btn:hover { background: #24242c; }
  .note { margin-top: 16px; color: #8c8c9c; font-size: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <div>
    <b>This game runs in the publisher's Flash browser.</b><br>
    The install-free web player has been switched off: the client does not behave
    correctly in it, so it would show you bugs that are not in the real game.
    <ol>
      <li>Open the launcher.</li>
      <li>Press <b>Play online</b>. It starts the publisher's own Flash browser for you,
          fetching it first if it is not on this PC yet.</li>
      <li>If it says the browser could not start, press Play online again once the
          download in the launcher's log has finished.</li>
    </ol>
    <a class="btn" href="/play-flash">I already have a Flash browser &mdash; open the game</a>
    <div class="note">That link needs a browser with Flash (the publisher's browser, or a
      Firefox with the Flash plugin).</div>
  </div>
</div>
</body>
</html>
""".encode("utf-8").decode("utf-8"))
changed.append("web/play_off.html created")

# ── 3. play_flash.html: no automatic hand-over to Ruffle ──────────────────────
P = ROOT / "lpo/web/play_flash.html"
p = P.read_text()

OLD_OVERLAY = """<div id="noflash">
  <div>
    <b id="nf-why">This browser cannot start Flash.</b><br>
    The game runs without Flash through Ruffle instead &mdash; this page opens it
    for you in <b id="nf-count">5</b> seconds.<br><br>
    <a class="btn" id="nf-go" href="/play">Play now (Ruffle)</a>
  </div>
</div>"""
NEW_OVERLAY = """<div id="noflash">
  <div>
    <b id="nf-why">This browser cannot start Flash.</b><br>
    Little Prince Online plays with real Flash, in the publisher's own browser &mdash;
    the launcher starts it for you, and fetches it first if it is not on this PC yet.
    The install-free web player is switched off on purpose.<br><br>
    <a class="btn" id="nf-go" href="#" onclick="location.reload();return false;">Try again</a>
    <a class="btn" href="/play-off">How to play</a>
  </div>
</div>"""

OLD_JS = """  // Never leave the player on a dead page.  Two ways Flash is missing here:
  //   1. the plugin is not installed at all (a normal browser, most Macs since
  //      Chrome dropped it) - navigator.plugins shows nothing;
  //   2. the plugin IS listed but the movie never started: blocked until allowed,
  //      a broken install, or the bundled Chromium running without Rosetta on
  //      Apple Silicon.  The user reported exactly this on a Mac - allowing Flash
  //      changed nothing - so the plugin LIST is not proof, and the <object> is
  //      asked directly instead.
  // Either way, hand over to the Ruffle player at /play, which needs no plugin.
  (function () {
    var WRAP = 5;                         // seconds on screen before the switch
    var WHY = document.getElementById("nf-why");
    var COUNT = document.getElementById("nf-count");

    function giveUp(why) {
      var box = document.getElementById("noflash");
      if (!box || box.getAttribute("data-shown") === "1") { return; }
      box.setAttribute("data-shown", "1");
      if (why) { WHY.textContent = why; }
      box.style.display = "flex";
      var left = WRAP;
      var t = setInterval(function () {
        left -= 1;
        if (COUNT) { COUNT.textContent = String(left > 0 ? left : 0); }
        if (left <= 0) { clearInterval(t); location.replace("/play"); }
      }, 1000);
    }
"""
NEW_JS = """  // Say so, plainly, when Flash is missing.  Two ways that happens:
  //   1. the plugin is not installed at all (a normal browser, most Macs since
  //      Chrome dropped it) - navigator.plugins shows nothing;
  //   2. the plugin IS listed but the movie never started: blocked until allowed,
  //      a broken install, or the bundled Chromium running without Rosetta on
  //      Apple Silicon - so the plugin LIST is not proof and the <object> is asked
  //      directly instead.
  // This used to hand the player over to the Ruffle page at /play.  The pack is
  // Flash-only now, so the overlay just explains where the game does run.
  (function () {
    var WHY = document.getElementById("nf-why");

    function giveUp(why) {
      var box = document.getElementById("noflash");
      if (!box || box.getAttribute("data-shown") === "1") { return; }
      box.setAttribute("data-shown", "1");
      if (why) { WHY.textContent = why; }
      box.style.display = "flex";
    }
"""

for old, new, label in ((OLD_OVERLAY, NEW_OVERLAY, "overlay"),
                        (OLD_JS, NEW_JS, "script")):
    if old in p:
        p = p.replace(old, new, 1)
        changed.append(f"play_flash.html {label}")
    else:
        print(f"  !! play_flash.html {label} anchor not found")
P.write_text(p)

# ── 4. launcher: Play online opens the Flash page ─────────────────────────────
G = ROOT / "Start_Server_GUI.pyw"
g = G.read_text()

OLD_BROWSER_URL = '''    The 127.0.0.1 page always comes from this machine, so that is what Play online
    opens; the game's own address stays available for anyone who wants it.
    """
    return "http://127.0.0.1:%d/play" % port'''
NEW_BROWSER_URL = '''    The 127.0.0.1 page always comes from this machine, so that is what Play online
    opens; the game's own address stays available for anyone who wants it.

    The Flash page, not /play: the pack plays with real Flash in the publisher's
    browser, and the install-free Ruffle page is switched off.
    """
    return "http://127.0.0.1:%d/play-flash" % port'''

OLD_TAIL = '''            ui.note("could not start it - falling back to the built-in player")'''
NEW_TAIL = '''            ui.note("could not start it - the publisher's browser is needed to play;")
            ui.note("  if it is still downloading, press Play online again when it is done")'''

OLD_CMT = '''        For the case where the game files were already there: Play opens with
        Ruffle this time and the publisher's browser is ready for the next press.'''
NEW_CMT = '''        For the case where the game files were already there: the publisher's browser
        is fetched now so the next press of Play can hand the game to real Flash.'''

for old, new, label in ((OLD_BROWSER_URL, NEW_BROWSER_URL, "browser_url"),
                        (OLD_TAIL, NEW_TAIL, "fallback note"),
                        (OLD_CMT, NEW_CMT, "comment")):
    if old in g:
        g = g.replace(old, new, 1)
        changed.append(f"Start_Server_GUI.pyw {label}")
    else:
        print(f"  !! Start_Server_GUI.pyw {label} anchor not found")
G.write_text(g)

# ── 5. web.html: the portal's game button ─────────────────────────────────────
W = ROOT / "lpo/web.html"
w = W.read_text()
OLD_BTN = '<a class="btn ghost" href="/play" target="_blank" rel="noopener">Open the game</a>'
NEW_BTN = '<a class="btn ghost" href="/play-flash" target="_blank" rel="noopener">Open the game</a>'
if OLD_BTN in w:
    w = w.replace(OLD_BTN, NEW_BTN, 1)
    changed.append("web.html game button -> /play-flash")
    W.write_text(w)
else:
    print("  !! web.html button anchor not found")

print("\nchanged:")
for c in changed:
    print("  -", c)
print("\nremaining /play references that are NOT /play-flash:")
import re
for f in sorted(ROOT.rglob("*")):
    if f.suffix in (".py", ".pyw", ".html", ".js", ".md") and f.is_file():
        try:
            t = f.read_text(errors="ignore")
        except Exception:
            continue
        for m in re.finditer(r'["\'(]/?play(?:\.html)?["\')]', t):
            line = t[:m.start()].count("\n") + 1
            print(f"  {f.relative_to(ROOT)}:{line}: {m.group(0)}")
