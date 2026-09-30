#!/usr/bin/env python3
"""LP3: a "defeated boss" mod, the equivalent of LP2's preset.

Pinned from LP3's own code:
  * `PrinceSystem.killBoss()` does `if(curUser.process[0] < 3) curUser.process[0]++`
    - so process[0] is the number of bosses defeated, capped at 3.
  * `BuyCard.as` gates on `!(curUser.process[0] != 3 && cardSetting[i].bosscard)`,
    so the four boss cards (cardSetting[0..3], bosscard:true) can only be bought once
    all three bosses are down.
  * `boss` itself (1 = miniboss, 2 = bigboss) is a runtime static, not a saved field,
    so `process[0]` is the only thing to write.
"""
import pathlib
import re
import subprocess
import sys

S = pathlib.Path.home() / "Downloads/littleprince-launcher/lpo/server.py"
src = S.read_text()

# count the boss cards from the client's own table, so the preset text cannot drift
setting = pathlib.Path("/tmp/lp3_src/scripts/__Packages/Prince3/Setting.as").read_text(errors="ignore")
cards = re.search(r"cardSetting\s*=\s*new Array\((.*?)\);", setting, re.S).group(1)
boss_cards = cards.count("bosscard:true")
print("LP3 card table: %d cards, %d of them boss cards"
      % (cards.count("{bosscard:"), boss_cards))

OLD = '''    {
        "id": "lp3_gems", "game": "LP3",'''
NEW = '''    {
        "id": "lp3_bosses", "game": "LP3",
        "label": "Every boss defeated",
        "detail": "process = 3, which is exactly what the client's own killBoss() counts "
                  "up to (it increments process[0] until it reaches 3).  The %d boss "
                  "cards in the card panel only open for purchase at 3, so pair this "
                  "with Max out the points." % boss_cards,
        "progress": {"process": LP3_BOSSES_DEFEATED},
    },
    {
        "id": "lp3_gems", "game": "LP3",'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    print("applied: lp3_bosses preset")
else:
    print("!! lp3_gems anchor not found")
    sys.exit(1)

OLD = '''LP3_CARD_FLOOR = "999"'''
NEW = '''LP3_BOSSES_DEFEATED = "3"    # what killBoss() stops counting at
LP3_CARD_FLOOR = "999"'''
if OLD in src:
    src = src.replace(OLD, NEW, 1)
    print("applied: LP3_BOSSES_DEFEATED constant")
else:
    print("!! LP3_CARD_FLOOR anchor not found")
    sys.exit(1)

S.write_text(src)
r = subprocess.run([sys.executable, "-m", "py_compile", str(S)], capture_output=True, text=True)
print("py_compile:", "OK" if r.returncode == 0 else r.stderr[-300:])

# ── verify through the dispatcher ────────────────────────────────────────────
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402

EMAIL = "wangzi1@littleprince.local"
body = srv.encode_strict_array([{"type": "login", "loginName": "wangzi1",
                                 "data": ["wangzi1", "x"]}])


def lp3_login():
    blobs = srv.amf0.decode(srv.dispatch_service(
        "login", "Prince3_personal.serviceRequest", body))
    return next(b for b in blobs if isinstance(b, dict) and "response" in b)


print("\nprocess before:", lp3_login().get("process"))
acct, written = srv.apply_mods(EMAIL, "lp3_bosses")
print("preset wrote  :", sorted(written))
p = lp3_login()
print("process after :", p.get("process"))

print("\n=== the client's own card gate, replayed ===")
print("   BuyCard: allowed when !( process[0] != 3 && cardSetting[i].bosscard )")
proc = [int(x) for x in str(p.get("process") or "0").split(",") if str(x).strip() != ""]
proc0 = proc[0] if proc else 0
boss_flags = [b == "true" for b in re.findall(r"bosscard:(true|false)", cards)]
allowed = [i for i, is_boss in enumerate(boss_flags) if not (proc0 != 3 and is_boss)]
print("   process[0] =", proc0)
print("   cards buyable: %d of %d (boss cards: %d)"
      % (len(allowed), len(boss_flags), sum(boss_flags)))
print("   every boss card buyable:", all(i in allowed
                                         for i, b in enumerate(boss_flags) if b))
