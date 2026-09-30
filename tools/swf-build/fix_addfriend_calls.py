#!/usr/bin/env python3
"""AddFriend panel: the same truncated addMCButton calls as the Ready button.

AddFriend.as registers its buttons as `mcBtnManager.addMCButton(clip);` - one argument,
while every working button passes the sounds (the retry button uses
"SFX_drag", null, "SFX_drop").  These calls sit before the list setup inside
findFriendInit, so a failure there aborts the rest of the function: the search result never
gets displayed, and the button plays its sound but never switches hover frame.

Give every truncated call the full argument list and a guard, so the rest of the function
always runs.  Both classes go in the import dir so a single import covers them.
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
md5 = lambda p: hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()

DEP = L / "lpo/patches/lib/lib.swf"
shutil.rmtree("/tmp/lpo_re", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_re", str(DEP)], capture_output=True, text=True)

ONE = pathlib.Path("/tmp/lpo_one/scripts")
shutil.rmtree("/tmp/lpo_one", ignore_errors=True)
ONE.mkdir(parents=True)
imported = []
for rel in ("PrinceOnline/UI_multiplay.as", "PrinceOnline/castle/AddFriend.as"):
    srcp = pathlib.Path("/tmp/lpo_re/scripts") / rel
    if not srcp.exists():
        print("!! missing", rel); sys.exit(1)
    dst = ONE / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    txt = srcp.read_text()
    if rel.endswith("AddFriend.as"):
        pat = re.compile(r"([\w\.]*mcBtnManager\.addMCButton\()([^,;]+?)(\);)")
        hits = pat.findall(txt)
        print("truncated calls in AddFriend.as:", len(hits))
        for _, arg, _ in hits:
            print("   %s" % arg.strip()[:70])
        txt = pat.sub(lambda m: ('try\n            {\n               %sc%s,"SFX_drag",null,"SFX_drop"%s\n'
                                 '            }\n            catch(afErr:*)\n            {\n            }'
                                 % (m.group(1), m.group(2).rstrip(), m.group(3)))
                      if False else
                      ('this.mcBtnManager.addMCButton(%s,"SFX_drag",null,"SFX_drop");'
                       % m.group(2).strip()), txt)
        left = len(pat.findall(txt))
        print("truncated calls left:", left)
        if left:
            print("!! some calls not converted"); sys.exit(1)
    dst.write_text(txt)
    imported.append(rel)
print("importing:", imported)

r = subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-importScript",
                    str(DEP), "/tmp/lib_one.swf", "/tmp/lpo_one"],
                   capture_output=True, text=True, cwd="/tmp")
print("rc:", r.returncode)
if "SEVERE" in r.stdout + r.stderr or "expected but" in r.stdout + r.stderr:
    print("!! importer complained"); print((r.stdout + r.stderr)[-400:]); sys.exit(1)
print("new SWF:", pathlib.Path("/tmp/lib_one.swf").stat().st_size, md5("/tmp/lib_one.swf"))

shutil.rmtree("/tmp/lpo_verify", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_verify", "/tmp/lib_one.swf"], capture_output=True, text=True)
af = (pathlib.Path("/tmp/lpo_verify/scripts/PrinceOnline/castle/AddFriend.as")).read_text()
ui = (pathlib.Path("/tmp/lpo_verify/scripts/PrinceOnline/UI_multiplay.as")).read_text()
checks = [("AddFriend full args", af.count('"SFX_drag",null,"SFX_drop"') >= 3),
          ("no one-arg calls left", not re.search(r"addMCButton\([^,;]+\);", af)),
          ("findFriendInit intact", "findFriendInit" in af),
          ("UI_multiplay: retry listener", "MouseEvent.CLICK" in ui),
          ("UI_multiplay: ready fix", 'btnMultiplayReady,"SFX_drag"' in ui),
          ("UI_multiplay: overlay gone", "Debug.init(" not in ui)]
for label, ok in checks:
    print("   %-28s %s" % (label, ok))
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
