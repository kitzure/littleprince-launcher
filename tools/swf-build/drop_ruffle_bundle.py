#!/usr/bin/env python3
"""Finish the Flash-only pass: fix the one doc line, drop the 28 MB Ruffle bundle,
and record in server.py that the revert now needs that bundle back."""
import pathlib
import shutil

ROOT = pathlib.Path.home() / "Downloads/littleprince-launcher"

# ── README: the pack is Flash-only now ────────────────────────────────────────
R = ROOT / "README.md"
r = R.read_text()
OLD = '''62 MB, 98 files. With the hosts redirect on, **the publisher's own Flash browser
plays them locally** - no binding, no internet, no CD, no patched SWFs. Any other
browser gets the bundled player instead, and the page notices the difference (the
publisher's browser says "Electron" in its user agent; everything else gets Ruffle).'''
NEW = '''62 MB, 98 files. With the hosts redirect on, **the publisher's own Flash browser
plays them locally** - no binding, no internet, no CD, no patched SWFs. This pack is
Flash-only: the pages know the publisher's browser by its user agent ("Electron"), and
any other browser is simply told to download the official browser - the same thing the
publisher's own site asks for. (There used to be a bundled substitute player for those
browsers; it is gone, because the client misbehaves in it and users saw those bugs as
ours.) The launcher fetches the publisher's browser for you, so a fresh machine still
needs nothing from this page.'''
if OLD in r:
    R.write_text(r.replace(OLD, NEW, 1))
    print("README.md: online-client section now describes the Flash-only pack")
else:
    print("!! README anchor not found")

# ── server.py: the revert note must mention the bundle ────────────────────────
S = ROOT / "lpo/server.py"
s = S.read_text()
OLD_C = '''        #    others) and users were seeing those bugs.  Swap the serve below back to
        #    play.html to bring the Ruffle player back.'''
NEW_C = '''        #    others) and users were seeing those bugs.  Swap the serve below back to
        #    play.html to bring the Ruffle player back - that page loads the browser
        #    build of Ruffle from web/ruffle/, which no longer ships (28 MB of dead
        #    weight once the pack went Flash-only), so re-add it first.'''
if OLD_C in s:
    S.write_text(s.replace(OLD_C, NEW_C, 1))
    print("server.py: revert note now says the bundle is needed back")
else:
    print("!! server.py revert-note anchor not found")

# ── drop the bundle ───────────────────────────────────────────────────────────
B = ROOT / "lpo/web/ruffle"
if B.is_dir():
    before = sum(f.stat().st_size for f in B.rglob("*") if f.is_file())
    shutil.rmtree(B)
    print("removed lpo/web/ruffle/ (%.1f MB)" % (before / 1e6))
else:
    print("bundle already gone")

# ── what still points at it? ──────────────────────────────────────────────────
print("\nremaining references to the bundle:")
hits = 0
for f in ROOT.rglob("*"):
    if f.is_file() and f.suffix in (".html", ".py", ".pyw", ".js", ".md"):
        try:
            t = f.read_text(errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(t.splitlines(), 1):
            if "web/ruffle" in line:
                print(f"  {f.relative_to(ROOT)}:{i}: {line.strip()[:90]}")
                hits += 1
print("  (none)" if not hits else f"  {hits} line(s) - these are the pages that are now unreachable or excluded from the zip")

print("\nweb folder now:")
for f in sorted((ROOT / "lpo/web").iterdir()):
    print("   %-22s %s" % (f.name, "dir" if f.is_dir() else "%.1f KB" % (f.stat().st_size / 1024)))
