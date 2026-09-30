#!/usr/bin/env python3
"""Billboard asset generator, attempt 2 - let ffdec do the SWF authoring.

Hand-written SWF bytes failed validation (malformed shape/tag stream), so instead: find a small
SWF in the game folder that already holds a bitmap, swap that bitmap for the uploaded image
with ffdec's own writer, and re-read the result to prove it is valid.

Step 1 (this script): find a usable template and prove the replace round-trip works.
"""
import pathlib
import shutil
import subprocess

JAR = "/home/yoke/lpo_build/ffdec/ffdec-cli.jar"
GAME = pathlib.Path("/home/yoke/littleprince-online")
SRC_IMG = pathlib.Path("/tmp/notice_test.jpg")


def ffdec(*args):
    return subprocess.run(["java", "-jar", JAR, "-onerror", "ignore"] + list(args),
                          capture_output=True, text=True)


# candidate templates: small SWFs, shallow
cands = sorted(((p.stat().st_size, p) for p in GAME.glob("*.swf")
                if 8000 < p.stat().st_size < 900_000), key=lambda t: t[0])[:8]
print("=== candidate templates (smallest first) ===")
templates = []
for size, p in cands:
    shutil.rmtree("/tmp/tpl_img", ignore_errors=True)
    r = ffdec("-export", "image", "/tmp/tpl_img", str(p))
    imgs = [q for q in pathlib.Path("/tmp/tpl_img").rglob("*") if q.is_file()]
    print("   %-28s %8d  images=%d" % (p.name, size, len(imgs)))
    if imgs:
        templates.append((p, imgs[0]))

if not templates:
    print("\n!! no template with an extractable image found")
    raise SystemExit(1)

tpl, img = templates[0]
img_id = img.stem.split("_")[0]
print("\n=== chosen template: %s (image %s) ===" % (tpl.name, img.name))

out = pathlib.Path("/tmp/notice_from_tpl.swf")
for args in (["-replace", str(tpl), str(out), "image", img_id, str(SRC_IMG)],
             ["-replace", str(tpl), str(out), "image", str(img_id), str(SRC_IMG)]):
    r = ffdec(*args)
    print("   %s -> rc=%d %s" % (" ".join(args[3:]), r.returncode,
                                 (r.stdout + r.stderr).strip().splitlines()[:1]))
    if out.exists():
        break

if not out.exists():
    print("!! replace produced no file")
    raise SystemExit(1)
print("   wrote %s (%d bytes)" % (out, out.stat().st_size))

# validate: re-read the produced SWF
shutil.rmtree("/tmp/tpl_check", ignore_errors=True)
r = ffdec("-export", "image", "/tmp/tpl_check", str(out))
imgs = [q for q in pathlib.Path("/tmp/tpl_check").rglob("*") if q.is_file()]
errs = [l for l in (r.stdout + r.stderr).splitlines() if "SEVERE" in l or "xception" in l]
print("   re-read: images=%d  errors=%s" % (len(imgs), errs[:2] if errs else "none"))
print("   RESULT:", "VALID" if imgs and not errs else "NEEDS WORK")
