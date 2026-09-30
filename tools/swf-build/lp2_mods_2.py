#!/usr/bin/env python3
"""Add the three LP2 presets, then verify every shape in-process."""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path.home() / "Downloads/littleprince-launcher"
S = ROOT / "lpo/server.py"
src = S.read_text()

ANCHOR = '''    {
        "id": "lp3_cards", "game": "LP3",'''
NEW = '''    {
        "id": "lp2_bosses", "game": "LP2",
        "label": "Every boss defeated",
        "detail": "defeatedBoss = the 4 slots at 1. The client gates the map's "
                  "progress on hasDefeatedBoss(stage), so every stage opens",
        "progress": {"defeatedBoss": "1,1,1,1"},
    },
    {
        "id": "lp2_gems", "game": "LP2",
        "label": "All gems",
        "detail": "gemReport = the 10 energy gems at 999 - the board the login hands "
                  "to the client's Report (it reads gemID-1)",
        "progress": {"gemReport": ",".join(["999"] * 10)},
    },
    {
        "id": "lp2_levels", "game": "LP2",
        "label": "Every level cleared",
        "detail": "scoreReport = full marks on all %d levels of the 20 mini-games, "
                  "every date 2020-01-01 so injected state stays recognisable"
                  % sum(len(g) for g in LP2_LEVELS),
        # Built from the same spec the reply is sized by, so the two cannot drift.
        "progress": {"scoreReport": json.dumps(
            [[[fs, "2020-01-01 00:00:00", fs, "2020-01-01 00:00:00",
               fs, "2020-01-01 00:00:00"] for fs in levels]
             for levels in LP2_LEVELS])},
    },
    {
        "id": "lp3_cards", "game": "LP3",'''

if ANCHOR in src:
    src = src.replace(ANCHOR, NEW, 1)
    S.write_text(src)
    print("MODS_PRESETS: three LP2 presets added")
else:
    print("!! preset anchor not found")
    sys.exit(1)

r = subprocess.run([sys.executable, "-m", "py_compile", str(S)], capture_output=True, text=True)
print("py_compile:", "OK" if r.returncode == 0 else r.stderr[-600:])

# ── in-process verification of the builders and the presets ───────────────────
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402

print("\n=== the LP2 spec ===")
print("  games:", len(srv.LP2_LEVELS), " levels:", sum(len(g) for g in srv.LP2_LEVELS))

print("\n=== gem board ===")
blank = srv.lp2_gem_board({})
print("  empty store        :", blank, "len", len(blank))
for key in ("gemReport", "gemreport"):
    got = srv.lp2_gem_board({key: ",".join(["999"] * 10)})
    print(f"  {key:<18}=999x10  :", got[:3], "... len", len(got))
short = srv.lp2_gem_board({"gemreport": "5,5"})
print("  short save '5,5'   :", short, "-> padded to", len(short))

print("\n=== score report ===")
board = srv.lp2_score_report({})
print("  blank: %d games, rows per game: %s" % (len(board), [len(g) for g in board][:6]))
print("  blank row looks like:", board[0][0])
print("  matches the spec   :", [[len(g) for g in board] == [len(g) for g in srv.LP2_LEVELS]])

preset = [p for p in srv.MODS_PRESETS if p["id"] == "lp2_levels"][0]
stored = json.loads(preset["progress"]["scoreReport"])
filled = srv.lp2_score_report({"scoreReport": preset["progress"]["scoreReport"]})
print("  preset rows        :", len(filled), "games")
print("  game1 level1 row   :", filled[0][0])
print("  every level filled :", all(row[2] > 0 for g in filled for row in g))
print("  full marks match   :", all(row[2] == fs for g, row, fs
                                   in ((g, r, f) for gi, gg in enumerate(filled)
                                       for g, (r, f) in ((gi, [None]), [None]) ) ) if False
      else all(filled[gi][li][2] == srv.LP2_LEVELS[gi][li]
               for gi in range(len(srv.LP2_LEVELS))
               for li in range(len(srv.LP2_LEVELS[gi]))))

print("\n=== every LP2 preset ===")
for p in srv.MODS_PRESETS:
    if p["game"] == "LP2":
        keys = list(p.get("progress", {}).keys())
        sizes = {k: len(v) for k, v in p.get("progress", {}).items()}
        print(f"  {p['id']:<12} {p['label']:<24} writes {keys} ({[v for v in sizes.values()]} chars)")
