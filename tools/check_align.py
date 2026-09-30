#!/usr/bin/env python3
"""Where does ffdec put frame 1's content inside a sprite's PNG canvas?

If it aligns frames on the sprite's own origin (canvas = union bbox), then the
content bbox inside the PNG equals frame-1's bbox minus the union bbox origin.
"""
import glob
import sys

sys.path.insert(0, '/tmp/lpo_avatar')
from avbuild import SwfModel                      # noqa: E402
from PIL import Image                             # noqa: E402

it = SwfModel('/tmp/lpo_avatar/items.xml')
names = ('配件_口1', '配件_眉1', '配件_眼1', '配件_耳1', '配件_面珠1', '配件_前髮3')
for name in names:
    cid = it.find(name)
    f1 = it.bbox(cid)
    un = it.bbox_union(cid)
    f = glob.glob('/tmp/lpo_avatar/full/sprites/DefineSprite_%d*/1.png' % cid)[0]
    im = Image.open(f)
    cb = im.getbbox()                        # content bbox inside the PNG
    exp = (round(f1[0] - un[0]), round(f1[1] - un[1]),
           round(f1[2] - un[0]), round(f1[3] - un[1])) if f1 else None
    print('%-14s png %-9s content %-16s frame1-in-union %s' % (name, im.size, cb, exp))
