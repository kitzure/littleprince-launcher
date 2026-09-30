#!/usr/bin/env python3
"""Make a displayable SWF from an image, for the game's notice panel.

Why a SWF: the panel does `Bridge.res.load([url])` then `notice.news.addChild(...)`, so the URL
must yield a display object - and the user reports the official board shows its info via a SWF.

What it writes: an uncompressed (FWS) SWF with
  SetBackgroundColor, DefineBitsJPEG2 (the image bytes verbatim), DefineShape (a rectangle
  filled with that bitmap), PlaceObject2, ShowFrame, End.
The shape record is the fiddly part, so ffdec validates the result before this is ever served.
"""
import pathlib
import struct
import subprocess
import sys


def tag(code: int, body: bytes) -> bytes:
    if len(body) + 2 > 62:                      # long form
        return struct.pack("<HI", (code << 6) | 0x3F, len(body) + 2) + body
    return struct.pack("<H", (code << 6) | (len(body) + 2)) + body


def rect(x, y, w, h) -> bytes:
    """SWF RECT: 5-bit fields, then the coordinate bytes."""
    bits = ""
    for v in (x, y):
        bits += "1" + format(v & 0xFFFF, "016b") if v else "1" + "0" * 16
    parts = []
    for v in (x, y):
        s = format(v, "016b") if v >= 0 else format(v & 0xFFFF, "016b")
        parts.append("1" + s)
    for v in (w, h):
        parts.append("0" + format(v // 20, "015b"))
    b = "".join(parts)
    nbits = len(b) // 5 if False else 5
    out = format(nbits, "05b") + b
    while len(out) % 8:
        out += "0"
    return bytes(int(out[i:i + 8], 2) for i in range(0, len(out), 8))


def image_to_swf(image: pathlib.Path, out: pathlib.Path, width: int, height: int) -> pathlib.Path:
    img = image.read_bytes()
    body = b""
    body += tag(9, b"\xcc\xcc\xcc")                                  # SetBackgroundColor
    body += tag(21, struct.pack("<H", 1) + img)                       # DefineBitsJPEG2, id=1
    # DefineShape: id=2, bounds, one rect fill with the bitmap, one straight edge set
    shape = struct.pack("<H", 2) + rect(0, 0, width, height)
    shape += b"\x00"                                                  # no fill styles yet...
    # fill style: bitmap (type 0x41), bitmapId=1, 3x3 matrix = identity-ish
    matrix = b"\x00"                                                  # identity matrix (scale 1)
    fills = b"\x01" + b"\x41" + b"\x01\x00" + matrix                 # count, type, id, matrix
    lines = b"\x00"
    shape = struct.pack("<H", 2) + rect(0, 0, width, height) + fills + lines
    # shape record: 1 change record, numbits=6, then 5 fill/line bits + a straight edge
    bits = "1" + "00110" + "1" * 6 + "1" + "1" + "1" + "1"
    bits += "1" + "0" * 17 + "1" + "0" * 17                          # move to (0,0)
    bits += "1" + "0" * 17 + "1" + "0" * 17                          # edge to (w,0)
    bits += "1" + "0" * 17 + "1" + "0" * 17                          # edge to (w,h)
    bits += "1" + "0" * 17 + "1" + "0" * 17                          # edge back
    bits += "0"                                                      # end of shape
    while len(bits) % 8:
        bits += "0"
    shape += bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))
    body += tag(2, shape)                                             # DefineShape
    body += tag(26, b"\x01" + struct.pack("<H", 2) + b"\x01\x00")     # PlaceObject2
    body += tag(1, b"")                                               # ShowFrame
    body += tag(0, b"")                                               # End
    stage = rect(0, 0, width * 20, height * 20)
    data = b"FWS" + b"\x0a" + struct.pack("<I", 0) + stage + b"\x00\x00" + body
    data = data[:4] + struct.pack("<I", len(data)) + data[8:]
    out.write_bytes(data)
    return out


if __name__ == "__main__":
    src = pathlib.Path(sys.argv[1])
    dst = pathlib.Path(sys.argv[2])
    w, h = int(sys.argv[3]), int(sys.argv[4])
    image_to_swf(src, dst, w, h)
    print("wrote %s (%d bytes)" % (dst, dst.stat().st_size))
    # validate: ffdec must be able to read it back
    r = subprocess.run(["java", "-jar", "/home/yoke/lpo_build/ffdec/ffdec-cli.jar",
                        "-onerror", "error", "-export", "image", "/tmp/swf_check", str(dst)],
                       capture_output=True, text=True)
    print("ffdec rc:", r.returncode)
    err = [l for l in (r.stdout + r.stderr).splitlines() if "rror" in l or "xception" in l]
    print("ffdec said:", err[:4] if err else "no errors")
    print("images extracted:", [p.name for p in pathlib.Path("/tmp/swf_check").rglob("*")][:6])
