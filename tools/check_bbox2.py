#!/usr/bin/env python3
"""Do the union bbox (all frames) and the exported sprite PNG agree?"""
import glob
import sys

sys.path.insert(0, '/tmp/lpo_avatar')
from avbuild import SwfModel                      # noqa: E402
from PIL import Image                             # noqa: E402

NAMES = ('配件_眼1', '配件_口1', '配件_眉1', '配件_鼻1', '配件_耳1', '配件_面珠1',
         '配件_前髮1', '配件_後髮1', '配件_前髮3', '配件_後髮3', '配件_王子服',
         '配件_王子褲', '配件_王子鞋', '配件_小王冠', '配件_運動服', '配件_運動褲',
         '配件_運動鞋', '配件_運動服袖', '配件_便服', '配件_便服鞋')

it = SwfModel('/tmp/lpo_avatar/items.xml')
bad = 0
for name in NAMES:
    cid = it.find(name)
    box = it.bbox_union(cid) if cid else None
    f = glob.glob('/tmp/lpo_avatar/full/sprites/DefineSprite_%d*/1.png' % cid) if cid else []
    size = Image.open(f[0]).size if f else None
    if not box:
        print('%-14s %-7s NO BBOX' % (name, cid))
        continue
    w, h = round(box[2] - box[0], 1), round(box[3] - box[1], 1)
    ok = bool(size) and abs(size[0] - w) <= 1.5 and abs(size[1] - h) <= 1.5
    bad += 0 if ok else 1
    print('%-14s %-7s %6.1fx%-6.1f png %-10s %s' % (name, cid, w, h, size,
                                                    'OK' if ok else 'MISMATCH'))
print('mismatches:', bad)
