#!/usr/bin/env python3
"""Render the same look at several arm-lean angles, from ONE dataset build.

The part PNGs do not depend on the arm angle - only the two arm clusters' matrices do -
so build once with the arms at their authored pose and rewrite the matrices per variant.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, '/tmp/lpo_avatar')
sys.path.insert(0, '/home/yoke/Downloads/littleprince-launcher/lpo')

PKG = Path('/home/yoke/Downloads/littleprince-launcher/lpo')
BASE = Path('/tmp/lpo_avatar/ds0')
ANGLES = [0.0, 8.0, 14.0, 20.0]

# 1. one build with the authored arm pose
subprocess.run([sys.executable, '/tmp/lpo_avatar/build_dataset.py',
                str(BASE), '0'], check=True, capture_output=True)
print('built baseline dataset at', BASE)

import build_dataset as bd        # noqa: E402  (its helpers)

import avatar as pkg              # noqa: E402
from PIL import Image             # noqa: E402


def variant(angle, dest):
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(BASE, dest)
    rig = json.loads((dest / 'rig.json').read_text(encoding='utf-8'))
    right = {}
    for e in rig['base'] + rig['slots'] + rig['back']:
        p = str(e.get('path') or '')
        if p.startswith('right_arm'):
            if angle:
                e['matrix'] = bd.rot_about_shoulder(e['matrix'], angle)
            right[p[len('right_arm'):]] = e
    for e in rig['base'] + rig['slots'] + rig['back']:
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
    parts = dict(pkg.FALLBACK)
    img = pkg.render(parts, scale=2.0)
    out = Path('/tmp/lpo_avatar/lean_%02d.png' % int(angle))
    img.save(out)
    return out


shots = []
for a in ANGLES:
    shots.append(variant(a, Path('/tmp/lpo_avatar/variant_%02d' % int(a))))
    print('rendered', shots[-1])

ims = [Image.open(s).convert('RGBA') for s in shots]
H = max(i.height for i in ims)
strip = Image.new('RGBA', (sum(i.width for i in ims) + 12 * (len(ims) - 1), H),
                  (255, 255, 255, 255))
x = 0
for i in ims:
    strip.alpha_composite(i, (x, H - i.height))
    x += i.width + 12
strip.convert('RGB').save('/tmp/lpo_avatar/lean_strip.png')
print('wrote /tmp/lpo_avatar/lean_strip.png', strip.size, 'angles', ANGLES)
