#!/usr/bin/env python3
"""Draw a player's own LPO character - the picture the games' interface movie makes.

The client never stores a character image: `interface.swf` builds `PrinceOnline.Character`
at run time from a 16-slot cloth setting, and each part is a sprite in
`lib/lib_items.swf` placed at its container's matrix inside `lib/character_anim.swf`.
`avatar/rig.json` is that rig, read out of the game's own files once (see
`tools/build_avatar_data.py` in the handoff folder), so this module only has to
paste PNGs where the game pastes clips:

    base art   (head, body, arms, legs, hands)  -> always drawn
    slot parts (hair, eyes, cloth, shoes, ...)  -> the account's part, or nothing

A part the account has no value for draws nothing, exactly as the client's
`addItem(container, "")` removes the authored child; a part NAME the game does not
have falls back to the outfit the client itself falls back to (Character.addItem's
catch branch), so an unknown value can never leave a hole in the picture.

The render is cached as `web/avatars/<sha1 of the parts>.png`: the URL changes
with the look, so the browser may cache it for ever and no invalidation is needed.

Pillow is the one thing this module needs that the pack does not carry, and the
import stays inside the functions below - never at the top of the file - so a
machine without it still runs the whole server, every page and every other
feature: `available()` answers no and `why_not()` names the exact command that
fixes it (`python3 -m pip install --user Pillow`), which is what the page and the
launcher print.  A missing Pillow is also never remembered for ever: the macOS
launcher can install it while this server keeps running, so the look is repeated
and the picture comes back without a restart.
"""
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

PARTS = ("hat", "hair", "ears", "blusher", "mouth", "eyes", "eyeblows", "nose",
         "left_acc", "right_acc", "left_item", "right_item", "cloth", "trousers",
         "shoes", "tail")

# Character.addItem's own fallback list, plus the real default the publisher's
# login4 sends for a fresh account (hat/items/accessories/tail: nothing).
FALLBACK = {"hair": "髮3", "ears": "耳1", "blusher": "面珠1", "mouth": "口1",
            "eyes": "眼1", "eyeblows": "眉1", "nose": "鼻1", "cloth": "運動服",
            "trousers": "運動褲", "shoes": "運動鞋"}

DATA = Path(__file__).parent / "avatar"
OUT = Path(__file__).parent / "web" / "avatars"
KEEP = 40                                   # how many rendered looks to keep on disk

# The one dependency, and the exact way to install it.  The wording matters: the
# page used to say only "Pillow is not installed", which tells the reader what is
# wrong and not what to type, and the failure is silent everywhere else.
PILLOW_HINT = "python3 -m pip install --user Pillow"

_lock = threading.Lock()
_rig = None
_rig_tried = False
_rig_at = 0.0                 # when the dataset was last looked at
_pillow_missing = False       # ... and that look failed only for want of Pillow
_last_error = ""
RETRY_AFTER = 5.0             # a missing Pillow is looked for again this often


def install_command() -> str:
    """The exact command that installs Pillow for the python running here.

    `sys.executable` is the interpreter this server was started with, so the
    command fits the machine printing it: the python.org build on macOS (where
    --user needs no administrator), a python.org install on Windows, or a
    virtualenv - which refuses --user and does not need it.  PILLOW_HINT is the
    plain form for a page, which cannot know the interpreter.
    """
    exe = sys.executable or "python3"
    cmd = "%s -m pip install" % exe
    in_venv = bool(os.environ.get("VIRTUAL_ENV")) or \
        sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    return cmd + (" Pillow" if (os.name == "nt" or in_venv) else " --user Pillow")


def _pil_image():
    """PIL's Image module, or None - recording the reason when it is not there.

    Pillow is what does the pasting (translate/affine/alpha_composite), so this
    is the only import in the file that can fail on a machine the pack does not
    control.  It never raises: the caller has a documented answer for "no".
    """
    global _last_error, _pillow_missing
    try:
        from PIL import Image
    except Exception as e:                      # Pillow is what does the pasting
        _pillow_missing = True
        _last_error = ("Pillow is not installed (%s) - install it for the python "
                       "that runs this server: %s" % (e, PILLOW_HINT))
        return None
    _pillow_missing = False
    return Image


def _load_rig():
    """rig.json + the two PNG folders, or None when it cannot be drawn here.

    A missing Pillow is not remembered for ever: the launcher can install it
    while this server keeps running, so the look is repeated (at most every
    RETRY_AFTER seconds - one failed import, not a filesystem walk) and the page
    draws the character again on its next reload.  A missing or unreadable
    dataset is remembered: that one cannot fix itself.
    """
    global _rig, _rig_tried, _rig_at, _last_error
    with _lock:
        if _rig is not None:
            return _rig
        now = time.time()
        if _rig_tried and not _pillow_missing:
            return None                         # the dataset is what is missing
        if _rig_tried and now - _rig_at < RETRY_AFTER:
            return None                         # looked a moment ago
        _rig_tried, _rig_at = True, now
        if _pil_image() is None:
            return None
        path = DATA / "rig.json"
        if not path.exists():
            _last_error = "avatar dataset missing at %s" % DATA
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                _rig = json.load(fh)
        except Exception as e:
            _last_error = "avatar dataset unreadable (%s)" % e
            _rig = None
        return _rig


def available():
    """True when a real character can be drawn here."""
    return _load_rig() is not None


def why_not():
    """Why `available()` is False - naming the fix, not just the symptom."""
    return _last_error


def normalise(parts: dict) -> dict:
    """The 16 slots as the game would read them: value, fallback, or nothing."""
    out = {}
    for slot in PARTS:
        val = (parts or {}).get(slot)
        val = "" if val is None else str(val).strip()
        if val.startswith("_"):                    # hand-held game objects, not part art
            val = ""
        out[slot] = val
    return out


def _clip(rig, value, slot, template="%s"):
    """The part index entry for one slot value, falling back like the client does.

    The template matters: the hair slot draws `前<value>` AND `後<value>`, and the
    cloth slot's arms wear `<value>袖` - so the name looked up is not the value.
    """
    if not value:
        return None
    names = [template % value]
    if template != "%s":
        names.append(value)                    # tolerate a value that already carries it
    fb = FALLBACK.get(slot)
    if fb and fb != value:
        names.append(template % fb)
    for name in names:
        entry = rig["parts"].get(name)
        if entry:
            return entry
    return None


def _mul(m1, m2):
    a1, b1, c1, d1, tx1, ty1 = m1
    a2, b2, c2, d2, tx2, ty2 = m2
    return (a1 * a2 + b1 * c2, a1 * b2 + b1 * d2,
            c1 * a2 + d1 * c2, c1 * b2 + d1 * d2,
            a1 * tx2 + b1 * ty2 + tx1, c1 * tx2 + d1 * ty2 + ty1)


def _inv(m):
    a, b, c, d, tx, ty = m
    det = a * d - b * c
    if abs(det) < 1e-12:
        det = 1e-12
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return (ia, ib, ic, id_, -(ia * tx + ib * ty), -(ic * tx + id_ * ty))


def _apply(m, x, y):
    a, b, c, d, tx, ty = m
    return (a * x + b * y + tx, c * x + d * y + ty)


def render(parts: dict, scale: float = 2.0, pad: int = 2, view: str = "full"):
    """A PIL image of the character, or None when it cannot be drawn here."""
    rig = _load_rig()
    if not rig:
        return None
    Image = _pil_image()
    if Image is None:
        return None
    with _lock:
        # Draw order is the SWF's own: sprite 458's frame 1 places the clips by
        # depth, and the walk kept that order - so base art and slot parts are
        # interleaved exactly as the client interleaves them (the shoe's `back`
        # piece belongs behind the leg, the trouser over the leg but under the
        # shoe).  Sorting "base first, then parts" puts a hat under the hair and
        # the shoe's heel on top of the foot.
        items = []
        head_items = []          # everything drawn for the head: the crop anchors on these
        for base in rig["base"]:
            items.append((base.get("order", 0), DATA / base["png"], base["matrix"],
                          base["x"], base["y"]))
            if "head" in str(base.get("path") or "").split(".")[0]:
                head_items.append((DATA / base["png"], base["matrix"], base["x"], base["y"]))
        vals = normalise(parts)
        for slot_def in rig["slots"]:
            entry = _clip(rig, vals.get(slot_def["slot"]), slot_def["slot"],
                          slot_def.get("template", "%s"))
            if entry:
                items.append((slot_def.get("order", 0), DATA / entry["png"],
                              slot_def["matrix"], entry["x"], entry["y"]))
                if "head" in str(slot_def.get("path") or "").split(".")[0]:
                    head_items.append((DATA / entry["png"], slot_def["matrix"],
                                       entry["x"], entry["y"]))
        # the shoe's `back` piece: the client moves it into the clip behind the leg
        # (`clothInit`: back_shoes <- shoes.getChildAt(0).back), and a shoe without
        # one leaves that clip empty - it must never fall back to the authored boot.
        for back in (rig.get("back") or []):
            entry = _clip(rig, vals.get(back["slot"]), back["slot"],
                          back.get("template", "%s"))
            art = (entry or {}).get("back")
            if art:
                items.append((back.get("order", 0), DATA / art["png"],
                              _mul(back["matrix"], art["matrix"]),
                              art["x"], art["y"]))
        items.sort(key=lambda it: it[0])
        items = [(p, m, x, y) for _o, p, m, x, y in items]
        if not items:
            return None
        boxes = []
        for path, m, x, y in items:
            try:
                with Image.open(path) as im:
                    w, h = im.size
            except Exception:
                continue
            pts = [_apply(m, x, y), _apply(m, x + w, y),
                   _apply(m, x, y + h), _apply(m, x + w, y + h)]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
        if not boxes:
            return None
        x0 = min(b[0] for b in boxes) - pad
        y0 = min(b[1] for b in boxes) - pad
        x1 = max(b[2] for b in boxes) + pad
        y1 = max(b[3] for b in boxes) + pad
        W = max(1, int(round((x1 - x0) * scale)))
        H = max(1, int(round((y1 - y0) * scale)))
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for path, m, x, y in items:
            try:
                im = Image.open(path).convert("RGBA")
            except Exception:
                continue
            placed = _mul((scale, 0.0, 0.0, scale, -x0 * scale, -y0 * scale), m)
            back = _inv(placed)
            affine = (back[0], back[1], back[4] - x, back[2], back[3], back[5] - y)
            warped = im.transform((W, H), Image.AFFINE, affine,
                                  resample=Image.BICUBIC)
            canvas.alpha_composite(warped)
        if view == "head" and head_items:
            px = _head_box_px(head_items, x0, y0, scale, canvas.size)
            img = canvas.crop(px)
            b2 = img.getbbox()
            return img.crop(b2) if b2 else img
        box = canvas.getbbox()
        img = canvas.crop(box) if box else canvas
        return _head_crop(img, scale) if view == "head" else img


# A head crop anchored on the rig's own head geometry beats a fixed fraction of the
# render: a tall hat (the little prince's crown) makes the drawn figure taller, and
# "the top 46%" then starts above the hat and cuts the face off.  The head is also
# not centred on the drawn bounds - the side tuft pushes it right - so the crop is
# taken around the head's own box, not the picture's middle.
HEAD_MARGIN = 3.0              # character units of air around the head
HEAD_FRACTION = 0.46           # fallback only, when no head geometry is available
HEAD_CENTRE_OFFSET = 5.35      # fallback only, character units right of centre


def _head_box_px(head_items, x0: float, y0: float, scale: float, canvas_size):
    """The head's own box, in canvas pixels.  Units map as (p - x0) * scale."""
    Image = _pil_image()
    if Image is None:
        return None
    boxes = []
    for path, m, x, y in head_items:
        try:
            with Image.open(path) as im:
                w, h = im.size
        except Exception:
            continue
        pts = [_apply(m, x, y), _apply(m, x + w, y),
               _apply(m, x, y + h), _apply(m, x + w, y + h)]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        boxes.append((min(xs), min(ys), max(xs), max(ys)))
    if not boxes:
        return None
    ux0 = min(b[0] for b in boxes) - HEAD_MARGIN
    uy0 = min(b[1] for b in boxes) - HEAD_MARGIN
    ux1 = max(b[2] for b in boxes) + HEAD_MARGIN
    uy1 = max(b[3] for b in boxes) + HEAD_MARGIN
    W, H = canvas_size
    left = max(0, int(round((ux0 - x0) * scale)))
    top = max(0, int(round((uy0 - y0) * scale)))
    right = min(W, int(round((ux1 - x0) * scale)))
    bottom = min(H, int(round((uy1 - y0) * scale)))
    if right - left < 4 or bottom - top < 4:
        return None
    return (left, top, right, bottom)


def _head_crop(img, scale: float):
    """Fallback head crop: the top slice of the render, for when the rig is silent."""
    side = int(round(img.height * HEAD_FRACTION))
    side = max(1, min(side, img.width))
    cx = img.width / 2.0 + HEAD_CENTRE_OFFSET * scale
    left = max(0, min(int(round(cx - side / 2.0)), img.width - side))
    top = max(0, min(int(round(img.height * 0.015)), img.height - side))
    return img.crop((left, top, left + side, top + side))


def key_for(parts: dict, view: str = "full") -> str:
    """A stable name for one look - the cache key and the URL.

    The dataset's own stamp is part of it: the rig can be rebuilt (the hand clip's
    placement was wrong once), and a look already rendered from the old data must
    not keep being served.  The view is only mixed in when it is not the plain
    full-body one, so the existing full-body URLs stay valid.
    """
    vals = normalise(parts)
    blob = json.dumps([vals.get(s) for s in PARTS], ensure_ascii=False)
    try:
        st = (DATA / "rig.json").stat()
        stamp = "%x%x" % (int(st.st_mtime), st.st_size)
    except Exception:
        stamp = "0"
    if view and view != "full":
        blob += "|" + view
    return hashlib.sha1((stamp + "|" + blob).encode("utf-8")).hexdigest()[:16]


HEAD_SCALE = 4.0     # a head crop is shown large, so render it large and crop hard


def ensure(parts: dict, view: str = "full"):
    """(url, path) for this look's PNG, rendering it once. (None, None) if it cannot."""
    rig = _load_rig()
    if not rig:
        return None, None
    head = view == "head"
    name = key_for(parts, view) + ("-head.png" if head else ".png")
    path = OUT / name
    if not path.exists():
        img = render(parts, scale=HEAD_SCALE if head else 2.0, view=view)
        if img is None:
            return None, None
        OUT.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        img.save(tmp, "PNG", optimize=True)
        os.replace(tmp, path)
        _prune()
    return "/web/avatars/" + name, path


def _prune():
    """Keep the avatars folder small: the newest KEEP renders survive."""
    try:
        files = sorted(OUT.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[KEEP:]:
            old.unlink()
    except Exception:
        pass
