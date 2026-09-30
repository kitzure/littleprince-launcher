#!/usr/bin/env python3
"""Render the pack's blank notice card, lpo/notice_blank.png (694x510).

server.py serves this for a notice that has no uploaded artwork.  It is generated HERE,
at build time, because the player's machine must not need an imaging library or a font -
the pack ships the finished PNG and server.py just reads the bytes.

The size is the notice panel's real content area, read out of the publisher's notice.swf:
inside the detail overlay (sprite 41) the empty container `news` sits at (7.1, -14.4), and
the overlay itself is placed at (35.2, 94.5) inside the `Notice` panel, so the card is
addChild()ed at panel coordinates (42.3, 80.1).  The publisher's own scrollbar config for
that container is t_view = 510 and the scrollbar rail begins at panel x 737, so the
viewport the card has to fill is 694.7 x 510.  Drawing at 520x360 (the old size) left the
cream border the user saw around the card.

The layout mirrors the admin page's own canvas (lpo/web.html, bbDraw) and the hand-drawn
last-resort card (server.py, _plain_card_png): cream card, hairline border, a title band,
and the body centred in the column - a deliberate card rather than a white rectangle.

Run:  python3 tools/make_notice_blank.py
"""
import pathlib

from PIL import Image, ImageDraw, ImageFont

PKG = pathlib.Path.home() / "Downloads" / "littleprince-launcher"
OUT = PKG / "lpo" / "notice_blank.png"

W, H = 694, 510
BG = (252, 248, 236)
LINE = (206, 196, 170)
BAND = (244, 236, 214)
RULE = (217, 200, 145)
INKD = (107, 84, 35)
BODY = (58, 47, 28)
MUTED = (176, 161, 124)

FONT_CANDIDATES = [
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Medium.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if pathlib.Path(path).is_file():
            try:
                return ImageFont.truetype(path, size,
                                          index=2 if bold else 0)   # 2 = the TC face
            except Exception:                                         # noqa: BLE001
                return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def main() -> int:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    EDGE, HEAD, PAD = 4, 72, 44
    d.rectangle([0, 0, W - 1, H - 1], outline=LINE, width=EDGE)
    d.rectangle([EDGE, EDGE, W - 1 - EDGE, EDGE + HEAD], fill=BAND)
    d.rectangle([EDGE, EDGE + HEAD, W - 1 - EDGE, EDGE + HEAD + 2], fill=RULE)

    d.text((PAD, EDGE + HEAD / 2), "公告", font=load_font(28, True), fill=INKD,
           anchor="lm")

    content_top = EDGE + HEAD + 2 + 24
    content_bottom = H - 40
    d.text((W / 2, content_top + (content_bottom - content_top) / 2), "暫無內容",
           font=load_font(23), fill=MUTED, anchor="mm")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    print("wrote %s (%d bytes, %dx%d)" % (OUT, OUT.stat().st_size, W, H))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
