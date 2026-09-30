#!/usr/bin/env python3
"""Is a multi-frame sprite's frame-1 content where the placement maths thinks?

For every base clip of character_anim.swf: (frame1 bbox - union bbox).min must
equal the content offset inside the exported PNG.  A mismatch moves that clip -
which is what a hand that sits away from the wrist looks like.
"""
import glob
import sys

sys.path.insert(0, '/tmp/lpo_avatar')
from avbuild import SwfModel                      # noqa: E402
from PIL import Image                             # noqa: E402

ca = SwfModel('/tmp/lpo_avatar/ca.xml')
bad = 0
for cid in (66, 92, 102, 104, 110, 116, 140, 141, 132, 133):
    f1 = ca.bbox(cid)
    un = ca.bbox_union(cid)
    hits = (glob.glob('/tmp/lpo_avatar/ca_sprites/DefineSprite_%d' % cid) +
            glob.glob('/tmp/lpo_avatar/ca_sprites/DefineSprite_%d_*' % cid))
    if not (f1 and un and hits):
        print('%-5s skip (f1=%s union=%s png=%s)' % (cid, bool(f1), bool(un), bool(hits)))
        continue
    png = hits[0] + '/1.png'
    with Image.open(png) as im:
        cb = im.getbbox()
    exp = (round(f1[0] - un[0]), round(f1[1] - un[1]),
           round(f1[2] - un[0]), round(f1[3] - un[1]))
    ok = cb and max(abs(cb[i] - exp[i]) for i in range(4)) <= 1
    bad += 0 if ok else 1
    print('%-5s png %-10s content %-16s frame1-in-union %-16s %s %s'
          % (cid, im.size, cb, exp, 'OK' if ok else 'MISPLACED',
             'poly' if len(ca.frames.get(cid) or []) > 1 else ''))
print('misplaced:', bad)
