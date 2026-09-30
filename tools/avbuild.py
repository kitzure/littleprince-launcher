#!/usr/bin/env python3
"""Compose an LPO character portrait from a 16-slot cloth setting.

Everything geometric comes out of the game's own files - the container chain and
its matrices from `lib/character_anim.swf` (sprite 458, frame 1 = `nomotion`, the
standing pose the client starts on), and each part's art from `lib/lib_items.swf`:

    sprite 458 -> head / body / arms / legs / head_back / tail   (matrices)
    ...        -> fore_hair, eyes, mouth, cloth, trousers, shoes (containers)
    in a container the client does addChild(getResObj("配件_"+value)) at (0,0),
    so a part's art lands at containerMatrix * partRect.

Nothing is placed by eye: the matrix chain and each sprite's own rect decide.
"""
import glob
import os
import re
import struct
import xml.etree.ElementTree as ET
import zlib

from PIL import Image

# ── which clip takes which slot ──────────────────────────────────────────────
# Character.clothInit names every container; a slot with no value draws nothing
# (the client removes the authored child and adds none).
SLOT_CONTAINERS = {
    "hat": [("head.accessaries", "%s")],
    "hair": [("head.fore_hair", "前%s"), ("head_back.back_hair", "後%s")],
    "ears": [("head.ears", "%s")],
    "blusher": [("head.blusher", "%s")],
    "mouth": [("head.mouth", "%s")],
    "eyes": [("head.eyes", "%s")],
    "eyeblows": [("head.eyeblows", "%s")],
    "nose": [("head.nose", "%s")],
    "left_acc": [("left_arm.accessaries", "%s")],
    "right_acc": [("right_arm.accessaries", "%s")],
    "left_item": [("left_arm.hand.item", "%s")],
    "right_item": [("right_arm.hand.item", "%s")],
    "cloth": [("body.cloth", "%s"), ("left_arm.cloth", "%s袖"), ("right_arm.cloth", "%s袖")],
    "trousers": [("left_leg.trousers", "%s"), ("right_leg.trousers", "%s")],
    "shoes": [("left_leg.shoes", "%s"), ("right_leg.shoes", "%s")],
    "tail": [("tail", "%s")],
}
# author-time contents of the modifiable containers: never drawn as-is
CONTAINER_SLOTS = {c for pairs in SLOT_CONTAINERS.values() for c, _ in pairs}
# the container clip names, so the walk knows which clips to keep descending into
RIG_NAMES = ("shadow", "tail", "head_back", "right_arm", "right_leg", "left_leg", "body",
             "left_arm", "head", "face", "back_hair", "hand", "item", "cloth", "accessaries",
             "ears", "blusher", "fore_hair", "mouth", "eyes", "eyeblows", "nose",
             "back_shoes", "trousers", "shoes")

# the real default look: the publisher's own login4 reply for a fresh account
DEFAULT_PARTS = {"hat": "", "hair": "髮3", "ears": "耳1", "blusher": "面珠1", "mouth": "口1",
                 "eyes": "眼1", "eyeblows": "眉1", "nose": "鼻1", "left_acc": "", "right_acc": "",
                 "left_item": "", "right_item": "", "cloth": "運動服", "trousers": "運動褲",
                 "shoes": "運動鞋", "tail": ""}


def twips(v):
    return float(v or 0) / 20.0


def rect_of(el):
    return (twips(el.get('Xmin')), twips(el.get('Ymin')),
            twips(el.get('Xmax')), twips(el.get('Ymax')))


def matrix_of(el):
    """ffdec MATRIX -> (a, b, c, d, tx, ty) px units (twips/20)."""
    if el is None:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    def n(k, d):
        try:
            return float(el.get(k))
        except (TypeError, ValueError):
            return d
    return (n('scaleX', 1.0), n('rotateSkew0', 0.0), n('rotateSkew1', 0.0),
            n('scaleY', 1.0), twips(el.get('translateX')), twips(el.get('translateY')))


def alpha_of(el):
    """CXFORMWITHALPHA -> overall alpha.  `alphaMultTerm="0"` means INVISIBLE.

    Sprite 92 (the hand clip) places the authored weapon at frame 1 with a
    multiply-alpha of 0 and fades it in later; counting that placement put the
    hand's frame-1 box six times too wide and every hand was drawn off the wrist.
    """
    if el is None:
        return 1.0
    def n(k, d):
        try:
            return float(el.get(k))
        except (TypeError, ValueError):
            return d
    a = n('alphaMultTerm', 256) / 256.0
    if el.get('hasAddTerms') == 'true':
        a += n('alphaAddTerm', 0) / 256.0
    return a


def mul(m1, m2):
    a1, b1, c1, d1, tx1, ty1 = m1
    a2, b2, c2, d2, tx2, ty2 = m2
    return (a1 * a2 + b1 * c2, a1 * b2 + b1 * d2,
            c1 * a2 + d1 * c2, c1 * b2 + d1 * d2,
            a1 * tx2 + b1 * ty2 + tx1, c1 * tx2 + d1 * ty2 + ty1)


def inv(m):
    a, b, c, d, tx, ty = m
    det = a * d - b * c
    if abs(det) < 1e-12:
        det = 1e-12
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return (ia, ib, ic, id_, -(ia * tx + ib * ty), -(ic * tx + id_ * ty))


def apply(m, x, y):
    a, b, c, d, tx, ty = m
    return (a * x + b * y + tx, c * x + d * y + ty)


class SwfModel:
    """Everything the compositor needs out of a SWF's XML: shapes, sprites, symbols."""

    def __init__(self, xml_path):
        self.shapes = {}
        self.sprites = {}
        self.all_sprites = {}
        self.frames = {}
        self.records = {}
        self.bounds = {}
        self.symbols = {}
        root = ET.parse(xml_path).getroot()
        for el in root.iter('item'):
            t = el.get('type')
            if t and t.startswith('DefineShape'):
                b = el.find('shapeBounds')
                if b is not None:
                    self.shapes[int(el.get('shapeId'))] = rect_of(b)
            elif t in ('DefineMorphShapeTag', 'DefineMorphShape2Tag'):
                b = el.find('morphShapeBounds') or el.find('shapeBounds')
                if b is not None:
                    self.shapes[int(el.get('shapeId'))] = rect_of(b)
            elif t == 'DefineSpriteTag':
                sid = int(el.get('spriteId'))
                frames = [[]]
                sub = el.find('subTags')
                if sub is not None:
                    for ch in sub:
                        if ch.tag != 'item':
                            continue
                        if ch.get('type') == 'ShowFrameTag':
                            frames.append([])
                            continue
                        if ch.get('type') in ('PlaceObject2Tag', 'PlaceObject3Tag'):
                            has_char = ch.get('placeFlagHasCharacter') == 'true' \
                                or bool(ch.get('characterId'))

                            def _flag(k):
                                return ch.get('placeFlagHas' + k) == 'true'

                            frames[-1].append({
                                'depth': int(ch.get('depth')),
                                'name': ch.get('name'),
                                'charId': int(ch.get('characterId') or 0),
                                'matrix': matrix_of(ch.find('matrix')),
                                'has_char': has_char,
                                'has_matrix': _flag('Matrix') or ch.find('matrix') is not None,
                                'has_color': _flag('ColorTransform'),
                                'has_ratio': _flag('Ratio'),
                                'has_name': _flag('Name'),
                                'has_clip': _flag('ClipDepth'),
                                'ratio': ch.get('ratio'),
                                'move': _flag('Move'),
                                'alpha': alpha_of(ch.find('colorTransform')),
                            })
                # keep EVERY frame, including the ones that only show a frame or call
                # stop(): dropping empties shifts every later frame index, and the
                # frame LABELS read from the XML then point at the wrong pose.
                self.records[sid] = frames[:-1] if frames and not frames[-1] else frames
                self.all_sprites[sid] = [(d, n, c, m) for d, n, c, m, _a
                                         in self._live_frame(sid, 0, visible_only=False)]
                self.sprites[sid] = [(d, n, c, m) for d, n, c, m, _a
                                     in self._live_frame(sid, 0)]
                self.frames[sid] = [self._live_frame(sid, i)
                                    for i in range(len(self.records[sid]))]
            elif t == 'SymbolClassTag':
                tags = [int(x.text) for x in el.find('tags')]
                names = [x.text for x in el.find('names')]
                for i, n in enumerate(names):
                    if i < len(tags):
                        self.symbols[n] = tags[i]

    # ── SWF timeline semantics ───────────────────────────────────────────────
    # A sprite's timeline is STATEFUL: a child placed in frame 1 is still there in
    # frame 2, a `PlaceObject2` with only the Move flag REMOVES the depth, and a
    # move with a matrix re-places it.  Reading one frame's records as if they were
    # that frame's contents counts a child the timeline has already removed - which
    # is how sprite 92 (the hand clip, which places the authored weapon and then
    # drops it) got a frame-1 box six times its real size and the hand was drawn
    # off the wrist.
    def _live_frame(self, sid, index, visible_only=True):
        """[(depth, name, charId, matrix, alpha)] visible on one frame, draw order.

        `visible_only=False` keeps the children the timeline has faded out - the
        client still fills those containers at run time (`hand.item` is where an
        item goes), so the rig must see them even though they draw nothing.
        """
        if not hasattr(self, '_state_cache'):
            self._state_cache = {}
        cache = self._state_cache.setdefault(sid, {'at': -1, 'state': {}})
        if cache['at'] > index:
            cache['at'] = -1
            cache['state'] = {}
        state = cache['state']
        recs = self.records.get(sid) or []
        UPD = ('has_matrix', 'has_color', 'has_ratio', 'has_name', 'has_clip')
        for i in range(cache['at'] + 1, index + 1):
            for rec in (recs[i] if i < len(recs) else []):
                d = rec['depth']
                if rec['has_char']:
                    state[d] = {'charId': rec['charId'], 'name': rec['name'],
                                'matrix': rec['matrix'], 'alpha': rec['alpha'],
                                'ratio': rec['ratio']}
                elif rec['move'] and d in state:
                    # a Move that carries ANY field is an edit (a new matrix, a fade,
                    # a frame via ratio, a name, a clip depth); only a Move with none
                    # of them REMOVES the child.  Treating every field-less-looking
                    # move as a removal is what made the walk poses look armless.
                    if not any(rec[k] for k in UPD):
                        del state[d]
                        continue
                    if rec['has_matrix']:
                        state[d]['matrix'] = rec['matrix']
                    if rec['has_color']:
                        state[d]['alpha'] = rec['alpha']
                    if rec['has_ratio']:
                        state[d]['ratio'] = rec['ratio']
                    if rec['has_name']:
                        state[d]['name'] = rec['name']
            cache['at'] = i
        # an alpha of 0 is an invisible child (the weapon in the hand clip at
        # frame 1): it must not contribute to the picture's box
        return [(d, v['name'], v['charId'], v['matrix'], v['alpha'])
                for d, v in sorted(state.items())
                if v['alpha'] > 0.004 or not visible_only]

    def bbox(self, cid, depth=0):
        """Frame-1 bbox of a character, in its own coordinate space (px)."""
        if cid in self.bounds:
            return self.bounds[cid]
        if depth > 12:
            return None
        self.bounds[cid] = None                # cycle guard
        box = None
        if cid in self.shapes:
            x0, y0, x1, y1 = self.shapes[cid]
            box = [x0, y0, x1, y1]
        for rec in (self.frames.get(cid) or [[]])[0]:
            _d, _n, child, m = rec[:4]
            sub = self.bbox(child, depth + 1)
            if not sub:
                continue
            pts = [apply(m, x, y) for x in (sub[0], sub[2]) for y in (sub[1], sub[3])]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if box is None:
                box = [min(xs), min(ys), max(xs), max(ys)]
            else:
                box = [min(box[0], min(xs)), min(box[1], min(ys)),
                       max(box[2], max(xs)), max(box[3], max(ys))]
        self.bounds[cid] = tuple(box) if box else None
        return self.bounds[cid]

    def bbox_union(self, cid, depth=0):
        """Bbox over EVERY frame - the canvas ffdec sizes a sprite's PNGs to."""
        key = ('union', cid)
        if key in self.bounds:
            return self.bounds[key]
        if depth > 12:
            return None
        self.bounds[key] = None
        box = None
        frames = self.frames.get(cid) or ([self.sprites.get(cid) or []] if cid in self.sprites
                                          else [])
        if cid in self.shapes:
            x0, y0, x1, y1 = self.shapes[cid]
            box = [x0, y0, x1, y1]
        else:
            for frame in frames:
                for rec in frame:
                    _d, _n, child, m = rec[:4]
                    sub = self.bbox_union(child, depth + 1)
                    if not sub:
                        continue
                    pts = [apply(m, x, y) for x in (sub[0], sub[2]) for y in (sub[1], sub[3])]
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    if box is None:
                        box = [min(xs), min(ys), max(xs), max(ys)]
                    else:
                        box = [min(box[0], min(xs)), min(box[1], min(ys)),
                               max(box[2], max(xs)), max(box[3], max(ys))]
        self.bounds[key] = tuple(box) if box else None
        return self.bounds[key]

    @staticmethod
    def png_path(base_dir, cid):
        """The exported frame-1 PNG of one character - matched EXACTLY, or
        `DefineSprite_115*` quietly hands back 1150's art."""
        for pat in ('DefineSprite_%d', 'DefineSprite_%d_*'):
            hits = glob.glob(os.path.join(base_dir, pat % cid, '1.png'))
            if hits:
                return hits[0]
        return None

    def find(self, name):
        """charId of a symbol by name, or None."""
        v = self.symbols.get(name)
        if v is not None:
            return v
        for n, cid in self.symbols.items():        # ffdec keeps the raw double-byte name
            if n == name:
                return cid
        return None


class Avatar:
    """Renders a player's 16-part setting to a PNG."""

    def __init__(self, ca_xml, items_xml, ca_png_dir, items_png_dir, parts_dir):
        self.ca = SwfModel(ca_xml)
        self.items = SwfModel(items_xml)
        self.ca_png = ca_png_dir
        self.items_png = items_png_dir
        self.out_dir = parts_dir

    # ── the rig: every placement in sprite 458's frame 1, resolved ──
    SKIP = ('shadow', 'hitAreas', 'attackarea', 'att', 'waterMask1', 'waterMask2',
            'waterMask3', 'waterMask4', 'waterMask5', 'waterMask6', 'waterMask7',
            'waterMask8', 'hookPoint', 'fishPoint', 'snow', 'peal', 'hitAreaClip')
    # clips that hold a slot somewhere below them, so the walk must go inside;
    # every other named clip (face, back_shoes) is art and is drawn whole
    DESCEND = ('head', 'head_back', 'body', 'left_arm', 'right_arm', 'left_leg',
               'right_leg', 'hand')

    def rig(self):
        """[(path, matrix, charId, kind)] - kind is 'slot' or 'base'.

        A named clip is a slot container (`head.eyes`), a structural clip to
        descend into (`hand`), or a piece of authored art (`face`) - and the walk
        must not gap at a clip whose parts are shapes: sprite 116's face art is a
        shape inside it, so descending would draw nothing at all.  Where a clip's
        own child has no exportable art (the hand is a bare shape), the CLIP's
        frame-1 image is used instead - its frame 1 is just the hand, while the
        authored weapon in that clip is not visible on it.
        """
        out = []

        def walk(sid, prefix, m, depth=0, clip=None, stack=()):
            for _d, name, cid, mm in sorted(self.ca.all_sprites.get(sid, []),
                                            key=lambda r: r[0]):
                if name in self.SKIP:
                    continue
                acc = mul(m, mm)
                path = ("%s.%s" % (prefix, name)) if prefix else (name or prefix)
                if path in CONTAINER_SLOTS:
                    out.append((path, acc, cid, 'slot'))
                    continue
                # both arms are the SAME clip: a visited-set would drop the second
                # one (and with it that arm's item slot), so only a clip that is
                # already open on this branch is treated as a cycle
                if name in self.DESCEND and cid in self.ca.sprites and depth < 8 \
                        and cid not in stack:
                    walk(cid, path, acc, depth + 1, clip=cid, stack=stack + (cid,))
                    continue
                if not self._png_for('ca', cid) and clip and self._png_for('ca', clip):
                    out.append((path, acc, clip, 'base'))
                    continue
                out.append((path, acc, cid, 'base'))

        walk(458, "", (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))
        return out

    def _png_for(self, where, cid):
        """The exported frame-1 PNG of one character, matched exactly."""
        base = self.ca_png if where == 'ca' else self.items_png
        return SwfModel.png_path(base, cid)

    def draw_list(self, parts):
        """[(png, matrix, xmin, ymin)] - what to paste, where, in draw order."""
        out = []
        for path, acc, cid, kind in self.rig():
            if kind == 'base':
                png = self._png_for('ca', cid)
                box = self.ca.bbox_union(cid)
                if png and box:
                    out.append((png, acc, box[0], box[1]))
                continue
            slot = next(s for s, pairs in SLOT_CONTAINERS.items()
                        if any(c == path for c, _ in pairs))
            value = (parts.get(slot) or "").strip()
            if not value or value.startswith("_"):
                continue                       # the client draws nothing for an empty slot
            tmpl = next(t for c, t in SLOT_CONTAINERS[slot] if c == path)
            sprite_name = "配件_" + (tmpl % value)
            scid = self.items.find(sprite_name)
            box = self.items.bbox_union(scid) if scid else None
            png = self._png_for('items', scid) if scid else None
            if not (png and box):
                continue
            out.append((png, acc, box[0], box[1]))
        return out

    def compose(self, parts, scale=1.0, pad=4):
        items = self.draw_list(parts)
        if not items:
            return None
        # where every image lands, so the canvas can be sized to it
        boxes = []
        for png, m, x0, y0 in items:
            im = Image.open(png)
            w, h = im.size
            pts = [apply(m, x0, y0), apply(m, x0 + w, y0),
                   apply(m, x0, y0 + h), apply(m, x0 + w, y0 + h)]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
        cx0 = min(b[0] for b in boxes) - pad
        cy0 = min(b[1] for b in boxes) - pad
        cx1 = max(b[2] for b in boxes) + pad
        cy1 = max(b[3] for b in boxes) + pad
        W = max(1, int(round((cx1 - cx0) * scale)))
        H = max(1, int(round((cy1 - cy0) * scale)))
        canvas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        for png, m, x0, y0 in items:
            im = Image.open(png).convert('RGBA')
            shift = (cx0, cy0)
            m2 = mul((scale, 0.0, 0.0, scale, -shift[0] * scale, -shift[1] * scale), m)
            im_inv = inv(m2)
            affine = (im_inv[0], im_inv[1], im_inv[4] - x0,
                      im_inv[2], im_inv[3], im_inv[5] - y0)
            warped = im.transform((W, H), Image.AFFINE, affine,
                                  resample=Image.BICUBIC)
            canvas.alpha_composite(warped)
        return canvas
