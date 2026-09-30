#!/usr/bin/env python3
"""LP2/LP3 use a different ENTRY than LP1 (`index.swf?v=2`), which is the only reason
the first pass skipped them. Same Flash-only change, with the entry line matched."""
import pathlib
import re
import subprocess
import time

ROOT = pathlib.Path.home() / "Downloads/littleprince-launcher"

OLD_COMMENT_RE = re.compile(
    r'  const ENTRY = "[^"]+";\r?\n'
    r'  // the publisher\'s browser is Electron with Pepper Flash inside it; everyone else\r?\n'
    r'  // gets the player bundled with this package\r?\n'
    r'  const hasFlash = /Electron/\.test\(navigator\.userAgent\);'
)

NEW_COMMENT = '''  const ENTRY = "@@ENTRY@@";
  // The publisher's browser is Electron with Pepper Flash inside it.  This pack is
  // Flash-only on purpose: the game does not run correctly in the install-free player,
  // so a browser without Flash is sent to the publisher's own browser instead.
  const hasFlash = /Electron/.test(navigator.userAgent);
  const BROWSER_ZIP =
    "http://www.little-prince.com.hk/littleprince/Download/LittlePrinceBrowserHome.zip";'''

OLD_HEAD = '''<script>
  // config must exist before ruffle.js runs
  window.RufflePlayer = window.RufflePlayer || {};
  window.RufflePlayer.config = {
    autoplay: "on", unmuteOverlay: "hidden", letterbox: "on", scale: "showAll",
    quality: "high", splashScreen: false, allowScriptAccess: true,
    openUrlMode: "deny", logLevel: "error"
  };
</script>
<script src="/web/ruffle/ruffle.js"></script>
</head>'''
NEW_HEAD = '''</head>'''

OLD_RUFFLE = '''  function withRuffle() {
    const ruffle = window.RufflePlayer.newest();
    const player = ruffle.createPlayer();
    player.style.width = window.innerWidth + "px";
    player.style.height = window.innerHeight + "px";
    document.getElementById("stage").appendChild(player);
    window.addEventListener("resize", function () {
      player.style.width = window.innerWidth + "px";
      player.style.height = window.innerHeight + "px";
    });
    player.ruffle().load({ url: ENTRY });
    document.getElementById("note").innerHTML =
      'Served by the local server &middot; log in with any name, or ' +
      '<a href="/web">register / sign in</a> &middot; ' +
      '<a href="/LP/personal/">all games</a>';
  }'''
NEW_RUFFLE = '''  function showNoFlash() {
    document.getElementById("stage").innerHTML =
      '<div style="max-width:580px;margin:0 auto;padding:0 24px;text-align:center;' +
      'color:#fff;font:14px/1.9 -apple-system,\\'Segoe UI\\',system-ui,sans-serif">' +
      '<div style="font-size:19px;color:#ffd98a;margin-bottom:12px">' +
      'This game plays in the publisher\\'s own browser</div>' +
      'The install-free player has been switched off: the game does not run correctly ' +
      'in it, so it would show you bugs that are not in the real game.<br><br>' +
      'Download the official browser, then open this page again:<br>' +
      '<a style="color:#ffd98a" href="' + BROWSER_ZIP + '">LittlePrinceBrowserHome.zip</a>' +
      '<div style="margin-top:16px;color:rgba(255,255,255,.66);font-size:12px">' +
      'The launcher downloads it and sets it up for you &mdash; just press <b>Play</b> ' +
      'there.<br><a style="color:rgba(255,255,255,.8)" href="/LP/personal/">' +
      'Back to all games</a></div></div>';
    document.getElementById("note").innerHTML = "";
  }'''

OLD_BOOT = '''      if (hasFlash) withFlash(); else withRuffle();'''
NEW_BOOT = '''      if (hasFlash) withFlash(); else showNoFlash();'''

for code in ("LP2", "LP3"):
    p = ROOT / "patches" / code / "index.html"
    src = p.read_text()
    m = OLD_COMMENT_RE.search(src)
    if not m:
        print(f"  !! {code}: entry/comment block not matched")
        continue
    entry = re.search(r'const ENTRY = "([^"]+)"', m.group(0)).group(1)
    src = src[:m.start()] + NEW_COMMENT.replace("@@ENTRY@@", entry) + src[m.end():]
    misses = []
    for old, new, label in ((OLD_HEAD, NEW_HEAD, "ruffle include"),
                            (OLD_RUFFLE, NEW_RUFFLE, "withRuffle"),
                            (OLD_BOOT, NEW_BOOT, "boot")):
        if old in src:
            src = src.replace(old, new, 1)
        else:
            misses.append(label)
    if misses:
        print(f"  !! {code}: still missing {misses} - not written")
        continue
    p.write_text(src)
    print(f"  {code}/index.html patched (entry={entry}, ruffle mentions left: "
          f"{src.lower().count('ruffle')})")

print("\n=== serving the pages to confirm ===")
subprocess.run("pkill -f 'python3 lpo/server[.]py'", shell=True, check=False)
time.sleep(0.5)
log = open("/tmp/p5.log", "wb")
srv = subprocess.Popen(["python3", "lpo/server.py"], cwd=ROOT, stdout=log, stderr=log)
for _ in range(20):
    time.sleep(1)
    if subprocess.run("ss -ltn | grep -q :8080", shell=True).returncode == 0:
        break

for path in ("/LP/personal/LP1/", "/LP/personal/LP2/", "/LP/personal/LP3/"):
    r = subprocess.run(["curl", "-s", "-o", "/tmp/lp.html", "-w", "%{http_code}",
                        f"http://127.0.0.1:8080{path}"], capture_output=True, text=True)
    body = pathlib.Path("/tmp/lp.html").read_text(errors="ignore")
    low = body.lower()
    print(f"  {path:20} http={r.stdout.strip()} bytes={len(body):5} "
          f"ruffle_player={'ruffleplayer' in low or 'ruffle.js' in low} "
          f"flash_object={'x-shockwave-flash' in low} "
          f"official_link={'LittlePrinceBrowserHome.zip' in body}")

srv.terminate()
time.sleep(1)
print("test server stopped:",
      subprocess.run("pgrep -f 'python3 lpo/server[.]py' >/dev/null", shell=True).returncode != 0)
