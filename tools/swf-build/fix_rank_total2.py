#!/usr/bin/env python3
"""Fix the 水晶榜 total tab server-side.

The crystal board's total tab asks with a stray trailing 2 (`getCrystalsRank2`), but the
client's RemoteService router matches the reply field `response` against `getCrystalsRank`.
The server echoed the requested name, so the reply was dropped: the press registered and
the panel never redrew. Echo the canonical name instead.
"""
import pathlib
import subprocess
import sys

S = pathlib.Path.home() / "Downloads/littleprince-launcher/lpo/server.py"
src = S.read_text()
print("server.py:", S, f"({len(src):,} chars)")

ANCHOR = '''    if "rank" in service_lower and any(
            k in service_lower for k in RANK_METRICS):
        return lpo_rank_reply(service_type, CURRENT_PLAYER.get("profile"))'''

REPLACEMENT = '''    if "rank" in service_lower and any(
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
    """Echo the rank response name the CLIENT routes on, not the one it requested.

    The crystal board's total tab requests `getCrystalsRank2` while its own router
    matches `getCrystalsRank`, so the reply was dropped and the tab looked dead.
    """
    if service_type.endswith("2") and service_type[:-1].lower() in CLIENT_RANK_RESPONSES:
        return service_type[:-1]
    return service_type


'''

if ANCHOR not in src:
    print("ANCHOR NOT FOUND - no change")
    sys.exit(1)

if "def rank_reply_name" in src:
    print("helper already present")
else:
    src = src.replace(ANCHOR, HELPER + REPLACEMENT, 1)
    S.write_text(src)

src2 = S.read_text()
print("call site rewired :", "rank_reply_name(service_type)," in src2)
print("helper present    :", "def rank_reply_name" in src2)
r = subprocess.run([sys.executable, "-m", "py_compile", str(S)], capture_output=True, text=True)
print("py_compile        :", "OK" if r.returncode == 0 else r.stderr[-500:])

# prove the mapping logic on the names that matter
ns = {}
exec(HELPER + "\nfor n in ('getCrystalsRank2','getMonthCrystalsRank','getMazeRank','getTotalScoreRank'):\n"
     "    print('   ', n, '->', rank_reply_name(n))", ns)
