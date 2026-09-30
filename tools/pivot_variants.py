#!/usr/bin/env python3
"""Same lean, two different pivots - the clip's own origin vs the sleeve's shoulder.

Rotating about the clip origin drags the sleeve off the shoulder (the origin is not
the shoulder joint).  Rotating about the point where the SLEEVE sits keeps the T-shirt
sleeve on the shoulder while the arm swings under it.

Everything is done in the arm clip's own space: for the cluster's composed matrices
M = A @ L, a local transform P becomes M' = A @ P @ inv(A) @ M.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, '/tmp/lpo_avatar')
sys.path.insert(0, '/home/yoke/Downloads/littleprince-launcher/lpo')

import build_dataset as bd                                   # noqa: E402
import avatar as pkg                                         # noqa: E402
from PIL import Image                                        # noqa: E402

BASE = Path('/tmp/lpo_avatar/ds0')


def inv(m):
    a, b, c, d, tx, ty = m
    det = a * d - b * c
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return [ia, ib, ic, id_, -(ia * tx + ib * ty), -(ic * tx + id_ * ty)]


def mul(m1, m2):
    a1, b1, c1, d1, x1, y1 = m1
    a2, b2, c2, d2, x2, y2 = m2
    return [a1 * a2 + b1 * c2, a1 * b2 + b1 * d2,
            c1 * a2 + d1 * c2, c1 * b2 + d1 * d2,
            a1 * x2 + b1 * y2 + x1, c1 * x2 + d1 * y2 + y1]


def rotate_cluster(entries, angle, pivot=None):
    """Turn every right_arm entry about `pivot` (arm-local) or the clip origin."""
    A = None
    S = None
    for e in entries:
        if e.get('path') == 'right_arm.None':
            A = e['matrix']
        elif e.get('path') == 'right_arm.cloth':
            S = e['matrix']
    if pivot == 'sleeve' and A and S:
        L = mul(inv(A), S)
        px, py = L[4], L[5]                       # where the sleeve sits, arm-local
    else:
        px = py = 0.0
    r = __import__('math').radians(angle)
    cos, sin = __import__('math').cos(r), __import__('math').sin(r)
    P = [cos, -sin, sin, cos, px - (cos * px - sin * py), py - (sin * px + cos * py)]
    for e in entries:
        if str(e.get('path') or '').startswith('right_arm'):
            e['matrix'] = mul(mul(mul(A, P), inv(A)), e['matrix'])
    return px, py


def variant(angle, pivot, dest):
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(BASE, dest)
    rig = json.loads((dest / 'rig.json').read_text(encoding='utf-8'))
    all_e = rig['base'] + rig['slots'] + rig['back']
    px, py = rotate_cluster(all_e, angle, pivot)
    right = {str(e.get('path'))[len('right_arm'):]: e for e in all_e
             if str(e.get('path') or '').startswith('right_arm')}
    for e in all_e:
        p = str(e.get('path') or '')
        if p.startswith('left_arm'):
            src = right.get(p[len('left_arm'):])
            if src:
                e['matrix'] = bd.mirror_x(src['matrix'])
                if 'x' in src:
                    e['x'], e['y'] = src['x'], src['y']
    (dest / 'rig.json').write_text(json.dumps(rig, ensure_ascii=False, indent=1,
                                              sort_keys=True), encoding='utf-8')
    pkg._RIG = None
    pkg.DATA = dest
    out = Path('/tmp/lpo_avatar/pv_%s_%02d.png' % (pivot or 'origin', int(angle)))
    pkg.render(dict(pkg.FALLBACK), scale=2.0).save(out)
    print('%-8s %4.1f deg pivot arm-local (%.2f, %.2f) -> %s' % (pivot, angle, px, py, out))
    return out


shots = [variant(8, 'origin', Path('/tmp/lpo_avatar/v_o8')),
         variant(8, 'sleeve', Path('/tmp/lpo_avatar/v_s8')),
         variant(20, 'sleeve', Path('/tmp/lpo_avatar/v_s20')),
         variant(30, 'sleeve', Path('/tmp/lpo_avatar/v_s30'))]
ims = [Image.open(s).convert('RGBA') for s in shots]
H = max(i.height for i in ims)
strip = Image.new('RGBA', (sum(i.width for i in ims) + 12 * (len(ims) - 1), H),
                  (255, 255, 255, 255))
x = 0
for i in ims:
    strip.alpha_composite(i, (x, H - i.height))
    x += i.width + 12
strip.convert('RGB').save('/tmp/lpo_avatar/pivot_strip.png')
print('wrote pivot_strip.png', strip.size,
      '| 1 origin 8deg, 2 sleeve 8deg, 3 sleeve 20deg, 4 sleeve 30deg')
