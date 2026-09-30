#!/usr/bin/env python3
"""Render a few looks through the package renderer and save them for eyeballing."""
import sys

sys.path.insert(0, '/home/yoke/Downloads/littleprince-launcher/lpo')
import avatar as pkg                                          # noqa: E402
from PIL import Image                                         # noqa: E402

LOOKS = {
    'default': dict(pkg.FALLBACK),                            # the game's own default
    'prince': {'hat': '小王冠', 'cloth': '王子服', 'trousers': '王子褲',
               'shoes': '王子鞋', 'hair': '髮1'},
    'ninja': {'hat': '男忍者頭巾', 'cloth': '男忍者服', 'trousers': '男忍者褲',
              'shoes': '男忍者鞋', 'hair': '髮7', 'eyes': '眼6', 'mouth': '口5'},
    'boots': {'cloth': '便服', 'trousers': '便服褲', 'shoes': '飛機師靴',
              'hair': '髮2', 'hat': ''},
    'unknown': {'cloth': '不存在的衣服', 'hair': '髮1'},        # must fall back
}

for label, parts in LOOKS.items():
    img = pkg.render(parts, scale=3.0)
    if not img:
        print(label, 'NOT RENDERED')
        continue
    out = '/tmp/lpo_avatar/look_%s.png' % label
    img.save(out)
    print('%-8s %-12s %s' % (label, img.size, out))
