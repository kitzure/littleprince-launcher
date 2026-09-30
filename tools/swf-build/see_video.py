#!/usr/bin/env python3
"""Frames from the user's video + the client's coins request/reply contract."""
import pathlib
import re
import subprocess

VID = pathlib.Path("/home/yoke/.hermes/cache/documents/doc_052d65c02598_LittlePrinceBrowserHome_IDdoH1W52J.mp4")
print("video:", VID.name, VID.stat().st_size, "bytes")
out = pathlib.Path("/tmp/mp_frames")
out.mkdir(exist_ok=True)
for f in out.glob("*.png"):
    f.unlink()
r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(VID),
                    "-vf", "fps=1/3", "-frames:v", "8", str(out / "f%02d.png")],
                   capture_output=True, text=True)
print("ffmpeg rc:", r.returncode, r.stderr[-200:] if r.returncode else "")
print("frames:", sorted(f.name for f in out.glob("*.png")))

print("\n=== how the client routes a 'coins' reply ===")
root = pathlib.Path("/tmp/lpo_cur/scripts")
for f in sorted(root.rglob("*.as")):
    text = f.read_text(errors="ignore")
    for i, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        if "coins" in low and any(k in low for k in ("case ", "response", "onresult",
                                                     "==", "remote", "send(")):
            print("   %s:%d %s" % (f.relative_to(root), i, line.strip()[:104]))
