#!/usr/bin/env python3
"""1) Strip the diagnostic overlay.  2) Look up why the friend search finds nothing, and
whether the Ready button's clip even has a hover state.

The overlay was only ever the initialise+enable block inside mpDiag. Removing it leaves the
addLog calls inert (they just trace()), so the screen goes back to normal while the logging
stays available if we ever need it again.
"""
import hashlib
import pathlib
import re
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()
JAR = HOME / "lpo_build/ffdec/ffdec-cli.jar"
L = HOME / "Downloads/littleprince-launcher"
TOOLS = HOME / "Downloads/littleprince-patcher-handoff/tools"
SRC = pathlib.Path("/tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as")
md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

shutil.rmtree("/tmp/lpo_re", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_re", str(L / "lpo/patches/lib/lib.swf")], capture_output=True, text=True)
shutil.copy2(pathlib.Path("/tmp/lpo_re/scripts/PrinceOnline/UI_multiplay.as"), SRC)
src = SRC.read_text()

# strip the overlay: anything that creates or shows the on-screen field
pats = [r"[ \t]*if\(Debug\.tf_debug == null\)\s*\n\s*\{[^}]*\}[ \t]*\n",
        r"[ \t]*var holder:flash\.display\.Sprite = new flash\.display\.Sprite\(\);[ \t]*\n",
        r"[ \t]*holder\.mouseEnabled = false;[ \t]*\n",
        r"[ \t]*holder\.mouseChildren = false;[ \t]*\n",
        r"[ \t]*this\.addChild\(holder\);[ \t]*\n",
        r"[ \t]*Debug\.init\(holder,[^;]*\);[ \t]*\n",
        r"[ \t]*Debug\.tf_debug\.mouseEnabled = false;[ \t]*\n",
        r"[ \t]*Debug\.enable\(\);[ \t]*\n"]
removed = 0
for p in pats:
    src, n = re.subn(p, "", src)
    removed += n
print("overlay lines removed:", removed)
if "Debug.init(" in src or "Debug.enable()" in src:
    print("!! overlay remnants:", len(re.findall(r"Debug\.(init|enable)\(", src)))
    sys.exit(1)
SRC.write_text(src)

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print("\n".join(l for l in r.stdout.splitlines() if l.startswith(("new ", "base "))))
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer complained"); print(r.stdout[-300:]); sys.exit(1)
out = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as").read_text()
checks = [("overlay gone", "Debug.init(" not in out and "Debug.enable()" not in out),
          ("ready fix kept", 'btnMultiplayReady,"SFX_drag",null,"SFX_drop"' in out),
          ("mpFind once", out.count("function mpFind(") == 1),
          ("retry listener kept", "MouseEvent.CLICK" in out)]
for label, ok in checks:
    print("   %-22s %s" % (label, ok))
if not all(ok for _, ok in checks):
    print("!! NOT shipping"); sys.exit(1)

for p in sorted(L.rglob("lib.swf")):
    shutil.copy2(p, HOME / "lpo_build/swf_backups" /
                 (p.parent.relative_to(L).as_posix().replace("/", "_") + ".bak"))
    shutil.copy2("/tmp/lib_one.swf", p)
print("deployed ->", md5(L / "lpo/patches/lib/lib.swf"))
subprocess.run(["python3", str(TOOLS / "build_local.py")], capture_output=True, text=True, cwd=TOOLS)
rr = subprocess.run(["python3", str(TOOLS / "ship_launcher_pack.py")],
                    capture_output=True, text=True, cwd=TOOLS)
for l in rr.stdout.splitlines():
    if "drive after" in l or "VERIFIED" in l:
        print(l)

# ── why does the friend search find nothing, and does the Ready clip have a hover frame? ──
print("\n=== find_friends_reply: how it matches ===")
srv = (L / "lpo/server.py").read_text()
i = srv.index("def find_friends_reply")
print("\n".join("   " + l.strip()[:106] for l in srv[i:i + 1400].splitlines()[:26]))

print("\n=== local accounts ===")
for f in ("lpo/accounts.json", "lpo/accounts.py"):
    p = L / f
    if p.exists() and f.endswith(".json"):
        print("   " + p.read_text()[:600].replace("\n", "\n   "))

print("\n=== does the Ready clip have hover frames? ===")
xml = pathlib.Path("/tmp/interface.xml").read_text(errors="ignore")
for m in re.finditer(r"btnMultiplayReady", xml):
    seg = xml[max(0, m.start() - 300):m.start() + 300]
    labels = re.findall(r'name="([^"]+)"', seg)
    print("   nearby names:", [x for x in labels if len(x) < 24][:14])
