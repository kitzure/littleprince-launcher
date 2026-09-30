# Outstanding items

Reported by the user, newest first. **FIXED** items say what was done and how it
was verified; the rest are still open.

## Fixed in this pass

### 多人連線模式 could hang on 'connecting' for ever — **FIXED (shipped)**
Reported: "pressing 多人連線模式 hangs on a connecting message forever", blamed on the
billboard / friend work. What the bytecode actually says:
- `UI_multiplay.eBtnOnRelease` for `mcMultiplayBtn` does `Bridge.flow.connectServer();
  gotoAndStop("connectserver")`. The `connectserver` frame carries NO frame script (the UI's
  labels are registered by `Utils.batchAddFrameScript` in the UI classes and `connectserver`
  is not among them), so the ONLY thing that leaves that screen is the relay's `welcome`
  reply: SERVER_CONNECTED -> `connectGameLobby()` -> LOBBY_CONNECTED -> `gotoAndStop("lobby")`.
- `MultiplayFlow.eP2PStatus` had no branch for `NetEvent.SERVER_CONNECT_FAIL` (which `P2P`
  dispatches from its IOError/SecurityError listeners and from its own connect try/catch), so
  a relay that is down, refused, or unreachable left the player on 'connecting' for ever with
  no message and no retry.
- The recently changed classes are **not** on that path: since the last shipped build only
  `castle/AddFriend.as`, `castle/Notice.as` and `home/Mail.as` differ, every block added to
  them sits inside a `try/catch` on another screen, and `afArrowsSync` (the only new
  ENTER_FRAME handler) is fully guarded - it cannot throw out. So the billboard/friend work
  is ruled out, not blamed.
Fix (`PrinceOnline.flow.MultiplayFlow`, one class):
- a 10 s watchdog `flash.utils.Timer(10000,1)` armed with the connect attempt (covers a relay
  that answers nothing at all - no event ever arrives in that case),
- a `NetEvent.SERVER_CONNECT_FAIL` branch,
- one shared recovery `mpConnectFailed()`: leave the connecting screen the way the game's own
  exit does (`returnGameSelectLevel()` + `iLeaveLobby()`), then show the client's existing
  `connecterror` alert (EN/ZH, already in settings.cxd). It refuses to act when the failure
  arrives before the UI reaches the connecting screen (a synchronous XMLSocket error is
  dispatched from inside the constructor) - the watchdog reports it once the screen is up.
- the success branch now switches the screen FIRST and guards `introMySelf()`, so a throw in
  our own added call can no longer strand the player on 'connecting'.
Verified: relay protocol asserted with raw clients (real-Flash policy handshake, the silent
client path, the Ruffle WebSocket path, and the lobby broadcast - `mp_fix_verify_relay.py`,
ALL PASS); the built class re-read from the SWF with only `MultiplayFlow.as` differing, no
duplicate definitions; and the client boots to its login screen under Ruffle with the patched
lib and zero AVM2 errors. The on-screen recovery itself cannot be driven from here (no
synthetic input reaches Flash/Ruffle's player) - it needs one look from the user.
NOTE the third served copy: `~/littleprince-online/lib/lib.swf` was a STALE build (the
pre-`decode()` one that still called `decodeJSON()` and still pointed at
`rtmfp://p2p.rtmfp.net`), and the mirror's own `server.py` has no patch layer - anything
served from that folder gets it. All three copies are now the same md5 (6a529e70...).

### Players never announced themselves - empty room lists everywhere — **FIXED**
`MultiPlayLobby.introMySelf()` (which sends the MSG_INSTRO record carrying name,
avatar and seat) is **never called anywhere in the shipped client** - the only
occurrence of the name in any swf is the method definition itself. So `players[pid]`
was empty on every peer, `inRoom()` dereferenced `players[from]` from INROOM posts of
strangers (or silently did nothing), and room lists never populated: "i joined a
lobby but it wont show the user". `MultiplayFlow`'s LOBBY_CONNECTED case now calls
`this.p2p.introMySelf()` before showing the lobby. Combined with the relay replay
(below) both directions are covered: old players hear the newcomer, the newcomer
gets everyone else.

### Relay lobby snapshot had two more holes — **FIXED**
- The connect record's gameID is unreliable (the client sends it before its own
  `connectGameLobby()` has run - it arrives empty), so the connect-time replay read
  the wrong lobby. The lobby key now resolves from the first post and the replay
  happens there.
- The replayed record was the intro-time snapshot: a player who had since joined a
  room was replayed with `roomID:-1`, so joiners saw them as still in the lobby.
  The replay now stamps the relay's live seat onto the record. Also stores
  SETPLAYERSTATUS so the ready flag survives into snapshots.
  Tested with two raw clients: replay-with-seat, live intro, and leave all pass.

### Lobby exit dead on the second press / the relay's "not real time" room list — **FIXED**
- `UI_base.eBtnOnRelease`'s btnExit guard reads `!contentLayer.pause`, but the exit
  itself calls `Bridge.flow.pause()` and nothing ever cleared it - so the FIRST exit
  was swallowed mid-animation and every later press did nothing. `MiniGameFlow.returnGameSelectLevel()`
  now clears `contentLayer.pause` (covers the lobby, room and in-game exits - they all end there).
- The relay never told a NEW connection who was already in the lobby (the client builds
  its room list purely from MSG_INSTRO posts it hears), so a fresh joiner saw an empty
  lobby - "not real time to check the person is on the room". `mp_relay.py` now keeps
  each client's last INSTRO and replays them to every new connection
  (`replay_lobby_state`), and posts without a gameID stay in the connection's own lobby
  instead of a phantom "0". Tested with two raw clients: replay + live intro + leave all pass.

### Maze stuck on its loading screen (looping music) — **FIXED**
`maze.swf` fetches `lib_resMaze.swf` ROOT-relative (the publisher serves it at both
paths); the mirror only had `lib/lib_resMaze.swf`, so the root fetch 404'd and the
preload never finished. Added `lpo/patches/lib_resMaze.swf` (byte copy) - the mirror's
patch lookup serves it at the root path now.

### The owl froze on letters from unknown senders — **FIXED**
`checkMail`'s `ulist` only carried senders still present in accounts; a letter from a
deleted/old uid left `user` undefined and `setCharacter()` threw #1009, wedging the
panel ("sometime it works, sometime it froze"). The ulist now always includes every
sender, with a placeholder record when the account is gone. Verified live: empty inbox,
known sender, and unknown sender (name "?") - all render and the panel stays responsive.

### The forest/Magic-World teleport lost its animation — **FIXED (v2 of the race fix)**
The first race fix replaced the whole door flow with an instant `loadMap*`. v2 restores
the original animation (door `open` -> the character's `tranfer` float -> popup -> map
load -> the `back` arrival animation) and keeps the reliability: the `tranfer_end` label
handler attaches before the animation starts, a 240-frame watchdog forces the transfer
if the label event never fires, and the arrival pause (waiting for `back_end`) also
gives up after 240 frames so the player always regains control. The armed latch for the
return door stays. lib.swf = 04cf11249ac9c0459cb4df9ed9e029e2, export-verified surgical
(only MapForest / MapMagicWorld / MiniGameFlow differ from the base).

### The site avatar after an in-game look change — **verified working, no code change**
Cloth changes (`setCloth` -> `{"type":<slot>,"data":<value>}`) parse fine and persist
to the ACCOUNT (`saved ['totalItems'] -> <email>` proves the live path); the site
renders from the same account profile and the rig dataset already has the tiger parts
(虎帽/虎衣服/虎褲/虎鞋/虎尾). A look changed BEFORE this pack may sit in the old global
profile - redo it once in-game (更改樣貌) with this build and it shows on the site.

### Launcher close left the relay running — **FIXED**
The window's close path stopped the fake server and the online server (both in-process
threads) but not the relay - the one real subprocess (`mp_relay.py`, spawned by
`Relay.start()`). It outlived the window and had to be killed from Task Manager.
`WindowsBackend.close()` now stops `relay_srv` too, and `Relay.stop()` waits 3 s after
`terminate()` and falls back to `kill()`. The Mac side already kills its whole process
group in `stop_servers()`.

### Pack cleanup — **DONE**
Removed `screenshot_server_gui.png` (a dev screenshot of the window) and its two
README references; nothing else in the pack was junk (banners/ is the launcher's own
art, fake_server.py is the CD games' server, captures/ are replayed by lpo/server.py).

### The owl (Mail) listed people the player never added — **FIXED**
Reported: "the owl one sometime is bugging - when i tried to write a message it shows the
list of the people even i don't add people". `getMyFriends` used to return EVERY account
on the machine (a shortcut from when the boards were empty), so the Mail panel's 我的朋友
write list showed 6 people on a fresh account. Now:
- `friends.json` per account (uid list), empty until someone is actually added;
- `findFriends2` search + `requestBeFriend` / `confirmBeFriend` / `deleteMyFriend` make
  the AddFriend panel's 新增朋友 flow real;
- `mails.json` + `mailToFriend` / `checkMail` / `readMail` / `deleteMail` /
  `haveNewEmail` deliver letters between local accounts (the owl glows on unread).
GOTCHAS for this protocol:
- the client packs requests as an ECMA array: the request dict arrives as
  `[[{"0": {...request...}}]]` - `_request_object()` must dig through lists/keyed
  dicts, and `data` lists arrive as dicts keyed "0","1",... (`_as_list()`);
- AMF numbers decode as floats: uid 10003 arrives as 10003.0 - normalise with
  `_num_str()` or every uid compare silently fails;
- new services must be answered BEFORE the captured set (the getMyFriends/checkMail
  captures hold empty lists) and merged in `merge_friend_reply` for batch rides.
Verified live in a rig session: compose showed only the added friend, sent a letter
from wangzi1 to wangzi2, mails.json received it, haveNewEmail counted it.
Both stores are excluded from the pack (user data).

### The relay's port-check log spam — **FIXED** (shipped)
The launcher GUI probes the relay port every 500 ms for its status light; each probe
was logged as "closed without sending (the launcher's port check)" - ~2 lines/second.
The probe now accepts-and-closes silently. Live relay log: 3 lines total across a
whole test session.

### Minigame multiplayer: lobby never loaded — **FIXED** (shipped)
The shipped `lib.swf` called `decodeJSON()`/`encodeJSON()` - undefined everywhere in
the SWF - so the first relay message threw and the client sat on connectserver for
ever. Fixed to `decode()`/`encode()`. Also race-proofed the forest/Magic-World map
transfers (a frame-script timing race in Ruffle could freeze the character on
arrival). Verified live: 多人連線模式 -> lobby -> joined Room 1.

### The site's navigation: player card out, Leaderboard in — **DONE**
The user asked for the player card gone and a real leaderboard tab ("like the publisher's:
how rich / how many scores"), so:
- the rail's `data-tab="card"` button and the `#tab-card` section are gone;
- a new `data-tab="board"` -> `#tab-board` (with `<div id="board-body">`) holds the board,
  rendered by `boardLoad()`/`renderBoard()` from the SAME data the home screen already
  fetches (`loadCard()` -> `/web/api/games` -> `CARD.board`), so the tab costs no request:
  rank / player / Score / Coins / Items, the self row highlighted, `top score` and
  `richest` pills, and the account's own rank+score as chips;
- the character/outfit block was NOT deleted with the card: it moved into
  User settings -> Profile (`<div id="look-body">` + `renderLook()`);
- the phone CSS gives the figures 12px and keeps a label on each (`score ... coins ...`).
GOTCHAS worth remembering for this file:
- `renderNavigation()` toggled `$('tab-card')` directly, so removing a panel without
  updating that function is a null-dereference crash, not a cosmetic bug. Any tab rename
  must touch: `renderNavigation()`, `show()`, `loadInto()`, `loadCard()`'s re-render, the
  `privateTab` list, and `cardClear()`.
- `loadInto()` used to rely on the card page's own refresh; it now clears `CARD` and calls
  `loadCard()` so the board and the character follow the account being viewed.
- `cardLoad()`/`renderCard()` are dead but left in place, guarded (`if(!$('card-body')) return;`).

### The Mac-side empty avatar: missing Pillow — **cause found** (fix in flight)
The user's screenshot showed the character area empty with "Pillow 未安装". Their Mac's
Python has no Pillow, so `lpo/avatar.py` cannot paste the exported PNGs and every avatar
(character panel AND the home head) fails there. The pack is fine - the same code renders
correctly on a box with Pillow. Fix in flight: lazy/guarded import with a message naming
the exact command, plus the macOS launcher detecting and installing Pillow on a worker
thread with bilingual strings.

### The leftover account on their leaderboard
"小王子玩家" lives in the USER'S OWN `lpo/accounts.json` on the Mac (an older pack shipped
`accounts.json`; current builds exclude it). Nothing to fix in the code: delete it under
User settings -> Accounts -> Delete on that row. Do not edit their store from here.

### The launcher's repeating log line — **FIXED**
Reported from a Mac screenshot: after a download finished the log repeated
`: the game files are complete` forever, with a bare colon.
Cause: `MacBackend._tick_download()` cleared `_dl['code']` but not `_dl['done']`, so the
window's tick (many times a second) re-ran the "download finished" branch every time;
with the code already empty the message came out as `': the game files are complete'`.
Fix: clear `done` as well, and only prefix the code when there is one.
Proof: `tools/test_download_log_once.py` drives the real method 50 times per case ->
one line each, no bare colon.

### The macOS launcher's untranslated text — **FIXED**
The shared window re-renders from the backend after the ZH/EN badge is pressed
(`Window.toggle_language()` -> `backend.language_changed()` + re-runs the hooks), but
`MacBackend` never implemented that hook and returned hardcoded English.
Fix: a 122-key EN/ZH table + `current_language()`/`tr()`/`game_label()` helpers and the
`language_changed()` hook; every hook now returns the selected language (status word,
stats, actions + summary, drawer rows and section labels, footer, log lines, download
dialogs, folder picker, console mode). Chinese wording reuses the Windows launcher's own
table so the two platforms agree. English values are byte-identical to before (AST-checked).
Verified: keys identical on both sides, no ZH value still English, no EN value containing
CJK, window launches 1180x690 with zero tracebacks, user's `lpo/profile.json` restored to
its original bytes (md5 `9c5ea22aa7b9ffa9e30badad0c6df2cd`).
NOTE for anyone screenshotting on Linux: this container has no CJK font, so Chinese renders
as boxes there. That is an environment gap, not a bug.

### Two packs, one Drive file - and the recovery script
Both agents were shipping to the same Drive file id (`1EO64npbr0ts9...`). The MP agent had
renamed it `littleprince-launcher-mp.zip` and uploaded 14.6 MB two minutes before a patcher
upload, so that build was replaced. It was recovered byte-for-byte from Drive's own revision
history (`tools/recover_drive_revision.py <md5> [name]`) and re-uploaded as its own file:
`littleprince-launcher-mp.zip`, id `PRIVATE_FILE_ID_REMOVED`, md5 `102f482c665ad23297f4a450b41fdd3b`.
`ship_zip.py` now REFUSES to overwrite a Drive file whose name is not one it owns (pass
`--force` to do it deliberately). Rule: one pack per Drive file id.

### The Mac dead end after "allow Flash" — **FIXED**
Reported: on the Mac, Chrome blocked Flash; allowing it changed nothing; the game only ran
after manually visiting `/play`. Cause is visible in the launcher's own code:
`macos/launcher_gui.py` opens `http://127.0.0.1:8950/LP/Po/flash`, which is the REAL-Flash page
(`play_flash.html`, a plain <object> needing the bundled Chromium M87 + Pepper Flash). When Flash
does not start, that page showed a notice saying "open it from the launcher instead - Play Little
Prince Online starts the publisher's browser" - *while the user was already in the launcher's
browser* - and left them to find `/play` themselves. Allowing Flash cannot help: current Chrome
has no Flash support at all, and the bundled M87 was the only Flash path.

Two changes, one on each side:
- `lpo/web/play_flash.html` (server-side, done): the page now decides whether Flash really
  started instead of trusting `navigator.plugins`. The plugin can be listed and still dead
  (blocked until allowed, broken install, Chromium without Rosetta on Apple Silicon) - which is
  exactly the reported case - so the <object> is asked directly via `PercentLoaded()`, and if it
  is absent/null/throws the page shows a 5-second countdown and hands over to `/play` (Ruffle,
  no plugin needed). Never a dead end.
- The macOS backend's `play_online()` (folded into the shared-UI job): open `/play` when
  `setup_runtime.chromium_binary()` or `plugin_ready()` is false, and keep `/LP/Po/flash` only
  when both are ready.

Lesson: a page that detects a missing plugin from a *list* is guessing. Ask the plugin itself,
and make the failure path automatic - the user's next move should never be "find the other URL".

### The player card now lives on the home screen — **DONE**
`lpo/web.html`: the home panel carries the card, simplified - tags **LP1 / LP2 / LP3 / LPO**
(`#home-gtabs`) with the selected game's status under them (`#home-games`, the existing `.tiles`
blocks), instead of all four games stacked plus the leaderboard on a separate page. Data comes
from the same `/web/api/games` payload (`server.player_card_games`), fetched once by `loadCard()`
and reused by the card page, which keeps the leaderboard and the character.

Verified against a sandbox copy of the store with a seeded account: LP1 `Stars=9 / 51, Gems=2,
Cards=1, Ending=seen`, LP2 4 stats, LP3 5, LPO `Coins=250, Crystals=12, Items=7, Maze record=3`,
and the served page contains `home-gtabs` / `home-games` / `loadCard` / `homeGame`.

### The header avatar showed the whole body, not the head — **FIXED**
The `.pavatar` CSS block set `object-fit:cover;object-position:top center` and then, later in the
SAME rule, `object-fit:contain;padding:4px` - so `contain` won and the full-body render was shrunk
to fit inside the 64px circle. Two declarations fighting in one block, and the loser was the one
that looked correct in the source.

Now `avatar.py` renders a real head view: `render(parts, view="head")` crops to the head's own box
computed from the RIG (not a fixed fraction of the picture - a crown makes the figure taller and
"the top 46%" then starts above the hat and cuts the face off), at 4x scale so the small round
frame stays crisp, and `avatar.ensure(parts, "head")` serves it as `<hash>-head.png`. The full-body
URLs stay valid: the view is only mixed into the cache key when it is not "full". `server.py` adds
`avatar_head_url` to `/web/api/me` and the page prefers it (`ACC.avatar_head_url || ACC.avatar_url ||
default.png`). Verified: full 111x224 vs head 222x222, and the crop holds for the default look, a
crown outfit and a ninja variant.

### Shipped to Drive — ONE pack now carries Windows + macOS + the avatar work
`tools/build_local.py` rebuilt `~/Downloads/littleprince-patcher.zip` (30.4 MB, 652 entries, md5
`ba8040064f07c6331b83f72ff845d075`, ALL CHECKS PASSED) and `tools/ship_zip.py` replaced the Drive
file `PRIVATE_FILE_ID_REMOVED` with it; Drive's own `md5Checksum`/`size` match
("VERIFIED"). Same link as before.

**Why the size moved 28.2 → 18.5 → 30.4 MB:** the original 28.2 MB pack was the combined one. My
first build of this pass excluded `macos/` ("belongs to the mac zip"), which took ~10 MB out - and
broke the Mac: `LittlePrinceLauncher.command` execs `macos/launcher_gui.py`, so the download threw
`can't open file '.../macos/launcher_gui.py'` on the user's MacBook. `macos/` is back IN, and the
Mac GUI's own dependencies were verified present: `lpo/server.py`, `fake_server.py`,
`lpo/fetch_client.py`, `lpo/fetch_cloud.py`, `lpo/mp_relay.py`, `lpo/avatar.py` + `lpo/avatar/`, the
Pepper Flash plugin, and `LittlePrinceLauncher.command` stored 0755 (exec bit intact).
The avatar dataset adds ~2 MB, hence 30.4 MB.

**Also newly excluded** (the mac builder already knew this): `lpo/notices.json` and
`lpo/level_scores.json` are the user's own data, like `accounts.json`. `lpo/profile.json` is NOT
user data - it is the synthetic default profile the package ships (`player@littleprince.local`,
uid 10001), so it stays.

A build check is only as good as its exclusion list: the old `no mac content: True` check PASSED
on the pack that could not run on a Mac. It is now `mac launcher entry` / `mac gui present` /
`pepper flash present`, plus `no user notices` / `no user scores`.

### The arms were splayed wider than the official art — **FIXED (shipped: arm slid 2 units in)**
Reported as "compare the arm adjust — the left arm is kinda too left" with the official art as
the reference, then "now it looks much weirder" for the rotation attempt that followed.

What the rig allows, established by rendering every candidate and looking at it (the numbers are
in `tools/{lean,sleeve,translate}_variants.py`, each writing its PNG with a distinct md5):

- The stand pose splays the arms ~28 deg out from vertical; the official art hangs them nearly
  straight. Both arms are ONE clip (99), and the left arm is mirrored from the right so the pair
  is symmetric (that mirror stays - it is what took the left hand off the head).
- **Rotating the arm does not work.** The arm art, the hand and the T-shirt sleeve are separate
  rigid pieces drawn for one pose. Turning about the clip origin swings the sleeve cap off the
  shirt's shoulder (already visible at 8 deg); turning the arm and holding the sleeve still
  leaves the arm hanging out of its own sleeve. 14 deg / 20 deg are visibly broken either way.
- **Sliding the ARM (not the sleeve) inward is the one change that survives**: the sleeve cap
  keeps the shoulder covered. 2 character units is clean-ish, 3.5 shows a step between arm and
  sleeve, 5 is broken. Shipped: `ARM_INWARD_UNITS = 2.0` (`matrix[4] += 2` on the right arm's
  entries except `.cloth`, then the usual mirror onto the left).
- Matching the hand-drawn art exactly would need NEW ARM ART (a sprite drawn hanging closer to
  the body), not a transform.

**Lesson about the comparisons:** `avatar.py` caches the rig in the module globals `_rig` /
`_rig_tried`, so a variant script that only swaps `DATA` renders the FIRST variant's rig for
every variant. Four identical pictures then look like a progressive comparison to a vision
model, which will happily describe the change it was primed to expect. Check the md5s differ
before believing any A/B render. Also: a stale `look_default.png` was sent to the user as
"current" once - regenerate every artefact in the same step that rebuilds the dataset.

Two REAL BUGS in the SWF frame reader came out of this comparison, both of which had
made the pose data lie:

- **Empty frames were being dropped** (`[f for f in frames if f]`), which shifts every
  later frame index, so frame LABELS (read from the XML) pointed at the wrong pose. Keep
  every frame; only the trailing one after the last `ShowFrame` goes.
- **A `move` record carrying a field was treated as a removal.** `PlaceObject2` with
  `placeFlagMove` and no CHARACTER is an edit when it carries a matrix, colour, ratio
  (the child's own frame!), name or clip depth, and only a REMOVAL when it carries none.
  Without this, the walk/run poses looked like they had no arms at all - and any scan for
  "a pose with both arms down" was searching nonsense. This is why the earlier conclusion
  "no authored pose has both arms down" needed re-checking; the re-checked answer is the
  same, but now for a reason that holds.

### The left hand sat on top of the head — **FIXED**
Reported as "the left hand is still on the person head, can you able to move it just like
the right arm did". Not a bug in the reading this time - it is what the art says. The
character's stand frame is `nomotion` (the pose the game stops on, and the one the
dressing room uses), and that pose is the ARTIST'S LITTLE PRINCE **holding his staff**:
right hand at the waist, left hand up beside his head. The arm clip has a single frame,
and scanning all 2341 character frames for a left hand below waist height finds only
action poses (board / buy / walk4), never a stand - so there is no authored "both arms
down" pose to switch to.

The dataset now re-poses the left arm: every `left_arm…` entry takes the same-subpath
`right_arm…` entry's matrix, mirrored (`(-a, -b, c, d, -tx, ty)` in the compositor's
convention). Base art AND slots - the sleeve is a slot, and it stayed behind with the
raised arm until both were moved. Verified by rect arithmetic (the two arms' placed boxes
are exact x-mirrors, identical in y) and by re-reading the render: both arms hang with
their sleeves at the shoulder and hands at the ends.

### The drawn hands sat off the wrists — **FIXED**
Reported as "the hand is being weird if you can see that". Two faults in how the rig was
read out of the SWF, both in the same place:

1. **An `alphaMultTerm="0"` placement is invisible and contributes no box.** The hand
   clip (sprite 92) places the authored weapon at frame 1 with multiply-alpha 0 and fades
   it in later; the reader counted it, making the hand's frame-1 box six times too wide.
2. **Placing by ffdec's export canvas.** That canvas is the union box over a sprite's
   *every* frame, and the hand clip's union was therefore wrong too.

Fix: the dataset now crops each PNG to its own content box and places it at frame 1's own
box, so the export canvas is not used at all; alpha-0 children are skipped in the box but
kept in the rig (`hand.item` is a faded-out container at frame 1 and is exactly where an
item goes). Also fixed while in there: a visited-set in the rig walk dropped the second
arm's `hand.item`/`accessaries` slots (both arms are the same clip), so only cycles are
skipped now. Verified by re-reading the render - both hands attach at the wrist, no gap,
no hand in the hair.

The look cache key now includes a stamp of `rig.json`, so a rebuilt rig can never keep
serving a picture drawn from the old one.

### The player card hung for ever — **FIXED**
Reported as "on that admin website playercard is not even working where it just
keeps loading and it didnt grab it". Not a slow request: `player_card_games()` did
`any(stars or gems1 or p.get("cards"))`, and `any(None)` is a **TypeError** — so the
whole GET route raised before `send_json`, nothing reached the browser, and the page
had no error to show. Every account whose profile has no `cards` key took the card
down (four of the five on this machine). **Fix:** coerce once
(`cards1 = _csv_ints(p.get("cards"))`) and test the coerced list.
Verified: `player_card_payload()` now builds for every account on the real
`accounts.json`, and `/web/api/games` returns 200 with the board and the avatar.

### The website's avatar was a different character — **FIXED**
The page showed a static 256x256 prince-with-crown PNG, and `DEFAULT_CLOTH` was
`小王冠 + 王子服/王子褲/王子鞋` — which is the little prince **NPC's** outfit, taken
from `character_anim.swf`'s author-time content. The player's real default is the
white kit with **no hat** (the publisher's own `login4` capture:
`髮3/運動服/運動褲/運動鞋`), and the player's own clothes are what the client reports
as it changes them.

- `lpo/avatar.py` + the `lpo/avatar/` dataset (3.1 MB, 520 parts) draw the real
  character: the container matrices out of `character_anim.swf` sprite 458 frame 1
  (`nomotion`), the part art out of `lib_items.swf`, pasted in the SWF's own depth
  order. Cached as `web/avatars/<sha1 of the parts>.png`, so the URL moves with the
  outfit and nothing has to be invalidated.
- The 16 cloth slots are now ordinary profile fields, so `UserRecord.setCloth`'s
  `{type:<slot>, data:<value>}` reports are saved, served back in the login4 reply's
  `cloth` array (so the game and the site can never disagree), and drawn.
- Shown on the home panel (`ACC.avatar_url`) and on the player card
  (`d.avatar_url`); the small round avatar uses `object-fit:cover;object-position:top`
  so it shows the head rather than the middle of the body.
- Verified: protocol suite (`tools/test_appearance.py`), HTTP suite
  (`tools/avatar_http_test.sh`) and renders for the default, prince, ninja and
  boots outfits — the boot's `back` piece included, since the authored `back_shoes`
  content is the NPC's own boot and must not be drawn on a player wearing something
  else.

Still open on this: the git repo copy of the package is far behind the working one
(its `server.py` is 170 KB against 243 KB here), so the avatar work is NOT in the
repo yet - the repo needs a full reconcile, not a file-by-file copy.

### LP3 could not log in — stuck on 「連接中」 — **FIXED**
Two separate faults, both found by reading LP3's own ActionScript:

1. `Application.onHTTPStatus` calls `PrinceSystem.loadReg()` as soon as the network
   check returns 200, and `loadReg` preloads **`reg.swf`** — a file that exists
   nowhere, in the mirror or on the publisher (404 at every path tried). The preload
   never finished, so the client sat on its connecting button. **Fix:** hand-built a
   minimal valid `reg.swf` (29 bytes, one blank white frame). Nothing on that path
   reads anything out of it; it only has to load.
2. Even once it loaded, the client waits for specific reply names —
   `checkVersionResult`, `checkActivationResult`, `activationResult`,
   `reactivationResult` — and the server was answering a generic `{"response":"ok"}`,
   which the client silently ignores. **Fix:** `lp3_activation_reply()` in server.py
   answers those four with the right names. `checkVersion`'s message is `"0"` so
   `Number(msg) > verNumber` is false and the `e000` popup never fires.

The activation branch is checked **before** the Prince1/2/3 login branch: they share
the same `Prince3_personal.serviceRequest` target, so the login handler was
swallowing the activation calls.

### LPO maze not open — **FIXED**
`profile.json` stores `maze_open: null`, and `maze_reply` did `bool(None)` → `False`,
so `canPlayMaze` answered `result: False` and the guard said
「每天只能進入迷宮一次!」. **Fix:** treat `None`/`""` as "never set" → default open.
Also moved the maze check ahead of the login branch, which was swallowing it so the
client read `result` as undefined.

### Leaderboard empty — **FIXED**
The server answered `getRank` (and LPO's `getMonthScoreRank` / `getMonthMazeRank`)
with empty lists. **Fix:** `rank_rows()` compiles the board from the local accounts
plus the player themself if they have no account record, and `rank_reply()` returns
it in each game's own key shape (LP1 `score_rank/gem_rank/card_rank`, LP2
`scoreRank/gemRank/itemRank`, LP3 `score_rank/star_rank/equip_rank`). Rows carry the
value under several key names because no schema is published.
The publisher's own board cannot be mirrored: its gateway is AMFPHP and rejects
anything that is not an authenticated `/Service/Method` call.

### Accounts website blank in the publisher's browser — **FIXED**
`LittlePrinceBrowserHome` is Electron 4.2.12 = **Chromium 69** (confirmed from the
binary's own `Chrome/69` string). `web.html` and `admin.html` used `??` nullish
coalescing, which is a hard SyntaxError there, so the whole inline script died and
the page rendered as an empty black panel. **Fix:** rewrote those three expressions
as explicit `undefined/null` tests; `/tmp/check_es2019.py` now parses every inline
script of every shipped page with acorn at `--ecma2019` (all pass).
Remaining cosmetic gap: `gap:` is used on flex containers in `web.html`, and flex
`gap` needs Chrome 84, so spacing will be tight in that browser. Grid `gap` is fine.

### LP2 levels unplayable / showing `undefined` — **FIXED**
Each LP2 level loads its questions from an XML in its own folder
(`game1/gamea1.xml` …) and the mirror had **no** XML files for LP2. 17 files fetched
(15 level XMLs plus `game18/data.swf`, `game19/data.swf`); one of them,
`game8/gameb2.xml`, was only found by sweeping every game folder rather than
trusting the literal scan.

### LP2 missing music — **FIXED (as far as the publisher has files)**
The per-level `vo/` voice folders were absent from the mirror entirely. Mirrored
2,900 files (146 MB): game11 916 (`vo/level 1-2/<q>/<n>.mp3`, computed exactly from
the level XML, zero 404s), game12 1,126 (`vo/level|slevel <band>/<q>/<n>.mp3`),
game5/6/8/15/17 160–200 each (`vo/level <band>/<n>.mp3`), game10/16 40 each
(`vo/<n>.mp3`). LP1 and LP3 need none — checked, their audio was already complete.

### LP2's voice sets were incomplete — **FIXED (second pass)**
The first pass used fixed ranges (questions 1-20, clips 1-12) and that silently cut
files off. A second pass walks each sequence outwards and stops only after a run of
misses, which found **1,100 more files**: game8 +523, game12 +358, game16 +76,
game15 +60, game5 +47, game10 +30, game6 +5, game11 +1. LP2's voice set is now
4,000 files.

### Saved progress was thrown away every session — **FIXED**
Both games save their state a field at a time and read it back out of the login
reply, and nothing was keeping it:
- **LP3** sends `gems`, `items`, `cards`, `cardSequence`, `gameCards`, `process` as
  comma-joined strings plus totals (`tGem`, `tItem`, `tCard`, `tCard2`); its login
  reply was returning `items`/`cardSequence`/`process` as hard-coded `""`.
- **LP2** sends `setGem` `[gemID,amount]`, `setItem` `[itemID,amount]` and
  `updateUserInfo` `[equipment,bossQue,defeatedBoss,firstHint,quality,musicvolume,score,language,extra]`.

`accounts.set_progress` / `get_progress` now hold those fields, `save_progress_batch`
stores whatever a save batch carries, and the login replies return them. Verified by
`/tmp/test_progress.py`: log in, save six LP3 fields through the real gateway, log in
again, read all six back.

Note for anyone extending this: a save batch is **one AMF0 array** of `{type, data}`
objects. `amf0.encode([a, b])` writes two separate values and only the first is read —
wrap it as `amf0.encode([[a, b]])`.

### LP3's orbs read `undefined` — **FIXED**
LP3 runs its saved fields through `Prince3.Utils.str2nArray(val, ",")`, and the login
reply was sending them as `""`. An empty string splits into `[""]` — a one-element
array — so every orb past the first read `undefined`. The reply now sends
full-length zero strings (`0,0,0,0,0,0,0,0`, GEM_COUNT entries) for `gems`, `items`,
`cards`, `gameCards`, `process` and `cardSequence`, with saved progress overwriting
them when there is any. Verified with `/tmp/test_lp3_orbs.py` against the real
gateway: all six fields come back with 8 entries.

This is also the likely cause of the broken **house** function: the same fields feed
LP3's item/progress state, so anything reading an item by index was reading
`undefined` too. Worth re-testing once this build is in.

### LP2's 龍虎榜 showed `undefined` in every row — **FIXED**
LP2's `RankUI.rankResult` reads `result.scoreRank` / `result.gemRank` /
`result.itemRank` and indexes its rows **positionally**:

    row[0] name   row[1] gender   row[4] 總成績   row[5] 總數
    row[6..15] the ten 元素 counts             row[16] 武器及道具

The reply keys were already right, but `row_from_profile` returned **objects**, and a
dict has no `[0]` — so every cell read `undefined`. `lp2_array_row` / `lp2_rank_rows`
now build 17-entry arrays. Verified: rows come back as
`['小王子玩家', 1, 0, 0, 0, 0, ...]`, 17 entries each.

### Lesson: never stub a name the real code must resolve itself
The banner's Play button was wired as `command=play_clicked`, but `play_clicked` is
defined ~270 lines further down the same function, so building the window raised
`NameError` and **Start.bat appeared to do nothing** — `pythonw.exe` has no console,
so the traceback vanished. The test that should have caught it passed because it
supplied a `play_clicked` stub itself, masking the very failure it existed to find.
Bind late (`command=lambda: play_clicked()`) and let the test build the real thing.

## Still open

1. **LP2 is not finished.** User: "some game have issues, then some game have no
   music, not every game works". The level XMLs and voice sets are in, but that was
   not enough for every level.
2. **Launcher: one button, not three.** `Start_Server_GUI.pyw` lists Little Prince /
   Starwish Legend / Starwish Adventure each with a Play button; the web page already
   contains all three, so collapse them into a single Play button.
3. **LPO should run in the publisher's Flash browser, not Ruffle** — "so that can get
   native flash instead of ruffle cuz some errors". The package already ships that
   browser and `play.html` already switches on the Electron user agent; this is about
   launching it that way.
4. **Flex `gap` in `web.html`** renders tight in Chromium 69 (see above).

## How each game is served
- LP1 / LP2 / LP3 = the publisher's *cloud* edition, served from `cloud/` through the
  local server and played in a browser (Ruffle or the publisher's Flash browser).
- LPO ("Prince Online", the MMO) = a separate 324-file client, base
  `http://www1.little-prince.com.hk/LP/Po/`. Services it calls include `login4`,
  `canPlayMaze`, `mazeRec`, `totalItems`, `getMonthScoreRank`, `getMonthMazeRank`,
  `getMyFriends`, `checkMail`, `haveNewEmail`, `checkUpdateVersion`.
- The publisher's gateway is AMFPHP at
  `http://www.little-prince.com.hk/littleprince/amfservice/gateway.php`.

## Verification scripts (in /tmp)
- `test_lpo_fixes.py` — maze / leaderboard / activation handshake, all three fixed
  paths, end to end over the real HTTP gateway.
- `check_es2019.py` — every shipped page parses as ES2019 (the Chromium 69 level).
- `check_manifest.py` — 3,191 cloud entries present at their recorded sizes.
- `login_suite.py`, `login_name_suite.py`, `report_suite.py` — regressions, all pass.

### LP2 龍虎榜 shows `undefined` in every row — **reported, not yet diagnosed**
User, 2026-09-13, with a screenshot: the 成績表／龍虎榜 panel renders the three 三甲
columns and the 排名/姓名/性別/總成績/總數/武器及道具 table, but every cell reads
`undefined` and 總分 is 0. The page footer confirms it is the local server feeding the
browser's own Flash player. `rank_reply`/`rank_rows`/`row_from_profile` build LP2 rows
from the local accounts, so the likely cause is the *row shape* not matching LP2's own
keys - check the client's row reader against what `row_from_profile` emits for prince2.

### LPO MP result banner showed both languages at once — **fixed, lib_v5**
The MP win/lose screen (`UI_multiplay.label_mp_result_title`) never called
`showLang(["heading"],1)`, so both `heading0` (EN) and `heading1` (ZH) arts stayed
visible and the two strings drew over each other — the "Co恭喜你ion你已成功過關evel!"
mess. Fixed by adding `showLang(["heading"],1)` (plus `showLang(["btnRetry"],1)` in
`label_mp_result_end`), the same call every `UI_base` label already makes.
`lib_v5.swf` md5 `db842cf434a39e366e2a5375883cbbc7`, built from `lib_v2_base.swf`
+ the three patched classes only (MiniGameFlow / MultiplayFlow / UI_multiplay).
FFDec note: `-importScript` validates every `.as` in the stage folder; the full
export contains files it rejects (HouseFlow.as "Property init has package internal
access", Tween.as "Default value must be compiletime constant"), so import from a
**minimal stage with only the changed classes**.

### LP2/LP3 leaderboard missing — "'str' object has no attribute 'get'" — **fixed**
Two functions were both named `rank_reply`: the LP2/LP3 board builder and the LPO
one added later. The later definition shadowed the earlier, so LP2/LP3's own
`cloud_login_reply` called the LPO function with its game string as `profile`
and died. The LPO one is now `lpo_rank_reply` (with `profile=None` defaulting to
the current player), its two dispatch callers updated; the LP2/LP3 `rank_reply`
and its caller are untouched. Verified: `rank_reply('getRankList','prince2')`
returns a board again, and the LPO month boards answer with one arg.
**Lesson: two defs with the same name in one module silently shadow — scan with
`Counter(re.findall(r'^def (\w+)\(', src))` after adding functions.**

### LPO 國民 title never changed — **fixed, lib_v6**
The title on the ID card (更改資料), the report and the friend search card comes from
the profile's `gameLv`, but all three screens hard-coded `gotoAndStop(1)` — frame 1
of the `lv0`/`lv1` clips, which is the 國民 art. The game's own `PString` wrapper and
`RemoteService` field map show gameLv was meant to drive that clip. Now they read
`Bridge.user.gameLv` (and the friend's `gameLv` on the search card). The seven valid
titles (the clip's frame labels): 國民 / 資深國民 / 名人 / 貴族 / 皇室人員 / 小王子 / 小公主.
The launcher site already has a Title field (Profile → Title); it now suggests the
seven via a datalist, and the server coerces anything unknown to 國民 at both emit
points (`apply_profile` login splice + `find_friends_reply`) because the client's
gotoAndStop throws #2109 on an unknown label and freezes the screen.
`lib_v6.swf` md5 `478b184eebbe377628bcb50d359156a0` (lib_v5 + the three title files).

### Leaderboard "takes forever to load" — **fixed (server.py Connection: close)**
Root cause was NOT the board code: the mirror answered every AMF request in ~2 ms, but it
replied with `Connection: keep-alive`. Ruffle's NetConnection only hands the AMF payload
to the game when the HTTP stream ENDS, and the launcher relays (macOS proxy, and the
Windows fake server reads the same way) forward bytes but only finish when the upstream
closes — so every reply sat ~15 s until an idle timeout fired, then the client re-sent
the request (netStatusHandler retry). The board showed it worst because it has a spinner.
Reproduced live on the rig (mac proxy path): login sat at 登入中 for 30 s+ with retries;
after `Connection: close` + `self.close_connection = True` on the gateway response the
same login completed in <1 s with no retry. `curl` timing to the mirror was always 2 ms.
Shipped in the pack.

### Minigame 積分榜 tabs dead + level unlocks — **fixed**
1. getMonthScoreRank/getTotalScoreRank carry `data:[gameID, gameLv]` and the client
   re-renders the same panel per tab; the mirror answered with the general score
   board, so every game/level press looked dead (rows never changed). New
   `score_rank_reply` serves the per-game-level best scores (level_scores.json).
2. The website's "Unlock all" only set world permission bits - the minigame LEVELS
   stayed greyed in other worlds. It now also ticks a new "Every level unlocked"
   row, saved as profile `unlockLevels` (added to DEFAULT_PROFILE; /web/api/me
   accepts it). With the flag, game_record_rows reports full marks everywhere.
3. game_record_rows used to SKIP scoreless levels; the client appends rows and
   looks up `arr[level-2]`, so skips shifted indexes and locked the wrong levels.
   Now every level gets a row. Also accepts both score-key spellings ("<gid>-0"
   from setScore2 vs "<gid>-1" from the boards).
Still open: MP result screen - the loss side of the result is still to be
pinned down (what exactly should show where on lose) - asked the user.

### Register page keeps old account details - fixed
web.html register() success path never cleared the form, so after creating an
account the next registration still showed the previous email/login/name.
Added resetRegisterForm() (called only on success; failures keep input so
typos can be fixed): blanks the text fields and restores the default selects
(sex Male, level Other, class Other, class no "-", birth NOW-18/01/01).

### MP result banner on a loss - fixed (lib_v7, md5 fd527a335833e768136a242bc61c51f6)
label_mp_result_title did `heading.gotoAndStop("mp")` but the heading sprite's
frames are only pass/fail/hidden, so AS3 ignored the label and the result kept
frame 1 = the pass art ("congulation") win or lose. Now it picks pass/fail from
the match: my slot's score vs the top score (ties on the top score count as
pass - same rule Game2 uses for its racers), with the same success/fail SFX as
the single-player result. Coins earned stay = match score (as single-player).
