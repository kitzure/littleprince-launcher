# Little Prince Online - local server

This folder is the local stand-in for the online game's official server. The
patcher's window starts it automatically on port 8080.

* **Browser player** - `web/` holds Ruffle's web build plus `play.html`, served
  at `/play` **and** at the game's own path `/LP/Po/` (so the page shares the
  gateway's origin). Play at http://www1.little-prince.com.hk/LP/Po/ with the
  hosts redirect up, or http://127.0.0.1:8080/play without it. `?selftest=1`
  adds a connectivity readout; if a browser blocks the local-network call,
  use the version it offers instead.
* **Game gateway** - `server.py` answers the client's AMF calls from the captures
  in `captures/bodies/` (login, mail, friends, scores, maze).
* **Account website** - `web.html` (+ `accounts.py`, `admin.html`):
  register players, edit name/school/stats, tick the nine worlds, delete accounts.
  Open http://127.0.0.1:8080/web (or press *Accounts website* in the window).
* **Guest profile** - `profile.json` is what a login gets when the email is not a
  registered account. Guest logins are off: an account has to be created on the
  accounts page (`/web`) first, and that page is also where the billboard and the
  LPO client folder are edited. `/admin` redirects there.
* **Where are the game files?** `server.py` looks for them in, in order:
  `$LPO_GAME_DIR`, `lpo/game/`, `../game/`, `~/littleprince-online`, then whatever
  `lpo/game_dir.txt` says. The website works without them; the game needs them.
* **Worlds** - the client checks `permission & (1 << worldIndex)`; each bit is one
  world (and its five minigames). The website toggles them per account.

Everything is local: nothing is sent to the real server, and unknown services are
answered here instead of being forwarded.
