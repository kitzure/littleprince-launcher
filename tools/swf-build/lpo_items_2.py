#!/usr/bin/env python3
"""The two LPO presets, plus callable values in the writer so the item list is built
from the client's own catalogue at write time."""
import pathlib
import subprocess
import sys

S = pathlib.Path.home() / "Downloads/littleprince-launcher/lpo/server.py"
src = S.read_text()
applied = []

# ── callable preset values (the item list is generated, not a literal) ────────
OLD_TEXT = '''        text = value if isinstance(value, str) else str(value)'''
NEW_TEXT = '''        text = value() if callable(value) else value
        text = text if isinstance(text, str) else str(text)'''
if OLD_TEXT in src:
    src = src.replace(OLD_TEXT, NEW_TEXT, 1)
    applied.append("writer: callable progress values")
else:
    print("!! text anchor not found")
    sys.exit(1)

OLD_PROF = '''    if preset and preset.get("profile"):
        accounts.update(email, dict(preset["profile"]))
        written.update(preset["profile"])'''
NEW_PROF = '''    if preset and preset.get("profile"):
        profile_fields = {k: (v() if callable(v) else v)
                          for k, v in preset["profile"].items()}
        accounts.update(email, profile_fields)
        written.update(profile_fields)'''
if OLD_PROF in src:
    src = src.replace(OLD_PROF, NEW_PROF, 1)
    applied.append("writer: callable profile values")
else:
    print("!! profile anchor not found")
    sys.exit(1)

# ── the presets ──────────────────────────────────────────────────────────────
ANCHOR = '''    {
        "id": "lp2_bosses", "game": "LP2",'''
NEW = '''    {
        "id": "lpo_items", "game": "LPO",
        "label": "Every item obtained",
        "detail": "the whole wardrobe - every item in the client's own settings.cxd, "
                  "weapons and consumables included - written to the player record's "
                  "`items`, which the login reply hands to the client's own parser",
        "profile": {"items": lambda: lpo_items_json(lpo_item_catalogue())},
    },
    {
        "id": "lpo_unlimited", "game": "LPO",
        "label": "Unlimited weapon use",
        "detail": "unlimitedUse = 1: the equipped weapons' remaining uses "
                  "(left_total/right_total, which the maze decrements) are held at "
                  "%s at every login and on every save" % LPO_UNLIMITED_USES,
        "profile": {"unlimitedUse": "1",
                    "left_total": LPO_UNLIMITED_USES,
                    "right_total": LPO_UNLIMITED_USES},
    },
    {
        "id": "lp2_bosses", "game": "LP2",'''
if ANCHOR in src:
    src = src.replace(ANCHOR, NEW, 1)
    applied.append("two LPO presets")
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

cat = srv.lpo_item_catalogue()
rows = srv.lpo_all_item_rows()
print("\n=== the catalogue ===")
print("  items read from the client :", len(cat))
print("  wardrobe rows (sportswear skipped):", len(rows))
print("  first rows :", rows[:3])
print("  weapons in :", [n for n in cat if n in ("古木魔杖", "天使魔杖")])
print("  consumables:", [n for n in cat if n in ("精靈眼淚", "快速藥", "屠龍藥")])
stored = srv.lpo_items_json(cat)
print("  as JSON    : %d chars" % len(stored))
print("  round-trip :", len(srv.lpo_profile_items({"items": stored}) or []), "rows back")

print("\n=== the presets ===")
for p in srv.MODS_PRESETS:
    if p["game"] == "LPO":
        print("  %-14s %-28s writes %s" % (p["id"], p["label"],
                                           list((p.get("profile") or {}).keys())))
