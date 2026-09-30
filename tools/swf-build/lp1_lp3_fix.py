#!/usr/bin/env python3
"""LP1 + LP3: all levels, all cards, unlimited cards.

Pinned today:

* LP1's level select reads the account's gameResult board (one row per level, the rows
  the client itself writes with saveMark/setScore).  The existing writer wrote only ONE
  game's rows - `for level in range(levels)` with game=0 - which is why "Every level
  cleared" never unlocked anything past the first game.
* LP3 reads its per-game level counts from its own Setting.miniGameSetting, and carries
  the player's progress in `process` (a comma list), card counts in `gameCards`
  (BuyCard: gameCards[id-1] > 0 -> owned) and the currency in `score`.
* LP3 saves each of those by name (`gameCards`, `cards`, `process`, `items`), so
  "unlimited cards" is a clamp on the saved list, not a one-off write.
"""
import pathlib
import re
import subprocess
import sys

S = pathlib.Path.home() / "Downloads/littleprince-launcher/lpo/server.py"
src = S.read_text()
applied = []

# ── LP3's own level table ────────────────────────────────────────────────────
setting = pathlib.Path("/tmp/lp3_src/scripts/__Packages/Prince3/Setting.as")
text = setting.read_text(errors="ignore")
table = re.search(r"miniGameSetting\s*=\s*(?:new Array\(\))?\s*(.*?);", text, re.S)
raw = table.group(1) if table else ""
counts = [len(re.findall(r"[\[\{]", g)) for g in re.findall(r"\[[^\[\]]*\]", raw)]
print("LP3 miniGameSetting raw head:", raw[:160].replace("\r", " ").replace("\n", " "))
print("LP3 per-game level counts parsed:", counts[:12], "(%d games)" % len(counts))
if not counts:
    print("!! could not parse LP3's level table - stopping rather than guessing")
    sys.exit(1)

# ── 1. the writer's game_result section: all games, not just game 0 ──────────
OLD_GR = '''    if preset and preset.get("game_result"):
        for level in range(levels):
            accounts.set_game_result(email, game, level, [0, "", high, today, high, today])'''
NEW_GR = '''    if preset and preset.get("game_result"):
        # `all_games` writes every game's every level.  The first version used a single
        # `game` + `levels` pair, so only game 0 got rows and no other game's levels
        # ever unlocked.
        if preset["game_result"].get("all_games"):
            count = 0
            for gid, nlevels in enumerate(LP1_LEVELS):
                for level in range(nlevels):
                    accounts.set_game_result(email, gid, level,
                                             [0, "", high, today, high, today])
                    count += 1
            written["gameResult"] = "%d rows at %d" % (count, high)
        else:
            for level in range(levels):
                accounts.set_game_result(email, game, level,
                                         [0, "", high, today, high, today])'''
if OLD_GR in src:
    src = src.replace(OLD_GR, NEW_GR, 1)
    applied.append("writer: game_result fills every game")
else:
    print("!! game_result anchor not found")
    sys.exit(1)

# ── 2. the presets ───────────────────────────────────────────────────────────
OLD_P1 = '''        "progress": {"stars": ",".join(["3"] * len(LP1_LEVELS))},'''
NEW_P1 = '''        "progress": {"stars": ",".join(["3"] * len(LP1_LEVELS))},
        # The level select gates on the gameResult rows (score > 0 clears a level), so
        # stars alone left everything but the first game locked.
        "game_result": {"all_games": True, "high": 999},'''
if OLD_P1 in src:
    src = src.replace(OLD_P1, NEW_P1, 1)
    applied.append("lp1_levels now writes every game's level rows")
else:
    print("!! lp1_levels anchor not found")
    sys.exit(1)

OLD_P3 = '''    {
        "id": "lp3_gems", "game": "LP3",'''
NEW_P3 = '''    {
        "id": "lp3_levels", "game": "LP3",
        "label": "Every level unlocked",
        "detail": "process = each of the %d games' own level count (taken from the "
                  "client's Setting.miniGameSetting), so every level shows as available"
                  % len(counts),
        "progress": {"process": ",".join(str(n) for n in counts)},
    },
    {
        "id": "lp3_unlimited", "game": "LP3",
        "label": "Unlimited cards",
        "detail": "lp3unlimited = 1: the card counts are held at %s on every save, so "
                  "using a card never runs it out (BuyCard treats gameCards[id-1] > 0 "
                  "as owned)" % LP3_CARD_FLOOR,
        "progress": {"lp3unlimited": "1",
                     "gameCards": ",".join([LP3_CARD_FLOOR] * 50)},
    },
    {
        "id": "lp3_gems", "game": "LP3",'''
if OLD_P3 in src:
    src = src.replace(OLD_P3, NEW_P3, 1)
    applied.append("lp3_levels + lp3_unlimited presets")
else:
    print("!! lp3 preset anchor not found")
    sys.exit(1)

OLD_C3 = '''        "detail": "gameCards = 50 slots set to 1 (>0 unlocks the panel entry)",
        "progress": {"gameCards": ",".join(["1"] * 50)},'''
NEW_C3 = '''        "detail": "gameCards = 50 slots at %s (BuyCard shows a card as owned when "
                  "gameCards[id-1] > 0)" % LP3_CARD_FLOOR,
        "progress": {"gameCards": ",".join([LP3_CARD_FLOOR] * 50)},'''
if OLD_C3 in src:
    src = src.replace(OLD_C3, NEW_C3, 1)
    applied.append("lp3_cards count raised")
else:
    print("!! lp3_cards anchor not found")
    sys.exit(1)

# ── 3. the constant + the save clamp ─────────────────────────────────────────
OLD_LVL = '''LP2_ITEMS = '''
NEW_LVL = '''LP3_CARD_FLOOR = "999"            # what an unlimited-cards account keeps its counts at


LP2_ITEMS = '''
if OLD_LVL in src:
    src = src.replace(OLD_LVL, NEW_LVL, 1)
    applied.append("LP3_CARD_FLOOR constant")
else:
    print("!! LP2_ITEMS anchor not found")
    sys.exit(1)

OLD_CLAMP = '''    update, uid = player_update(raw_body)
    if not update:
        return False'''
NEW_CLAMP = '''    update, uid = player_update(raw_body)
    if not update:
        return False
    # LP3's unlimited cards: the client saves the whole gameCards list after spending
    # one, so hold every slot at the floor for an account with the mod applied.
    owner_mail = CURRENT_PLAYER.get("email") or ""
    if owner_mail and "gamecards" in {k.lower() for k in update}:
        owner_prog = accounts.get_progress(accounts.get(owner_mail) or {}) or {}
        if str(owner_prog.get("lp3unlimited") or "0") == "1":
            key = next(k for k in update if k.lower() == "gamecards")
            vals = []
            for part in str(update[key]).split(","):
                try:
                    n = int(float(part))
                except (TypeError, ValueError):
                    n = 0
                vals.append(str(max(n, int(LP3_CARD_FLOOR))))
            update[key] = ",".join(vals)'''
if OLD_CLAMP in src:
    src = src.replace(OLD_CLAMP, NEW_CLAMP, 1)
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
