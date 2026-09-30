#!/usr/bin/env python3
"""LP2: every item obtained, and unlimited item use.

Pinned from index.swf:

* `itemSpec` (initItemSpec) is the item catalogue: 6 traders, 36 items, ids "t-i".
* the player's own board is `itemReport`, rows [name, amount] - Report.setItemBoard
  splits the name on "-" into traderID/itemID and keeps `amount` as the count.
* Report.setItem sends {type:"setItem", data:[id, amount]} with the NEW amount, and
  Report.updateItem subtracts before sending - so holding a count up has to happen
  server-side on every save, not once in a preset.
"""
import pathlib
import re
import subprocess
import sys

S = pathlib.Path.home() / "Downloads/littleprince-launcher/lpo/server.py"
src = S.read_text()
applied = []

# ── the catalogue, counted from the client's own initItemSpec ────────────────
d8 = pathlib.Path('/tmp/lp2_idx/scripts/frame_3/DoAction_8.as').read_text(errors='ignore')
ids = sorted(set(re.findall(r'itemSpec\.trader\d+\.dat\[\d+\]\s*=\s*\{id:"([^"]+)"', d8)),
              key=lambda s: tuple(int(x) for x in s.split("-")))
print("catalogue: %d items %s ... %s" % (len(ids), ids[:4], ids[-2:]))

HELPER = '''# LP2's item catalogue, counted from the client's own initItemSpec (index.swf):
# 6 traders, %d items, ids "trader-item".  The player's board is `itemReport`, rows of
# [name, amount]; Report.setItemBoard splits the name on "-" and keeps amount as the
# count the trader screen shows.
LP2_ITEMS = %r
LP2_UNLIMITED_AMOUNT = "999"


def lp2_unlimited_on(prog: dict) -> bool:
    """Has the unlimited-items mod been applied to this account?"""
    prog = prog or {}
    return str(prog.get("lp2unlimited") or prog.get("lp2Unlimited") or "0") == "1"


def lp2_all_item_rows(amount: str = LP2_UNLIMITED_AMOUNT) -> list:
    """The whole catalogue as reply rows: [[id, amount], ...]."""
    return [[i, int(amount)] for i in LP2_ITEMS]


def lp2_item_board(prog: dict) -> list:'''

OLD_ITEM = '''def lp2_item_board(prog: dict) -> list:'''
if OLD_ITEM in src:
    src = src.replace(OLD_ITEM, HELPER % (len(ids), ids), 1)
    applied.append("catalogue + helpers")
else:
    print("!! lp2_item_board anchor not found")
    sys.exit(1)

# ── clamp the counts on every save ───────────────────────────────────────────
OLD_MERGE = '''    else:
        board = lp2_item_board(prog)
        name = str(gem_id)
        for row in board:
            if row[0] == name:
                row[1] = int(float(amount))
                break
        else:
            board.append([name, int(float(amount))])'''
NEW_MERGE = '''    else:
        board = lp2_item_board(prog)
        name = str(gem_id)
        try:
            new_amount = int(float(amount))
        except (TypeError, ValueError):
            return False
        # Unlimited-items accounts: the client subtracts locally and saves the result,
        # so hold the count at the floor here rather than seeding it once.
        if lp2_unlimited_on(prog) and new_amount < int(LP2_UNLIMITED_AMOUNT):
            new_amount = int(LP2_UNLIMITED_AMOUNT)
        for row in board:
            if row[0] == name:
                row[1] = new_amount
                break
        else:
            board.append([name, new_amount])'''
if OLD_MERGE in src:
    src = src.replace(OLD_MERGE, NEW_MERGE, 1)
    applied.append("setItem clamps for unlimited accounts")
else:
    print("!! merge anchor not found")
    sys.exit(1)

# ── the presets ──────────────────────────────────────────────────────────────
ANCHOR = '''    {
        "id": "lp2_gems", "game": "LP2",'''
NEW = '''    {
        "id": "lp2_items", "game": "LP2",
        "label": "Every item obtained",
        "detail": "itemReport = all %d items of the six traders, at %s each (the ids "
                  "come from the client's own initItemSpec)" % (len(ids),
                                                               LP2_UNLIMITED_AMOUNT),
        "progress": {"itemReport": "[%s]" % ", ".join(
            '["%s", %s]' % (i, LP2_UNLIMITED_AMOUNT) for i in ids)},
    },
    {
        "id": "lp2_unlimited", "game": "LP2",
        "label": "Unlimited item use",
        "detail": "lp2unlimited = 1: every item's count is held at %s on every save, "
                  "so using one never runs it out (the client subtracts locally)"
                  % LP2_UNLIMITED_AMOUNT,
        "progress": {"lp2unlimited": "1",
                     "itemReport": "[%s]" % ", ".join(
                         '["%s", %s]' % (i, LP2_UNLIMITED_AMOUNT) for i in ids)},
    },
    {
        "id": "lp2_gems", "game": "LP2",'''
if ANCHOR in src:
    src = src.replace(ANCHOR, NEW, 1)
    applied.append("two LP2 presets")
else:
    print("!! preset anchor not found")
    sys.exit(1)

S.write_text(src)
print("applied:")
for a in applied:
    print("  -", a)
r = subprocess.run([sys.executable, "-m", "py_compile", str(S)], capture_output=True, text=True)
print("py_compile:", "OK" if r.returncode == 0 else r.stderr[-500:])

# ── verify ───────────────────────────────────────────────────────────────────
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402
import accounts                                                         # noqa: E402

print("\n=== builders ===")
print("  catalogue        :", len(srv.LP2_ITEMS), "items")
print("  all rows (first3):", srv.lp2_all_item_rows()[:3])
print("  blank board      :", srv.lp2_item_board({}))
stored = srv.MODS_PRESETS and [p for p in srv.MODS_PRESETS if p["id"] == "lp2_items"][0]
rows = srv.lp2_item_board({"itemReport": stored["progress"]["itemReport"]})
print("  preset -> board  :", len(rows), "rows, e.g.", rows[0])
print("  unlimited off    :", srv.lp2_unlimited_on({}))
print("  unlimited on     :", srv.lp2_unlimited_on({"lp2unlimited": "1"}))

print("\n=== apply both presets to the test account, then check the clamp ===")
EMAIL = "wangzi1@littleprince.local"
for pid in ("lp2_items", "lp2_unlimited"):
    acct, written = srv.apply_mods(EMAIL, pid)
    print(f"  {pid}: wrote {sorted(written)}")

prog = accounts.get_progress(accounts.get(EMAIL) or {})
print("  stored rows      :", len(srv.lp2_item_board(prog)))
print("  unlimited flag   :", srv.lp2_unlimited_on(prog))
# the client would now send "1-0" down to 4 after four uses
ok = srv.lp2_merge_board(EMAIL, "setitem", "1-0", 4)
prog = accounts.get_progress(accounts.get(EMAIL) or {})
now = dict((r[0], r[1]) for r in srv.lp2_item_board(prog))
print("  saved 4 for 1-0  :", ok, "-> stored", now.get("1-0"), "(held at the floor)")
