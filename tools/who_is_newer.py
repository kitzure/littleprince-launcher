#!/usr/bin/env python3
"""Whose copy of the shared source files is newest: theirs (zip), mine (zip), the tree."""
import hashlib
import zipfile
from pathlib import Path

TREE = Path("/home/yoke/Downloads/littleprince-launcher")
THEIRS = Path("/tmp/drive_newest_pack.zip")
MINE = Path.home() / "Downloads" / "littleprince-patcher.zip"

FILES = ["lpo/server.py", "lpo/web.html", "lpo/mp_relay.py", "Start_Server_GUI.pyw",
         "lpo/avatar.py", "lpo/web/play_flash.html", "lpo/web/play.html"]


def from_zip(z, rel):
    with zipfile.ZipFile(z) as zf:
        name = "littleprince-launcher/" + rel
        try:
            return hashlib.md5(zf.read(name)).hexdigest()
        except KeyError:
            return None


print("%-26s %-10s %-10s %-10s  verdict" % ("file", "theirs", "mine", "tree now"))
for rel in FILES:
    t = from_zip(THEIRS, rel)
    mi = from_zip(MINE, rel)
    p = TREE / rel
    tr = hashlib.md5(p.read_bytes()).hexdigest() if p.exists() else None
    shorts = lambda x: (x or "-")[:8]
    if tr and tr == mi:
        verdict = "tree == my build"
    elif tr and tr == t:
        verdict = "tree == theirs (I am behind)"
    elif tr:
        verdict = "TREE CHANGED since both builds"
    else:
        verdict = "file missing in tree"
    print("%-26s %-10s %-10s %-10s  %s" % (rel, shorts(t), shorts(mi), shorts(tr), verdict))

# does their server.py carry multiplayer routes the tree does not?
import re
with zipfile.ZipFile(THEIRS) as zf:
    ts = zf.read("littleprince-launcher/lpo/server.py").decode("utf-8", "replace")
tr_s = (TREE / "lpo/server.py").read_text(encoding="utf-8", errors="replace")
mp_their = set(re.findall(r"['\"](/[a-z0-9_/]*(?:mp|relay)[a-z0-9_/]*)['\"]", ts, re.I))
mp_tree = set(re.findall(r"['\"](/[a-z0-9_/]*(?:mp|relay)[a-z0-9_/]*)['\"]", tr_s, re.I))
print("\nmultiplayer-ish paths only in THEIR server.py:", sorted(mp_their - mp_tree) or "none")
print("multiplayer-ish paths only in the TREE's server.py:", sorted(mp_tree - mp_their) or "none")
print("their server.py references mp_relay:", "mp_relay" in ts, "| the tree's:", "mp_relay" in tr_s)
with zipfile.ZipFile(THEIRS) as zf:
    tm = zf.read("littleprince-launcher/lpo/mp_relay.py").decode("utf-8", "replace") if any(
        n.endswith("lpo/mp_relay.py") for n in zf.namelist()) else ""
tr_m = (TREE / "lpo/mp_relay.py").read_text(encoding="utf-8", errors="replace") \
    if (TREE / "lpo/mp_relay.py").exists() else ""
print("their mp_relay.py bytes %d | the tree's %d" % (len(tm), len(tr_m)))
