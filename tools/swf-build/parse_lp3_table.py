#!/usr/bin/env python3
"""Print the writer's real game_result block, and parse LP3's level table properly."""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher"))
sys.path.insert(0, str(pathlib.Path.home() / "Downloads/littleprince-launcher/lpo"))
import server as srv                                                    # noqa: E402

src = pathlib.Path(srv.__file__).read_text()
i = src.find('preset.get("game_result")')
print("=== the real block ===")
print(src[i - 200:i + 700])

print("\n=== LP3 level table, parsed properly ===")
text = pathlib.Path("/tmp/lp3_src/scripts/__Packages/Prince3/Setting.as").read_text(errors="ignore")
m = re.search(r"miniGameSetting\s*=\s*", text)
start = m.end()
# walk forward to the matching end of the statement
depth = 0
end = start
for j in range(start, len(text)):
    c = text[j]
    if c in "([{":
        depth += 1
    elif c in ")]}":
        depth -= 1
        if depth == 0:
            end = j + 1
            break
body = text[start:end]
print("   statement length:", len(body))
print("   head:", body[:80].replace("\r", " ").replace("\n", " "))

# top-level elements: split on `new Array(` at depth 1
elems = []
depth = 0
cur = None
k = 0
while k < len(body):
    ch = body[k]
    if body.startswith("new Array(", k) and depth == 1:
        # start of a top-level element
        cur = k
    if ch in "([{":
        depth += 1
    elif ch in ")]}":
        depth -= 1
        if depth == 1 and cur is not None:
            elems.append(body[cur:k + 1])
            cur = None
    k += 1
print("   top-level games found:", len(elems))
counts = [len(re.findall(r"\{descript", e)) for e in elems]
print("   levels per game:", counts)
print("   total levels:", sum(counts))
