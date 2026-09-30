#!/usr/bin/env python3
"""Build the avatar dataset the accounts site renders from.

Reads the character rig out of the game's own files (via ffdec's XML export plus
its sprite PNGs) and writes a small, self-contained folder:

    avatar/rig.json              slot -> container matrix, base art, part index
    avatar/base/<id>.png         the body/face/arm/leg/hand art (character_anim.swf)
    avatar/parts/<name>.png      every wearable 配件_* sprite (lib_items.swf)
    avatar/parts/<name>__back.png   a shoe's `back` piece, when it has one

Each PNG is CROPPED to its own frame-1 content and placed by that frame's own box,

    containerMatrix @ (frame1Bbox.xmin, frame1Bbox.ymin)

so the placement never depends on ffdec's export canvas.  (It used to: the canvas
is the union box over every frame, and my copy of that union was wrong for the hand
clip, which places the authored weapon at alpha 0 - the hands were drawn off the
wrists.  Cropping removes the whole class of error.)

Run it when the game files change; the site never touches the SWFs themselves.
"""
import json
import math
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image                                     # noqa: E402
from avbuild import Avatar, SLOT_CONTAINERS               # noqa: E402

CA_XML = '/tmp/lpo_avatar/ca.xml'
ITEMS_XML = '/tmp/lpo_avatar/items.xml'
CA_PNG = '/tmp/lpo_avatar/ca_sprites'
ITEMS_PNG = '/tmp/lpo_avatar/full/sprites'


def rot_about_shoulder(m, degrees):
    """Turn an arm about its own shoulder joint.

    `avatar._apply` reads a matrix as x' = ax + by + tx, y' = cx + dy + ty, so a
    rotation is applied on the RIGHT (M @ R) - that keeps the clip's origin, which
    IS the shoulder joint, exactly where it is and swings the arm around it.  M @ R
    on the arm's art and on its sleeve/hand slots keeps the whole arm rigid.
    """
    r = math.radians(degrees)
    cos, sin = math.cos(r), math.sin(r)
    a, b, c, d, tx, ty = m
    ra, rb, rc, rd = cos, -sin, sin, cos
    return [a * ra + b * rc, a * rb + b * rd,
            c * ra + d * rc, c * rb + d * rd,
            tx, ty]


def mirror_x(m):
    """Reflect a matrix through the character's vertical axis (x -> -x).

    `avatar._apply` reads a matrix as x' = ax + by + tx, y' = cx + dy + ty, so the
    mirror is [-1,0;0,1] @ M = (-a, -b, c, d, -tx, ty).  Negating the pair the other
    way round puts the arm somewhere else entirely.
    """
    a, b, c, d, tx, ty = m
    return [-a, -b, c, d, -tx, ty]


def fetch(model, png_dir, cid, out_dir, rel):
    """Crop a character's frame-1 render to its content; -> dict for rig.json.

    Returns the placement origin in the SPRITE'S OWN space: the content's top-left
    corner sits where frame 1's box starts.
    """
    png = model.png_path(png_dir, cid)
    box = model.bbox(cid)                      # frame 1 only
    if not (png and box):
        return None
    im = Image.open(png).convert('RGBA')
    cb = im.getbbox()
    if cb:
        im = im.crop(cb)
    dest = os.path.join(out_dir, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    im.save(dest, 'PNG', optimize=True)
    return {'png': rel, 'x': box[0], 'y': box[1]}


def main(out_dir, lean_deg=None):
    av = Avatar(CA_XML, ITEMS_XML, CA_PNG, ITEMS_PNG, out_dir)

    rig = {'slots': [], 'base': [], 'back': [], 'parts': {}}

    for order, (path, m, cid, kind) in enumerate(av.rig()):
        if kind == 'slot':
            for slot, pairs in SLOT_CONTAINERS.items():
                for c, tmpl in pairs:
                    if c == path:
                        rig['slots'].append({'path': path, 'slot': slot, 'order': order,
                                             'template': tmpl, 'matrix': list(m)})
            continue
        if path.endswith('.back_shoes'):
            # the authored content is the little prince's own boot: the client
            # removes it and puts the worn shoe's `back` piece there instead, so
            # this must never be drawn as base art.
            rig['back'].append({'path': path, 'slot': 'shoes', 'order': order,
                                'template': '%s', 'matrix': list(m)})
            continue
        art = fetch(av.ca, CA_PNG, cid, out_dir, 'base/%d.png' % cid)
        if not art:
            print('  !! no art for base clip %s (%s)' % (path, cid))
            continue
        art['order'] = order
        art['matrix'] = list(m)
        art['path'] = path
        rig['base'].append(art)

    # The stand pose also sPLAYS the arms ~28 deg out from vertical; the official art
    # (and anyone's eye) has them hanging almost straight. Both arms are one clip, so
    # turn each about its own shoulder joint, then mirror right onto left below - the
    # sleeve, accessory, hand and item slots turn with it because they live inside the
    # arm and get the same M @ R.
    # The stand pose SPLAYS the arms ~28 deg out from vertical, which reads as "the arm
    # is too far out" beside the official hand-drawn art. A rotation cannot fix it: the
    # arm art, the hand and the T-shirt sleeve are separate rigid pieces drawn for this
    # one pose, so turning the arm about the clip origin swings the sleeve cap off the
    # shirt's shoulder, and turning the arm alone leaves the arm hanging out of its own
    # sleeve. Sliding the ARM (not the sleeve) inward is the one change that survives:
    # the sleeve cap keeps covering the shoulder, and ~2 character units is as far as it
    # goes before the arm stops meeting the sleeve cleanly.
    ARM_INWARD_UNITS = 2.0
    for _e in rig['base'] + rig['slots'] + rig['back']:
        _p = str(_e.get('path') or '')
        if _p.startswith('right_arm') and not _p.endswith('.cloth'):
            _m = list(_e['matrix'])
            _m[4] += ARM_INWARD_UNITS
            _e['matrix'] = _m

    # The authored stand ('nomotion') is the little prince holding his staff: the
    # right hand hangs at the waist and the LEFT hand sits up beside his head. The
    # site draws a portrait, so give the left arm the right arm's pose, mirrored:
    # take each left_arm entry's counterpart (both arms are clip 99, so the subpaths
    # match one for one - art, sleeve, accessory, hand, item) and mirror ITS matrix.
    # Mirroring the left arm's own matrix instead would keep the raised pose and just
    # put it on the wrong side of the body.
    _right = {}
    for _e in rig['base'] + rig['slots'] + rig['back']:
        _p = str(_e.get('path') or '')
        if _p.startswith('right_arm'):
            _right[_p[len('right_arm'):]] = _e
    for _e in rig['base'] + rig['slots'] + rig['back']:
        _p = str(_e.get('path') or '')
        if not _p.startswith('left_arm'):
            continue
        _src = _right.get(_p[len('left_arm'):])
        if _src:
            _e['matrix'] = mirror_x(_src['matrix'])
            if 'x' in _src:
                _e['x'], _e['y'] = _src['x'], _src['y']

    made = missing = 0
    for name, cid in sorted(av.items.symbols.items()):
        if not name.startswith('配件_'):
            continue
        short = name[len('配件_'):]
        entry = fetch(av.items, ITEMS_PNG, cid, out_dir, 'parts/%s.png' % short)
        if not entry:
            missing += 1
            continue

        for _d, cname, child, cm in av.items.sprites.get(cid, []):
            if cname != 'back' or child not in av.items.sprites:
                continue
            back = fetch(av.items, ITEMS_PNG, child, out_dir,
                         'parts/%s__back.png' % short)
            if back:
                back['matrix'] = list(cm)
                entry['back'] = back
        rig['parts'][short] = entry
        made += 1

    with open(os.path.join(out_dir, 'rig.json'), 'w', encoding='utf-8') as fh:
        json.dump(rig, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print('slots %d, base %d, back %d, parts %d (missing art %d)'
          % (len(rig['slots']), len(rig['base']), len(rig['back']), made, missing))
    print('dataset:', out_dir)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '/tmp/lpo_avatar/dataset',
         sys.argv[2] if len(sys.argv) > 2 else None)
