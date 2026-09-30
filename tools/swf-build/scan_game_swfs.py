import pathlib
import re
import zlib

ROOT = pathlib.Path("/home/yoke/littleprince-online")
needles = [b"getData", b"URLLoader", b"URLRequest", b"notice", b"Notice", b"news.addChild"]
hits = {}
for p in sorted(ROOT.rglob("*.swf")):
    try:
        raw = p.read_bytes()
    except Exception:
        continue
    body = raw
    if raw[:3] == b"CWS":
        try:
            body = raw[:8] + zlib.decompress(raw[8:])
        except Exception:
            body = raw
    found = [n.decode() for n in needles if n in body]
    if found:
        hits[p.relative_to(ROOT)] = found

print("files mentioning loader/notice symbols:", len(hits))
for k, v in list(hits.items())[:14]:
    print("   %-34s %s" % (k, ",".join(v)))

# which one carries the Res class itself
print("\n=== Res / resource class ===")
for p in sorted(ROOT.rglob("*.swf")):
    try:
        raw = p.read_bytes()
    except Exception:
        continue
    body = raw[:8] + zlib.decompress(raw[8:]) if raw[:3] == b"CWS" else raw
    if b"$Res" in body or b"Res.as" in body or b"class_Res" in body:
        print("   ", p.relative_to(ROOT))
