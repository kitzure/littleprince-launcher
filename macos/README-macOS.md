# Little Prince Launcher - macOS

Plays the same things the Windows launcher does, without anything the publisher
never shipped for the Mac:

* **Little Prince Online** (the 星願 online world) against the local mirror in `lpo/`
* **the three CD games** (LP1 / LP2 / LP3) and the portal page
* **the accounts website** and the profile editor, both served by the mirror

There is no Mac build of the publisher's browser, so the launcher uses the
closest equivalent that still runs Flash: **Chromium M87** - the last release
with Pepper Flash support - together with **Pepper Flash Player 32.0.0.465**,
the exact version the publisher's Windows browser carries.

Nothing is installed system-wide and **no administrator rights are needed**: no
hosts edit, no port 80, no `/Library` changes. Chromium is pointed at a small
relay (`macos/mac_relay.py`) instead, and the Flash plugin is imported straight
from this folder with `--ppapi-flash-path`.

## Requirements

* macOS 10.15 or newer, Intel or Apple Silicon.
* Python 3 with Tk for the window. The build from
  [python.org](https://www.python.org/downloads/macos/) has it; Apple's command
  line Python does not, and the launcher then runs in the terminal instead.
* About 1.5 GB of free disk space (the CD games take most of it; the Chromium
  download is around 150 MB, unpacked about 400 MB).
* On an **Apple Silicon** Mac, Rosetta 2 is required: Chromium M87 and the bundled
  Pepper Flash plugin are Intel (x86_64) binaries and there is no arm64 build of
  either. The launcher installs it for you the first time you press **Set up Flash
  runtime** (macOS will ask for your password); without it macOS refuses to start
  the browser with `[Errno 86] Bad CPU type in executable`. To do it by hand:
  `softwareupdate --install-rosetta --agree-to-license`

## Running it

1. Double-click **`LittlePrinceLauncher.command`** (in the folder above `macos/`).
   If macOS refuses the first time, right-click it and choose **Open**.
2. In the window, press **Set up Flash runtime**. It downloads Chromium M87 once
   (about 150 MB) into `macos/runtime/`. The Flash plugin is already there.
3. Press the gold button along the bottom of the banner: **Play online world**, or
   **CD LP1/LP2/LP3** for the three CD games - it plays whichever game tab is showing.

The window is the same one the Windows launcher draws: the title strip, the game
banner, the status line and stats row, the log, and the ☰ drawer with **Start
servers**, **Stop servers**, **Set up Flash runtime**, the CD games, the game files,
**Mods** and **Accounts website**. The four game-file counts sit along the stats row
(`3 of 4 ready`) and beside **Download the game files**. The servers start by
themselves when the window opens. Log in with any name you like: this is a local
mirror of the game, so any account works.

Without the Flash runtime the online world opens in the install-free **Ruffle**
player instead (`/play`) - real Flash needs the Chromium download above.  Either
way it opens in the launcher's own browser, never your normal one: that browser
carries the proxy which routes the game's own server names to this machine.

Addresses, if you prefer a browser by hand:

* online world - `http://127.0.0.1:8950/LP/Po/flash` (real Flash) or
  `http://127.0.0.1:8950/play` (Ruffle, no runtime needed - what the launcher opens
  when the Flash runtime is not set up)
* CD games - `http://127.0.0.1:8081/index.html`
* accounts website - `http://127.0.0.1:8950/web`
* mods panel - `http://127.0.0.1:8950/mods` (also the **Mods** button in the launcher window)

Every one of the four games reads its progress back from this mirror, so a mod is a value
written into the saved player record: gems, coins, crystals, cards, levels and per-level
scores, with the preset buttons and the field editor on the mods page. On Windows the same
panel also sits in the publisher's browser menu bar; the Mac has no such shell - the games
run in the bundled Flash runtime - so the launcher's own **Mods** button is the entry point
here. A change lands at the next login of that game.

Ports: mirror 8950, CD games / portal 8081, relay 8900. They are only bound to
`127.0.0.1`, so nothing is exposed to your network.

## What runs

| process | port | job |
| --- | --- | --- |
| `lpo/server.py` | 8950 | the online world's mirror, accounts website, profile editor |
| `fake_server.py 8081 --no-hosts` | 8081 | answers the CD games' activation checks, serves the portal, relays online traffic |
| `macos/mac_relay.py` | 8900 | the address the browser is pointed at; routes online names to 8950 and everything else to 8081 |

The split is the same rule the Windows server uses: anything addressed to
`www1.little-prince.com.hk` - or to `/web`, `/admin`, `/play`, `/LP/personal/` -
is the online world; everything else belongs to the CD games.

## Troubleshooting

* **"Chromium is damaged and cannot be opened"** - the download kept macOS's
  quarantine flag. The launcher clears it; if the dialog still appears run
  `xattr -dr com.apple.quarantine macos/runtime/Chromium.app`.
* **A page asks to run Flash once** - Chromium 87 gates Flash behind a prompt.
  The launcher pre-allows `127.0.0.1` for you; if you see the prompt anyway,
  allow it once and it is remembered in the profile.
* **"I registered an account but cannot log in"** - the game asks for the publisher's
  own addresses (`www1.little-prince.com.hk`, `www.starwish-fair.com`). The launcher's
  browser routes those names back to this machine; your normal browser does not, so it
  reaches the real publisher and the login fails there. Always start the game with
  **Play online world** / **CD LP1-3** in the launcher, never by pasting a local
  address into your own browser.
* **The window never appears, only a terminal** - this Python has no Tk. Install
  the python.org build, or keep using the terminal version (`--console`) - the
  games behave identically.
* **No sound / a black picture** - give Chromium a moment after login; the first
  frames are the loading screen.
* **A server row is red** - press **Start servers**; if a port is taken by an
  older run, quit that first with `Stop servers`.
* Logs: the launcher window's log pane, plus `macos/runtime/` for the browser
  profile (delete it to reset Flash permissions).

## Files added for the Mac

```
LittlePrinceLauncher.command     double-click entry point (runs the launcher)
launcher_ui.py                   the window itself - shared with the Windows launcher
macos/launcher_gui.py            the macOS backend behind it: servers, games, runtime
macos/mac_relay.py               the relay the browser is pointed at
macos/setup_runtime.py           downloads Chromium M87, checks the plugin
macos/runtime/PepperFlashPlayer.plugin/   Pepper Flash 32.0.0.465 for macOS
macos/build_mac_zip.sh           makes a Mac-only zip (skips the Windows files)
```

The Windows files (`Start.bat`, `Start_Server_GUI.pyw`, `browser/`) are unused on
the Mac and are left out of the Mac-only zip, but keeping them in the folder does
no harm.  `launcher_ui.py` is NOT one of them: it is the window both launchers
draw, so it travels in both packs.
