#!/usr/bin/env python3
"""LP3's per-level maxscore table + whether the LP3 reply carries gameResult."""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402

print("=== LP3 reply: which keys the builder sets ===")
src = pathlib.Path(srv.__file__).read_text()
i = src.find('game.lower() == "prince3"', src.find("def cloud_login_reply"))
chunk = src[i:i + 2600]
for line in chunk.splitlines():
    s = line.strip()
    if s.startswith(("payload[", "lp3", "prog", "saved")) and "=" in s:
        print("   " + s[:100])

print("\n=== LP3's per-level maxscore table ===")
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
scores = [[int(m) for m in re.findall(r"maxscore:(\d+)", e)] for e in elems]
print("   games:", len(scores))
for g, row in enumerate(scores):
    print("     game %-2d %d levels  maxscores %s" % (g, len(row), row))
print("   flat table:", scores)
