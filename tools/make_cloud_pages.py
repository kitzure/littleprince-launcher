#!/usr/bin/env python3
"""Regenerate the three cloud game host pages.

The first version created a bare <ruffle-player> element and never got a player
back - Ruffle only hands one out through `RufflePlayer.newest().createPlayer()`,
and its config has to be set *before* ruffle.js runs.  Result: a blank stage on
all three games (the user saw exactly that).  This uses the same bootstrap as
the working /play page, keeps the publisher's real-Flash branch for their
Electron browser, and takes the entry SWF from their own index page.
"""
import re
from pathlib import Path

CLOUD = Path.home() / "Downloads/littleprince-patcher/cloud"
TITLES = {"LP1": "Little Prince", "LP2": "Starwish Legend", "LP3": "Starwish Adventure"}

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  html, body {{ margin:0; padding:0; width:100%; height:100%; background:#014587;
                overflow:hidden; }}
  /* No `inset` here: the publisher's browser is Electron 4 (Chromium 69) and does not
     support it, which leaves the stage zero-sized and makes Flash complain that the
     movie is too small. */
  #stage {{ position:absolute; top:0; left:0; width:100%; height:100%; }}
  #note {{ position:absolute; left:0; right:0; bottom:6px; text-align:center; z-index:5;
           color:rgba(255,255,255,.6); font:11px -apple-system,"Segoe UI",system-ui,sans-serif; }}
  #note a {{ color:rgba(255,255,255,.85); }}
</style>
<script>
  // config must exist before ruffle.js runs
  window.RufflePlayer = window.RufflePlayer || {{}};
  window.RufflePlayer.config = {{
    autoplay: "on", unmuteOverlay: "hidden", letterbox: "on", scale: "showAll",
    quality: "high", splashScreen: false, allowScriptAccess: true,
    openUrlMode: "deny", logLevel: "error"
  }};
</script>
<script src="/web/ruffle/ruffle.js"></script>
</head>
<body>
<div id="stage"></div>
<div id="note"></div>
<script>
  const ENTRY = "{entry}";
  // the publisher's browser is Electron with Pepper Flash inside it; everyone else
  // gets the player bundled with this package
  const hasFlash = /Electron/.test(navigator.userAgent);

  function fill(el) {{
    el.setAttribute("width", window.innerWidth + "px");
    el.setAttribute("height", window.innerHeight + "px");
  }}

  function withFlash() {{
    document.getElementById("stage").innerHTML =
      '<object width="' + window.innerWidth + '" height="' + window.innerHeight +
      '" type="application/x-shockwave-flash" data="' + ENTRY + '">' +
      '<param name="movie" value="' + ENTRY + '">' +
      '<param name="quality" value="high">' +
      '<param name="bgcolor" value="#014587">' +
      '<param name="scale" value="showall">' +
      '<param name="allowScriptAccess" value="sameDomain">' +
      '<param name="wmode" value="window"></object>';
    document.getElementById("note").innerHTML =
      'Served by the local server &middot; playing with the browser\\'s own Flash player';
  }}

  function withRuffle() {{
    const ruffle = window.RufflePlayer.newest();
    const player = ruffle.createPlayer();
    player.style.width = window.innerWidth + "px";
    player.style.height = window.innerHeight + "px";
    document.getElementById("stage").appendChild(player);
    window.addEventListener("resize", function () {{
      player.style.width = window.innerWidth + "px";
      player.style.height = window.innerHeight + "px";
    }});
    player.ruffle().load({{ url: ENTRY }});
    document.getElementById("note").innerHTML =
      'Served by the local server &middot; log in with any name, or ' +
      '<a href="/web">register / sign in</a> &middot; ' +
      '<a href="/LP/personal/">all games</a>';
  }}

  function boot() {{
    try {{
      if (hasFlash) withFlash(); else withRuffle();
    }} catch (e) {{
      document.getElementById("note").textContent = "Could not start the player: " + e;
    }}
  }}
  if (document.readyState === "complete") boot();
  else window.addEventListener("load", boot);
</script>
</body>
</html>
"""

for game, title in TITLES.items():
    folder = CLOUD / game
    original = folder / "index.original.html"
    html = original.read_text(errors="replace")
    entry = None
    for pattern in (r"""['"](?:movie|src|data)['"]\s*,\s*['"]([^'"]+\.swf)['"]""",
                    r"""name=["']movie["']\s+value=["']([^"']+\.swf)["']"""):
        m = re.search(pattern, html, re.I)
        if m:
            entry = m.group(1)
            break
    if not entry:
        print("%s: no entry found, skipped" % game)
        continue
    if not (folder / entry).exists():
        print("%s: !! %s is missing from the mirror" % (game, entry))
    (folder / "index.html").write_text(PAGE.format(title=title, entry=entry))
    print("%s -> %s (entry %s)" % (game, title, entry))
