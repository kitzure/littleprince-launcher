#!/usr/bin/env python3
"""LPO: all items obtained, and unlimited weapon/item use.

Pinned from the client (lib.swf), not guessed:

* the loginSuccess reply carries `items`, an array of [kind, name, pos, total] rows:
  kind 1 = owned in the wardrobe, 2 = in the bag (with a count in `total`), read by
  RemoteService's own parser.
* the catalogue is the client's settings.cxd (types hat/cloth/weapons/items...), the
  same file searchItemType/searchItemData consult.
* left_total / right_total are the equipped weapons' remaining uses (MazePlayer
  decrements them and saves them back), and they are profile fields (slots 14/15).
* UserRecord.addItem refuses 運動服/運動褲/運動鞋, so those are skipped.
"""
import pathlib
import subprocess
import sys

S = pathlib.Path.home() / "Downloads/littleprince-launcher/lpo/server.py"
src = S.read_text()
applied = []

# ── 1. helpers, next to cloth_parts ──────────────────────────────────────────
ANCHOR = '''def known_players() -> list:'''
HELPERS = '''LPO_ITEM_CACHE = None
LPO_UNLIMITED_USES = "999999"          # the floor the mod keeps the weapons at
LPO_SPORTSWEAR = ("運動服", "運動褲", "運動鞋")   # addItem() refuses these


def lpo_item_catalogue() -> list:
    """Every item id in the client's own settings.cxd, in file order.

    That file is what the client's searchItemType/searchItemData read, so the list
    cannot drift from the game: hat/cloth/shoes/trousers/weapons/items and the
    appearance parts.  Cached - the file never changes while the server runs.
    """
    global LPO_ITEM_CACHE
    if LPO_ITEM_CACHE is not None:
        return LPO_ITEM_CACHE
    ids = []
    import re as _re
    import zlib as _zlib
    for candidate in (GAME_DIR / "settings.cxd", GAME_DIR / "game/settings.cxd"):
        try:
            if not candidate.is_file():
                continue
            xml = _zlib.decompress(candidate.read_bytes()).decode("utf-8", "replace")
            block = _re.search(r"<items>(.*?)</items>", xml, _re.S)
            if not block:
                continue
            for chunk in _re.findall(r'<type name="[^"]+">(.*?)</type>', block.group(1), _re.S):
                ids.extend(_re.findall(r'<item [^>]*id="([^"]+)"', chunk))
            if ids:
                log.info("  LPO item catalogue: %d items from %s" % (len(ids), candidate.name))
                break
        except Exception as exc:                                      # noqa: BLE001
            log.warning("  could not read the item catalogue from %s: %s" % (candidate, exc))
    LPO_ITEM_CACHE = ids
    return ids


LPO_ALL_ITEMS_CACHE = None


def lpo_all_item_rows() -> list:
    """The whole wardrobe as reply rows: [[1, name], ...]."""
    global LPO_ALL_ITEMS_CACHE
    if LPO_ALL_ITEMS_CACHE is None:
        LPO_ALL_ITEMS_CACHE = [[1, name] for name in lpo_item_catalogue()
                               if name not in LPO_SPORTSWEAR]
    return LPO_ALL_ITEMS_CACHE


def lpo_profile_items(prof: dict):
    """The account's own item rows, as the reply wants them, or None.

    Written by the mods preset (every item) or by the client's own addItem/removeItem
    saves; stored as JSON under the profile's `items`.  None means "leave the captured
    array alone", which is what an account that never touched its wardrobe gets.
    """
    import json as _json
    raw = (prof or {}).get("items")
    if raw in (None, ""):
        return None
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except Exception:                                            # noqa: BLE001
            return None
    if not isinstance(raw, (list, tuple)):
        return None
    rows = []
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        if isinstance(row[1], str) and row[1] in LPO_SPORTSWEAR:
            continue
        out = [int(row[0]), str(row[1])]
        if len(row) >= 4:
            out += [int(row[2]), int(row[3])]
        rows.append(out)
    return rows


def lpo_items_json(names) -> str:
    """[[1, name], ...] -> the JSON string the profile stores."""
    import json as _json
    return _json.dumps([[1, n] for n in names], ensure_ascii=False)


def known_players() -> list:'''

if ANCHOR in src:
    src = src.replace(ANCHOR, HELPERS, 1)
    applied.append("helpers (catalogue, items, unlimited floor)")
else:
    print("!! helpers anchor not found")
    sys.exit(1)

# ── 2. the profile keys the mods write ───────────────────────────────────────
OLD_KEY = '''    "unlockLevels": "0",'''
NEW_KEY = '''    "unlockLevels": "0",
    # the mods panel's LPO presets: "items" holds the owned rows as JSON ([[1, name], ...])
    # and unlimitedUse keeps the equipped weapons topped up (left_total/right_total).
    "items": "",
    "unlimitedUse": "0",'''
if OLD_KEY in src:
    src = src.replace(OLD_KEY, NEW_KEY, 1)
    applied.append("DEFAULT_PROFILE keys")
else:
    print("!! profile anchor not found")
    sys.exit(1)

# ── 3. the login reply: the account's own items + the unlimited floor ────────
OLD_CLOTH = '''        if isinstance(value, dict) and isinstance(value.get("cloth"), list):
            parts = cloth_parts(prof)
            row = value["cloth"]
            for i, part in enumerate(parts):
                if i < len(row) and row[i] != part:
                    row[i] = part
                    changed = True'''
NEW_CLOTH = OLD_CLOTH + '''
        # `items` is the wardrobe: rows of [kind, name, pos, total], kind 1 owned and
        # kind 2 in the bag.  The capture belongs to whoever it was recorded from, so an
        # account that has its own list gets that instead - otherwise everyone wears the
        # same captured wardrobe.  An account with no list keeps the capture, as before.
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            rows = lpo_profile_items(prof)
            if rows is not None and value.get("items") != rows:
                value["items"] = rows
                changed = True
        # The unlimited-use mod: the equipped weapons' remaining uses, kept at the floor
        # here and again on every save below.
        if isinstance(value, dict) and str((prof or {}).get("unlimitedUse") or "0") == "1":
            for idx, k in ((14, "left_total"), (15, "right_total")):
                row = value.get("user")
                if isinstance(row, list) and idx < len(row) and row[idx] != LPO_UNLIMITED_USES:
                    row[idx] = LPO_UNLIMITED_USES
                    changed = True'''
if OLD_CLOTH in src:
    src = src.replace(OLD_CLOTH, NEW_CLOTH, 1)
    applied.append("reply: items + unlimited floor")
else:
    print("!! cloth anchor not found")
    sys.exit(1)

# ── 4. saves: merge item changes, clamp the weapon uses ──────────────────────
OLD_PERSIST = '''    update, uid = player_update(raw_body)
    if not update:
        return False'''
NEW_PERSIST = '''    update, uid = player_update(raw_body)
    if not update:
        return False
    # LPO's wardrobe saves: addItem/removeItem carry one item name, and the weapon
    # totals arrive as left_total/right_total.  Merge them into the profile's own item
    # list, and (for an account with the unlimited-use mod) refuse to let the equipped
    # weapons' uses fall - the client decrements them locally and saves the result, so
    # a one-time preset would otherwise be spent after 999999 swings' worth of play.
    owner_email = CURRENT_PLAYER.get("email") or ""
    owner_prof = (accounts.get(owner_email) or {}).get("profile") or accounts.get(owner_email) or {}
    if owner_email:
        import json as _json
        rows = lpo_profile_items(owner_prof) or []
        names = [r[1] for r in rows]
        touched = False
        add = update.pop("additem", None)
        if isinstance(add, str) and add and add not in names and add not in LPO_SPORTSWEAR:
            rows.append([1, add])
            touched = True
        drop = update.pop("removeitem", None)
        if isinstance(drop, str) and drop in names:
            rows = [r for r in rows if r[1] != drop]
            touched = True
        if touched:
            update["items"] = _json.dumps(rows, ensure_ascii=False)
            log.info("  LPO wardrobe: %d items for %s" % (len(rows), owner_email))
        if str(owner_prof.get("unlimitedUse") or "0") == "1":
            for k in ("left_total", "right_total"):
                if k in update:
                    try:
                        if int(float(update[k])) < int(LPO_UNLIMITED_USES):
                            update[k] = LPO_UNLIMITED_USES
                    except (TypeError, ValueError):
                        update[k] = LPO_UNLIMITED_USES
    update, uid = update, uid'''
if OLD_PERSIST in src:
    src = src.replace(OLD_PERSIST, NEW_PERSIST, 1)
    applied.append("saves: merge items, clamp weapon uses")
else:
    print("!! persist anchor not found")
    sys.exit(1)

S.write_text(src)
print("applied:")
for a in applied:
    print("  -", a)
r = subprocess.run([sys.executable, "-m", "py_compile", str(S)], capture_output=True, text=True)
print("py_compile:", "OK" if r.returncode == 0 else r.stderr[-500:])
