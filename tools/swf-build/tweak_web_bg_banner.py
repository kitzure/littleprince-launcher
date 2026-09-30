#!/usr/bin/env python3
"""Two tweaks: drop the sign-in banner, and replace the publisher's sky JPEG with CSS.

The user: 'the sign in page no need that banner of little prince one / then the bg can NOT use
theirs one you can use anothers or made a css'.  So: the sign-in cover card goes, and the page
background becomes a CSS star field over a soft daylight gradient - no publisher art.
"""
import pathlib
import re

W = pathlib.Path("/home/yoke/Downloads/littleprince-launcher/lpo/web.html")
src = W.read_text()
before = len(src)

# 1 - the sign-in cover block (their portal card art)
cover = '''    <div class="lp-cover">
      <img src="/web/theme/prince-card.png" alt="Little Prince Online">
      <span>Little Prince Online</span>
    </div>
'''
assert cover in src, "cover block not found"
src = src.replace(cover, "", 1)
print("removed the sign-in banner block")

# its CSS reserved space on the right - let the form use the full width
old_pad = "#tab-login{padding-right:250px;min-height:300px}"
assert old_pad in src, "cover padding rule not found"
src = src.replace(old_pad, "#tab-login{min-height:260px}", 1)
print("released the space the banner reserved")

# 2 - background: CSS only, no bg.jpg
old_bg = '''html{background:#e2f3fd}'''
new_bg = '''html{background:#dff1fd}'''
src = src.replace(old_bg, new_bg, 1)

old_body = '''    /* the publisher's own page: their sky JPEG across the top, then the pale
       end of that gradient continuing under it, so the band has no seam */
    background:#e2f3fd url("/web/theme/bg.jpg") center top repeat-x;'''
new_body = '''    /* CSS-only sky - a soft daylight gradient with a drifting star field.
       No publisher artwork is used here. */
    background:
      radial-gradient(circle at 12% 18%, rgba(255,255,255,.92) 0 1.6px, transparent 1.7px),
      radial-gradient(circle at 34% 44%, rgba(255,255,255,.78) 0 1.3px, transparent 1.4px),
      radial-gradient(circle at 57% 11%, rgba(255,255,255,.88) 0 1.5px, transparent 1.6px),
      radial-gradient(circle at 79% 34%, rgba(255,255,255,.72) 0 1.2px, transparent 1.3px),
      radial-gradient(circle at 91% 63%, rgba(255,255,255,.62) 0 1.4px, transparent 1.5px),
      radial-gradient(1200px 540px at 50% -150px, #ffffff 0%, #e9f6fe 44%, #d2ecfc 100%);
    background-repeat:repeat,repeat,repeat,repeat,repeat,no-repeat;
    background-size:260px 220px,320px 260px,210px 190px,300px 240px,240px 210px,100% 100%;'''
assert old_body in src, "body background rule not found"
src = src.replace(old_body, new_body, 1)
print("background is now CSS-only")
W.write_text(src)
print("web.html: %d -> %d chars" % (before, len(src)))
print("bg.jpg still referenced:", "bg.jpg" in src, "| prince-card still referenced:",
      "prince-card" in src)

# retire the two publisher assets that are no longer used
theme = pathlib.Path("/home/yoke/Downloads/littleprince-launcher/lpo/web/theme")
for name in ("bg.jpg", "prince-card.png"):
    p = theme / name
    if p.exists():
        p.unlink()
        print("removed asset:", name)
