"""Minimal AMF0 codec: enough to decode/edit/re-encode LPO's serviceRequest bodies.

Supports NUMBER, BOOLEAN, STRING, LONG_STRING, OBJECT, ECMA_ARRAY, STRICT_ARRAY,
NULL, UNDEFINED, DATE.  Decoding returns plain Python values; encoding rebuilds
bytes.  Object key order is preserved (dicts keep insertion order).
"""
import struct

T_NUMBER = 0x00
T_BOOLEAN = 0x01
T_STRING = 0x02
T_OBJECT = 0x03
T_NULL = 0x05
T_UNDEFINED = 0x06
T_REFERENCE = 0x07
T_ECMA_ARRAY = 0x08
T_OBJECT_END = 0x09
T_STRICT_ARRAY = 0x0A
T_DATE = 0x0B
T_LONG_STRING = 0x0C
T_TYPED_OBJECT = 0x10
T_AMF3 = 0x11


QUIET = False          # set while probing offsets, so a failed decode stays silent


class AmfObject(dict):
    """Marker type so an OBJECT survives a decode/encode round trip."""


class AmfEcmaArray(dict):
    """ECMA (associative) array."""


def decode_one(buf, pos=0):
    t = buf[pos]
    pos += 1
    if t == T_NUMBER:
        v = struct.unpack("!d", buf[pos:pos + 8])[0]
        return v, pos + 8
    if t == T_BOOLEAN:
        return bool(buf[pos]), pos + 1
    if t == T_STRING:
        ln = struct.unpack("!H", buf[pos:pos + 2])[0]
        return buf[pos + 2:pos + 2 + ln].decode("utf-8", "replace"), pos + 2 + ln
    if t == T_LONG_STRING:
        ln = struct.unpack("!I", buf[pos:pos + 4])[0]
        return buf[pos + 4:pos + 4 + ln].decode("utf-8", "replace"), pos + 4 + ln
    if t == T_OBJECT:
        obj = AmfObject()
        pos = _read_props(buf, pos, obj, end_marker=True)
        return obj, pos
    if t == T_ECMA_ARRAY:
        n = struct.unpack("!I", buf[pos:pos + 4])[0]
        arr = AmfEcmaArray()
        pos = _read_props(buf, pos + 4, arr, end_marker=True)
        return arr, pos
    if t == T_STRICT_ARRAY:
        n = struct.unpack("!I", buf[pos:pos + 4])[0]
        pos += 4
        out = []
        for _ in range(n):
            v, pos = decode_one(buf, pos)
            out.append(v)
        return out, pos
    if t == T_TYPED_OBJECT:
        # Flash Player marks an object with the class it came from (class name,
        # then the same key/value pairs as OBJECT).  Ruffle sends a plain OBJECT for
        # the same call, so a body captured under Ruffle decoded fine while the real
        # Flash client's body raised here and every login from the publisher's
        # browser was unreadable.
        ln = struct.unpack("!H", buf[pos:pos + 2])[0]
        obj = AmfObject()
        obj._class = buf[pos + 2:pos + 2 + ln].decode("utf-8", "replace")
        pos += 2 + ln
        pos = _read_props(buf, pos, obj, end_marker=True)
        return obj, pos
    if t == T_REFERENCE:
        # A pointer to an object already in this packet.  The fields we dispatch on
        # are read from the object's own copy, so a marker is enough to keep walking.
        idx = struct.unpack("!H", buf[pos:pos + 2])[0]
        return AmfReference(idx), pos + 2
    if t == T_NULL:
        return None, pos
    if t == T_UNDEFINED:
        return AmfUndefined(), pos
    if t == T_DATE:
        ms = struct.unpack("!d", buf[pos:pos + 8])[0]
        tz = struct.unpack("!h", buf[pos + 8:pos + 10])[0]
        return AmfDate(ms, tz), pos + 10
    if t == T_AMF3:
        raise ValueError("AMF3 payloads are not supported by this codec")
    raise ValueError(f"unsupported AMF0 marker 0x{t:02x} at {pos - 1}")


class AmfReference:
    def __init__(self, index):
        self.index = index

    def __repr__(self):
        return f"AmfReference({self.index})"


class AmfUndefined:
    def __repr__(self):
        return "undefined"

    def __eq__(self, o):
        return isinstance(o, AmfUndefined)


class AmfDate:
    def __init__(self, ms, tz):
        self.ms, self.tz = ms, tz

    def __repr__(self):
        return f"AmfDate({self.ms}, {self.tz})"


def _read_props(buf, pos, sink, end_marker=True):
    while True:
        ln = struct.unpack("!H", buf[pos:pos + 2])[0]
        pos += 2
        if ln == 0:
            if buf[pos] == T_OBJECT_END:
                return pos + 1
            if not end_marker:
                return pos
            raise ValueError(f"malformed object at {pos}")
        key = buf[pos:pos + ln].decode("utf-8", "replace")
        pos += ln
        v, pos = decode_one(buf, pos)
        sink[key] = v


def decode(buf):
    """Decode a whole buffer (list of values)."""
    out = []
    pos = 0
    buf = bytes(buf)
    while pos < len(buf):
        v, pos = decode_one(buf, pos)
        out.append(v)
    return out


def encode_value(v):
    if v is None:
        return bytes([T_NULL])
    if isinstance(v, AmfUndefined):
        return bytes([T_UNDEFINED])
    if isinstance(v, AmfDate):
        return bytes([T_DATE]) + struct.pack("!d", v.ms) + struct.pack("!h", v.tz)
    if isinstance(v, bool):
        return bytes([T_BOOLEAN, 1 if v else 0])
    if isinstance(v, (int, float)):
        return bytes([T_NUMBER]) + struct.pack("!d", float(v))
    if isinstance(v, str):
        b = v.encode("utf-8")
        if len(b) > 0xFFFF:
            return bytes([T_LONG_STRING]) + struct.pack("!I", len(b)) + b
        return bytes([T_STRING]) + struct.pack("!H", len(b)) + b
    if isinstance(v, AmfEcmaArray):
        out = bytes([T_ECMA_ARRAY]) + struct.pack("!I", len(v))
        for k, val in v.items():
            kb = k.encode("utf-8")
            out += struct.pack("!H", len(kb)) + kb + encode_value(val)
        return out + b"\x00\x00" + bytes([T_OBJECT_END])
    if isinstance(v, AmfObject):
        out = bytes([T_OBJECT])
        for k, val in v.items():
            kb = k.encode("utf-8")
            out += struct.pack("!H", len(kb)) + kb + encode_value(val)
        return out + b"\x00\x00" + bytes([T_OBJECT_END])
    if isinstance(v, (list, tuple)):
        out = bytes([T_STRICT_ARRAY]) + struct.pack("!I", len(v))
        for x in v:
            out += encode_value(x)
        return out
    if isinstance(v, dict):              # plain dict -> object
        return encode_value(AmfObject(v))
    raise TypeError(f"cannot encode {type(v)}")


def encode(values):
    out = b""
    for v in values:
        out += encode_value(v)
    return out
