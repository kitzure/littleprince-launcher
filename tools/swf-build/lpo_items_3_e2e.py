#!/usr/bin/env python3
"""End to end: apply both LPO presets to the test account, then build a real login4
reply through the server's own splice and read the fields back."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402
import accounts                                                         # noqa: E402

EMAIL = "wangzi1@littleprince.local"
TARGET = "PrinceOnline.serviceRequest"


def show(tag):
    acct = accounts.get(EMAIL) or {}
    prof = acct.get("profile") or {}
    items = srv.lpo_profile_items(prof)
    print(f"  [{tag}] profile items: {len(items) if items is not None else 'none'}"
          f"  unlimitedUse={prof.get('unlimitedUse')!r}"
          f"  left={prof.get('left_total')!r} right={prof.get('right_total')!r}")
    return prof


print("=== before ===")
show("before")

print("\n=== applying the presets (as the Mods panel does) ===")
for pid in ("lpo_items", "lpo_unlimited"):
    acct, written = srv.apply_mods(EMAIL, pid)
    print(f"  {pid}: wrote {sorted(written)}")

print("\n=== after ===")
prof = show("after")

print("\n=== the login4 reply the client receives ===")
# find the captured login4 body the server replays
cap = None
for p in (srv.LPO_DIR / "captures").glob("*.json"):
    try:
        import json
        blob = json.loads(p.read_text())
    except Exception:                                                   # noqa: BLE001
        continue
    for k, v in (blob.items() if isinstance(blob, dict) else []):
        if "login4" in str(k).lower():
            cap = v
if cap is None:
    print("  (no login4 capture on disk to replay - skipping the reply check)")
else:
    body = srv.apply_profile(cap if isinstance(cap, bytes) else str(cap).encode(), prof)
    blobs = srv.amf0.decode(body)
    payload = next((b for b in (blobs if isinstance(blobs, list) else [blobs])
                    if isinstance(b, dict) and "items" in b), None)
    if payload is None:
        print("  reply decoded but no `items` field found")
    else:
        items = payload["items"]
        user = payload.get("user") or []
        print("  items rows      :", len(items))
        print("  first 3         :", items[:3])
        print("  names present   :", ("古木魔杖" in [i[1] for i in items]),
              ("精靈眼淚" in [i[1] for i in items]))
        print("  sportswear gone :", not any(i[1] in srv.LPO_SPORTSWEAR for i in items))
        print("  user[14/15]     :", user[14] if len(user) > 15 else "?", "/",
              user[15] if len(user) > 15 else "?")
