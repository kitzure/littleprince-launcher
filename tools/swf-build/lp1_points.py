#!/usr/bin/env python3
"""LP1: max the 積分 so every card in 部首咭 can be bought (and printed).

The card panel charges 積分 per card (the screenshot shows 100-160 each, 共需積分 for the
set) and shows the player's 總分.  LP1's reply already carries `score` and the client
saves `cards`/`gameCards` back, both of which are profile fields - so a big score is the
whole unlock, and a purchase persists through the client's own save.
"""
import pathlib
import subprocess
import sys

S = pathlib.Path.home() / "Downloads/littleprince-launcher/lpo/server.py"
src = S.read_text()
applied = []

# ── the new preset ───────────────────────────────────────────────────────────
OLD = '''    {
        "id": "lp1_gems", "game": "LP1",'''
NEW = '''    {
        "id": "lp1_points", "game": "LP1",
        "label": "Max out the points (積分)",
        "detail": "score = %s.  The 部首咭 panel charges 積分 per card (100-160 each) and "
                  "shows this as 總分, so every card can be bought - and what the client "
                  "buys it saves back as cards/gameCards, which the server keeps"
                  % LP1_POINTS,
        "profile": {"score": LP1_POINTS},
    },
    {
        "id": "lp1_gems", "game": "LP1",'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("lp1_points preset")
else:
    print("!! lp1_gems anchor not found")
    sys.exit(1)

# ── the constant ─────────────────────────────────────────────────────────────
OLD = '''LP3_CARD_FLOOR = "999"'''
NEW = '''LP1_POINTS = "999999"        # 積分: the 部首咭 cards cost 100-160 each
LP3_CARD_FLOOR = "999"'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("LP1_POINTS constant")
else:
    print("!! LP3_CARD_FLOOR anchor not found")
    sys.exit(1)

# ── the leftover: lp1_scores wrote one game's rows only ──────────────────────
OLD = '''        "game_result": {"game": 0, "levels": len(LP1_LEVELS), "high": 999},'''
NEW = '''        "game_result": {"all_games": True, "high": 999},'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied.append("lp1_scores now fills every game (it wrote game 0's rows only)")
else:
    print("!! lp1_scores anchor not found (already fixed?)")

S.write_text(src)
print("applied:")
for a in applied:
    print("  -", a)
r = subprocess.run([sys.executable, "-m", "py_compile", str(S)], capture_output=True, text=True)
print("py_compile:", "OK" if r.returncode == 0 else r.stderr[-400:])

# ── verify through the dispatcher ────────────────────────────────────────────
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402
import accounts                                                         # noqa: E402

EMAIL = "wangzi1@littleprince.local"
body = srv.encode_strict_array([{"type": "login", "loginName": "wangzi1",
                                 "data": ["wangzi1", "x"]}])


def lp1_login():
    blobs = srv.amf0.decode(srv.dispatch_service(
        "login", "Prince1_personal.serviceRequest", body))
    return next(b for b in blobs if isinstance(b, dict) and "response" in b)


p = lp1_login()
print("\nbefore: score = %r" % p.get("score"))
acct, written = srv.apply_mods(EMAIL, "lp1_points")
print("preset wrote:", sorted(written))
p = lp1_login()
print("after : score = %r" % p.get("score"))
print("cards fields the client will fill on purchase:",
      {k: str(p.get(k))[:14] for k in ("cards", "gameCards")})
print("a purchase save round-trips:", srv.persist_player_update(
    srv.amf0.encode([{"type": "cards", "data": "3,1,0,2"}])))
prof = accounts.get(EMAIL) or {}
print("stored cards:", str((prof.get("profile") or prof).get("cards"))[:40])
print("\nRESULT: 積分 = %s, purchases persist" % p.get("score"))
