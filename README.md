![ai gen banner lol](banner.jpeg)
<p align="center">ignore that ai gen banner</p>

# Little Prince Launcher

A launcher and local server for a set of discontinued Hong Kong Flash games. The
games call the publisher's server for a login, a save, mail, friends, the notice
board and the ranks; this package answers those calls on your own machine, so the
games work again - single player and local online play both.

- Little Prince 星願小王子 (LP1)
- Starwish Legend 星願外傳 (LP2)
- Prince Adventure 星願歷奇 (LP3)
- Little Prince Online 星願小王子 Online / 星之國 Online (LPO)

## What it does

- Patches each game's licence check so the full version opens without a key.
- Answers the games' own AMF calls locally (login, save, mail, friends, ranks).
- Local online play: a lobby, rooms and player lists, on one machine.
- Friends and mail between local accounts.
- The castle's notice board (佈告欄), with an editor.
- Leaderboards, with each title's scores kept apart.
- Mods presets per title.
- A local accounts website, plus a launcher window that starts everything.

## How to install

1. Download [the latest Windows/macOS launcher ZIP](https://github.com/kitzure/littleprince-launcher/releases/latest/download/littleprince-patcher.zip).
2. Unzip it into a new folder and install Python 3 with Tkinter if needed.
3. Run `Start.bat` (Windows) or `LittlePrinceLauncher.command` (macOS).
4. Choose your game in the launcher; download any missing files when prompted.

Pack sources are **Catbox, Pixeldrain or a self-hosted URL**. Google Drive
installation and fallback links are removed. This repository is the source code;
the release ZIP is the ready-to-use launcher package.

## Documents

- **[HOW-IT-WORKS.md](HOW-IT-WORKS.md)** - how the patching and the relay work,
  and every function and service that exists.
- **[PATCHING.md](PATCHING.md)** - the step-by-step recipe for the SWF patches.
- **[GUIDE.md](GUIDE.md)** - a player's guide to all four games.
- **[HANDOFF.md](HANDOFF.md)** - the developer notes: layout, build and traps.
- **[TODO.md](TODO.md)** - what is still open.

## Disclaimer

For educational and preservation purposes only. All games, artwork, music,
characters and code belong to Starwish Little Prince Ltd. / Starwish Fair and
their developers. Nothing here claims any right over them.

- Own the game first. Patch only a copy you legally own, and keep a backup.
- Do not sell or bundle this package commercially, and do not use it for piracy.
  No serial keys or licences are provided here.
- Support the official release if the company ever makes these games available
  again. If a rights holder asks, this repository should be removed.

## Credits

- **Starwish Little Prince Ltd. / Starwish Fair** (`little-prince.com.hk`,
  `starwish-fair.com`) - the original publisher and rights holder of the
  星願小王子 family.
- **JPEXS Free Flash Decompiler (FFDec)** - used to open, read and patch the SWF
  clients. https://github.com/jindrapetrik/jpexs-decompiler
- **Chromium M87 + Pepper Flash** - the last Chromium that still ships the Flash
  plugin, used for the "real Flash" path.
- **Python 3** (standard library only for the relay) and **Tkinter** - the relay,
  tools and launcher window.
