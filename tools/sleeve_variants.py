#!/usr/bin/env python3
"""Lean the arm WITHOUT dragging the T-shirt sleeve off the shoulder.

The sleeve is a T-shirt part sitting on the shoulder, and its placement inside the arm
clip is the identity, so rotating "the arm" rotated the sleeve with it - which is what
pulled it off the shirt at every angle.  Rotate the arm's own art, hand, accessory and
item, and leave the sleeve where the shirt puts it; the arm then swings under the sleeve.
"""
import json
import math
import shutil
import sys
from pathlib import Path

sys.path.insert(0, '/tmp/lpo_avatar')
sys.path.insert(0, '/home/yoke/Downloads/littleprince-launcher/lpo')

import avatar as pkg                                          # noqa: E402
from PIL import Image                                        # noqa: E402

BASE = Path('/tmp/lpo_avatar/ds0')


def rot(m, degrees):
    r = math.radians(degrees)
    cos, sin = math.cos(r), math.sin(r)
    a, b, c, d, tx, ty = m
    return [a * cos + b * sin, -a * sin + b * cos,
            c * cos + d * sin, -c * sin + d * cos, tx, ty]


def mirror_x(m):
    a, b, c, d, tx, ty = m
    return [-a, -b, c, d, -tx, ty]


def variant(angle, rotate_sleeve, dest, tag):
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(BASE, dest)
    rig = json.loads((dest / 'rig.json').read_text(encoding='utf-8'))
    all_e = rig['base'] + rig['slots'] + rig['back']

    def is_sleeve(e):
        return str(e.get('path') or '').endswith('.cloth') and \
            (str(e.get('path')).startswith('right_arm') or
             str(e.get('path')).startswith('left_arm'))

    right = {}
    for e in all_e:
        p = str(e.get('path') or '')
        if not p.startswith('right_arm'):
            continue
        if angle and (rotate_sleeve or not is_sleeve(e)):
            e['matrix'] = rot(e['matrix'], angle)
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
    out = Path('/tmp/lpo_avatar/sl_%s.png' % tag)
    pkg.render(dict(pkg.FALLBACK), scale=2.0).save(out)
    print('%-22s -> %s' % (tag, out))
    return out


shots = [variant(0, True, Path('/tmp/lpo_avatar/w_00'), '00-reference'),
         variant(14, False, Path('/tmp/lpo_avatar/w_14n'), '14-arm-only'),
         variant(20, False, Path('/tmp/lpo_avatar/w_20n'), '20-arm-only'),
         variant(20, True, Path('/tmp/lpo_avatar/w_20y'), '20-sleeve-too')]
ims = [Image.open(s).convert('RGBA') for s in shots]
H = max(i.height for i in ims)
strip = Image.new('RGBA', (sum(i.width for i in ims) + 12 * (len(ims) - 1), H),
                  (255, 255, 255, 255))
x = 0
for i in ims:
    strip.alpha_composite(i, (x, H - i.height))
    x += i.width + 12
strip.convert('RGB').save('/tmp/lpo_avatar/sleeve_strip.png')
print('wrote sleeve_strip.png', strip.size,
      '| 1: 0deg  2: 14deg arm-only  3: 20deg arm-only  4: 20deg sleeve rotates too')
