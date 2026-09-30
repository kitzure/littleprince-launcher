# How it works

The technical side of Little Prince Launcher: what gets patched and why, what the
relay replaces and how a client talks to it, and the full list of functions and
services the package provides.

For the player-facing guide to the games, see [GUIDE.md](GUIDE.md). For the
step-by-step patch recipe with FFDec commands, see [PATCHING.md](PATCHING.md).

---

## 1. What the package replaces

The four titles were built around a publisher server that no longer answers:

| What the client expects | What it gets instead |
|---|---|
| `http://www1.little-prince.com.hk/littleprince/amfservice/gateway.php` (AMF login, save, mail, friends, ranks) | `lpo/server.py` on `127.0.0.1:8080`, answering the same AMF calls |
| A licence/activation check per title | The SWFs are patched so the full version opens without a key |
| Adobe RTMFP multiplayer (shut down by Adobe) | `lpo/mp_relay.py`, a local lobby/room relay |
| The games' own website pages | `patches/LP1|LP2|LP3/index.html` and the relay's own `/play`, `/play-flash`, `/web`, `/mods` |

Everything runs on the user's machine. Nothing is forwarded to the real server
unless it was explicitly turned on (`LPO_FORWARD=1`).

---

## 2. How the patching works

### 2.1 The two gates

Each CD game has the same shape: a **Zinc projector** (`start.exe`, UPX-packed)
whose **entry SWF is embedded inside the exe**, plus external SWFs (`reg.swf`,
`login.swf`, `start.swf`, `index.swf`) that are read from the content folder at
runtime. Only the external ones can be edited - and that is enough, because the
licence gate is reachable from them:

1. **The Activate button.** The registration form's green button calls a
   serial/email validator (`checkInput()` / `connectActivationServer()`). It is
   redirected to the game's own *full version* entry point instead
   (`_root.startInit()`, `_root.loadFullVersion()`, or
   `Prince3.PrinceSystem.loadOpening()`).
2. **The licence function.** `activationSuccess(sn, hdkey, akey)` guards both
   full-version detection *and* account save/load. It is overridden to return
   `true` from the loaded SWF, on the game's own root timeline:

   ```actionscript
   if(_level0) { _level0.activationSuccess = function(sn, hdkey, akey) { return true; }; }
   ```

   Because the game's root is `_level0`, a patch placed at the top of **frame 1
   of a loaded SWF** runs before that SWF's own preloader and overwrites the
   gate that lives in the (uneditable) embedded entry SWF. Two supporting
   switches are pinned the same way where a build needs them: `_level0.getHDKey`
   is forced to a fixed string, and `saveActivation(...)` is seeded with a fake
   activation record.

### 2.2 What is actually patched

| Game | SWF | Script | Change |
|---|---|---|---|
| Prince Adventure 星願歷奇 | `3-Prince-Adventure/reg.swf` | `frame_1/DoAction` | appended the `activationSuccess` override |
| Prince Adventure 星願歷奇 | `3-Prince-Adventure/reg.swf` | `frame_3/DoAction` | `btn_activate.onRelease`: `this._parent.checkInput();` → `Prince3.PrinceSystem.loadOpening();` |
| Prince Adventure 星願歷奇 | `3-Prince-Adventure/login.swf` | `frame_1/DoAction` | prepended the same `activationSuccess` override |
| Little Prince 星願小王子 | `2-Little-Prince/reg.swf` | `frame_1/DoAction` | prepended the `activationSuccess` / `getHDKey` / `saveActivation` block |
| Little Prince 星願小王子 | `2-Little-Prince/reg.swf` | `frame_3/DoAction` | `btn_activate.onRelease`: → `_root.startInit();` |
| Starwish Legend 星願外傳 | `1-Starwish-Legend/reg.swf` | `frame_3/DoAction_2` | `btn_activate.onRelease`: → `_root.loadFullVersion();` |
| Starwish Legend 星願外傳 | `1-Starwish-Legend/start.swf` | `frame_3/DoAction_15` | `loadOpening()`: always `loadFullVersion()` |
| Starwish Legend 星願外傳 | `1-Starwish-Legend/start.swf` | `frame_3/DoAction_32` | `loadTrialVersion()`: `initSystem("cddemo")` → `initSystem("cdsingle")`, no DEMO user |
| Starwish Legend 星願外傳 | `1-Starwish-Legend/index.swf` | `frame_3/DoAction_34` | same `initSystem("cdsingle")` change |

The same SWF can appear in more than one game folder; the per-title copies are
kept together under `patches/LP1/`, `patches/LP2/` and `patches/LP3/`.

### 2.3 The LPO patch layer

Little Prince Online's own client is patched separately, in
[`lpo/patches/`](lpo/patches/README.md). Only the **sources** are committed
(`CastleHall.board-forward.as`, `MapForestMaze.door-open.as`) - the rebuilt
`lib.*.swf` files are patched copies of the publisher's `lib.swf` and are not
redistributed here. The scripts that rebuild them live in `tools/swf-build/`.

### 2.4 Why the client can reach `127.0.0.1`

The games call the publisher's **absolute** hostname, so a local server is only
reached if the name is redirected:

- **Windows** - `Start.bat` adds
  `127.0.0.1 www1.little-prince.com.hk` (and friends) to the hosts file, which is
  why it asks for administrator rights; `Revert_Hosts.bat` removes them again.
- **macOS** - the launcher runs the bundled Chromium with
  `--proxy-server=http://127.0.0.1:8900` (`macos/mac_relay.py`), so the same
  absolute URLs land on the local relay without touching the hosts file.
- **The publisher's own homepage** is still live, so the games must *never* be
  opened in the system browser: the login would go to the real publisher. Every
  Play path launches the bundled Flash-capable browser instead.

---

## 3. How the relay works

Two servers, both in `lpo/`, both plain Python standard library.

### 3.1 The AMF gateway - `lpo/server.py`

- Listens on **8080** (`LPO_PORT`), and serves three things on that one port:
  the AMF gateway, the game file tree, and the accounts website.
- Speaks **AMF0** itself (`lpo/amf0.py`) and dispatches on the service name the
  client sent (`extract_service_type()` handles both the MMO's doubly-nested
  array and the cloud games' flat call).
- The publisher's real answers were captured once into `lpo/captures/bodies/`
  (`login4`, `checkMail`, `getMyFriends`, `canPlayMaze`, `getMonthScoreRank`,
  `totalItems`, `haveNewEmail`, `checkUpdateVersion`, `mazeRec`,
  `getMonthMazeRank`) and are replayed - but only *after* the hand-written
  handlers have had their turn, because several captures hold empty lists that
  are exactly the bug being fixed (an empty rank board, a Mail panel listing
  everyone).
- Player state reported by the client (coins, gems, scores, items, level bests)
  is persisted back into the account record before the reply is built, so a
  re-login gets the progress back.
- An unknown service is answered locally with a generic `{"response":"ok"}`, and
  the request's own field names are logged so it can be implemented later. A body
  that cannot be decoded at all is dumped to `lpo/captures/unreadable/` with a hex
  prefix - that is how the real Flash Player's TYPED_OBJECT/REFERENCE markers
  were found.
- Response ordering matters: the client maps answers to its requests **by
  index**, so the gateway answers exactly as many objects as were asked for, and
  the per-feature branches (maze, notice, ranks, friends, mail, cloud login) run
  before the generic captured-replay lookup, otherwise a `login` request would
  partial-match the MMO's `login4` capture.

### 3.2 The multiplayer relay - `lpo/mp_relay.py`

- Replaces **RTMFP**, which Adobe shut down. It is not an RTMFP implementation:
  it is an XMLSocket-style message relay that speaks the *game's own* lobby
  protocol (the same `parse_frame()` fields the client sends: lobby, room, seat,
  ready, chat, and the player list).
- Serves the two ways the clients connect:
  - **real Flash** (the publisher's browser or the projector) over plain TCP,
    including the socket policy request Flash sends first on the same connection;
  - **Ruffle** (the web player) over a **WebSocket** - hand-rolled
    (`ws_key_accept`/`RawWS`), so no third-party dependency.
- Keeps each lobby's rooms, seats and ready flags server-side and **replays the
  current state to a new connection**, so a fresh joiner sees who is already
  there instead of an empty room.
- Defaults to `--host 0.0.0.0 --port 8443`. In this package it is used on
  loopback only: two windows on one machine work, and a second PC would need the
  relay host changed in the patched client.

### 3.3 The pack installer

`lpo/server.py` also drives the downloads: `PACK_SOURCES` holds a mirror list per
title, `fetch_pack()` pulls the first URL that answers and unpacks it, and
`cloud_state_reply()` compares the local `cloud/` tree against `fetch_cloud`'s
manifest (size, and a hash for the client files) to decide whether a card is
"installed", "repairable" or "missing". A file that is missing or the wrong size
is repaired file by file when fewer than `REPAIR_LIMIT` (40) files are off, and a
download that finishes without satisfying the manifest is retried at most
`CLOUD_ATTEMPT_LIMIT` (3) times.

Where the packs live:

| Pack | Host | Note |
|---|---|---|
| LP1 pack, browser pack, LPO pack | catbox.moe | An anonymous host: one direct link, no sign-in, kept until 2 years of no access |
| SWF patch files (`SWF_PACK_URL`) | catbox.moe | The patched CD/website SWFs |
| Gone pack (`GONE_PACK_URL`) | catbox.moe | Everything the publisher's server has ever served, for repairs after their 404s |
| LP2 pack, LP3 pack | pixeldrain | ~300 MB and ~352 MB - over catbox's 200 MB per-file limit, so they use Pixeldrain |

Pack installation uses Catbox, Pixeldrain or HTTP(S) self-hosted URLs. Google
Drive is not an installer source or fallback. Legacy source selections become
Auto; Drive custom links and redirects are rejected before connecting.

---

## 4. Functions and services

### Accounts and login

- Register, sign in and sign out on the local accounts site (`/web`); sessions
  are cookie-backed (`lpo_session`).
- `login4` / `Prince1|2|3_personal.serviceRequest` are answered with the local
  account's record. Guest logins are off - an account has to be created on
  `/web` first.
- Profile fields: name, school, the nine **worlds** (each one a bit in
  `permission`, checked by the client as `permission & (1 << worldIndex)`), and
  the per-game saved record the mods panel edits.
- Prince Adventure's activation handshake
  (`checkActivation` / `activationSuccess` / `connectActivationServer`) is
  answered on the same `Prince3_personal` target.
- `checkUpdateVersion` is answered so the client never shows an update popup.

### Friends

- `findFriends` - search for a player by name.
- `requestBeFriend` - send a request; it stays **pending** until the other
  account confirms it.
- `confirmBeFriend` - accept, from the letter the request arrived as.
- `deleteMyFriend` - remove a friend.
- `getMyFriends` / `getMyFriends2` - the friend list, and mutual friends.
- `friendResultInGame` - the in-game 1st/2nd/3rd board's friend data.

### Mail

- `mailToFriend` - write to a friend.
- `checkMail` / `readMail` / `deleteMail` - the Mail panel (the room's owl).
- `haveNewEmail` / `checkNewEmail` - the unread count, which is what makes the
  owl glow.
- The store is `lpo/mails.json` (per account, local only).

### Notice board (佈告欄)

- `getNotice` / `readNotice` are answered from `lpo/notices.json`, so the castle
  hall's board is live instead of frozen.
- A notice card carries its own picture, styled text blocks and a whole-card
  theme (colours, gradient, pattern, presets).
- Animated notices are a **sprite sheet** - the patched client shows one frame
  per timer tick. A plain animated GIF does not work: Flash's loader decodes it
  to its first frame.

### Leaderboards and scores

- The castle's rank boards (coins, score, items, crystals, maze) are compiled
  from the local accounts by `rank_reply()` / `lpo_rank_reply()`, each with a
  monthly and a total tab.
- The mini-games' 積分榜 is per game and level
  (`getMonthScoreRank` / `getTotalScoreRank`), and `setScore2` stores one level's
  best score (`lpo/level_scores.json`).
- Scores are kept apart **by title**: LP1, LP2 and LP3 have their own points key
  and their own board (`game_key()`, `score_field()`, `board_field()`), so
  maxing one leaves the other two alone. LPO keeps its own per-level scores and
  crystal ranks.

### Mods presets

- `/mods` (and the `/web` mods panel) writes a preset into an account's saved
  record; the game reads it at its next login.
- LP1 - every level cleared, max points, all gems, max every level's score.
- LP2 - every boss defeated, every item obtained, unlimited item use, max points,
  all gems, every level cleared.
- LP3 - every card unlocked, every level unlocked, unlimited cards, max points,
  every boss defeated, all gems.
- LPO - every item obtained, unlimited weapon use, every level unlocked, coins
  maxed, every crystal maxed.
- There is also a per-field editor for whatever values a title can store.

### The admin site and the pages

| Path | What it is |
|---|---|
| `/web` | The accounts site: register/sign in, profile, account, worlds, stats, account list, billboard editor, mods panel, LPO game-folder setting |
| `/admin` | The guest profile / defaults editor (redirects to `/web`) |
| `/mods` | The mods presets page |
| `/` | The portal: the four game cards, install state, and the download buttons |
| `/cloud/install?code=LPn` | Server-rendered download page with a progress bar and meta refresh, so it works without JavaScript |
| `/play` , `/LP/Po/` | Little Prince Online in Ruffle (the install-free path) |
| `/play-flash` | Little Prince Online in real Flash (the bundled publisher browser) |
| `/LP/personal/<code>/` | The launcher's entry URL for the three CD/cloud titles |

Unknown paths under `/web/` are served from the package; `/web/play.html` stays
reachable for older builds.

---

## 5. Ports

| Port | Who | Why |
|---|---|---|
| 8080 | `lpo/server.py` | AMF gateway, game files, accounts website, portal |
| 8900 | `macos/mac_relay.py` | The proxy the bundled Chromium is pointed at on macOS |
| 8443 | `lpo/mp_relay.py` | The lobby/room relay (loopback in this package) |

---

## 6. Verifying a rebuild

1. Export the scripts of the rebuilt SWF with FFDec and confirm the **script
   count matches the original**.
2. `diff -rq pristine_out/ out/` - only the intended scripts may differ. This is
   the check that catches a recompile which silently dropped the rest of a
   frame's script.
3. Run the game with the relay up: it must reach the **world map**, with no error
   dialog (`錯誤:090` / `錯誤:091` mean the licence gate still failed) and no
   trial banner.

The relay itself logs every dispatch (`Dispatch: service='…' target='…'`) and
says what it answered with, which is the quickest way to tell "unhandled
service" from "handled, but the client ignored it".
