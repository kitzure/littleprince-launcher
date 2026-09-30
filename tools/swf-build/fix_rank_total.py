#!/usr/bin/env python3
"""1) Test whether the publisher's library videos still exist.
   2) Fix the 水晶榜 total tab: the client asks with `getCrystalsRank2` but routes the
      reply on `getCrystalsRank`, so the total tab never redrew."""
import pathlib
import re
import subprocess
import sys

BASE = "http://www.little-prince.com.hk/littleprince/prince_online/update/flv/"

print("=== 1. publisher's library videos (official source) ===")
subprocess.run(["getent", "hosts", "www.little-prince.com.hk"], check=False)
for name in ("game9.flv", "game10.flv", "game2chi.flv", "game4.flv", "game6.flv"):
    for url in (BASE + name, BASE.replace("http://", "https://") + name):
        r = subprocess.run(["curl", "-sIL", "--max-time", "20", "-o", "/dev/null",
                            "-w", "%{http_code} %{size_download} %{content_type}",
                            "-A", "Mozilla/5.0", url],
                           capture_output=True, text=True)
        print(f"  {r.stdout:40}  {url}")

print("\n=== 2. server patch: rank reply names ===")
S = pathlib.Path.home() / "Downloads/littleprince-launcher/lpo/server.py"
src = S.read_text()

OLD = '''    # The castle's rank boards.  Must be answered before the captured set is
    # consulted: there is no useful capture for these (the publisher's own answer is
    # an empty list), and the generic {"response":"ok"} left the board undrawn.
    if "rank" in service_lower and any(
            k in service_lower for k in RANK_METRICS):
        return lpo_rank_reply(service_type, CURRENT_PLAYER.get("profile"))'''

NEW = '''    # The castle's rank boards.  Must be answered before the captured set is
    # consulted: there is no useful capture for these (the publisher's own answer is
    # an empty list), and the generic {"response":"ok"} left the board undrawn.
    if "rank" in service_lower and any(
            k in service_lower for k in RANK_METRICS):
        return lpo_rank_reply(rank_reply_name(service_type),
                              CURRENT_PLAYER.get("profile"))'''

HELPER = '''CLIENT_RANK_RESPONSES = {
    # Exactly the response names the client's RemoteService router matches on.
    "getcoinsrank", "getmonthcoinsrank", "getmonthscorerank", "gettotalscorerank",
    "getitemsrank", "getmonthitemsrank", "getmazerank", "getmonthmazerank",
    "getcrystalsrank", "getmonthcrystalsrank",
}


def rank_reply_name(service_type: str) -> str:
    """Echo the rank response name the CLIENT routes on, not the name it requested.

    The crystal board's total tab asks with a stray trailing 2 (`getCrystalsRank2`)
    while its own router matches `getCrystalsRank`, so the reply was dropped and the
    tab registered the press and never redrew.  Strip the suffix when the base name is
    one the client knows.
    """
    if service_type.endswith("2") and service_type[:-1].lower() in CLIENT_RANK_RESPONSES:
        return service_type[:-1]
    return service_type


'''

if NEW not in src:
    print("  ANCHOR NOT FOUND - aborting (no change made)")
    sys.exit(1)

if "def rank_reply_name" in src:
    print("  helper already present; only checking the call site")
else:
    # insert the helper just before the rank branch that uses it
    src = src.replace(OLD, HELPER + NEW, 1)
    print("  inserted helper + rewired the branch")

S.write_text(src)
print("  written:", S)

r = subprocess.run([sys.executable, "-m", "py_compile", str(S)], capture_output=True, text=True)
print("  py_compile:", "OK" if r.returncode == 0 else r.stderr[-400:])
print("  call site now:", "rank_reply_name(service_type)" in S)
