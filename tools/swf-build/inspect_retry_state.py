import pathlib
import re

src = pathlib.Path("/tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as").read_text()

print("=== the retry registration in label_mp_result_end ===")
i = src.find("label_mp_result_end")
chunk = src[i:i + 2200]
for line in chunk.splitlines():
    if any(k in line for k in ("retryBtn", "btnRetry", "addMCButton", "onRelease",
                               "addEventListener", "visible", "Debug.addLog")):
        print("   " + line.strip()[:110])

print("\n=== the tail of label_mp_result_title (where I inserted the call) ===")
m = re.search(r"function label_mp_result_title\(\) : void", src)
s = src.index("{", m.end())
depth, j = 0, s
while j < len(src):
    if src[j] == "{":
        depth += 1
    elif src[j] == "}":
        depth -= 1
        if depth == 0:
            break
    j += 1
print("\n".join("   " + l for l in src[s:j].splitlines()[-16:]))

print("\n=== my helper ===")
k = src.find("function setupMpRetryButton")
print(src[k - 40:k + 900] if k > 0 else "   (not present)")
