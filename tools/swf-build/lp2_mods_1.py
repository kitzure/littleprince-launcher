#!/usr/bin/env python3
"""LP2 mods: round-trip its real saves, and give the panel the presets.

Everything here is pinned from LP2's own client code (index.swf), not guessed:

* `saveUserData` calls PrinceSystem.updateUserInfo(cb, equipment, bossQue, defeatedBoss,
  firstHint, quality, musicvolume, score, language, extra) - nine args, that order.
* `Report.setScore(gameID, level, ...)` sends data:[game, level, initS, initD, highS,
  highD, latestS, latestD] and reads rows back the same way; game/level are 1-based.
* the gem board is 10 slots (gemSpec: 火木金土水鑽黑彩月寶), indexed gemID-1.
* an unplayed level row is score 0 with an empty date: Report.setScoreBoard tests the
  score for falsiness and getHighestScore returns null while the date is null.
* the mini-games are 20 with 106 levels between them - counted from initGameSpec.
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path.home() / "Downloads/littleprince-launcher"
S = ROOT / "lpo/server.py"
src = S.read_text()
applied = []

# ── the spec the client carries, extracted from its own initGameSpec ──────────
spec_src = pathlib.Path('/tmp/lp2_idx/scripts/frame_3/DoAction_4.as').read_text(errors='ignore')
per_game = {}
for m in re.finditer(r'gameSpec\.game(\d+)\.dat\[(\d+)\]\s*=\s*\{(.*?)\};', spec_src):
    g, body = int(m.group(1)), m.group(3)
    fs = re.search(r'fullScore:(\d+)', body)
    per_game.setdefault(g, []).append(int(fs.group(1)) if fs else 0)
LP2_LEVELS = tuple(tuple(per_game[g]) for g in sorted(per_game))
print("LP2 spec: %d games, %d levels" % (len(LP2_LEVELS), sum(len(g) for g in LP2_LEVELS)))

# ── 1. the spec constant + the LP2 helpers ───────────────────────────────────
HELPERS = '''# LP2's mini-games: the level count per game and each level's fullScore, counted
# from the client's own initGameSpec (index.swf).  20 games, %d levels.
LP2_LEVELS = %s

# LP2's whole save record, in the order its own saveUserData passes them to
# PrinceSystem.updateUserInfo.  The client sends all nine in one call.
LP2_USER_INFO_FIELDS = ("equipment", "bossQue", "defeatedBoss", "firstHint",
                        "quality", "musicvolume", "score", "language", "extra")


def _lp2_saved(prog: dict, key: str):
    """One saved field.  Client saves land lower-cased, the panel writes the camelCase
    spelling, so both are tried."""
    prog = prog or {}
    for k in (key, key.lower()):
        if prog.get(k) not in (None, ""):
            return prog[k]
    return None


def _lp2_ints(raw):
    """A stored list, a JSON list or a comma-joined string -> a list of ints."""
    if raw in (None, ""):
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:                                            # noqa: BLE001
            return [int(float(x)) for x in raw.split(",") if str(x).strip()]
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for v in raw:
        try:
            out.append(int(float(v)))
        except (TypeError, ValueError):
            out.append(0)
    return out


def lp2_gem_board(prog: dict) -> list:
    """The 10 能量 gems, by gem id.  Always 10 slots: the client's gemSpec is exactly
    that long and Report indexes gemID-1, so a short save must not shorten the board."""
    vals = _lp2_ints(_lp2_saved(prog, "gemReport"))
    return (vals + [0] * 10)[:10]


def lp2_item_board(prog: dict) -> list:
    """The item rows the client keeps as [name, amount] (a name is 'trader-item')."""
    raw = _lp2_saved(prog, "itemReport")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:                                            # noqa: BLE001
            return []
    rows = []
    for row in (raw if isinstance(raw, (list, tuple)) else []):
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            try:
                rows.append([str(row[0]), int(float(row[1]))])
            except (TypeError, ValueError):
                continue
    return rows


def lp2_blank_score_report() -> list:
    """Every game and level, unplayed: score 0 with an empty date."""
    return [[[0, "", 0, "", 0, ""] for _ in levels] for levels in LP2_LEVELS]


def lp2_score_report(prog: dict) -> list:
    """The 20xN score board.  A stored board of the right shape wins; anything else is
    merged over a blank board so the reply always matches the client's own spec."""
    board = lp2_blank_score_report()
    raw = _lp2_saved(prog, "scoreReport")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:                                            # noqa: BLE001
            raw = None
    if not isinstance(raw, (list, tuple)):
        return board
    for g, levels in enumerate(LP2_LEVELS):
        if g >= len(raw) or not isinstance(raw[g], (list, tuple)):
            continue
        for lv in range(len(levels)):
            row = raw[g][lv] if lv < len(raw[g]) else None
            if isinstance(row, (list, tuple)) and len(row) >= 6:
                board[g][lv] = [row[0], str(row[1] or ""), row[2], str(row[3] or ""),
                                row[4], str(row[5] or "")]
    return board


def lp2_merge_board(who: str, key: str, gem_id, amount) -> bool:
    """One setGem/setItem call -> the stored board.  setGem's data is [gemID, amount]."""
    if not who:
        return False
    acct = accounts.get(who) or {}
    prog = accounts.get_progress(acct)
    if key == "gemreport":
        board = lp2_gem_board(prog)
        try:
            idx = int(float(gem_id)) - 1
            board[idx] = int(float(amount))
        except (TypeError, ValueError, IndexError):
            return False
    else:
        board = lp2_item_board(prog)
        name = str(gem_id)
        for row in board:
            if row[0] == name:
                row[1] = int(float(amount))
                break
        else:
            board.append([name, int(float(amount))])
    accounts.set_progress(who, key, json.dumps(board))
    return True


def lp2_merge_score_row(who: str, args) -> bool:
    """One LP2 setScore call -> the stored board.  data is [game, level, initS, initD,
    highS, highD, latestS, latestD] with game/level 1-based (Report.setScore)."""
    if not who or not isinstance(args, (list, tuple)) or len(args) < 8:
        return False
    try:
        g, lv = int(float(args[0])) - 1, int(float(args[1])) - 1
        if not (0 <= g < len(LP2_LEVELS)) or not (0 <= lv < len(LP2_LEVELS[g])):
            return False
        acct = accounts.get(who) or {}
        board = lp2_score_report(accounts.get_progress(acct))
        board[g][lv] = [int(float(args[2])), str(args[3] or ""),
                        int(float(args[4])), str(args[5] or ""),
                        int(float(args[6])), str(args[7] or "")]
        accounts.set_progress(who, "scorereport", json.dumps(board))
        log.info(f"  LP2 score saved: game {g + 1} level {lv + 1} -> "
                 f"{board[g][lv][2]} for {who}")
        return True
    except (TypeError, ValueError) as e:
        log.warning(f"  LP2 score row not saved: {e}")
        return False


''' % (sum(len(g) for g in LP2_LEVELS),
       "(\n    " + ",\n    ".join("(" + ", ".join(str(v) for v in g) + ")" for g in LP2_LEVELS)
       + ",\n)")

ANCHOR = "def save_progress_batch(reqs) -> bool:"
if ANCHOR in src:
    src = src.replace(ANCHOR, HELPERS + ANCHOR, 1)
    applied.append("helpers + LP2 spec")
else:
    print("!! save_progress_batch anchor not found")

# ── 2. store LP2's saves properly ────────────────────────────────────────────
OLD_BATCH = '''def save_progress_batch(reqs) -> bool:
    """Store everything a save batch carries; True if anything was kept.

    Both games send several {type, data} requests in one call, and the score rows
    and the progress fields (gems, items, cards, cardSequence, process, equipment,
    the totals ...) all arrive this way.  The games read them back from the login
    reply, so anything dropped here is progress lost at the next login.
    """
    who = CURRENT_PLAYER.get("email")
    kept = []
    for r in reqs:
        field = str(r.get("type") or "").lower()
        if field == "setscore":
            if store_score_row(r.get("data")):
                kept.append("setScore")
        elif field in PROGRESS_FIELDS and who:'''
NEW_BATCH = '''def save_progress_batch(reqs, game: str = "") -> bool:
    """Store everything a save batch carries; True if anything was kept.

    Both games send several {type, data} requests in one call, and the score rows
    and the progress fields (gems, items, cards, cardSequence, process, equipment,
    the totals ...) all arrive this way.  The games read them back from the login
    reply, so anything dropped here is progress lost at the next login.

    LP2 needs unpacking on the way in: its whole record rides in one updateUserInfo
    call (nine args, see LP2_USER_INFO_FIELDS) and its gems/items/scores arrive as
    per-id or per-level pairs.  Its setScore is 1-based, LP1's is 0-based, so the two
    games must not share one row store - hence the `game` argument.
    """
    who = CURRENT_PLAYER.get("email")
    lp2 = str(game or "").lower().startswith("prince2")
    kept = []
    for r in reqs:
        field = str(r.get("type") or "").lower()
        if field == "setscore":
            ok = (lp2_merge_score_row(who, r.get("data")) if lp2
                  else store_score_row(r.get("data")))
            if ok:
                kept.append("setScore")
        elif field == "updateuserinfo" and lp2:
            data = r.get("data")
            if isinstance(data, (list, tuple)) and who:
                for name, val in zip(LP2_USER_INFO_FIELDS, data):
                    if isinstance(val, (list, tuple, dict)):
                        continue
                    accounts.set_progress(who, name.lower(), val)
                    kept.append(name)
        elif field in ("setgem", "setitem") and lp2:
            data = r.get("data")
            if isinstance(data, (list, tuple)) and len(data) >= 2:
                if lp2_merge_board(who, field, data[0], data[1]):
                    kept.append(field)
        elif field in PROGRESS_FIELDS and who:'''
if OLD_BATCH in src:
    src = src.replace(OLD_BATCH, NEW_BATCH, 1)
    applied.append("save_progress_batch unpacks LP2")
else:
    print("!! batch anchor not found")

# the call site must pass the game
OLD_CALL = '''        save_progress_batch(reqs)'''
NEW_CALL = '''        save_progress_batch(reqs, game)'''
if OLD_CALL in src:
    src = src.replace(OLD_CALL, NEW_CALL, 1)
    applied.append("call site passes the game")
else:
    print("!! call site anchor not found")

# ── 3. the login reply carries real boards ───────────────────────────────────
OLD_PAY = '''                "classLevel": payload["classLv"] or "0", "scoreReport": None,
                "gemReport": None, "itemReport": None,'''
NEW_PAY = '''                "classLevel": payload["classLv"] or "0",
                # Built from the store, always sized to the client's own spec: the
                # reply's loadUserDataFromDB walks all three by .length and hands them
                # to Report(), so nulls here left every gem and every level blank.
                "scoreReport": lp2_score_report(prog),
                "gemReport": lp2_gem_board(prog),
                "itemReport": lp2_item_board(prog),'''
if OLD_PAY in src:
    src = src.replace(OLD_PAY, NEW_PAY, 1)
    applied.append("LP2 reply carries the boards")
else:
    print("!! payload anchor not found")

# ── 4. the whitelist and the panel's field list ──────────────────────────────
OLD_WL = '''    "setgem", "setitem", "updateuserinfo",              # LP2's savers'''
NEW_WL = '''    "setgem", "setitem", "updateuserinfo",              # LP2's savers
    "gemreport", "itemreport", "scorereport",           # LP2's boards'''
if OLD_WL in src:
    src = src.replace(OLD_WL, NEW_WL, 1)
    applied.append("whitelist")

OLD_FIELDS = '''        ("setItem", "progress", "per item id: itemID, amount"),'''
NEW_FIELDS = '''        ("setItem", "progress", "per item id: itemID, amount"),
        ("gemReport", "progress", "the 10 energy gems, by gem id (the login sends it)"),
        ("scoreReport", "progress", "per game and level: init/highest/latest score+date"),
        ("itemReport", "progress", "the item rows the client keeps: name, amount"),'''
if OLD_FIELDS in src:
    src = src.replace(OLD_FIELDS, NEW_FIELDS, 1)
    applied.append("panel field list")

S.write_text(src)
print("\napplied:")
for a in applied:
    print("  -", a)

r = subprocess.run([sys.executable, "-m", "py_compile", str(S)], capture_output=True, text=True)
print("py_compile:", "OK" if r.returncode == 0 else r.stderr[-600:])
