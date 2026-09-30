#!/usr/bin/env python3
"""LP1 + LP3: all levels, all cards, unlimited cards - with the real anchors."""
import pathlib
import re
import subprocess
import sys

S = pathlib.Path.home() / "Downloads/littleprince-launcher/lpo/server.py"
src = S.read_text()
applied = []

# ── LP3's own level table (24 games, 102 levels) ─────────────────────────────
text = pathlib.Path("/tmp/lp3_src/scripts/__Packages/Prince3/Setting.as").read_text(errors="ignore")
start = re.search(r"miniGameSetting\s*=\s*", text).end()
depth, end = 0, start
for j in range(start, len(text)):
    if text[j] in "([{":
        depth += 1
    elif text[j] in ")]}":
        depth -= 1
        if depth == 0:
            end = j + 1
            break
body = text[start:end]
elems, depth, cur = [], 0, None
for k, ch in enumerate(body):
    if body.startswith("new Array(", k) and depth == 1:
        cur = k
    if ch in "([{":
        depth += 1
    elif ch in ")]}":
        depth -= 1
        if depth == 1 and cur is not None:
            elems.append(body[cur:k + 1])
            cur = None
counts = [len(re.findall(r"\{descript", e)) for e in elems]
print("LP3 games: %d  levels/game: %s  total: %d" % (len(counts), counts, sum(counts)))
assert counts[:7] == [4, 3, 6, 5, 6, 5, 3], "the farm games' counts changed - re-check"

# ── 1. the writer: fill every game's levels, not just game 0 ─────────────────
OLD = '''        levels = int(spec.get("levels") or 0)
        for level in range(levels):
            accounts.set_game_result(email, game, level, [0, "", high, today, high, today])
        written["gameResult"] = "%d rows at %d" % (levels, high)'''
NEW = '''        levels = int(spec.get("levels") or 0)
        if spec.get("all_games"):
            # Every game's every level.  The first version wrote one game's rows, so
            # "Every level cleared" unlocked nothing past the first game.
            table = spec.get("table") or LP1_LEVELS
            count = 0
            for gid, nlevels in enumerate(table):
                for level in range(int(nlevels)):
                    accounts.set_game_result(email, gid, level,
                                             [0, "", high, today, high, today])
                    count += 1
            written["gameResult"] = "%d rows at %d (all %d games)" % (count, high,
                                                                      len(table))
        else:
            for level in range(levels):
                accounts.set_game_result(email, game, level,
                                         [0, "", high, today, high, today])
            written["gameResult"] = "%d rows at %d" % (levels, high)'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("writer: all_games game_result")
else:
    print("!! game_result anchor not found")
    sys.exit(1)

# ── 2. lp1_levels: the rows, not just the stars ──────────────────────────────
OLD = '''        "progress": {"stars": ",".join(["3"] * len(LP1_LEVELS))},'''
NEW = '''        "progress": {"stars": ",".join(["3"] * len(LP1_LEVELS))},
        # The level select gates on the gameResult rows - a row with a score clears its
        # level - so stars alone left every game but the first locked.
        "game_result": {"all_games": True, "high": 999},'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("lp1_levels writes every game's level rows")
else:
    print("!! lp1_levels anchor not found")
    sys.exit(1)

# ── 3. the constant ──────────────────────────────────────────────────────────
OLD = '''LP2_ITEMS = '''
if OLD in src:
    src = src.replace(OLD, '''LP3_CARD_FLOOR = "999"      # what an unlimited-cards account keeps its counts at
LP3_LEVEL_COUNTS = %r


LP2_ITEMS = ''' % (counts,), 1)
    applied.append("LP3_CARD_FLOOR + LP3_LEVEL_COUNTS")
else:
    print("!! LP2_ITEMS anchor not found")
    sys.exit(1)

# ── 4. the two new presets, and the card count ───────────────────────────────
OLD = '''        "detail": "gameCards = 50 slots set to 1 (>0 unlocks the panel entry)",
        "progress": {"gameCards": ",".join(["1"] * 50)},'''
NEW = '''        "detail": "gameCards = 50 slots at %s (BuyCard shows a card as owned when "
                  "gameCards[id-1] > 0)" % LP3_CARD_FLOOR,
        "progress": {"gameCards": ",".join([LP3_CARD_FLOOR] * 50)},'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("lp3_cards count raised to the floor")
else:
    print("!! lp3_cards anchor not found")
    sys.exit(1)

OLD = '''    {
        "id": "lp3_gems", "game": "LP3",'''
NEW = '''    {
        "id": "lp3_levels", "game": "LP3",
        "label": "Every level unlocked",
        "detail": "process = each of the %d games' own level count (read from the "
                  "client's Setting.miniGameSetting), so every level is available"
                  % len(LP3_LEVEL_COUNTS),
        "progress": {"process": ",".join(str(n) for n in LP3_LEVEL_COUNTS)},
    },
    {
        "id": "lp3_unlimited", "game": "LP3",
        "label": "Unlimited cards",
        "detail": "lp3unlimited = 1: every card count is held at %s on every save, so "
                  "using a card never runs it out" % LP3_CARD_FLOOR,
        "progress": {"lp3unlimited": "1",
                     "gameCards": ",".join([LP3_CARD_FLOOR] * 50)},
    },
    {
        "id": "lp3_gems", "game": "LP3",'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("lp3_levels + lp3_unlimited presets")
else:
    print("!! lp3 preset anchor not found")
    sys.exit(1)

# ── 5. the save clamp (before the LPO wardrobe block) ────────────────────────
OLD = '''    # LPO's wardrobe saves: addItem/removeItem carry one item name, and the weapon'''
NEW = '''    # LP3's unlimited cards: the client saves the whole gameCards list after spending
    # one, so hold every slot at the floor for an account with the mod applied.
    _mail = CURRENT_PLAYER.get("email") or ""
    if _mail:
        _prog = accounts.get_progress(accounts.get(_mail) or {}) or {}
        if str(_prog.get("lp3unlimited") or "0") == "1":
            for _k in [k for k in update if k.lower() == "gamecards"]:
                _vals = []
                for _p in str(update[_k]).split(","):
                    try:
                        _n = int(float(_p))
                    except (TypeError, ValueError):
                        _n = 0
                    _vals.append(str(max(_n, int(LP3_CARD_FLOOR))))
                update[_k] = ",".join(_vals)
    # LPO's wardrobe saves: addItem/removeItem carry one item name, and the weapon'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("LP3 gameCards clamp on save")
else:
    print("!! clamp anchor not found")
    sys.exit(1)

S.write_text(src)
print("\napplied:")
for a in applied:
    print("  -", a)
r = subprocess.run([sys.executable, "-m", "py_compile", str(S)], capture_output=True, text=True)
print("py_compile:", "OK" if r.returncode == 0 else r.stderr[-400:])
