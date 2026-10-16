![ai gen banner lol](banner.jpeg)
<p align="center">ignore that ai gen banner, since the offical DID use ai on these 2 characters</p>

# Little Prince Launcher

https://kitzure.github.io/littleprince-launcher/ <br>
a launcher for a game created in 2006 which supports as below:

- Little Prince 星願小王子 (LP1)
- Starwish Legend 星願外傳 (LP2)
- Prince Adventure 星願歷奇 (LP3)
- Little Prince Online 星願小王子 Online (LPO)
- 星願思語 · 星空聯盟 (LP4) - the publisher's web build, played in the launcher's portal
- 星夜重圓 Starwish Reunion (LP5) - the Android app, run in a local Android emulator
  that the launcher sets up; a patched APK for Android 10+ phones is on the
  [website](https://kitzure.github.io/littleprince-launcher/guide.html#android)

## What it does

- Unlocks locked minigames to make it playable
- Full function localstorage to storage your user's data
- Customizable user settings in the webpage (LPO's billboard)
- Local Multiplayer function for LPO (some of the minigames)
- Mod selection for each games

## The launcher window

Unzip and run **Little Prince Launcher.exe**, and answer Yes at Windows'
administrator prompt. Python comes bundled - nothing else to install. Pick a
game and press Play once: the launcher downloads the game and the publisher's
game browser if they are missing, then opens the game.

The release keeps its top level short - the exe, `WebView2Loader.dll` (which
the exe needs beside it), this README and the guide. Everything else, including
the games it downloads, lives in `app\`.

How it fits together:

- `launcher-app/` - the exe (Tauri, Rust). It asks for admin rights, starts the
  bundled Python, shows the window and stops the servers when it closes.
- `launcher_web.py` - everything behind the window: the same servers, hosts
  redirect and downloads the old Tk window (`Start_Server_GUI.pyw`) ran.
- `launcher/ui/` - the screens: plain HTML/CSS/JS, served by `launcher_web.py`.
  Edit them and reopen the launcher - no rebuild needed.
- `tools/build_launcher.py` - builds the release zip: the exe, the embeddable
  Python from python.org with Pillow, and the package. Needs Rust; with Rust's
  GNU toolchain also a MinGW-w64 `bin` folder (for `dlltool`).

## Disclaimer

This is an unofficial project for educational and game preservation purposes.
It is not affiliated with, endorsed by, or sponsored by Starwish Little Prince
Ltd., Starwish Fair, or the original developers.

All original games, game code, artwork, music, characters and trademarks
remain the property of their respective rights holders. This project claims
no ownership of those materials. This disclaimer does not grant permission
to copy or redistribute copyrighted content.

- Use only game copies you legally own. Back up your files before applying
  any patches.
- Do not sell or commercially bundle this package, or use it for piracy.
  No serial keys or game licences are provided.
- Support official releases whenever they are available.
- Rights holders can contact the repository maintainer with any concerns.
  Affected content or the repository will be removed upon a verified
  rights-holder request.

**THIS LAUNCHER IS FREE. DO NOT PAY FOR IT.**

Little Prince Launcher is free to download and use. We do not sell it or
authorise anyone to sell it on our behalf. Anyone claiming to offer an
"official paid version" is not associated with this project.

Download it from this repository or the project website.
This warning applies to the launcher, not to legitimate purchases of
the original games.
