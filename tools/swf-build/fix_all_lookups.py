#!/usr/bin/env python3
"""The publisher's own retry lookups throw the same #1069, in label_mp_result_end.

That aborts the handler before its stop(), which is the original "jumps to the settings
page" failure.  Convert every bracket lookup of this button to mpFind(), drop the MovieClip
type annotation (coercing a non-MovieClip button throws #1034), and neutralise the
addMCButton calls for it - those gotoAndStop the clip, which blanked the stage.
"""
import pathlib
import re
import shutil
import subprocess
import sys

HOME = pathlib.Path.home()
JAR = HOME / "lpo_build/ffdec/ffdec-cli.jar"
DEP = HOME / "Downloads/littleprince-launcher/lpo/patches/lib/lib.swf"
SRC = pathlib.Path("/tmp/lpo_cur/scripts/PrinceOnline/UI_multiplay.as")

shutil.rmtree("/tmp/lpo_re", ignore_errors=True)
subprocess.run(["java", "-jar", str(JAR), "-onerror", "ignore", "-export", "script",
                "/tmp/lpo_re", str(DEP)], capture_output=True, text=True)
shutil.copy2(pathlib.Path("/tmp/lpo_re/scripts/PrinceOnline/UI_multiplay.as"), SRC)
src = SRC.read_text()

pat = re.compile(r'this\[("(?:btnRetry[^"]*)")[^\]]*\]')
found = pat.findall(src)
print("bracket lookups of the retry button still in the class:", len(found))


def to_find(m):
    inner = m.group(0)
    return inner.replace('this[', 'this.mpFind(', 1).replace(']', ')', 1) \
        if False else None   # placeholder, see below


def conv(m):
    whole = m.group(0)
    # this["btnRetry" + X]  ->  this.mpFind("btnRetry" + X)
    body = whole[len("this["):-1]
    return "this.mpFind(" + body + ")"


src, n = pat.subn(conv, src)
print("converted:", n)

src, n2 = re.subn(r"var (\w+):MovieClip = this\.mpFind\(", r"var \1:* = this.mpFind(", src)
print("type annotations dropped:", n2)

# neutralise addMCButton for the retry button only
def drop_addmc(m):
    return 'Debug.addLog("\\\\tmp_diag: skipped addMCButton for " + %s.name);' % m.group(1)

src, n3 = re.subn(r"this\.(\w+)\.addMCButton\((\w+)\,\"[^\"]*\",null,\"[^\"]*\"\)", drop_addmc, src)
print("addMCButton calls neutralised:", n3)

SRC.write_text(src)
left = re.findall(r'this\["btnRetry[^\]]*\]', src)
print("bracket lookups remaining:", len(left))

r = subprocess.run(["bash", str(HOME / "lpo_build/rebuild_one_class.sh")],
                   capture_output=True, text=True, cwd="/tmp")
print("\n".join(l for l in r.stdout.splitlines() if l.startswith(("new", "base", "deployed"))))
if "SEVERE" in r.stdout or "expected but" in r.stdout:
    print("!! importer complained")
    print(r.stdout[-400:])
    sys.exit(1)
out = pathlib.Path("/tmp/lpo_one_out/scripts/PrinceOnline/UI_multiplay.as").read_text()
print("dupes:", out.count("function mpDiag"), out.count("function mpWireRetry"),
      out.count("function mpFind("), out.count("function mpFindDeep"))
print("bracket lookups in the rebuilt class:", len(re.findall(r'this\["btnRetry[^\]]*\]', out)))
print("mpFind in use:", out.count("mpFind(") > 1)
