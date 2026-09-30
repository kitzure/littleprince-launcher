#!/usr/bin/env python3
"""Where does each base entry land, and what is still up beside the head?"""
import sys

sys.path.insert(0, '/home/yoke/Downloads/littleprince-launcher/lpo')
import avatar as pkg                                         # noqa: E402
from PIL import Image                                        # noqa: E402

rig = pkg._load_rig()
vals = pkg.normalise(dict(pkg.FALLBACK))
items = []
for b in rig['base']:
    items.append((b.get('path', b['png']), b['png'], b['matrix'], b['x'], b['y']))
for s in rig['slots']:
    e = pkg._clip(rig, vals.get(s['slot']), s['slot'], s.get('template', '%s'))
    if e:
        items.append((s['path'], e['png'], s['matrix'], e['x'], e['y']))

print('%-26s %-14s %s' % ('entry', 'art', 'placed rect in character space'))
for path, png, m, x, y in items:
    with Image.open(pkg.DATA / png) as im:
        w, h = im.size
    pts = [pkg._apply(m, x, y), pkg._apply(m, x + w, y),
           pkg._apply(m, x, y + h), pkg._apply(m, x + w, y + h)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    print('%-26s %-14s x %6.1f..%6.1f  y %7.1f..%6.1f%s'
          % (path, png, min(xs), max(xs), min(ys), max(ys),
             '   <== UP BY THE HEAD' if min(ys) < -62 and max(xs) > 0 else ''))
