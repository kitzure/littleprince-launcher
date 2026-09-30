#!/usr/bin/env python3
"""LP3 levels the way its own code gates them, plus 積分 presets for LP2 and LP3.

GameBar.showLevel: level N (N>1) is available only when
    int(curUser.gameResult[game][N-2][2]) >= miniGameSetting[game][N-2].maxscore
so "all levels unlocked" = a gameResult board whose every row's high score is that
level's own maxscore.  `process` was never the gate (the farm panel showed level 1 only
however it was set).
"""
import pathlib
import re
import subprocess
import sys

S = pathlib.Path.home() / "Downloads/littleprince-launcher/lpo/server.py"
src = S.read_text()
applied = []

# ── the maxscore table ───────────────────────────────────────────────────────
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
maxscores = [[int(m) for m in re.findall(r"maxscore:(\d+)", e)] for e in elems]
assert [len(r) for r in maxscores] == [4, 3, 6, 5, 6, 5, 3, 6, 4, 3, 4, 5, 4, 4, 4, 3,
                                       5, 3, 3, 3, 6, 3, 3, 7], "table drifted"
print("LP3 maxscores: %d games, %d levels" % (len(maxscores), sum(len(r) for r in maxscores)))

# ── 1. constant + the reply board ────────────────────────────────────────────
OLD = '''LP3_CARD_FLOOR = "999"'''
NEW = '''LP3_LEVEL_MAXSCORES = %r


LP3_CARD_FLOOR = "999"''' % (maxscores,)
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("LP3_LEVEL_MAXSCORES table")
else:
    print("!! LP3_CARD_FLOOR anchor missing")
    sys.exit(1)

OLD = '''def lp2_blank_score_report() -> list:'''
NEW = '''def lp3_game_result(acct) -> list:
    """LP3's gameResult board, padded to its own 24-game / 102-level table.

    The client indexes it as [game][level] and reads row[2] (the high score) to decide
    whether the NEXT level is available, so every level needs its own row.
    """
    stored = (acct or {}).get("gameResult")
    board = []
    for gid, count in enumerate([len(r) for r in LP3_LEVEL_MAXSCORES]):
        have = stored[gid] if isinstance(stored, list) and gid < len(stored) else []
        row_in = have if isinstance(have, list) else []
        board.append([list(row_in[j]) if j < len(row_in) and isinstance(row_in[j], list)
                      else blank_row() for j in range(count)])
    return board


def lp2_blank_score_report() -> list:'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("lp3_game_result board")
else:
    print("!! lp2_blank_score_report anchor missing")
    sys.exit(1)

# ── 2. the writer: per-level scores ──────────────────────────────────────────
OLD = '''        if spec.get("all_games"):'''
NEW = '''        if spec.get("scores"):
            # One row per level with that level's own threshold as the high score - the
            # client unlocks level N only when level N-1 reached its maxscore.
            count = 0
            for gid, row in enumerate(spec["scores"]):
                for level, sc in enumerate(row):
                    accounts.set_game_result(email, gid, level,
                                             [0, "", int(sc), today, int(sc), today])
                    count += 1
            written["gameResult"] = "%d rows at each level's maxscore" % count
        elif spec.get("all_games"):'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("writer: per-level score rows")
else:
    print("!! writer all_games anchor missing")
    sys.exit(1)

# ── 3. lp3_levels: the rows, not process ─────────────────────────────────────
OLD = '''        "progress": {"process": ",".join(str(n) for n in LP3_LEVEL_COUNTS)},'''
NEW = '''        # The gate is the gameResult board (GameBar.showLevel compares each level's
        # high score against its maxscore), not `process`.
        "game_result": {"scores": LP3_LEVEL_MAXSCORES},'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("lp3_levels writes the gameResult board")
else:
    print("!! lp3_levels anchor missing")
    sys.exit(1)

# ── 4. the two points presets ────────────────────────────────────────────────
OLD = '''    {
        "id": "lp2_gems", "game": "LP2",'''
NEW = '''    {
        "id": "lp2_points", "game": "LP2",
        "label": "Max out the points (積分)",
        "detail": "score = %s (the points the shop and the card panels charge), written "
                  "to both stores so whichever one the reply reads has it"
                  % GAME_POINTS,
        "progress": {"score": GAME_POINTS},
        "profile": {"score": GAME_POINTS},
    },
    {
        "id": "lp2_gems", "game": "LP2",'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("lp2_points preset")
else:
    print("!! lp2_gems anchor missing")
    sys.exit(1)

OLD = '''    {
        "id": "lp3_gems", "game": "LP3",'''
NEW = '''    {
        "id": "lp3_points", "game": "LP3",
        "label": "Max out the points (積分)",
        "detail": "score = %s.  The card panels charge 積分 per card (the earlier "
                  "screenshot showed 所需積分 400) and show it as 分數, so every card can "
                  "be bought; LP3's reply reads it from the player record"
                  % GAME_POINTS,
        "progress": {"score": GAME_POINTS},
        "profile": {"score": GAME_POINTS},
    },
    {
        "id": "lp3_gems", "game": "LP3",'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("lp3_points preset")
else:
    print("!! lp3_gems anchor missing")
    sys.exit(1)

OLD = '''LP1_POINTS = "999999"'''
NEW = '''GAME_POINTS = "999999"        # 積分: the card panels charge 100-400 per card
LP1_POINTS = "999999"'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("GAME_POINTS constant")
else:
    print("!! LP1_POINTS anchor missing")
    sys.exit(1)

# ── 5. make sure the LP3 reply actually carries the board ────────────────────
if 'payload["gameResult"]' not in src[src.find('game.lower() == "prince3"'):
                                     src.find('game.lower() == "prince3"') + 3000]:
    OLD = '''            payload["score"] = (prog.get("score") or prog.get("Score")'''
    NEW = '''            payload["gameResult"] = lp3_game_result(acct)
            payload["score"] = (prog.get("score") or prog.get("Score")'''
    if OLD in src:
        src = src.replace(OLD, NEW, 1)
        applied.append("LP3 reply now carries gameResult")
    else:
        print("!! LP3 score anchor missing")
        sys.exit(1)
else:
    applied.append("LP3 reply already carried gameResult")

S.write_text(src)
print("applied:")
for a in applied:
    print("  -", a)
r = subprocess.run([sys.executable, "-m", "py_compile", str(S)], capture_output=True, text=True)
print("py_compile:", "OK" if r.returncode == 0 else r.stderr[-400:])
