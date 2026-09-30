#!/usr/bin/env python3
"""Move the arm inward by TRANSLATION (arm + hand only; the sleeve stays on the shirt).

The sleeve cap covers the shoulder, so sliding the arm in a little should hide the seam
under it - unlike a rotation, which swings the sleeve cap off the shirt.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, '/tmp/lpo_avatar')
sys.path.insert(0, '/home/yoke/Downloads/littleprince-launcher/lpo')

import avatar as pkg                                          # noqa: E402
from PIL import Image                                        # noqa: E402

BASE = Path('/tmp/lpo_avatar/ds0')


def mirror_x(m):
    a, b, c, d, tx, ty = m
    return [-a, -b, c, d, -tx, ty]


def variant(dx, dest, tag):
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(BASE, dest)
    rig = json.loads((dest / 'rig.json').read_text(encoding='utf-8'))
    all_e = rig['base'] + rig['slots'] + rig['back']

    def sleeve(e):
        p = str(e.get('path') or '')
        return p.endswith('.cloth') and ('_arm' in p)

    right = {}
    for e in all_e:
        p = str(e.get('path') or '')
        if not p.startswith('right_arm'):
            continue
        if dx and not sleeve(e):
            m = list(e['matrix'])
            m[4] += dx                       # slide the arm inward, in character units
            e['matrix'] = m
        right[p[len('right_arm'):]] = e
    for e in all_e:
        p = str(e.get('path') or '')
        if p.startswith('left_arm'):
            src = right.get(p[len('left_arm'):])
            if src:
                e['matrix'] = mirror_x(src['matrix'])
                if 'x' in src:
                    e['x'], e['y'] = src['x'], src['y']
    (dest / 'rig.json').write_text(json.dumps(rig, ensure_ascii=False, indent=1,
                                              sort_keys=True), encoding='utf-8')
    pkg._rig = None
    pkg._rig_tried = False
    pkg.DATA = dest
    out = Path('/tmp/lpo_avatar/tr_%s.png' % tag)
    pkg.render(dict(pkg.FALLBACK), scale=2.0).save(out)
    print('%-12s -> %s' % (tag, out))
    return out


shots = [variant(0, Path('/tmp/lpo_avatar/t_000'), '0-ref'),
         variant(2.0, Path('/tmp/lpo_avatar/t_020'), 'in-2'),
         variant(3.5, Path('/tmp/lpo_avatar/t_035'), 'in-3.5'),
         variant(5.0, Path('/tmp/lpo_avatar/t_050'), 'in-5')]
ims = [Image.open(s).convert('RGBA') for s in shots]
H = max(i.height for i in ims)
strip = Image.new('RGBA', (sum(i.width for i in ims) + 12 * (len(ims) - 1), H),
                  (255, 255, 255, 255))
x = 0
for i in ims:
    strip.alpha_composite(i, (x, H - i.height))
    x += i.width + 12
strip.convert('RGB').save('/tmp/lpo_avatar/translate_strip.png')
print('wrote translate_strip.png', strip.size, '| 0, 2, 3.5, 5 units inward')
