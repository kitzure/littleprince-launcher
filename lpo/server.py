#!/usr/bin/env python3
"""
Little Prince Online - Local Server
Serves game files and handles all AMF0 gateway requests with realistic fake responses.

Usage: python3 server.py
  - Serves game files from ~/littleprince-online/ on port 8080
  - Handles AMF gateway at /littleprince/amfservice/gateway.php
"""

import base64
import http.server
import secrets
import socketserver
import struct
import threading
import time
import json
import os
import re
import sys
import zlib
import logging
import traceback
from pathlib import Path
from urllib.parse import unquote, parse_qs

import subprocess
import amf0      # local module: minimal AMF0 codec (amf0.py)
import accounts  # local module: player accounts (accounts.json)
import avatar    # local module: draws the player's character
from pack_download import DOWNLOAD_METHODS, clean_download_settings, open_pack, validate_pack_url

# ─── Configuration ───────────────────────────────────────────────────────────

def _on_windows() -> bool:
    return os.name == "nt"


def _has_swfs(p) -> bool:
    try:
        return Path(p).is_dir() and next(Path(p).glob("*.swf"), None) is not None
    except Exception:
        return False


def _regval(key, name):
    import winreg
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return ""


def _shortcut_target(lnk: str):
    """Resolve a Windows .lnk to its target (PowerShell, a couple of seconds)."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(New-Object -ComObject WScript.Shell).CreateShortcut('%s').TargetPath" % lnk],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=20).stdout.strip()
        return out if out and os.path.exists(out) else ""
    except Exception:
        return ""


def _windows_game_dirs():
    """Places Windows keeps an installed Little Prince Online.

    Registry uninstall entries first (the installer records the folder there),
    then shortcuts, then prince-named folders in the usual install roots.
    """
    import glob
    if not _on_windows():
        return
    import winreg
    for root, sub in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                      (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")):
        try:
            with winreg.OpenKey(root, sub) as k:
                for i in range(winreg.QueryInfoKey(k)[0]):
                    try:
                        with winreg.OpenKey(k, winreg.EnumKey(k, i)) as sk:
                            disp = str(_regval(sk, "DisplayName"))
                            if "prince" not in disp.lower():
                                continue
                            loc = str(_regval(sk, "InstallLocation") or "")
                            if loc:
                                yield from _with_swfs(loc)
                    except OSError:
                        continue
        except OSError:
            continue

    home = os.environ.get("USERPROFILE", "")
    for base in (os.path.join(home, "Desktop"),
                 os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
                 os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop")):
        if not base or not os.path.isdir(base):
            continue
        try:
            for lnk in glob.glob(os.path.join(base, "**", "*.lnk"), recursive=True):
                if "prince" in os.path.basename(lnk).lower():
                    tgt = _shortcut_target(lnk)
                    if tgt:
                        yield from _with_swfs(os.path.dirname(tgt))
        except Exception:
            pass

    roots = [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
             os.environ.get("LOCALAPPDATA"), os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
             os.environ.get("APPDATA"), home,
             os.path.join(home, "Downloads"), os.path.join(home, "Desktop"),
             os.path.join(home, "Documents"), "C:\\Games", "D:\\", "E:\\"]
    for r in roots:
        if not r or not os.path.isdir(r):
            continue
        try:
            for d in glob.glob(os.path.join(r, "*")):
                if os.path.isdir(d) and "prince" in os.path.basename(d).lower():
                    yield from _with_swfs(d)
            for d in glob.glob(os.path.join(r, "*", "*")):
                if os.path.isdir(d) and "prince" in os.path.basename(d).lower():
                    yield from _with_swfs(d)
        except Exception:
            pass


def _with_swfs(root):
    """The folder itself, or the one obvious subfolder, if it holds the client."""
    root = Path(root)
    if _has_swfs(root):
        yield root
        return
    try:
        for sub in sorted(root.iterdir()):
            if _has_swfs(sub):
                yield sub
    except Exception:
        pass


GAME_DIR_TXT = Path(__file__).parent / "game_dir.txt"   # remembered client folder


def _resolve_game_dir() -> Path:
    """Where the Little Prince Online client files live.

    Order: $LPO_GAME_DIR, <package>/lpo/game, whatever game_dir.txt says, the
    client found on this machine (registry, shortcuts, usual install folders),
    then ~/littleprince-online.  Falls back to this folder.

    The branch it took is kept in GAME_DIR_SOURCE so the accounts page can say
    WHERE the folder came from instead of just showing a path.
    """
    global GAME_DIR_SOURCE
    here = Path(__file__).parent
    if os.environ.get("LPO_GAME_DIR"):
        p = Path(os.environ["LPO_GAME_DIR"])
        if _has_swfs(p):
            GAME_DIR_SOURCE = "env"
            return p
    for cand in (here / "game", here.parent / "game"):
        if _has_swfs(cand):
            GAME_DIR_SOURCE = "package"
            return cand
    try:
        txt = here / "game_dir.txt"
        if txt.is_file():
            p = Path(txt.read_text(encoding="utf-8").strip().strip('"'))
            if _has_swfs(p):
                GAME_DIR_SOURCE = "game_dir.txt"
                return p
    except Exception:
        pass
    try:
        for cand in _windows_game_dirs() or ():
            if _has_swfs(cand):
                log.info(f"  found the client here: {cand}")
                GAME_DIR_SOURCE = "auto-detected"
                return Path(cand)
    except Exception:
        pass
    for cand in (Path.home() / "littleprince-online", Path.home() / "Downloads" / "Little Prince Online"):
        if _has_swfs(cand):
            GAME_DIR_SOURCE = "auto-detected"
            return cand
    GAME_DIR_SOURCE = "not found (serving this folder)"
    return here


def game_dir_candidates() -> list:
    """Every place the client has been found, or might be - for the admin page."""
    here = Path(__file__).parent
    out = []
    if os.environ.get("LPO_GAME_DIR"):
        out.append(Path(os.environ["LPO_GAME_DIR"]))
    out += [here / "game", here.parent / "game"]
    try:
        if GAME_DIR_TXT.is_file():
            out.append(Path(GAME_DIR_TXT.read_text(encoding="utf-8").strip().strip('"')))
    except Exception:
        pass
    try:
        out += [Path(c) for c in (_windows_game_dirs() or ())]
    except Exception:
        pass
    out += [Path.home() / "littleprince-online",
            Path.home() / "Downloads" / "Little Prince Online"]
    seen, uniq = set(), []
    for p in out:
        if str(p) not in seen:
            seen.add(str(p))
            uniq.append(p)
    return uniq


def _looks_like_client(p: Path) -> bool:
    """The online client's own entry points - what the launcher checks for too."""
    return (p / "index.swf").is_file() or (p / "login.swf").is_file()


def game_dir_payload() -> dict:
    """What the accounts page shows for the LPO client folder."""
    root = Path(GAME_DIR or "")
    swfs = list(root.glob("**/*.swf")) if root.is_dir() else []
    return {
        "path": str(root),
        "source": GAME_DIR_SOURCE,
        "env": os.environ.get("LPO_GAME_DIR", ""),
        "exists": root.is_dir(),
        "installed": root.is_dir() and _looks_like_client(root),
        "swf_count": len(swfs),
        "configured": (GAME_DIR_TXT.read_text(encoding="utf-8").strip()
                       if GAME_DIR_TXT.is_file() else ""),
        "game_dir_txt": str(GAME_DIR_TXT),
        "package_dir": str(Path(__file__).parent / "game"),
        "candidates": [{"path": str(p), "ok": _has_swfs(p), "installed": _looks_like_client(p)}
                       for p in game_dir_candidates()][:10],
    }


def set_game_dir(value: str) -> dict:
    """Point the mirror at another client folder (the Game files tab).

    Empty value clears the remembered folder and lets the resolver decide again.
    The path is checked before it is accepted: a folder without the client in it
    would simply break every page afterwards.
    """
    global GAME_DIR, GAME_DIR_SOURCE
    value = (value or "").strip().strip('"')
    if not value:
        try:
            GAME_DIR_TXT.unlink()
        except FileNotFoundError:
            pass
        except Exception as e:                                            # noqa: BLE001
            raise ValueError(f"could not clear {GAME_DIR_TXT}: {e}")
        GAME_DIR = _resolve_game_dir()
        log.info(f"  client folder override cleared - now {GAME_DIR} ({GAME_DIR_SOURCE})")
        return game_dir_payload()
    p = Path(value).expanduser()
    if not p.is_dir():
        raise ValueError(f"{p} is not a folder on this machine")
    if not _has_swfs(p):
        raise ValueError(f"{p} has no .swf files in it - that is not the game client")
    if not _looks_like_client(p):
        raise ValueError(f"{p} has no index.swf or login.swf - the client is not installed there"
                         " (a partial download would not start)")
    try:
        GAME_DIR_TXT.write_text(str(p) + "\n", encoding="utf-8")
    except Exception as e:                                                # noqa: BLE001
        raise ValueError(f"could not write {GAME_DIR_TXT}: {e}")
    GAME_DIR = p
    GAME_DIR_SOURCE = "game_dir.txt"
    log.info(f"  client folder set from the accounts page: {p}")
    return game_dir_payload()


def save_game_dir(path) -> Path:
    """Remember where the client is (lpo/game_dir.txt), for the next start."""
    p = Path(path)
    try:
        GAME_DIR_TXT.write_text(str(p) + "\n", encoding="utf-8")
    except Exception:
        pass
    return p


GAME_DIR_SOURCE = "unknown"
GAME_DIR = _resolve_game_dir()

LPO_DIR = Path(__file__).parent                   # this folder: pages, profile, captures
CLOUD_DIR = LPO_DIR.parent / "cloud"              # mirror of the publisher's cloud portal
PACKAGE_WEB = LPO_DIR / "web"                     # the browser player + launcher page
# Small client fixes we ship, laid out like the mirror (patches/LP2/index.swf).
# They are served in place of the mirrored file rather than written into it: the
# client check compares cloud/<code>/ against the publisher's build, and a patched
# file sitting in there would fail that check forever.
PATCH_DIR = LPO_DIR.parent / "patches"
LPO_PATCH_DIR = LPO_DIR / "patches"                # LPO client fixes: lpo/patches/lpo/<rel>

CROSSDOMAIN = (b'<?xml version="1.0"?>\n'
               b'<!DOCTYPE cross-domain-policy SYSTEM '
               b'"http://www.adobe.com/xml/dtds/cross-domain-policy.dtd">\n'
               b'<cross-domain-policy>'
               b'<allow-access-from domain="*" to-ports="*" secure="false"/>'
               b'</cross-domain-policy>\n')
PORT = int(os.environ.get("LPO_PORT", "8080"))
HOST = "0.0.0.0"
GATEWAY_PATH = "/littleprince/amfservice/gateway.php"
# Unknown services are answered locally by default (privacy: no login data,
# ever, leaves this machine).  LPO_FORWARD=1 restores forwarding to the
# real server for services that were never captured.
FORWARD_UNKNOWN = os.environ.get("LPO_FORWARD") == "1"

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("LittlePrinceServer")

# ─── AMF0 Type Constants ────────────────────────────────────────────────────

# AMF0 type markers (used in body values)
AMF0_NUMBER       = 0x00  # double (8 bytes)
AMF0_BOOLEAN      = 0x01  # single byte (0/1)
AMF0_STRING       = 0x02  # uint16 length + bytes
AMF0_OBJECT       = 0x03  # key-value pairs + end marker
AMF0_NULL         = 0x05
AMF0_UNDEFINED    = 0x06
AMF0_ECMA_ARRAY   = 0x08  # count + key-value pairs
AMF0_OBJECT_END   = 0x09  # end marker (0x00 0x00 0x09)
AMF0_STRICT_ARRAY = 0x0A  # count + values
AMF0_LONG_STRING  = 0x0C  # uint32 length + bytes

# ─── AMF0 Encoding Helpers ──────────────────────────────────────────────────

def encode_raw_string(s: str) -> bytes:
    """Encode a raw string for packet headers: uint16 length + UTF-8 bytes (NO type marker)."""
    encoded = s.encode("utf-8")
    return struct.pack("!H", len(encoded)) + encoded

def encode_typed_string(s: str) -> bytes:
    """Encode a typed string for body values: 0x02 + uint16 length + UTF-8 bytes."""
    encoded = s.encode("utf-8")
    if len(encoded) > 65535:
        # Use long string for very long strings
        return bytes([AMF0_LONG_STRING]) + struct.pack("!I", len(encoded)) + encoded
    return bytes([AMF0_STRING]) + struct.pack("!H", len(encoded)) + encoded

def encode_number(n: float) -> bytes:
    """Encode a number: 0x00 + double (8 bytes big-endian)."""
    return bytes([AMF0_NUMBER]) + struct.pack("!d", float(n))

def encode_boolean(b: bool) -> bytes:
    """Encode a boolean: 0x01 + 0x01 (true) or 0x00 (false)."""
    return bytes([AMF0_BOOLEAN, 1 if b else 0])

def encode_null() -> bytes:
    """Encode null: 0x05."""
    return bytes([AMF0_NULL])

def encode_amf_value(value) -> bytes:
    """Encode a Python value as a typed AMF0 value."""
    if value is None:
        return encode_null()
    elif isinstance(value, bool):
        return encode_boolean(value)
    elif isinstance(value, (int, float)):
        return encode_number(float(value))
    elif isinstance(value, str):
        return encode_typed_string(value)
    elif isinstance(value, dict):
        return encode_object(value)
    elif isinstance(value, (list, tuple)):
        return encode_strict_array(value)
    else:
        return encode_null()

def encode_object(obj: dict) -> bytes:
    """Encode a dict as AMF0 Object: 0x03 + (key_raw + typed_val)* + 0x00000x09."""
    parts = [bytes([AMF0_OBJECT])]
    for key, value in obj.items():
        parts.append(encode_raw_string(key))
        parts.append(encode_amf_value(value))
    parts.append(b"\x00\x00\x09")  # Object end marker
    return b"".join(parts)

def encode_strict_array(arr: list) -> bytes:
    """Encode a list as AMF0 Strict Array: 0x0A + count(4B) + typed values."""
    parts = [bytes([AMF0_STRICT_ARRAY])]
    parts.append(struct.pack("!I", len(arr)))
    for value in arr:
        parts.append(encode_amf_value(value))
    return b"".join(parts)

def encode_amf0_response(target: str, response_id: str, body_data: bytes) -> bytes:
    """Build a complete AMF0 response packet.
    
    Packet format:
      version(2B=0x0000) + header_count(2B=0x0000) + body_count(2B=0x0001)
      + raw_str(target) + raw_str(response_id) + uint32(body_len) + body_data
    """
    packet = b""
    packet += struct.pack("!HHH", 0, 0, 1)  # version=0, 0 headers, 1 body
    packet += encode_raw_string(target)
    packet += encode_raw_string(response_id)
    packet += struct.pack("!I", len(body_data))
    packet += body_data
    return packet

# ─── AMF0 Request Parsing ───────────────────────────────────────────────────

def parse_raw_string(data: bytes, offset: int) -> tuple:
    """Parse a raw string: uint16 length + bytes. Returns (string, new_offset)."""
    if offset + 2 > len(data):
        return ("", offset)
    length = struct.unpack("!H", data[offset:offset+2])[0]
    offset += 2
    if offset + length > len(data):
        return ("", offset)
    s = data[offset:offset+length].decode("utf-8", errors="replace")
    return (s, offset + length)

def parse_typed_value(data: bytes, offset: int) -> tuple:
    """Parse a typed AMF0 value. Returns (value, new_offset)."""
    if offset >= len(data):
        return (None, offset)
    
    type_marker = data[offset]
    offset += 1
    
    if type_marker == AMF0_NUMBER:  # 0x00: Number (double)
        if offset + 8 > len(data):
            return (0.0, offset)
        val = struct.unpack("!d", data[offset:offset+8])[0]
        return (val, offset + 8)
    
    elif type_marker == AMF0_BOOLEAN:  # 0x01: Boolean
        if offset >= len(data):
            return (False, offset)
        val = data[offset] != 0
        return (val, offset + 1)
    
    elif type_marker == AMF0_STRING:  # 0x02: String
        if offset + 2 > len(data):
            return ("", offset)
        length = struct.unpack("!H", data[offset:offset+2])[0]
        offset += 2
        if offset + length > len(data):
            return ("", offset)
        s = data[offset:offset+length].decode("utf-8", errors="replace")
        return (s, offset + length)
    
    elif type_marker == AMF0_OBJECT:  # 0x03: Object
        obj = {}
        while offset < len(data):
            # Check for end marker (0x00 0x00 0x09)
            if offset + 2 < len(data):
                if data[offset] == 0x00 and data[offset+1] == 0x00:
                    if data[offset+2] == 0x09:
                        offset += 3
                        break
            # Parse key (raw string)
            key, offset = parse_raw_string(data, offset)
            if key == "":
                # Empty key might mean end of object
                # Check if we just passed the end marker
                break
            # Parse value
            value, offset = parse_typed_value(data, offset)
            obj[key] = value
        return (obj, offset)
    
    elif type_marker == AMF0_NULL:  # 0x05: Null
        return (None, offset)
    
    elif type_marker == AMF0_UNDEFINED:  # 0x06: Undefined
        return (None, offset)
    
    elif type_marker == AMF0_ECMA_ARRAY:  # 0x08: ECMA Array
        if offset + 4 > len(data):
            return ({}, offset)
        count = struct.unpack("!I", data[offset:offset+4])[0]
        offset += 4
        obj = {}
        # Parse associative key-value pairs until end marker
        while offset < len(data):
            if offset + 2 < len(data):
                if data[offset] == 0x00 and data[offset+1] == 0x00:
                    if data[offset+2] == 0x09:
                        offset += 3
                        break
            key, offset = parse_raw_string(data, offset)
            if key == "":
                break
            value, offset = parse_typed_value(data, offset)
            obj[key] = value
        return (obj, offset)
    
    elif type_marker == AMF0_STRICT_ARRAY:  # 0x0A: Strict Array
        if offset + 4 > len(data):
            return ([], offset)
        count = struct.unpack("!I", data[offset:offset+4])[0]
        offset += 4
        arr = []
        for _ in range(count):
            if offset >= len(data):
                break
            value, offset = parse_typed_value(data, offset)
            arr.append(value)
        return (arr, offset)
    
    elif type_marker == AMF0_LONG_STRING:  # 0x0C: Long String
        if offset + 4 > len(data):
            return ("", offset)
        length = struct.unpack("!I", data[offset:offset+4])[0]
        offset += 4
        if offset + length > len(data):
            return ("", offset)
        s = data[offset:offset+length].decode("utf-8", errors="replace")
        return (s, offset + length)
    
    elif type_marker == 0x0B:  # Date
        if offset + 10 > len(data):
            return (0.0, offset)
        val = struct.unpack("!d", data[offset:offset+8])[0]
        offset += 10  # 8 bytes value + 2 bytes timezone
        return (val, offset)
    
    else:
        if not QUIET:
            log.warning(f"Unknown AMF0 type marker: 0x{type_marker:02x} at offset {offset-1}")
        return (None, offset)

def _parse_body_header(data: bytes, offset: int) -> tuple:
    """Read one AMF0 body header: target, response id, length, start of value.

    Two envelopes turn up in practice and they differ by the 0x02 string marker:

      * with the marker    - 02 <len> "target"  02 <len> "resp"  <u32 len> <value>
      * without the marker -    <len> "target"     <len> "resp"  <u32 len> <value>

    The publisher's Flash client sends the first, so parsing it with the
    marker-less reader ate the marker as the high byte of the length: the target
    came out empty, the length was read out of the middle of "serviceRequest"
    (1919512163) and the service was dispatched as 'unknown' -> generic
    {response:'ok'} answer -> the caller's window never got its data.

    Returns (target, response_id, body_length, value_offset); value_offset is
    None when the header does not fit in the packet.
    """
    # Variant A - standard envelope, type markers present.
    if offset < len(data) and data[offset] in (0x02, 0x0C):
        off = offset
        target, off = parse_typed_value(data, off)
        response_id, off = parse_typed_value(data, off)
        if isinstance(target, str) and off + 4 <= len(data):
            body_len = struct.unpack("!I", data[off:off+4])[0]
            if body_len <= len(data) - (off + 4):
                return (target, response_id if isinstance(response_id, str) else "",
                        body_len, off + 4)
    # Variant B - no markers (the layout this server was originally written for).
    target, off = parse_raw_string(data, offset)
    response_id, off = parse_raw_string(data, off)
    if off + 4 > len(data):
        return (target, response_id, 0, None)
    body_len = struct.unpack("!I", data[off:off+4])[0]
    return (target, response_id, body_len, off + 4)


def parse_amf0_request(data: bytes) -> dict:
    """Parse an AMF0 request packet and extract key fields."""
    result = {
        "raw_length": len(data),
        "bodies": []
    }
    
    if len(data) < 6:
        return result
    
    offset = 0
    version = struct.unpack("!H", data[offset:offset+2])[0]
    offset += 2
    header_count = struct.unpack("!H", data[offset:offset+2])[0]
    offset += 2
    body_count = struct.unpack("!H", data[offset:offset+2])[0]
    offset += 2
    
    result["version"] = version
    result["header_count"] = header_count
    result["body_count"] = body_count
    
    # Skip headers
    for _ in range(header_count):
        _, offset = parse_raw_string(data, offset)
        if offset < len(data):
            offset += 1  # must_understand byte
        if offset + 4 <= len(data):
            header_len = struct.unpack("!I", data[offset:offset+4])[0]
            offset += 4 + header_len
    
    # Parse bodies
    for _ in range(body_count):
        target, response_id, body_len, body_start = _parse_body_header(data, offset)
        if body_start is None or body_start > len(data):
            break
        offset = body_start

        body_data = data[offset:min(offset+body_len, len(data))]
        offset += body_len
        
        # Parse the body value
        try:
            body_value, _ = parse_typed_value(body_data, 0)
        except Exception as e:
            log.error(f"Error parsing body value: {e}")
            body_value = None
        
        body_info = {
            "target": target,
            "response_id": response_id,
            "body_length": body_len,
            "value": body_value,
            "raw_body": body_data,
        }
        result["bodies"].append(body_info)
    
    return result

def extract_service_type(parsed: dict) -> tuple:
    """Extract the service type from the AMF body.
    Returns (service_type, target, response_id)."""
    target = ""
    response_id = ""
    service_type = ""
    
    for body in parsed.get("bodies", []):
        target = body.get("target", "")
        response_id = body.get("response_id", "")
        value = body.get("value")
        
        if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
            # Array wrapping an object — extract type from first element
            t = value[0].get("type") or value[0].get("Type")
            if t:
                service_type = str(t)
                break
            # ECMA array wrapping: {"0": {"type": "login4", ...}}
            # Dig one level deeper
            for k, v in value[0].items():
                if isinstance(v, dict):
                    t = v.get("type") or v.get("Type")
                    if t:
                        service_type = str(t)
                        break
            if service_type:
                break

        # An ARRAY inside the ARRAY.  The online client sends
        # [{0: {password:.., type: 'login4', ...}}] and the request object was one
        # level too deep, so every call arrived with an empty type label and was
        # answered as 'unknown'.
        if isinstance(value, list) and value and isinstance(value[0], list):
            for inner in value:
                for item in (inner if isinstance(inner, list) else [inner]):
                    if isinstance(item, dict):
                        t = item.get("type") or item.get("Type")
                        if not t:
                            for v in item.values():
                                if isinstance(v, dict) and (v.get("type") or v.get("Type")):
                                    t = v.get("type") or v.get("Type")
                                    break
                        if t:
                            service_type = str(t)
                            break
                if service_type:
                    break
            if service_type:
                break
        
        if isinstance(value, dict):
            # Direct object with 'type' field
            t = value.get("type") or value.get("Type")
            if t:
                service_type = str(t)
                break
        
        # Also check if the target contains method info
        # Some Flash apps use "ClassName.methodName" as target
        if "." in target:
            parts = target.split(".")
            if len(parts) >= 2:
                method = parts[-1]
                if method and method not in ("serviceRequest", "call"):
                    service_type = method
                    break
    
    return (service_type, target, response_id)

def extract_response_number(response_id: str) -> str:
    """Extract the N from /N style response IDs."""
    if response_id.startswith("/"):
        parts = response_id.split("/")
        if len(parts) >= 2 and parts[1]:
            return parts[1]
    return "1"

# ─── Game Data (Realistic Fake Data) ────────────────────────────────────────

USER_PROFILE = {
    "uid": 100001,
    "email": "prince@starwish.com",
    "nickname": "小王子",
    "birthday": "2000-01-01",
    "role": "admin",
    "joinDate": "2008-06-01",
    "closet_size": 999,
    "money": 999999,
    "exp": 999999,
    "level": 99,
    "hp": 100,
    "max_hp": 100,
    "attack": 100,
    "defend": 100,
    "country": "HK",
    "language": "CHI",
    "gender": "M",
    "online_status": 1,
    "vip": 1,
    "crystal": 9999,
    "star": 999,
    "diamond": 999,
}

# All worlds/maps unlocked
ALL_WORLDS = [
    {"map_id": 1, "name": "魔法世界", "name_eng": "Magic World", "unlocked": 1},
    {"map_id": 2, "name": "玩具世界", "name_eng": "Toy World", "unlocked": 1},
    {"map_id": 3, "name": "海灘世界", "name_eng": "Beach World", "unlocked": 1},
    {"map_id": 4, "name": "冰雪世界", "name_eng": "Ice World", "unlocked": 1},
    {"map_id": 5, "name": "甲蟲世界", "name_eng": "Bug World", "unlocked": 1},
    {"map_id": 6, "name": "雲朵世界", "name_eng": "Cloud World", "unlocked": 1},
    {"map_id": 7, "name": "古文明世界", "name_eng": "Ancient World", "unlocked": 1},
    {"map_id": 8, "name": "忍者世界", "name_eng": " Ninja World", "unlocked": 1},
    {"map_id": 9, "name": "聖誕工場", "name_eng": "Xmas Factory", "unlocked": 1},
    {"map_id": 10, "name": "迷宮", "name_eng": "Maze", "unlocked": 1},
    {"map_id": 11, "name": "森林", "name_eng": "Forest", "unlocked": 1},
    {"map_id": 12, "name": "城堡", "name_eng": "Castle", "unlocked": 1},
    {"map_id": 13, "name": "市集", "name_eng": "Market", "unlocked": 1},
    {"map_id": 14, "name": "家", "name_eng": "Home", "unlocked": 1},
]

# Game missions — cover all worlds
ALL_MISSIONS = []
game_id = 1
worlds_for_missions = [
    ("Magic World", 1, 7), ("Toy World", 2, 6), ("Beach World", 3, 7),
    ("Ice World", 4, 6), ("Bug World", 5, 4), ("Cloud World", 6, 5),
    ("Ancient World", 7, 6), ("Ninja World", 8, 5), ("Christmas World", 9, 5),
]
for world_name, map_id, count in worlds_for_missions:
    for i in range(1, count + 1):
        ALL_MISSIONS.append({
            "id": game_id,
            "map_id": map_id,
            "game_id": game_id,
            "name": f"{world_name} Mission {i}",
            "name_eng": f"{world_name} Mission {i}",
            "description": f"Complete the {world_name} game #{i}",
            "description_eng": f"Complete the {world_name} game #{i}",
            "difficulty": min(i, 3),
            "reward_money": 100 * i,
            "reward_exp": 50 * i,
            "status": 2,  # completed
        })
        game_id += 1

# Items — extensive set (fashion/clothes)
ALL_CLOTHES = [
    {"id": 1, "name": "王子服", "name_eng": "Prince Outfit", "type": "cloth", "slot": "body", "price": 0, "paid": 0},
    {"id": 2, "name": "魔法帽", "name_eng": "Magic Hat", "type": "cloth", "slot": "head", "price": 100, "paid": 0},
    {"id": 3, "name": "星形眼鏡", "name_eng": "Star Glasses", "type": "cloth", "slot": "face", "price": 150, "paid": 0},
    {"id": 4, "name": "紅色披風", "name_eng": "Red Cape", "type": "cloth", "slot": "back", "price": 200, "paid": 0},
    {"id": 5, "name": "金靴子", "name_eng": "Gold Boots", "type": "cloth", "slot": "shoes", "price": 180, "paid": 0},
    {"id": 6, "name": "忍者裝", "name_eng": "Ninja Outfit", "type": "cloth", "slot": "body", "price": 300, "paid": 0},
    {"id": 7, "name": "聖誕帽", "name_eng": "Christmas Hat", "type": "cloth", "slot": "head", "price": 0, "paid": 0},
    {"id": 8, "name": "海盜帽", "name_eng": "Pirate Hat", "type": "cloth", "slot": "head", "price": 250, "paid": 0},
    {"id": 9, "name": "蝴蝶翅膀", "name_eng": "Butterfly Wings", "type": "cloth", "slot": "back", "price": 500, "paid": 0},
    {"id": 10, "name": "星星權杖", "name_eng": "Star Scepter", "type": "cloth", "slot": "hand", "price": 400, "paid": 0},
    {"id": 11, "name": "玫瑰花", "name_eng": "Rose", "type": "cloth", "slot": "hand", "price": 50, "paid": 0},
    {"id": 12, "name": "皇冠", "name_eng": "Crown", "type": "cloth", "slot": "head", "price": 999, "paid": 0},
    {"id": 13, "name": "太空裝", "name_eng": "Space Suit", "type": "cloth", "slot": "body", "price": 500, "paid": 0},
    {"id": 14, "name": "魔法靴", "name_eng": "Magic Boots", "type": "cloth", "slot": "shoes", "price": 300, "paid": 0},
    {"id": 15, "name": "古文明護甲", "name_eng": "Ancient Armor", "type": "cloth", "slot": "body", "price": 600, "paid": 0},
]

# Weapons
ALL_WEAPONS = [
    {"id": 101, "name": "星星劍", "name_eng": "Star Sword", "type": "weapon", "attack": 50, "defend": 10, "price": 500, "paid": 0},
    {"id": 102, "name": "魔法杖", "name_eng": "Magic Staff", "type": "weapon", "attack": 40, "defend": 20, "price": 450, "paid": 0},
    {"id": 103, "name": "忍者飛鏢", "name_eng": "Ninja Star", "type": "weapon", "attack": 60, "defend": 5, "price": 550, "paid": 0},
    {"id": 104, "name": "玫瑰之劍", "name_eng": "Rose Sword", "type": "weapon", "attack": 70, "defend": 15, "price": 700, "paid": 0},
    {"id": 105, "name": "冰霜之弓", "name_eng": "Frost Bow", "type": "weapon", "attack": 55, "defend": 10, "price": 600, "paid": 0},
]

# Consumable items
ALL_CONSUMABLES = [
    {"id": 201, "name": "小藥水", "name_eng": "Small Potion", "type": "item", "effect": "heal", "value": 20, "price": 30, "paid": 0},
    {"id": 202, "name": "大藥水", "name_eng": "Large Potion", "type": "item", "effect": "heal", "value": 50, "price": 80, "paid": 0},
    {"id": 203, "name": "復活藥水", "name_eng": "Revival Potion", "type": "item", "effect": "revive", "price": 200, "paid": 0},
    {"id": 204, "name": "經驗卡", "name_eng": "EXP Card", "type": "item", "effect": "exp", "value": 100, "price": 150, "paid": 0},
    {"id": 205, "name": "幸運星", "name_eng": "Lucky Star", "type": "item", "effect": "luck", "price": 100, "paid": 0},
]

ALL_ITEMS = ALL_CLOTHES + ALL_WEAPONS + ALL_CONSUMABLES

# Equipped clothing
EQUIPPED_CLOTH = [
    {"item_id": 1, "slot": "body"},
    {"item_id": 2, "slot": "head"},
    {"item_id": 4, "slot": "back"},
    {"item_id": 5, "slot": "shoes"},
    {"item_id": 10, "slot": "hand"},
]

# Game records — completed games
GAME_RECORDS = []
for i in range(1, 46):
    GAME_RECORDS.append({
        "game_id": i,
        "score": 1000 + i * 50,
        "completed": 1,
        "best_time": 30 + i * 2,
        "play_count": 5 + i,
    })

# ─── AMF Response Builders (Captured Replay) ──────────────────────────────────

# Load captured response bodies from the captures/bodies/ directory
# Each .bin file contains the raw AMF body (not the full packet)
CAPTURED_BODIES = {}
_CAPTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures", "bodies")
if os.path.isdir(_CAPTURE_DIR):
    for _fname in os.listdir(_CAPTURE_DIR):
        if _fname.endswith(".bin") and not _fname.startswith("unreadable_"):
            _type = _fname[:-4].lower()
            with open(os.path.join(_CAPTURE_DIR, _fname), "rb") as _f:
                CAPTURED_BODIES[_type] = _f.read()
    log.info(f"Loaded {len(CAPTURED_BODIES)} captured responses: {list(CAPTURED_BODIES.keys())}")


# ─── Player profile: identity, stats and world unlocks (editable at /admin) ───
# RemoteService.data2ObjAtt maps the login4 user STRICT_ARRAY positionally:
#   ["uid","permission","email","name","sex","birth","gameLv","createDate",
#    "_screenQuality","_language","_TextLanguage","_volume","_fullScreen",
#    "eventData","left_total","right_total","mazeRec","coins","totalItems",
#    "totalCrystals","crystal0".."crystal4"]
# HouseFlow.isTrial() gates every world / minigame on:
#     Bridge.user.permission & (1 << worldIndex)
#   worlds: 0 magic 1 toy 2 beach 3 ice 4 bug 5 ancient 6 xmas 7 cloud 8 ninja
#   games : (gameNumber - 1) / 5      -> the same bits
# Everything is a STRING in the captured array except index 1 (permission = NUMBER).
WORLDS = [
    (0, "魔法師之考驗", "map_magicworld.swf", "Magic World"),
    (1, "奇幻玩具箱", "map_toyworld.swf", "Toy World"),
    (2, "暢遊海之島", "map_beachworld.swf", "Beach World"),
    (3, "夢幻雪映國", "map_iceworld.swf", "Ice World"),
    (4, "森林大樂章", "map_bugworld.swf", "Forest World"),
    (5, "古文明之旅", "map_ancientworld.swf", "Ancient World"),
    (6, "聖誕夢工廠", "map_XmasFactory.swf", "Christmas Factory"),
    (7, "雲上之國", "map_cloudworld.swf", "Cloud World"),
    (8, "忍者之里", "map_ninjaworld.swf", "Ninja Village"),
]

# user[] index -> profile key (string-typed slots)
USER_STRING_SLOTS = {
    0: "uid", 2: "email", 3: "name", 4: "sex", 5: "birth", 6: "gameLv",
    7: "createDate", 8: "screenQuality", 9: "language", 10: "textLanguage",
    11: "volume", 12: "fullScreen", 13: "eventData", 14: "left_total",
    15: "right_total", 16: "mazeRec", 17: "coins", 18: "totalItems",
    19: "totalCrystals", 20: "crystal0", 21: "crystal1", 22: "crystal2",
    23: "crystal3", 24: "crystal4",
}
PERMISSION_SLOT = 1                      # NUMBER, the world bitfield

# Optional env override of the profile's world bits (scripted runs / A-B tests):
# LPO_PERMISSION=65535 forces every world on, 0 forces everything locked.
_perm_env = os.environ.get("LPO_PERMISSION")
try:
    PERMISSION_OVERRIDE = int(_perm_env) if _perm_env not in (None, "") else None
except ValueError:
    log.warning(f"  LPO_PERMISSION={_perm_env!r} is not a number - ignoring it")
    PERMISSION_OVERRIDE = None

PROFILE_PATH = Path(__file__).parent / "profile.json"   # ships with the package
DEFAULT_PROFILE = {
    "uid": "10001",
    "email": "player@littleprince.local",
    "name": "小王子玩家",
    "sex": "1",
    "birth": "2000-01-01",
    "gameLv": "國民",
    "createDate": "2014-01-01 00:00:00",
    "screenQuality": "2",
    "language": "0",
    "textLanguage": "1",
    "volume": "3",
    "fullScreen": "1",
    "eventData": "0",
    "left_total": "0",
    "right_total": "0",
    "mazeRec": "",
    # the mods panel's "every level unlocked": with this set the login reply reports
    # full marks on every level, so no level is greyed in any world.  A profile key
    # (not progress) so the website's Unlock all can set it through /web/api/me.
    "unlockLevels": "0",
    # the mods panel's LPO presets: "items" holds the owned rows as JSON ([[1, name], ...])
    # and unlimitedUse keeps the equipped weapons topped up (left_total/right_total).
    "items": "",
    "unlimitedUse": "0",
    "coins": "100",
    "totalItems": "0",
    "totalCrystals": "0",
    "crystal0": "0", "crystal1": "0", "crystal2": "0", "crystal3": "0", "crystal4": "0",
    "permission": 511,   # all 9 worlds unlocked for new accounts (was 0 = trial)
    # ── site-only meta, mirrors the official editaccount.php form ──
    "school_name": "",
    "school_level": "3",          # 0 kindergarten 1 primary 2 secondary 3 other
    "class_name": "0",            # 班級
    "class_no": "-",              # 班別
    "linked_account": "",         # 連結戶口名稱 (another local account's email)
    "maze_open": True,            # the daily maze: open every day unless turned off
    # ── what the character is wearing (Character.clothInit's 16 slots) ──
    # The client reports each one as it is changed (`UserRecord.setCloth` ->
    # RemoteService.addRequest{type:<slot>, data:<value>}), so they are ordinary
    # player fields: stored here, served back in the login4 reply's `cloth`
    # array, and drawn on the accounts site.
    "hat": "", "hair": "髮3", "ears": "耳1", "blusher": "面珠1", "mouth": "口1",
    "eyes": "眼1", "eyeblows": "眉1", "nose": "鼻1", "left_acc": "", "right_acc": "",
    "left_item": "", "right_item": "", "cloth": "運動服", "trousers": "運動褲",
    "shoes": "運動鞋", "tail": "",
}
FLAG_KEYS = {"screenQuality", "language", "textLanguage", "volume", "fullScreen", "sex"}
NUM_KEYS = {"coins", "left_total", "right_total", "totalItems", "totalCrystals",
            "crystal0", "crystal1", "crystal2", "crystal3", "crystal4", "eventData"}

# The titles the client's ID-card clip (`lv0`/`lv1`) can draw - they are its
# frame labels.  An unknown one makes the client's gotoAndStop throw #2109 and
# the whole screen freezes, so the server never serves anything else.
LPO_TITLES = ("國民", "資深國民", "名人", "貴族", "皇室人員", "小王子", "小公主")


def valid_title(value) -> str:
    """The profile's gameLv, coerced to something the client can actually show."""
    text = str(value or "").strip()
    return text if text in LPO_TITLES else LPO_TITLES[0]


def load_profile() -> dict:
    prof = dict(DEFAULT_PROFILE)
    if PROFILE_PATH.is_file():
        try:
            prof.update(json.loads(PROFILE_PATH.read_text("utf-8")))
        except Exception as e:
            log.warning(f"  profile.json unreadable ({e}) - using defaults")
    if PERMISSION_OVERRIDE is not None:          # env still wins for scripted runs
        prof["permission"] = PERMISSION_OVERRIDE
    return prof


def save_profile(patch: dict) -> dict:
    global PROFILE
    prof = dict(PROFILE)
    for k, v in (patch or {}).items():
        if k not in DEFAULT_PROFILE:
            continue
        if k == "permission":
            prof[k] = max(0, min(0xFFFF, int(v)))
        elif k in NUM_KEYS or k in FLAG_KEYS:
            prof[k] = str(int(v))
        else:
            prof[k] = str(v)
    PROFILE = prof
    PROFILE_PATH.write_text(json.dumps(prof, ensure_ascii=False, indent=2), "utf-8")
    return prof


PROFILE = load_profile()

# The capture came from a real account: remember its identifying strings so they
# can be scrubbed from EVERY captured response, not just the login one.
SENSITIVE_STRINGS = {}


def _collect_identity(body: bytes, tag: str):
    try:
        for value in amf0.decode(body):
            user = value.get("user") if isinstance(value, dict) else None
            if isinstance(user, list) and len(user) >= 4:
                for idx, slot in ((0, "uid"), (2, "email"), (3, "name")):
                    v = user[idx]
                    if isinstance(v, str) and v and v != PROFILE.get(slot):
                        SENSITIVE_STRINGS[v] = slot
    except Exception:
        pass


def _map_string(s: str) -> str:
    slot = SENSITIVE_STRINGS.get(s)
    return PROFILE.get(slot, s) if slot else s


def _walk_replace(node):
    """Replace any captured identity string anywhere in a decoded AMF tree."""
    if isinstance(node, str):
        return _map_string(node)
    if isinstance(node, list):
        return [_walk_replace(x) for x in node]
    if isinstance(node, (amf0.AmfObject, amf0.AmfEcmaArray)):
        return type(node)((k, _walk_replace(v)) for k, v in node.items())
    return node


# ─── every level of every game: the record rows the client unlocks levels with ───
# The client maps the login reply's `gameRecords` onto UserRecord.gameRecords
# ([game, first, firstDate, last, lastDate, highest, highestDate], RemoteService.as)
# and UI_base locks level N unless highestScore[N-1] >= fullScore[N-1].  The
# publisher's own reply for a fresh account carries an EMPTY array, which is why
# every online account can only ever open level 1.  Serve the real per-level
# scores we already keep (level_scores.json), and - when the account has the mods
# panel's unlockLevels flag - report full marks on every level so nothing is greyed.
LEVEL_TABLE_CACHE = None


def level_table() -> dict:
    """{game number: [fullScore per level]} from the client's own settings.cxd."""
    global LEVEL_TABLE_CACHE
    if LEVEL_TABLE_CACHE is not None:
        return LEVEL_TABLE_CACHE
    table = {}
    for candidate in (GAME_DIR / "settings.cxd",
                      LPO_DIR / "patches" / "settings.cxd"):
        try:
            if not candidate.is_file():
                continue
            import re as _re
            import zlib as _zlib
            xml = _zlib.decompress(candidate.read_bytes()).decode("utf-8", "replace")
            for m in _re.finditer(r'file="game(\d+)\.swf"(.*?)</game>', xml, _re.S):
                table[int(m.group(1))] = [int(x) for x in
                                          _re.findall(r'fullScore="(\d+)"', m.group(2))]
            if table:
                log.info("  level table: %d games from %s" % (len(table), candidate.name))
                break
        except Exception as exc:                                      # noqa: BLE001
            log.warning("  could not read the level table from %s: %s" % (candidate, exc))
    LEVEL_TABLE_CACHE = table
    return table


def wants_all_levels(prof: dict) -> bool:
    """True when the mods panel's 'every level unlocked' flag is set for this player."""
    def flag(source) -> bool:
        try:
            return str((source or {}).get("unlockLevels") or "").strip() not in ("", "0")
        except Exception:                                             # noqa: BLE001
            return False
    if flag(prof):
        return True
    email = (prof or {}).get("email") or CURRENT_PLAYER.get("email")
    if not email:
        return False
    try:
        return flag(accounts.get_progress(email))
    except Exception:                                                 # noqa: BLE001
        return False


def game_record_rows(prof: dict) -> list:
    """Rows for the login reply's `gameRecords`: one per level of every game.

    The client APPENDS each row into a per-game array and looks a level up by
    position (`getGameRecords(file, level-1)` -> `arr[level-2]`), so a skipped
    level shifts every later row up one and the lock test then reads the wrong
    level's score - that is why levels stayed greyed in worlds the player had
    barely touched.  Every level gets a row, score or not.

    The stored key convention is not pinned (setScore2 has been seen saving
    "<gid>-0" for the first level while the boards ask for "<gid>-1"), so each
    row takes the best of both spellings.
    """
    uid = str((prof or {}).get("uid") or (prof or {}).get("email") or "")
    scores = level_scores().get(uid) or {}
    if not scores:                      # the client logs in with its own uid
        for key, val in level_scores().items():
            if key and (key == uid or key == str((prof or {}).get("email"))):
                scores = val
                break
    unlock = wants_all_levels(prof)
    today = time.strftime("%Y%m%d")
    rows = []
    for gid, full in sorted(level_table().items()):
        for idx, full_score in enumerate(full):
            glv = idx + 1
            best = 0
            for key in ("%s-%s" % (gid, glv), "%s-%s" % (gid, glv - 1)):
                try:
                    best = max(best, int(float(scores.get(key) or 0)))
                except (TypeError, ValueError):
                    continue
            if unlock:
                best = max(best, int(full_score))
            rows.append([gid, best, today, best, today, best, today])
    return rows


def apply_profile(body: bytes, profile: dict = None):
    """Rewrite the login4 user array from profile.json (identity, stats, worlds).

    Anything that cannot be decoded is served untouched - a broken profile must
    never stop the game from logging in.  `profile` defaults to the server-wide
    profile.json; passing an account's profile serves that account instead.
    """
    prof = profile if profile is not None else PROFILE
    try:
        values = amf0.decode(body)
    except Exception as e:
        log.warning(f"  body not re-encodable ({e}) - serving as captured")
        return body
    changed = False
    for value in values:
        if isinstance(value, str):
            continue
        if isinstance(value, dict) and isinstance(value.get("user"), list):
            user = value["user"]
            for idx, key in USER_STRING_SLOTS.items():
                if idx < len(user) and isinstance(user[idx], str):
                    new = str(prof.get(key, user[idx]))
                    if key == "gameLv":
                        new = valid_title(new)      # the client only has the seven
                    if user[idx] != new:
                        user[idx] = new
                        changed = True
            if len(user) > PERMISSION_SLOT and isinstance(user[PERMISSION_SLOT], (int, float)):
                perm = int(prof.get("permission", 0))
                if int(user[PERMISSION_SLOT]) != perm:
                    user[PERMISSION_SLOT] = float(perm)
                    changed = True
        else:
            new = _walk_replace(value)
            if new != value:
                changed = True
                value = new
        # Every level of every game: the client needs a record row per level or
        # only level 1 is playable (see game_record_rows above).
        if isinstance(value, dict) and "gameRecords" in value:
            rows = game_record_rows(prof)
            if rows and value.get("gameRecords") != rows:
                value["gameRecords"] = rows
                changed = True
        # `cloth` is the positional 16-part outfit the client draws the character
        # from.  Leaving the captured array in place clothes every account in the
        # same outfit and throws away what the player changed in 更改樣貌 - spell
        # the profile's parts into it instead.  (This belongs OUTSIDE the branch
        # above: the login4 object carries `user` AND `cloth`, so it never reaches
        # the else - which is exactly how the first attempt missed.)
        if isinstance(value, dict) and isinstance(value.get("cloth"), list):
            parts = cloth_parts(prof)
            row = value["cloth"]
            for i, part in enumerate(parts):
                if i < len(row) and row[i] != part:
                    row[i] = part
                    changed = True
        # `items` is the wardrobe: rows of [kind, name, pos, total], kind 1 owned and
        # kind 2 in the bag.  The capture belongs to whoever it was recorded from, so an
        # account that has its own list gets that instead - otherwise everyone wears the
        # same captured wardrobe.  An account with no list keeps the capture, as before.
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            rows = lpo_profile_items(prof)
            if rows is not None and value.get("items") != rows:
                value["items"] = rows
                changed = True
        # The unlimited-use mod: the equipped weapons' remaining uses, kept at the floor
        # here and again on every save below.
        if isinstance(value, dict) and str((prof or {}).get("unlimitedUse") or "0") == "1":
            for idx, k in ((14, "left_total"), (15, "right_total")):
                row = value.get("user")
                if isinstance(row, list) and idx < len(row) and row[idx] != LPO_UNLIMITED_USES:
                    row[idx] = LPO_UNLIMITED_USES
                    changed = True
    if not changed:
        return body
    try:
        return amf0.encode(values)
    except Exception as e:
        log.warning(f"  re-encode failed ({e}) - serving as captured")
        return body


def _dig_credentials(node):
    """Recursively find the dict holding loginname/password (the client nests it)."""
    if isinstance(node, dict):
        if "loginname" in node or "password" in node:
            return node.get("loginname"), node.get("password")
        for value in node.values():
            found = _dig_credentials(value)
            if found:
                return found
    elif isinstance(node, (list, tuple)):
        for value in node:
            found = _dig_credentials(value)
            if found:
                return found
    return None


def login_credentials(raw_body: bytes):
    """Pull (loginname, password) out of a login4 request body, however nested.

    The caller hands over the WHOLE gateway packet - version, flags, count, target,
    response id, then the AMF body - and decoding that from offset 0 is what made
    this return (None, None) on every live login (it reports a bogus marker where
    the target string starts).  Take the body slice first; keep the whole-bytes
    decode as the fallback for a bare payload (tests, replays, the mac relay).
    """
    body, _ = _amf_body_slice(raw_body)
    for candidate in (body, raw_body):
        if not candidate:
            continue
        try:
            values = amf0.decode(candidate)
        except Exception:
            continue
        for value in values:
            found = _dig_credentials(value)
            if found:
                return found
    return None, None


# ─── keeping the player's progress ───────────────────────────────────────────

# What the game reports back about the player.  The minigames send their result
# (score, coins, crystals, items...), so storing whatever arrives is what makes
# progress survive a re-login - the same record is spliced back into login4.
PLAYER_FIELDS = {
    "coins", "totalitems", "totalcrystals", "crystal0", "crystal1", "crystal2",
    "crystal3", "crystal4", "mazerec", "eventdata", "left_total", "right_total",
    "score", "high", "gamelv", "weapon", "name", "sex", "birth",
}
NUMERIC_FIELDS = {"coins", "totalitems", "totalcrystals", "crystal0", "crystal1",
                  "crystal2", "crystal3", "crystal4", "left_total", "right_total",
                  "score", "high", "eventdata"}


def _collect_pairs(value, out, depth=0):
    """Every scalar name/value pair in a decoded AMF request, at any nesting."""
    if depth > 6:
        return
    if isinstance(value, dict):
        # The MMO names the field in `type` and puts its value in `data`
        # (a captured save is {type:"coins", data:100}).  A plain scalar sweep
        # only ever sees "type"/"data" and never the field itself, which is why
        # nothing the online client saved used to reach the player record.
        t, d = value.get("type"), value.get("data")
        if isinstance(t, str) and isinstance(d, (str, int, float, bool)):
            out.setdefault(str(t).strip().lower(), d)
        for k, v in value.items():
            key = str(k).strip().lower()
            if isinstance(v, (str, int, float, bool)):
                out.setdefault(key, v)
            else:
                _collect_pairs(v, out, depth + 1)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _collect_pairs(v, out, depth + 1)


def request_values(raw_body: bytes):
    """Decoded AMF values from a gateway request - proper packet or bare payload."""
    values = []
    try:
        parsed = parse_amf0_request(raw_body)
        for entry in parsed.get("bodies") or ():
            if isinstance(entry, dict) and entry.get("value") is not None:
                values.append(entry["value"])
    except Exception:
        pass
    if not values:
        try:
            values = amf0.decode(raw_body)
        except Exception:
            values = []
    return values


def player_update(raw_body: bytes):
    """What this request says about the player: (fields, uid)."""
    if not raw_body:
        return {}, ""
    values = request_values(raw_body)
    pairs = {}
    for v in values:
        _collect_pairs(v, pairs)
    # the game sends camelCase (totalItems, mazeRec); compare case-insensitively and
    # store under the name the profile actually uses
    canonical = {k.lower(): k for k in DEFAULT_PROFILE.keys()}
    for k in PLAYER_FIELDS:                       # keep the profile's own spelling
        canonical.setdefault(k.lower(), k)
    update = {}
    for k, v in pairs.items():
        if k not in PLAYER_FIELDS and k not in canonical:
            continue
        if k in NUMERIC_FIELDS:
            try:
                v = int(float(v))
            except (TypeError, ValueError):
                continue
            if v < 0 or v > 100_000_000:
                continue
        update[canonical.get(k, k)] = v
    # `uid` identifies the record, it is not part of it: leaving it in overwrote
    # profile.json's own uid with the id the client happened to send.
    update.pop("uid", None)
    return update, str(pairs.get("uid") or "").strip()


def persist_player_update(raw_body: bytes, service: str = "") -> bool:
    """File what the game told us against the right player record."""
    update, uid = player_update(raw_body)
    if not update:
        return False
    # LP3's unlimited cards: the client saves the whole gameCards list after spending
    # one, so hold every slot at the floor for an account with the mod applied.
    _mail = CURRENT_PLAYER.get("email") or ""
    if _mail:
        _prog = accounts.get_progress(accounts.get(_mail) or {}) or {}
        if str(_prog.get("lp3unlimited") or "0") == "1":
            for _k in [k for k in update if k.lower() == "gamecards"]:
                _vals = []
                for _p in str(update[_k]).split(","):
                    try:
                        _n = int(float(_p))
                    except (TypeError, ValueError):
                        _n = 0
                    _vals.append(str(max(_n, int(LP3_CARD_FLOOR))))
                update[_k] = ",".join(_vals)
    # LPO's wardrobe saves: addItem/removeItem carry one item name, and the weapon
    # totals arrive as left_total/right_total.  Merge them into the profile's own item
    # list, and (for an account with the unlimited-use mod) refuse to let the equipped
    # weapons' uses fall - the client decrements them locally and saves the result, so
    # a one-time preset would otherwise be spent after 999999 swings' worth of play.
    owner_email = CURRENT_PLAYER.get("email") or ""
    owner_prof = (accounts.get(owner_email) or {}).get("profile") or accounts.get(owner_email) or {}
    if owner_email:
        import json as _json
        rows = lpo_profile_items(owner_prof) or []
        names = [r[1] for r in rows]
        touched = False
        add = update.pop("additem", None)
        if isinstance(add, str) and add and add not in names and add not in LPO_SPORTSWEAR:
            rows.append([1, add])
            touched = True
        drop = update.pop("removeitem", None)
        if isinstance(drop, str) and drop in names:
            rows = [r for r in rows if r[1] != drop]
            touched = True
        if touched:
            update["items"] = _json.dumps(rows, ensure_ascii=False)
            log.info("  LPO wardrobe: %d items for %s" % (len(rows), owner_email))
        if str(owner_prof.get("unlimitedUse") or "0") == "1":
            for k in ("left_total", "right_total"):
                if k in update:
                    try:
                        if int(float(update[k])) < int(LPO_UNLIMITED_USES):
                            update[k] = LPO_UNLIMITED_USES
                    except (TypeError, ValueError):
                        update[k] = LPO_UNLIMITED_USES
    key = str(uid).split(".")[0] if uid else ""          # a numeric uid arrives as 10002.0
    where = ""
    if key:
        for acct in accounts.all_accounts():
            if str(acct.get("uid")).split(".")[0] == key:
                accounts.update(acct["email"], dict(update),
                                profile_keys=set(DEFAULT_PROFILE.keys()))
                where = acct["email"]
                break
    if not where:
        # The online client's saves carry no uid at all, so the id cannot pick the
        # record - but whoever is logged in right now is the player.  Without this
        # their coins/gems went to the shared guest profile while their own account
        # kept its old numbers, and the login reply (which splices the account's
        # profile) showed nothing they had earned.
        owner = CURRENT_PLAYER.get("email") or ""
        if owner and accounts.get(owner):
            accounts.update(owner, dict(update),
                            profile_keys=set(DEFAULT_PROFILE.keys()))
            where = owner
    if not where:                       # a casual login: the default record
        prof = load_profile()
        prof.update(update)
        save_profile(prof)
        where = "the default profile"
    log.info(f"  saved {sorted(update)} -> {where}")
    return True


LOGIN_FAIL_BODY = amf0.encode([amf0.AmfObject({"response": "loginFail"})])


def build_generic_ok_response() -> bytes:
    """Harmless answer for a service we have no capture for (nothing forwarded)."""
    return amf0.encode([amf0.AmfObject({"response": "ok"})])


# ── LP3 (Prince3) activation handshake ───────────────────────────────────────
# Before Prince3 will show its login screen it asks the gateway four questions,
# and it only acts on a reply whose `response` field names the question it asked
# (Prince3/PrinceSystem.as, the serviceResponse handler).  A generic
# {"response":"ok"} is silently ignored, so the client sits on its "connecting"
# button for ever - which is exactly the LP3 symptom.
#
#   checkVersion     -> checkVersionResult    message must NOT be a number
#                                             greater than _root.verNumber, or
#                                             the client pops up error "e000".
#                                             "0" is always safe.
#   checkActivation  -> checkActivationResult any value other than e070/e080/e091
#                                             makes the client load the opening
#                                             movie.  "e091" means the copy was
#                                             activated elsewhere.
#   activation       -> activationResult      "" or e055/e080 are special-cased;
#   reactivation     -> reactivationResult    anything else is accepted.
LP3_ACTIVATION_REPLIES = {
    "checkversion":    ("checkVersionResult", "0"),
    "checkactivation": ("checkActivationResult", "ok"),
    "activation":      ("activationResult", "ok"),
    "reactivation":    ("reactivationResult", "ok"),
}


def lp3_activation_reply(service_lower: str):
    """The activation answer Prince3 expects, or None if this is not one of them."""
    hit = LP3_ACTIVATION_REPLIES.get(service_lower.split(".")[-1].strip())
    if not hit:
        return None
    response, message = hit
    log.info(f"  activation: answering '{service_lower}' -> {response} ({message!r})")
    return amf0.encode([amf0.AmfObject({"response": response, "message": message})])


# ── the rank board, built from this machine's own accounts ───────────────────
# The publisher's rank board cannot be consulted (its gateway only answers
# authenticated /Service/Method calls), and an empty list leaves the board blank,
# so the board is compiled from the accounts stored here instead.
# Which source the packs come from.  The launcher's settings drawer writes this file;
# the server reads it fresh on every download, so a change needs no restart.
DOWNLOAD_SETTINGS_FILE = LPO_DIR / "download-settings.json"


def download_settings() -> dict:
    """The saved choice of download source.

    auto       - the default: try every mirror in turn, in the built-in order
    pixeldrain - Catbox / Pixeldrain mirrors (the key keeps its saved name)
    custom     - an HTTP(S) self-hosted or custom pack URL, per game
    """
    out = {"method": "auto", "custom": {}}
    try:
        if DOWNLOAD_SETTINGS_FILE.is_file():
            data = json.loads(DOWNLOAD_SETTINGS_FILE.read_text(encoding="utf-8"))
            out = clean_download_settings(data)
    except Exception as exc:                                          # noqa: BLE001
        log.error("  could not read download-settings.json: %s" % exc)
    return out


def pack_sources(code: str) -> list:
    """The pack URLs to try for one game, in the order the settings ask for.

    Self-hosted URLs can be tried first in Auto mode, or exclusively in Custom
    mode. Blocked or obsolete settings are normalized before choosing sources.
    """
    settings = download_settings()
    method = settings["method"]
    if method == "auto":
        # the default: a URL you gave first, then every mirror in the built-in order,
        # so one dead source just moves on to the next
        urls = []
        own = (settings["custom"].get(code) or settings["custom"].get(code.upper())
               or settings["custom"].get(code.lower()))
        if own:
            urls.append(own)
        for url in PACK_SOURCES.get(code, []):
            if url not in urls:
                urls.append(url)
        return urls
    if method == "custom":
        url = (settings["custom"].get(code) or settings["custom"].get(code.upper())
               or settings["custom"].get(code.lower()))
        return [url] if url else []
    return list(PACK_SOURCES.get(code, []))


# Pack downloads use Catbox and Pixeldrain, without account-owned Drive links.
# LP2 and LP3 exceed Catbox's 200 MB limit and stay on Pixeldrain.
#
# Anonymous hosts such as catbox.moe drop the connection when a request arrives
# with no User-Agent or with Python's default one, so every pack request says who
# it is.  Without this a catbox link looks like a dead mirror.
PACK_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) littleprince-launcher/1.0"


def pack_request(url: str):
    """A Request for a pack URL that an anonymous host will actually serve."""
    import urllib.request
    return urllib.request.Request(validate_pack_url(url), headers={"User-Agent": PACK_UA})

PACK_SOURCES = {
    "LP1": ["https://files.catbox.moe/hqrqto.zip"],
    "LP2": ["https://pixeldrain.com/api/file/jirbPgbb"],
    "LP3": ["https://pixeldrain.com/api/file/jPAAE3e8"],
}

# One entry per game while (or after) a download runs, so the portal can show it.
CLOUD_DOWNLOADS = {}
CLOUD_LOCK = threading.Lock()
# An install with no more than this many files missing (or the wrong size) is
# repaired file by file instead of pulling the whole pack again.
REPAIR_LIMIT = 40
# How many finished-but-still-incomplete attempts have run for a game.  Without a
# cap the installer restarts the same download every second, forever, when the
# files land somewhere the manifest check cannot see them.
CLOUD_ATTEMPTS = {}
CLOUD_ATTEMPT_LIMIT = 3


def cloud_dir():
    return Path(__file__).resolve().parent.parent / "cloud"


def _fetch_cloud_files(code, state):
    """Pull one game's missing files straight from the publisher.

    Used when no pack source answers: a dead mirror must not leave the portal
    button looking like it did nothing.  Reports progress through state.
    """
    import urllib.request
    import fetch_cloud

    dest = cloud_dir()
    missing, wrong = fetch_cloud.check(dest)
    # A file that is there but the wrong size counts too: that is exactly what the
    # CD's overwritten client files look like, and skipping them means "repair"
    # repairs nothing.
    wanted = []
    # The client files go first: they decide whether the game is the publisher's
    # cloud build or the CD's registration shell, and the CD's copy can be exactly
    # the same size as the publisher's, so the manifest's size check cannot see it.
    # Only their hash can, which is what client.txt is for.
    try:
        stale = fetch_cloud.client_bad(dest, code)
    except Exception:                                                 # noqa: BLE001
        stale = []
    for name in stale:
        rel = "%s/%s" % (code, name)
        if rel not in wanted:
            wanted.append(rel)
    for rel in list(missing) + list(wrong):
        if rel.split("/")[0] == code and rel not in wanted:
            wanted.append(rel)
    with CLOUD_LOCK:
        state["done"], state["total"] = 0, len(wanted)
        state["phase"] = "files"

    base = fetch_cloud.DEFAULT_BASE
    host_header = ""
    resolver = getattr(fetch_cloud, "resolve_base", None)
    if resolver:
        try:
            base, host_header = resolver(base, log=lambda m: log.info("  " + m))
        except Exception:                                             # noqa: BLE001
            host_header = ""

    ok, failed = 0, []
    from_pack = []                     # files the publisher no longer has
    for rel in wanted:
        try:
            req = urllib.request.Request(base + rel)
            if host_header:
                req.add_header("Host", host_header)
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            if not data:
                raise IOError("empty response")
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            ok += 1
        except Exception as exc:                                      # noqa: BLE001
            why = str(exc)[:60]
            failed.append((rel, why))
            # a definite "we do not have it" is worth another route; a timeout is not
            if "404" in why or "410" in why or "not found" in why.lower():
                from_pack.append(rel)
        with CLOUD_LOCK:
            state["done"] = ok + len(failed)
    # A file the publisher has taken down can still be had.  Every file their server
    # ever served is in our own pack, uploaded once, so nothing has to come from them
    # that they no longer have.
    if from_pack and GONE_PACK_URL:
        try:
            fixed = _fetch_from_own_pack(dest, code, from_pack, state)
        except Exception as exc:                                      # noqa: BLE001
            log.info("cloud %s: our own copy did not help (%s)" % (code, str(exc)[:80]))
            fixed = []
        for rel in fixed:
            failed = [f for f in failed
                      if (f[0] if isinstance(f, (list, tuple)) else f) != rel]
            ok += 1
    if from_pack:
        missed = set(from_pack) - set(fixed or [])
        if missed:
            remember_unfetchable(code, [(r, "404 gone") for r in missed])
    # say so if a client file still is not the publisher's build - a repair that
    # silently leaves the CD's registration shell in place is worse than none
    try:
        for name in fetch_cloud.client_bad(dest, code):
            failed.append(("%s/%s" % (code, name), "not the publisher's build"))
    except Exception:                                                 # noqa: BLE001
        pass
    return ok, failed


def cloud_download_worker(code):
    """Fetch one game's pack and unpack it into cloud/.  Runs on its own thread.

    The pack keeps the package layout (cloud/LP1/...), so unpacking into the cloud
    directory's parent puts everything where the manifest expects it.
    """
    import tempfile
    import urllib.request
    import zipfile

    dest = cloud_dir()
    state = CLOUD_DOWNLOADS.get(code)
    if state is None:
        return
    problems = []
    failed = []
    # A nearly-complete install (a handful of files, e.g. a client file the CD had
    # overwritten) is repaired file by file from the publisher.  Pulling the whole
    # 300 MB pack to replace three files is a waste of the user's connection.
    if state.get("repair"):
        log.info("cloud %s: %d file(s) to repair - fetching just those from the "
                 "publisher" % (code, state.get("repair_count") or 0))
        with CLOUD_LOCK:
            state["phase"] = "files"
        # A few files usually fail on the first pass - a dropped request, a slow read
        # - and arrive happily on the second.  Without this, a two-file miss sent the
        # whole 300 MB pack down again, which is why the same button had to be
        # pressed twice.
        failed = []
        for attempt in range(2):
            try:
                ok, failed = _fetch_cloud_files(code, state)
            except Exception as exc:                                  # noqa: BLE001
                ok, failed = 0, [str(exc)[:120]]
            if ok and not failed:
                log.info("cloud %s: repaired (%d files)" % (code, ok))
                disk_state_invalidate()
                with CLOUD_LOCK:
                    state["state"] = "ready"
                    state["error"] = ""
                return
            if attempt == 0 and failed:
                log.info("cloud %s: %d file(s) did not arrive - trying them once more"
                         % (code, len(failed)))
        disk_state_invalidate()
        log.info("cloud %s: repair left %d problem(s) - falling back to the pack"
                 % (code, len(failed or [])))
    # Each source gets two goes before the next one is tried.  A single dropped
    # connection - which is what a "download failed, then the retry worked" report
    # actually is - should not send the player back to press the button again.
    sources = list(pack_sources(code)) * 2
    if not sources:
        log.info("cloud %s: download method is '%s' - no pack, the files came from the "
                 "publisher directly" % (code, download_settings()["method"]))
    for url in sources:
        try:
            log.info("cloud %s: fetching the pack from %s" % (code, url.split("/")[2]))
            with open_pack(url, timeout=120) as r:
                total = int(r.headers.get("Content-Length") or 0)
                with CLOUD_LOCK:
                    state["total"] = total
                got = 0
                step = -1
                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                    tmp_name = tmp.name
                    while True:
                        chunk = r.read(262144)
                        if not chunk:
                            break
                        tmp.write(chunk)
                        got += len(chunk)
                        with CLOUD_LOCK:
                            state["done"] = got
                        if total:
                            tenth = got * 10 // total
                            if tenth != step:
                                step = tenth
                                log.info("cloud %s: %d%%" % (code, tenth * 10))
            if total and got < total:
                # A connection that drops mid-download leaves a short file, and the
                # unpack then fails with something that reads like a corrupt pack.
                # Say what actually happened so the retry makes sense.
                raise IOError("only %d of %d bytes arrived" % (got, total))
            with CLOUD_LOCK:
                state["phase"] = "unpack"
            # Check what we actually got before blaming the unpacker: a host that
            # sends a confirmation page for a big file produces the same error as a
            # truncated pack, and the two need different answers.
            if not zipfile.is_zipfile(tmp_name):
                with open(tmp_name, "rb") as f:
                    head = f.read(200)
                blob = head.lstrip().lower()
                if blob[:1] in (b"<", b"{") or b"<html" in blob or b"<!doctype" in blob:
                    raise IOError("the source sent a web page, not a pack (%d bytes) - "
                                  "a host asking to confirm a large download does this" % got)
                raise IOError("the source sent something that is not a pack "
                              "(%d bytes, starts %r)" % (got, head[:16]))
            log.info("cloud %s: download done, unpacking" % code)
            with zipfile.ZipFile(tmp_name) as zf:
                zf.extractall(str(dest.parent))
            os.unlink(tmp_name)
            log.info("cloud %s: pack unpacked into cloud/%s" % (code, code))
            # A pack can be a few files short, and a game missing even one never
            # counts as ready - the card goes on saying "download first" and the
            # player has no way to tell why.  Count the leftovers while we are still
            # holding the download, and fetch them if there are only a few.
            with CLOUD_LOCK:
                state["phase"] = "verify"
            short = stale2 = []
            try:
                here = str(Path(__file__).resolve().parent)
                if here not in sys.path:
                    sys.path.insert(0, here)
                import fetch_cloud
                missing2, wrong2 = fetch_cloud.check(dest)
                short = [r for r in list(missing2) + list(wrong2)
                         if str(r).split("/")[0] == code]
                stale2 = fetch_cloud.client_bad(dest, code)
            except Exception as exc:                                  # noqa: BLE001
                log.info("cloud %s: could not check the unpacked files (%s)"
                         % (code, str(exc)[:80]))
            if short or stale2:
                if len(short) + len(stale2) <= 500:
                    log.info("cloud %s: pack was short of %d file(s) - fetching them"
                             % (code, len(short) + len(stale2)))
                    try:
                        _ok2, left2 = _fetch_cloud_files(code, state)
                        remember_unfetchable(code, left2)
                    except Exception as exc:                          # noqa: BLE001
                        log.info("cloud %s: the leftovers failed (%s)"
                                 % (code, str(exc)[:80]))
                else:
                    log.info("cloud %s: pack was short of %d file(s) - too many to "
                             "fetch one by one, opening the game will get them"
                             % (code, len(short) + len(stale2)))
            disk_state_invalidate()      # the cards must stop saying "download"
            with CLOUD_LOCK:
                state["state"] = "ready"
                state["error"] = ""
            return
        except Exception as exc:                                      # noqa: BLE001
            problems.append(str(exc)[:120])
            log.info("cloud %s: that pack failed (%s)" % (code, problems[-1]))

    # every pack source failed - go file by file straight from the publisher
    log.info("cloud %s: no pack worked, fetching the files directly" % code)
    try:
        ok, failed = _fetch_cloud_files(code, state)
        if ok and not failed:
            log.info("cloud %s: complete (%d files)" % (code, ok))
            disk_state_invalidate()      # the cards must stop saying "download"
            with CLOUD_LOCK:
                state["state"] = "ready"
                state["error"] = ""
            return
        problems.append("%d files could not be fetched" % len(failed))
    except Exception as exc:                                          # noqa: BLE001
        problems.append(str(exc)[:120])

    with CLOUD_LOCK:
        state["state"] = "error"
        state["error"] = "; ".join(p for p in problems if p)[:160]
    log.info("cloud %s: download failed - %s" % (code, state.get("error")))
    # anything the publisher answered 404 for is gone for good - do not let it
    # block the game forever
    try:
        remember_unfetchable(code, failed)
        cloud_state_reply(fresh=True)
    except Exception:                                                 # noqa: BLE001
        pass


# The launch page: what the player gets once the game is installed.  Deliberately
# plain - they pressed a button and are waiting for a game to appear, so anything
# else on the screen is noise.  One line, one thin bar that moves by itself, in the
# game's own colour (the publisher gives each one a button colour; these are those,
# lifted enough to read on a dark screen).
LAUNCH_ACCENT = {"LP1": "#4aa3e0", "LP2": "#c8579a", "LP3": "#8cc44f"}

LAUNCH_PAGE = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="3;url=@@url@@">
<title>@@name@@</title><style>
html,body{margin:0;height:100%;}
body{background:#0b0b0b;color:#f2f2f2;overflow:hidden;
\tfont-family:DFLiYusn-Bd,'Microsoft JhengHei','Microsoft YaHei','PingFang TC',sans-serif;}
.wrap{height:100%;display:flex;flex-direction:column;align-items:center;
\tjustify-content:center;gap:15px;}
.name{font-size:14px;color:#8a8a96;letter-spacing:.06em;}
.what{font-size:21px;color:@@accent@@;font-weight:600;}
.bar{width:190px;height:3px;border-radius:2px;background:#22222c;overflow:hidden;}
.bar i{display:block;height:100%;width:34%;background:@@accent@@;
\tanimation:go 1.15s ease-in-out infinite;}
@keyframes go{0%{transform:translateX(-110%);}100%{transform:translateX(330%);}}
.back{position:fixed;bottom:15px;left:0;right:0;text-align:center;font-size:12px;}
.back a{color:#6c6c78;text-decoration:none;}
</style></head><body><div class="wrap">
\t<div class="name">@@name@@</div>
\t<div class="what">@@what@@</div>
\t<div class="bar"><i></i></div>
</div>
<div class="back"><a href="/LP/personal/">@@back@@</a></div>
</body></html>
"""

CLOUD_NAMES = {
    "LP1": "星願小王子 (LP1)",
    "LP2": "星願外傳 (LP2)",
    "LP3": "星願歷奇 (LP3)",
    "LPO": "星願小王子 ONLINE",
}

# Where a card goes once its game is installed.  The mirrored games have their own
# page in the portal; the online client is played through the real-Flash page,
# which falls back to the Ruffle one for browsers without Flash.
def launch_url(code):
    return "/play-flash" if code == "LPO" else "/LP/personal/%s/" % code

# The installer page.  Plain HTML, no script at all: an old browser only has to
# handle a meta refresh and some CSS.  @@tokens@@ are filled in per request.
DOWNLOAD_PAGE = """<!doctype html>
<html><head><meta charset="utf-8">@@refresh@@<title>@@name@@</title><style>
html,body{height:100%;margin:0;}
body{
	background:radial-gradient(120% 90% at 50% 0%,#16305c 0%,#0a1429 62%,#060d1c 100%);
	color:#fff;
	font-family:DFLiYusn-Bd,'Microsoft JhengHei','Microsoft YaHei','PingFang TC',sans-serif;
	display:table;width:100%;}
.wrap{display:table-cell;vertical-align:middle;text-align:center;padding:0 22px;}
.card{
	display:inline-block;width:520px;max-width:94%;
	background:rgba(10,20,42,.78);border:1px solid rgba(255,255,255,.16);
	border-radius:14px;padding:32px 34px 24px;
	box-shadow:0 18px 50px rgba(0,0,0,.45);}
.icon{margin:0 auto 14px;width:58px;height:58px;border-radius:50%;
	background:rgba(240,201,106,.14);display:table;}
.icon span{display:table-cell;vertical-align:middle;text-align:center;}
h1{margin:0 0 6px;font-size:21px;font-weight:normal;letter-spacing:.4px;}
.sub{margin:0 0 22px;font-size:13px;color:rgba(255,255,255,.5);}
.pct{margin:0 0 12px;font-size:34px;color:#f0c96a;}
.pct small{font-size:15px;color:rgba(255,255,255,.5);margin-left:6px;}
.bar{height:12px;background:rgba(255,255,255,.13);border-radius:6px;overflow:hidden;}
.fill{height:100%;border-radius:6px;
	background:linear-gradient(90deg,#d8a94e,#f7dfa0);}
.bar.busy .fill{width:30%;background:linear-gradient(90deg,rgba(240,201,106,0),#f0c96a,rgba(240,201,106,0));
	animation:slide 1.1s linear infinite;}
@keyframes slide{from{transform:translateX(-110%)}to{transform:translateX(340%)}}
.bytes{margin:12px 0 0;font-size:13px;color:rgba(255,255,255,.55);}
.msg{margin:18px 0 0;font-size:14px;line-height:1.65;color:rgba(255,255,255,.85);}
.msg.bad{color:#ff9b9b;word-break:break-all;}
a.back{display:inline-block;margin-top:22px;padding:9px 24px;border-radius:20px;
	border:1px solid rgba(240,201,106,.5);color:#f0c96a;text-decoration:none;font-size:14px;}
</style></head><body>
<div class="wrap"><div class="card">
<div class="icon"><span><svg width="25" height="25" viewBox="0 0 24 24"
	fill="#f0c96a">@@icon@@</svg></span></div>
<h1>@@name@@</h1>
<div class="sub">@@sub@@</div>
<div class="pct">@@pct@@</div>
<div class="bar @@barclass@@"><div class="fill" style="width:@@fill@@"></div></div>
<div class="bytes">@@bytes@@</div>
<div class="msg @@msgclass@@">@@msg@@</div>
<a class="back" href="/LP/personal/">@@back@@</a>
</div></div></body></html>
"""

# down arrow / tick / cross: filled shapes, drawn rather than typed so no font can
# tofu them.  Solid reads far better than thin strokes at 25px.
ICON_DOWN = ('<path d="M12 3.2c.72 0 1.3.58 1.3 1.3v6.6l2.2-2.2a1.3 1.3 0 0 1 1.84 '
             '1.84l-4.42 4.42a1.3 1.3 0 0 1-1.84 0L6.66 10.74A1.3 1.3 0 0 1 8.5 '
             '8.9l2.2 2.2V4.5c0-.72.58-1.3 1.3-1.3z"/>'
             '<rect x="4.6" y="17.4" width="14.8" height="2.6" rx="1.3"/>')
ICON_TICK = ('<path d="M20.3 6.3a1.3 1.3 0 0 1 0 1.84l-9.1 9.1a1.3 1.3 0 0 1-1.84 '
             '0l-4.6-4.6A1.3 1.3 0 0 1 6.6 10.8l3.68 3.68 8.18-8.18a1.3 1.3 0 0 1 '
             '1.84 0z"/>')
ICON_CROSS = ('<path d="M6.32 4.48 12 10.16l5.68-5.68a1.3 1.3 0 0 1 1.84 1.84L13.84 '
              '12l5.68 5.68a1.3 1.3 0 0 1-1.84 1.84L12 13.84l-5.68 5.68a1.3 1.3 0 0 '
              '1-1.84-1.84L10.16 12 4.48 6.32a1.3 1.3 0 0 1 1.84-1.84z"/>')


# ─── one place for the words the pages show ──────────────────────────────────
# The launcher's language button writes the player's TextLanguage (0 = English,
# 1 = Chinese) into the profile, the games read it, and these pages - served by
# the local server, seen in the publisher's browser - follow the same setting.
UI_TEXT = {
    "en": {
        "connecting": "Connecting &hellip;",
        "downloading": "Downloading",
        "unpacking": "Unpacking",
        "unpacking_sub": "Writing the files to your computer",
        "unpacking_msg": "Every byte is in. Finishing up, then the game starts.",
        "unpacking_bytes": "%.1f MB downloaded",
        "files_sub": "Fetching file by file",
        "files_bytes": "%d / %d files",
        "files_msg": "Downloading file by file from the game site - this is slower.",
        "download_msg": "Keep this window open - the game starts by itself when it is ready.",
        "source_failed": "That source did not work - trying the next one &hellip;",
        "failed": "Download failed",
        "failed_msg": "Please try again.",
        "retry": "Download again",
        "not_done": "Install did not finish",
        "not_done_missing": ("The download finished, but %d files are still not where "
                             "they should be."),
        "not_done_other": "The download finished, but the game files did not pass the check.",
        "loading": "Loading",
        "loading_sub": "Starting the game",
        "loading_msg": "The game is loading - the first time takes a few seconds.",
        "back": "Back to the games",
    },
    "zh": {
        "connecting": "正在連線 &hellip;",
        "downloading": "下載中",
        "unpacking": "解壓中",
        "unpacking_sub": "正在解開檔案",
        "unpacking_msg": "檔案已下載完成，正在寫入你的電腦。完成後會自動進入遊戲。",
        "unpacking_bytes": "%.1f MB 已下載",
        "files_sub": "逐個檔案下載中",
        "files_bytes": "%d / %d 個檔案",
        "files_msg": "正在直接從遊戲網站逐個檔案下載，可能會慢一點。",
        "download_msg": "請保持這個視窗開著，下載完成後會自動進入遊戲。",
        "source_failed": "上一個來源失敗，正在改用下一個來源 &hellip;",
        "failed": "下載失敗",
        "failed_msg": "請再試一次。",
        "retry": "重新下載",
        "not_done": "安裝未完成",
        "not_done_missing": "下載已經完成，但檢查後仍有 %d 個檔案不在預期的位置。",
        "not_done_other": "下載已經完成，但遊戲檔案沒有通過檢查。",
        "loading": "載入中",
        "loading_sub": "正在進入遊戲",
        "loading_msg": "遊戲正在載入，第一次可能需要幾秒。",
        "back": "返回遊戲選單",
    },
}


def ui_language() -> str:
    """'zh' or 'en', from the player record the launcher's language button writes."""
    try:
        prof = load_profile() or {}
    except Exception:                                                 # noqa: BLE001
        return "en"
    val = str(prof.get("textLanguage", prof.get("language", "0"))).strip().lower()
    return "zh" if val in ("1", "chi", "zh", "zh-tw", "tw", "big5") else "en"


def ui_text() -> dict:
    return UI_TEXT[ui_language()]


def start_cloud_download(code, repair=False, repair_count=0):
    """Kick off a pack download for one game.  Returns the state dict.

    `repair` fetches only the files that are missing or the wrong size, straight
    from the publisher - for an install that is nearly complete.
    """
    if code not in PACK_SOURCES:
        return {"ok": False, "error": "unknown game %s" % code}
    with CLOUD_LOCK:
        state = CLOUD_DOWNLOADS.get(code)
        if state and state.get("state") == "downloading":
            return {"ok": True, "started": False, "state": dict(state)}
        state = {"state": "downloading", "done": 0, "total": 0, "error": "",
                 "phase": "download"}
        if repair:
            state["repair"] = True
            state["repair_count"] = repair_count
        CLOUD_DOWNLOADS[code] = state
    threading.Thread(target=cloud_download_worker, args=(code,), daemon=True).start()
    return {"ok": True, "started": True, "state": dict(state)}


def repair_stale_clients():
    """Replace the CD's client files with the publisher's, when asked to.

    An install that came from the CD keeps the CD's own registration shell - the
    one that asks for a serial number - even when every other file matches the
    manifest, because the sizes are identical and only the hash gives it away.

    This is NOT run at startup: a download the player did not ask for is a download
    they do not want.  The portal shows those games as needing a download, and this
    runs when they press it.
    """
    try:
        here = str(Path(__file__).resolve().parent)
        if here not in sys.path:
            sys.path.insert(0, here)
        import fetch_cloud
    except Exception:                                                 # noqa: BLE001
        return []
    started = []
    cloud = cloud_dir()
    for code in ("LP1", "LP2", "LP3"):
        try:
            bad = fetch_cloud.client_bad(cloud, code)
        except Exception:                                             # noqa: BLE001
            continue
        if not bad:
            continue
        with CLOUD_LOCK:
            state = CLOUD_DOWNLOADS.get(code)
            if state and state.get("state") == "downloading":
                continue
        log.info("cloud %s: the CD's client is in place (%s) - replacing it with "
                 "the publisher's" % (code, ", ".join(bad)))
        start_cloud_download(code, repair=True, repair_count=len(bad))
        started.append(code)
    if not started:
        log.info("cloud: all three clients are the publisher's build")
    return started


def lpo_client_state() -> dict:
    """Is the online client on this machine, and is it complete?

    The portal shows Little Prince Online as a fourth card and it should read like the
    other three: not installed until the client is here, then Play.  A count of .swf
    files is not the test - half a client folder passed that and left the player on a
    "files not found" page.
    """
    root = Path(str(GAME_DIR or ""))
    missing = [name for name in ("index.swf", "login.swf") if not (root / name).is_file()]
    return {"ready": not missing, "missing_names": missing, "dir": str(root),
            "swfs": len(list(root.glob("**/*.swf"))) if root.is_dir() else 0}


def start_lpo_download():
    """Fetch the online client - the same files the launcher's own download gets.

    Runs in the background and reports through the same state dict the portal's bar
    already reads, so the fourth card behaves exactly like the other three.
    """
    code = "LPO"
    with CLOUD_LOCK:
        live = CLOUD_DOWNLOADS.get(code)
        if live and live.get("state") == "downloading":
            return {"ok": True, "started": False, "state": dict(live)}
        state = {"state": "downloading", "done": 0, "total": 0, "error": "",
                 "phase": "download", "percent": 0}
        CLOUD_DOWNLOADS[code] = state

    def worker():
        try:
            import fetch_client
            log.info("lpo: fetching the online client (this is the big one)")
            rows = [size for _rel, size in fetch_client.read_manifest()]
            with CLOUD_LOCK:
                state["total"] = sum(rows)

            def progress(st):
                with CLOUD_LOCK:
                    state["done"] = int(st.get("bytes") or 0)
                    total = int(st.get("total_bytes") or 0) or state["total"] or 1
                    state["percent"] = min(99, int(state["done"] * 100 / total))

            summary = fetch_client.fetch(GAME_DIR, progress=progress)
            failed = int(summary.get("failed") or 0)
            check = lpo_client_state()
            with CLOUD_LOCK:
                state["done"] = int(summary.get("bytes") or state["done"])
                state["percent"] = 100
                state["state"] = "done"
                state["total"] = state["done"] or state["total"]
                state["error"] = ("" if check["ready"] and not failed else
                                  "%d file(s) did not arrive" % failed if failed else
                                  "the client is still incomplete: %s"
                                  % ", ".join(check["missing_names"]))
            log.info("lpo: client fetch finished - %s (%d ok, %d failed)"
                     % ("complete" if check["ready"] else "incomplete",
                        int(summary.get("ok") or 0), failed))
        except Exception as exc:                                      # noqa: BLE001
            with CLOUD_LOCK:
                state["state"] = "failed"
                state["error"] = str(exc)[:160]
            log.error("lpo: the client download failed: %s" % exc)

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True, "started": True, "state": dict(state)}


def start_cloud_game(code):
    """Start the right kind of download for one game.

    A game that is nearly complete - a few files missing, or the CD's client files
    sitting in place of the publisher's - is repaired file by file; anything else
    pulls the whole pack.  The portal's own button and the installer page both come
    through here, so the two cannot drift apart.
    """
    if code == "LPO":
        # the online client is not a mirrored cloud game, so it has its own fetch -
        # the same one the launcher uses.  A complete client is left alone, exactly
        # as the other three cards are.
        if lpo_client_state()["ready"]:
            return {"ok": True, "started": False, "state": {"ready": True}}
        return start_lpo_download()
    info = cloud_state_reply(fresh=True)["games"].get(code, {})
    if info.get("ready"):
        # already here: downloading the pack again over a good install would only
        # risk breaking it
        return {"ok": True, "started": False, "state": info}
    if info.get("downloading"):
        return {"ok": True, "started": False, "state": info}
    left = (info.get("missing") or 0) + len(info.get("stale") or [])
    if 0 < left <= REPAIR_LIMIT:
        return start_cloud_download(code, repair=True, repair_count=left)
    return start_cloud_download(code)


# The check below stats every file in the mirror and hashes the client files.  On a
# Windows box with a scanner in the way that took about ten seconds, and the portal
# asks for it on every poll and whenever a game is opened.  So split it: the disk
# part is cached (it only changes when files land), while the live download state is
# always read fresh, so the progress bar still moves.
_DISK_CACHE = {"at": 0.0, "found": None, "busy": False}
_DISK_TTL = 5.0

# Files that were asked for twice and never arrived: the publisher does not have
# them any more.  They can never be fetched, so they must not keep a game that
# plays perfectly well looking like it still needs a download.
CLOUD_UNFETCHABLE = {}
_GONE_SET = {}


def known_gone():
    """Files the publisher's server no longer serves, listed in cloud/gone.txt.

    Their server answers 404 for these now (31 of them: .original.html, .zinc, test*.swf,
    VC runtime DLLs, reg.swf ...).  A game must not look un-downloaded just because one of
    them is not on disk - they are not part of playing, and no download can get them.
    """
    if "set" in _GONE_SET:
        return _GONE_SET["set"]
    names = set()
    try:
        text = (CLOUD_DIR / "gone.txt").read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                names.add(line)
    except OSError:
        pass
    _GONE_SET["set"] = names
    return names


# Everything the publisher's server has ever served, packed and uploaded once.  Their
# server does drop files (LP2/start.swf is a 404 already), and a repair must not be
# left depending on something they no longer have.
GONE_PACK_URL = "https://files.catbox.moe/tumswl.zip"


def _fetch_from_own_pack(dest, code, rels, state):
    """Take files the publisher no longer serves out of our own uploaded pack."""
    import urllib.request
    import zipfile

    want = set(rels)
    with CLOUD_LOCK:
        state["phase"] = "pack"
    log.info("cloud %s: %d file(s) the publisher no longer has - taking them from "
             "our own pack" % (code, len(want)))
    # Keep it: it is fetched once and reused, so a repair costs one download of this
    # pack ever, not one per file and not one per repair.
    cache = LPO_DIR / "gone-pack.zip"
    fresh = False
    try:
        fresh = (cache.is_file()
                 and time.time() - cache.stat().st_mtime < 30 * 86400)
    except OSError:
        fresh = False
    if not fresh:
        part = cache.with_suffix(".part")
        with open_pack(GONE_PACK_URL, timeout=180) as r, \
                open(part, "wb") as out:
            while True:
                chunk = r.read(262144)
                if not chunk:
                    break
                out.write(chunk)
        os.replace(part, cache)
        log.info("cloud: our own pack saved to %s" % cache)
    got = []
    with zipfile.ZipFile(cache) as zf:
        names = set(zf.namelist())
        for rel in sorted(want):
            if rel not in names:
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(rel) as src:
                target.write_bytes(src.read())
            got.append(rel)
    log.info("cloud %s: %d of %d came from our own pack" % (code, len(got), len(want)))
    return got


def remember_unfetchable(code, failed):
    """Note the files the publisher's server says it does not have.

    Only a definite answer counts - a 404, not a dropped connection.  A transient
    failure must never end up being quietly treated as "fine", or the launcher would
    call a broken install ready.
    """
    names = set()
    for item in failed or []:
        why = ""
        if isinstance(item, (list, tuple)) and len(item) > 1:
            name, why = item[0], str(item[1])
        else:
            name = item
        low = str(why).lower()
        if not any(tag in low for tag in ("404", "not found", "gone", "no such")):
            continue
        name = str(name)
        if not name.startswith(code + "/"):
            name = "%s/%s" % (code, name)
        names.add(name)
    if names:
        CLOUD_UNFETCHABLE.setdefault(code, set()).update(names)
        log.info("cloud %s: %d file(s) are gone from the publisher's server - not "
                 "counting them (%s)" % (code, len(names), sorted(names)[0]))


def disk_state_invalidate():
    """Forget the cached check - call it whenever files have landed."""
    _DISK_CACHE["at"] = 0.0


def _scan_disk_state():
    """{code: {"missing": n, "stale": [...]}} - the slow part."""
    found = {code: {"missing": [], "stale": []} for code in ("LP1", "LP2", "LP3")}
    cloud = cloud_dir()
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import fetch_cloud
    missing, wrong = fetch_cloud.check(cloud)
    for rel in list(missing) + list(wrong):
        code = str(rel).split("/", 1)[0]
        if code in found:
            found[code]["missing"].append(str(rel))
    for code in found:
        # an install can have every file the manifest knows about and still be the
        # CD's build - that is the one that asks for a serial, so it must not count
        # as ready
        try:
            found[code]["stale"] = fetch_cloud.client_bad(cloud, code)
        except Exception:                                             # noqa: BLE001
            found[code]["stale"] = []
    return found


def _refresh_disk_state():
    """Work out a fresh answer in the background, without making anyone wait."""
    if _DISK_CACHE["busy"]:
        return
    _DISK_CACHE["busy"] = True

    def work():
        try:
            _DISK_CACHE.update({"at": time.time(), "found": _scan_disk_state()})
        except Exception:                                             # noqa: BLE001
            pass
        finally:
            _DISK_CACHE["busy"] = False

    threading.Thread(target=work, daemon=True).start()


def disk_state(fresh=False):
    """The last check, refreshed behind the scenes.

    A stale answer beats a ten-second wait: hand back what we have and re-check in
    the background.  `fresh=True` is for callers about to act on the result.
    """
    cached = _DISK_CACHE["found"]
    if cached is not None and not fresh and time.time() - _DISK_CACHE["at"] < _DISK_TTL:
        return cached
    if cached is not None and not fresh:
        _refresh_disk_state()
        return cached
    found = _scan_disk_state()
    _DISK_CACHE.update({"at": time.time(), "found": found})
    return found


def cloud_state_reply(fresh=False):
    """Which mirrored games are complete on this machine, keyed by LP1/LP2/LP3.

    The portal page asks for this before starting a game, so it can grey out the
    ones that are missing and offer to download them on the spot.
    """
    games = {code: {"ready": False, "missing": 0, "downloading": False,
                    "percent": 0, "error": "", "stale": [], "phase": ""}
             for code in ("LP1", "LP2", "LP3")}
    # the online client is the portal's fourth card, so it answers with the same shape
    lpo = lpo_client_state()
    games["LPO"] = {"ready": lpo["ready"],
                    "missing": 0 if lpo["ready"] else len(lpo["missing_names"]),
                    "names": [] if lpo["ready"] else lpo["missing_names"],
                    "downloading": False, "percent": 0, "error": "", "stale": [],
                    "phase": "", "swfs": lpo["swfs"]}
    try:
        found = disk_state(fresh=fresh)
        for code, state in games.items():
            if code == "LPO":
                # the online client is not one of the mirrored games: its readiness
                # comes from the client check above, not from the mirror's file walk
                continue
            one = found.get(code) or {}
            gone = (CLOUD_UNFETCHABLE.get(code) or set()) | known_gone()
            missed = [r for r in (one.get("missing") or []) if r not in gone]
            state["missing"] = len(missed)
            state["names"] = missed[:4]
            state["stale"] = one.get("stale", [])
            state["ready"] = state["missing"] == 0 and not state["stale"]
    except Exception as exc:                                          # noqa: BLE001
        return {"ok": False, "error": str(exc)[:120], "games": games,
                "language": ui_language()}
    with CLOUD_LOCK:
        for code, live in CLOUD_DOWNLOADS.items():
            if code not in games:
                continue
            games[code]["downloading"] = live.get("state") == "downloading"
            games[code]["error"] = live.get("error", "")
            games[code]["phase"] = live.get("phase") or ""
            total = live.get("total") or 0
            if live.get("state") == "downloading" and total:
                games[code]["percent"] = int(100.0 * live.get("done", 0) / total)
    return {"ok": True, "games": games, "language": ui_language()}


RANK_SIZE = 10                      # the board shows the 三甲 and a little more

# Fields the games save one at a time and expect back at the next login.
# LP3 sends the field name as the request type with a comma-joined string;
# LP2 sends setGem/setItem/updateUserInfo with a list of arguments.
PROGRESS_FIELDS = {
    # LP1's own savers (saveStar/saveEnding in the client): without these two the
    # star and ending saves were rejected before they reached the account, which is
    # why the login's stars lookup had nothing to find.
    "stars", "ending",
    "gems", "items", "cards", "cardsequence", "gamecards", "process",
    "tgem", "titem", "tcard", "tcard2",                 # LP3's totals
    "setgem", "setitem", "updateuserinfo",              # LP2's savers
    "gemreport", "itemreport", "scorereport",           # LP2's boards
    "equipment", "bossque", "defeatedboss", "firsthint", "quality",
    "musicvolume", "score", "language", "extra", "timer",
}


# ── one score per game ───────────────────────────────────────────────────────
# The three cloud titles all save their 積分 under the SAME request field name and
# all read it back out of the same reply key:
#
#   title  its own save                                   its own login read
#   -----  ---------------------------------------------  ------------------------
#   LP1    {type:"score", data:user.totalScore}           user.totalScore = int(val.score)
#          (start.swf saveMark/saveCard)                  (start.swf serviceResponse)
#   LP2    7th of updateUserInfo's nine arguments         _loc3_.score = int(dbdata.score)
#          (index.swf saveUserData->PrinceSystem)         (index.swf DoAction_16)
#   LP3    {type:"score", ...} pushed from updateList      curUser.score = int(val.score)
#          (PrinceSystem.as save())                       (PrinceSystem.as serviceResponse)
#
# One shared store key therefore made a score earned in one title appear in the
# other two.  The reply's FIELD NAME stays `score` in every reply - what changes is
# WHICH stored key each title reads and writes.
SCORE_KEYS = {"prince1": "lp1score", "prince2": "lp2score", "prince3": "lp3score"}

# LP1's and LP3's per-level score rows shared one account key as well (both save
# through setScore -> accounts.set_game_result), so a level cleared in LP1 also
# showed up - and unlocked - the same level in LP3.  LP2's board was already its
# own (progress `scoreReport`), so it is not listed here.
BOARD_KEYS = {"prince1": "gameResult", "prince3": "gameResult3"}


def game_key(game: str) -> str:
    """'Prince1' / 'Prince1_personal.serviceRequest' -> 'prince1'."""
    return (str(game or "").split("_")[0] or "").strip().lower()


def score_field(game: str) -> str:
    """The progress key this title's 積分 is kept under ('' for the MMO)."""
    return SCORE_KEYS.get(game_key(game), "")


def board_field(game: str) -> str:
    """The account key this title's per-level score rows are kept under."""
    return BOARD_KEYS.get(game_key(game), "")


def read_score(prog: dict, prof: dict, game: str):
    """The 積分 one title's login reply reports.

    Its own key first.  An account that has not saved since the split still holds
    its old value under the single shared `score` key the three titles used to
    share (or, for LP1's historic preset, on the profile) - so fall back to those
    rather than showing the player a fresh 0.  The fallback cannot re-share the
    titles: nothing writes either legacy key again, every save now lands in the
    game's own key.
    """
    key = score_field(game)
    if key:
        for k in (key, key.lower()):
            if (prog or {}).get(k) not in (None, ""):
                return prog[k]
    for k in ("score", "Score"):
        if (prog or {}).get(k) not in (None, ""):
            return prog[k]
    if (prof or {}).get("score") not in (None, ""):
        return prof["score"]
    return ""


def row_from_profile(prof: dict, account: dict = None, board: list = None) -> dict:
    """One rank-board row, under every key name the games might read."""
    prof = prof or {}
    account = account or {}
    name = (prof.get("name") or account.get("login_name")
            or account.get("email") or "?")
    sex = str(prof.get("sex") or "1")
    try:
        coins = int(prof.get("coins") or 0)
    except (TypeError, ValueError):
        coins = 0
    try:
        items = int(prof.get("totalItems") or 0)
    except (TypeError, ValueError):
        items = 0
    try:
        crystals = int(prof.get("totalCrystals") or 0)
    except (TypeError, ValueError):
        crystals = 0

    total = 0
    month = 0
    month_tag = time.strftime("%Y%m")
    for game in (board or []):
        if not isinstance(game, list):
            continue
        for row in game:
            if isinstance(row, list) and len(row) > 2:
                try:
                    value = int(row[2] or 0)      # row[2] = highest score
                except (TypeError, ValueError):
                    continue
                total += value
                # row[3] = the date of that score, e.g. "20260921"
                try:
                    if str(row[3] or "").startswith(month_tag):
                        month += value
                except (TypeError, ValueError):
                    pass
    if not total:
        # Accounts that played before the setScore2 -> gameResult bridge existed
        # only have their scores in level_scores.json - count those too, or their
        # board stays 0 until they replay every level (same rule as _rank_value).
        uid = str(account.get("uid") or prof.get("uid") or "")
        for value in (level_scores().get(uid) or {}).values():
            try:
                total += int(float(value))
            except (TypeError, ValueError):
                continue
        month = total

    try:
        maze = len([x for x in str(prof.get("mazeRec") or "")
                    .replace(";", ",").split(",") if x.strip()])
        maze_month = len([x for x in str(prof.get("mazeRec") or "")
                          .replace(";", ",").split(",")
                          if x.strip() and x.strip().startswith(month_tag)])
    except (TypeError, ValueError):
        maze = maze_month = 0

    # the month's gain for the counted fields, from the baseline the account
    # keeps (see accounts.MONTH_TRACKED); without one the month reads 0
    base = account.get("monthBase") if isinstance(account.get("monthBase"), dict) else {}

    def month_gain(field, current):
        if base.get("m") != month_tag or field not in base:
            return 0
        try:
            return max(0, current - int(base.get(field) or 0))
        except (TypeError, ValueError):
            return 0

    return {"rank": 0, "name": name, "username": name, "userName": name,
            "playerName": name, "nickname": name,
            "gender": sex, "sex": sex,
            "score": total, "total": total, "totalScore": total,
            "scoreMonth": month, "monthScore": month,
            "coins": coins, "coinsMonth": month_gain("coins", coins),
            "crystal": crystals, "crystals": crystals,
            "crystalsMonth": month_gain("totalCrystals", crystals),
            "item": items, "items": items,
            "itemsMonth": month_gain("totalItems", items),
            "maze": maze, "mazeMonth": maze_month,
            "uid": str(account.get("uid") or prof.get("uid") or "")}


def rank_rows(board_key: str = "gameResult", board_of=None) -> list:
    """The rank board: every local account, best score first.

    A row carries the same value under several names on purpose - each game's
    ranking UI reads a different set of keys (`name` vs `userName`, `score` vs
    `totalScore`, ...) and no schema is published, so supply them all.

    The score column is counted from the asking title's OWN board: `board_key`
    names an account key (see BOARD_KEYS), `board_of` a callable for a board kept
    elsewhere (LP2's lives in the account's saved progress).  Counting one shared
    board put the same 總成績 on every title's board.
    """
    rows = []
    for a in accounts.all_accounts():
        prof = dict(a.get("profile") or {})
        # gems, cards, the boss record and the totals are saved into the account's
        # `progress`, not its profile - so merge the saved copy in before the row is
        # built.  The saved copy WINS: it is what the game last wrote, while the
        # profile still holds the values the account started with (setdefault here
        # meant a stale profile masked every newer save - the same defect LP3's
        # board had).
        for k, v in (accounts.get_progress(a) or {}).items():
            if str(v) in ("", "None"):
                continue
            for key in DEFAULT_PROFILE:
                if key.lower() == str(k).lower():
                    prof[key] = v
        board = board_of(a) if board_of is not None else a.get(board_key)
        rows.append(row_from_profile(prof, a, board))

    # The player themself, when they are not a stored account (the built-in
    # default profile has no account record) - otherwise their own board is blank.
    me = row_from_profile(CURRENT_PLAYER.get("profile") or load_profile())
    if me["name"] != "?" and not any(r["name"] == me["name"] for r in rows):
        rows.append(me)

    rows.sort(key=lambda r: r["score"], reverse=True)
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    if not rows:
        # An empty board is what "the leaderboard does not work" looks like.  Always
        # send at least the player, so the ranking screen has something to draw.
        empty = row_from_profile(CURRENT_PLAYER.get("profile") or load_profile())
        empty["name"] = empty.get("name") if empty.get("name") not in ("", "?") \
            else "Player"
        empty["rank"] = 1
        rows = [empty]
    return rows[:RANK_SIZE]


def lp2_array_row(prof: dict, score) -> list:
    """One LP2 rank row, as an ARRAY.

    LP2's RankUI indexes its rows positionally:

        row[0]        name            row[5]        總數 (items)
        row[1]        gender          row[6..15]    the ten 元素 counts
        row[4]        總成績 (score)   row[16]       武器及道具 (cards)

    It reads `row[0]` straight off the row object, so a dict-shaped row - however
    many friendly key aliases it carries - gives `undefined` in every cell.  That
    is what the 龍虎榜 panel was showing.
    """
    prof = prof or {}
    name = prof.get("name") or prof.get("email") or "?"

    def num(key, default=0):
        try:
            return int(prof.get(key) or default)
        except (TypeError, ValueError):
            return default

    elements = [num("crystal%d" % i) for i in range(10)]      # ten 元素 slots
    return [name, num("sex", 1), 0, 0, int(score or 0), num("totalItems")] \
        + elements + [num("totalCrystals")]


def lp3_array_row(prof: dict, score) -> list:
    """One LP3 rank row, as an ARRAY.

    LP3's RankUI indexes its rows positionally, exactly as LP2's does:

        row[0] name        row[4] score    row[7] tItem
        row[1] sex         row[5] tGem     row[8] tCard
        row[2] classLv     row[6] gems     row[9] tCard2
        row[3] className

    A dict-shaped row gives `undefined` in every cell, which is why LP3's 龍虎榜
    came up as an empty table however many accounts were on it.
    """
    prof = prof or {}
    name = prof.get("name") or prof.get("email") or "?"

    def text(key, default="0"):
        value = prof.get(key)
        if value is None or value == "":
            return default
        return str(value)

    def num(key, default=0):
        try:
            return int(prof.get(key) or default)
        except (TypeError, ValueError):
            return default

    gems = [v for v in text("gems").split(",") if v.strip() != ""]
    return [name, num("sex", 1), text("classLv"), text("className", ""),
            int(score or 0), text("tgem"), ",".join(gems) or "0",
            num("titem"), num("tcard"), num("tcard2")]


def lp3_rank_rows() -> list:
    """rank_rows(), converted to the array shape LP3 reads.

    LP3's own board (`gameResult3`) feeds the score column, not LP1's.
    """
    profiles = {}
    for a in accounts.all_accounts():
        prof = dict(a.get("profile") or {})
        # gems/tGem/tItem/tCard/tCard2 are saved into the account's `progress`, not
        # its profile (the profile merge in cloud_login_reply does this for the
        # login reply) - without the merge every rank row's totals read 0.
        for k, v in (accounts.get_progress(a) or {}).items():
            prof.setdefault(k, v)
        profiles[prof.get("name") or a.get("login_name") or a.get("email") or "?"] = prof
    return [lp3_array_row(profiles.get(r["name"])
                          or CURRENT_PLAYER.get("profile") or load_profile() or {},
                          r["score"])
            for r in rank_rows(board_key="gameResult3")]


def lp2_rank_rows() -> list:
    """rank_rows(), converted to the array shape LP2 reads.

    LP2's 總成績 comes from LP2's own board, the saved `scoreReport`, not from the
    board another title happened to write.
    """
    profiles = {}
    for a in accounts.all_accounts():
        prof = a.get("profile") or {}
        profiles[prof.get("name") or a.get("login_name") or a.get("email") or "?"] = prof
    return [lp2_array_row(profiles.get(r["name"])
                          or CURRENT_PLAYER.get("profile") or load_profile() or {},
                          r["score"])
            for r in rank_rows(board_of=lambda a: lp2_score_report(accounts.get_progress(a)))]


def rank_reply(service_lower: str, game: str = "") -> bytes:
    """A populated rank board in the shape the asking game expects."""
    rows = rank_rows()
    if service_lower.startswith("getmonth"):
        # the MMO's monthly boards: {response, rank:[...], self: rank-or-'No'}
        # who is asking? CURRENT_PLAYER holds the profile the last login used.
        me = ((CURRENT_PLAYER.get("profile") or {}).get("name")
              or (CURRENT_PLAYER.get("email") or ""))
        mine = "No"
        for row in rows:
            if me and row.get("name") == me:
                mine = row["rank"]
                break
        log.info(f"  rank: '{service_lower}' -> {len(rows)} row(s), self={mine}")
        return amf0.encode([amf0.AmfObject({
            "response": service_lower.replace("_", "").replace(".", ""),
            "rank": rows, "self": mine})])
    if game.lower() == "prince2":
        # arrays, not dicts - see lp2_array_row
        lp2 = lp2_rank_rows()
        board = {"scoreRank": lp2, "gemRank": lp2, "itemRank": lp2}
    elif game.lower() == "prince3":
        # arrays, not dicts - same reason as prince2 (see lp3_array_row)
        lp3 = lp3_rank_rows()
        board = {"score_rank": lp3, "star_rank": lp3, "equip_rank": lp3}
    else:
        board = {"score_rank": rows, "gem_rank": rows, "card_rank": rows}
    log.info(f"  rank: getRank ({game or 'prince1'}) -> {len(rows)} row(s)")
    return amf0.encode([amf0.AmfObject({"response": "getRank", **board})])


# ── friends: what the mini-games' 1st/2nd/3rd board is drawn from ────────────
# The end-of-game board is NOT the rank board.  UI_base.label_preload() calls
# RemoteService.getFriendResultInGame(gid, glv), and UI_base.getFriendResultInGame()
# fills four slots from `reply.list[i]` as POSITIONAL rows
#
#     [0] uid   [1] name   [2] score   [3..18] the 16 appearance parts
#
# in UserRecord.charSettingList order.  A slot with no row reads "-----", and the
# player's own row is never drawn in a slot - it goes to the footer's `me` panel
# with the rank position found in the list.  We had no handler for it at all, so
# the reply was the generic {response:"ok"}: `param1.list` was undefined, the
# `if(param1.list)` guard failed, and every slot stayed blank.
MMO_CHAR_PARTS = ("hat", "hair", "ears", "blusher", "mouth", "eyes", "eyeblows",
                  "nose", "left_acc", "right_acc", "left_item", "right_item",
                  "cloth", "trousers", "shoes", "tail")
# The publisher's own login4 reply for a fresh account carries exactly this
# outfit and Character.addItem's fallback list names the same parts, so the
# default is the white kit with NO hat - an empty slot draws nothing at all
# (the crown + prince tunic that used to sit here are the little prince NPC's
# own clothes, which is why the site's avatar looked like a different character).
DEFAULT_CLOTH = ("", "髮3", "耳1", "面珠1", "口1", "眼1", "眉1", "鼻1",
                 "", "", "", "", "運動服", "運動褲", "運動鞋", "")
LEVEL_SCORES_PATH = Path(__file__).parent / "level_scores.json"
LEVEL_SCORES_LOCK = threading.Lock()


def level_scores() -> dict:
    """Per-player best score for each game level: {uid: {"<gid>-<glv>": best}}."""
    try:
        data = json.loads(LEVEL_SCORES_PATH.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:                                                 # noqa: BLE001
        return {}


def best_level_score(uid, gid, glv) -> int:
    entry = level_scores().get(str(uid)) or {}
    try:
        return int(float(entry.get("%s-%s" % (gid, glv)) or 0))
    except (TypeError, ValueError):
        return 0


def remember_level_score(uid, gid, glv, score) -> None:
    """Keep the best score this player has ever reached on one game level."""
    if not uid:
        return
    with LEVEL_SCORES_LOCK:
        data = level_scores()
        entry = data.get(str(uid))
        if not isinstance(entry, dict):
            entry = {}
        key = "%s-%s" % (gid, glv)
        try:
            if int(float(entry.get(key) or 0)) >= int(score):
                return
        except (TypeError, ValueError):
            pass
        entry[key] = int(score)
        data[str(uid)] = entry
        try:
            LEVEL_SCORES_PATH.write_text(json.dumps(data, indent=1), "utf-8")
        except Exception as exc:                                      # noqa: BLE001
            log.error(f"  could not save level scores: {exc}")


# ─── the player card: one account's stats and standing, game by game ────────
# What each game actually stores (the same fields the Mods panel writes, see
# MODS_FIELDS) is spread over the account's `profile` (the MMO) and its
# `progress` (the mini-games), so the card reads both and never invents a
# number: a field the account has never written reads as "not played yet".

def _csv_ints(value) -> list:
    """'3,3,0' -> [3, 3, 0]; anything unparseable is dropped."""
    out = []
    for part in str(value or "").replace(" ", "").split(","):
        if not part:
            continue
        try:
            out.append(int(float(part)))
        except ValueError:
            continue
    return out


def _pair_total(value, step=2, take=1) -> tuple:
    """'11,2,12,5' -> (total, how many ids) for the paired lists the games send.

    LP2 stores per-id amounts as flat pairs (gemID, amount) - `step` values per
    id, and the amount is the one after the id (`take`), so a gem count is the
    sum of every second number, not the sum of all of them.
    """
    vals = _csv_ints(value)
    total, ids = 0, 0
    for i in range(0, len(vals) - step + 1, step):
        total += vals[i + take]
        ids += 1
    return total, ids


def _stat(label, value, hint="") -> dict:
    return {"label": label, "value": value, "hint": hint}


# LPO's mission table: gid -> (world, title). gids are 1-based, 5 games per world.
LPO_GAME_TITLES = {}
_world_names = ("Magic World", "Toy World", "Beach World", "Ice World", "Bug World",
                "Cloud World", "Ancient World", "Ninja World", "Christmas Factory")
_counts = (7, 6, 7, 6, 4, 5, 6, 5, 5)
_gid = 1
for _wname, _cnt in zip(_world_names, _counts):
    for _i in range(1, _cnt + 1):
        LPO_GAME_TITLES[_gid] = (_wname, f"{_wname} game {_i}")
        _gid += 1


def recent_play_rows(acct, limit=6) -> list:
    """The home page's Recent play list, newest first.

    LPO reports one row per level with setScore2: [gid, glv, first, firstDate,
    last, lastDate, highest, highestDate, ...] (see save_level_scores).  The
    client's own dates are "YYYY/MM/DD hh:mm" strings - shown as-is.  LP1-3
    saves carry no date, so those games fall back to the account's last_login.
    """
    prof = acct.get("profile") or {}
    rows = []

    # ── LPO levels with real timestamps from the level-score store ──
    uid = str(acct.get("uid") or prof.get("uid") or "")
    stored = level_scores().get(uid) or {}
    for key, best in sorted(stored.items(), key=lambda kv: kv[1], reverse=True):
        try:
            gid_s, glv_s = key.split("-", 1)
            gid, glv = int(gid_s), int(glv_s)
        except ValueError:
            continue
        world, title = LPO_GAME_TITLES.get(gid, ("LPO", f"game {gid}"))
        rows.append({"title": title,
                     "when": f"{world} · level {glv + 1}",
                     "score": str(best)})

    # ── LP1-3: best per level from the gameResult board (no client date) ──
    lp_names = ("星願小王子 (LP1)", "星願外傳 (LP2)", "星願歷奇 (LP3)")
    for gi, gname in enumerate(lp_names):
        board = acct.get("gameResult")
        if not isinstance(board, list) or gi >= len(board):
            continue
        world = board[gi]
        if not isinstance(world, list):
            continue
        best_row, best_val = None, -1
        for lv, level in enumerate([x for x in world if isinstance(x, list)]):
            for played in level:
                if isinstance(played, list) and len(played) >= 5:
                    try:
                        v = int(played[4])
                    except (TypeError, ValueError):
                        continue
                    if v > best_val:
                        best_val, best_row = v, (lv, played)
        if best_row and best_val > 0:
            lv, played = best_row
            rows.append({"title": f"{gname} level {lv + 1}",
                         "when": f"last login {acct.get('last_login') or '—'}",
                         "score": str(best_val)})

    rows.sort(key=lambda r: 0 if r["when"].startswith(("Magic", "Toy", "Beach", "Ice",
                                                       "Bug", "Cloud", "Ancient",
                                                       "Ninja", "Christmas")) else 1)
    return rows[:limit]


def avatar_ensure(prof: dict, view: str = "full"):
    """(url, path) for this player's own character picture, drawn from its clothes.

    The suit is the one the game is served (cloth_parts fills the defaults), so
    the picture and the character in the room cannot disagree.  `view="head"` gives
    the same character cropped to the head, for the round avatar in the page header
    - a full-body render shrunk into a 64px circle is a smudge, not a face.
    """
    try:
        return avatar.ensure(dict(zip(MMO_CHAR_PARTS, cloth_parts(prof))), view)
    except Exception as e:
        log.warning("  could not draw this account's character: %s" % e)
        return None, None


def player_card_games(prof: dict, prog: dict) -> list:
    """The four games' stat blocks for one player (profile + progress merged)."""
    p = dict(prof or {})
    for k, v in (prog or {}).items():
        if str(v) not in ("", "None"):
            p.setdefault(k, v)

    # ── LP1: stars are one 0-3 value per level, in level order ──
    stars = _csv_ints(p.get("stars"))
    cards1 = _csv_ints(p.get("cards"))
    levels = len(globals().get("LP1_LEVELS") or []) or len(stars)
    earned = sum(stars)
    possible = levels * 3 if levels else None          # 0-3 per level (MODS_FIELDS)
    perfect = sum(1 for v in stars if v >= 3)
    played = sum(1 for v in stars if v > 0)
    gems1 = _csv_ints(p.get("gems"))
    gem_slots = len(gems1) or int(globals().get("GEM_COUNT") or 0)
    lp1 = [_stat("Stars", f"{earned} / {possible}" if possible else str(earned),
                 f"{perfect} perfect · {played} of {levels or '?'} level(s) played"),
           _stat("Gems", str(sum(gems1)),
                 f"{sum(1 for g in gems1 if g)} of {gem_slots or '?'} counters set"),
           _stat("Cards", str(len([c for c in cards1 if c])), "card ids owned"),
           _stat("Ending", "seen" if str(p.get("ending") or "0") not in ("0", "") else "not yet",
                 "the ending flag")]
    # `any(None)` is a TypeError, not a False: an account with no `cards` key at
    # all took the whole player card down with it (the page sat on
    # "Reading this account's records..." for ever, because the request never
    # came back).  `_csv_ints` already answers [] for anything missing.
    if not any(stars or gems1 or cards1):
        lp1 = []

    # ── LP2: per-id amounts; bosses and the weapon list are plain lists ──
    gem_total, gem_ids = _pair_total(p.get("setGem"))
    item_total, item_ids = _pair_total(p.get("setItem"))
    lp2 = [s for s in (
        _stat("Gems", str(gem_total), f"{gem_ids} gem kind(s)"),
        _stat("Items", str(item_total), f"{item_ids} item kind(s)"),
        _stat("Bosses beaten", str(len(_csv_ints(p.get("defeatedBoss")))), "from the boss record"),
        _stat("Weapons", str(len(_csv_ints(p.get("equipment")))), "equipment list"),
    ) if s["value"] not in ("0", "")] or []

    # ── LP3: totals the client keeps, plus the counters behind them ──
    g3 = _csv_ints(p.get("gems"))
    cards3 = _csv_ints(p.get("cards"))
    gc3 = _csv_ints(p.get("gameCards"))
    lp3 = [s for s in (
        _stat("Gems", str(p.get("tGem") or sum(g3) or 0), f"{sum(1 for g in g3 if g)} of {len(g3)} counters"),
        _stat("Items", str(p.get("tItem") or 0), f"{sum(1 for i in _csv_ints(p.get('items')) if i)} held"),
        _stat("Cards", str(p.get("tCard") or 0), f"{sum(1 for c in cards3 if c)} of {len(cards3)} slots"),
        _stat("Panels open", str(sum(1 for c in gc3 if c)), f"of {len(gc3)} card panels"),
        _stat("Story", str(p.get("process") or 0), "how far it has gone"),
    ) if s["value"] not in ("0", "")] or []

    # ── LPO: the MMO keeps everything in the player record itself ──
    crystals = [p.get("crystal%d" % i) for i in range(5)]
    try:
        cryst_sum = sum(int(float(c or 0)) for c in crystals)
    except (TypeError, ValueError):
        cryst_sum = 0
    lpo = [s for s in (
        _stat("Coins", str(p.get("coins") or 0), "the MMO's coin count"),
        _stat("Crystals", str(p.get("totalCrystals") or cryst_sum),
              "world 1-5: " + " / ".join(str(c or 0) for c in crystals)),
        _stat("Items", str(p.get("totalItems") or 0), "total items"),
        _stat("Maze record", str(p.get("mazeRec") or "—"), "the daily maze"),
        _stat("Events", str(p.get("eventData") or 0), "event counter"),
    ) if s["value"] not in ("0", "")] or []

    return [
        {"game": "LP1", "title": "星願小王子", "stats": lp1,
         "note": "Stars are one 0-3 value per level; gems are the 8 counters the mini-games pay."},
        {"game": "LP2", "title": "星願外傳", "stats": lp2,
         "note": "Gems and items are per-id amounts; the boss record and weapons are lists."},
        {"game": "LP3", "title": "星願歷奇", "stats": lp3,
         "note": "The totals the game's own header shows, plus the counters behind them."},
        {"game": "LPO", "title": "小王子 Online", "stats": lpo,
         "note": "The MMO's player record - the same numbers the castle's HUD reads."},
    ]


def player_card_avatar(prof: dict) -> dict:
    """The character art the client draws, plus the 16 parts this account has.

    The look lives in lib/character_anim.swf and the client only ever sets it at
    runtime, so the page can show the art (Ruffle) and the part values the server
    would hand the game - with every part marked when it is only the default.
    """
    prof = prof or {}
    parts = []
    for i, key in enumerate(MMO_CHAR_PARTS):
        val = prof.get(key)
        mine = val not in (None, "")
        parts.append({"part": key, "value": str(val) if mine else str(DEFAULT_CLOTH[i]),
                      "mine": bool(mine)})
    return {
        "swf": "/lib/character_anim.swf",
        "parts": parts,
        "custom": sum(1 for x in parts if x["mine"]),
        "picture": avatar.available(),
        "note": ("The character the game itself draws: lib/character_anim.swf with the"
                 " parts below pasted into their own clips, so this is what the player"
                 " looks like in the room."
                 if avatar.available() else
                 "The parts below are what the server hands the client at login;"
                 " the character picture is not drawn here: %s"
                 % avatar.why_not()),
    }


def player_card_payload(email: str) -> dict:
    """Everything the profile page shows for one account."""
    acct = accounts.get(email) if email else None
    if not acct:
        raise ValueError("no account %s on this machine" % (email or "?"))
    prof = acct.get("profile") or {}
    prog = accounts.get_progress(acct) or {}
    rows = rank_rows()
    me = None
    for row in rows:
        if (row.get("uid") and row["uid"] == str(acct.get("uid"))) or \
           (row.get("name") and row["name"] == (prof.get("name") or "")):
            me = row
            break
    url, _path = avatar_ensure(prof)
    return {
        "avatar_url": url,
        "email": acct.get("email"),
        "login_name": acct.get("login_name") or "",
        "name": prof.get("name") or acct.get("login_name") or acct.get("email"),
        "uid": str(acct.get("uid") or ""),
        "created": acct.get("created") or "",
        "last_login": acct.get("last_login") or "",
        "games": player_card_games(prof, prog),
        "avatar": player_card_avatar(prof),
        "board": {
            "me": ({"rank": me["rank"], "score": me["score"], "of": len(rows)} if me else None),
            "rows": [{"rank": r["rank"], "name": r["name"], "score": r["score"],
                      "scoreMonth": r.get("scoreMonth") or 0,
                      "coins": r["coins"], "coinsMonth": r.get("coinsMonth") or 0,
                      "items": r["items"], "itemsMonth": r.get("itemsMonth") or 0,
                      "crystals": r.get("crystals") or 0,
                      "crystalsMonth": r.get("crystalsMonth") or 0,
                      "maze": r.get("maze") or 0,
                      "mazeMonth": r.get("mazeMonth") or 0,
                      "me": bool(me and r["uid"] == me["uid"] and r["name"] == me["name"])}
                     for r in rows[:RANK_SIZE]],
            "note": ("Built from the accounts on this machine - it is exactly what the"
                     " games' own boards show. The publisher's global board is offline."),
        },
    }


def cloth_parts(prof: dict) -> list:
    """The 16 appearance parts of a reply row, in charSettingList order."""
    prof = prof or {}
    out = []
    for i, key in enumerate(MMO_CHAR_PARTS):
        val = prof.get(key)
        out.append(str(val) if val not in (None, "") else DEFAULT_CLOTH[i])
    return out


LPO_ITEM_CACHE = None
LPO_UNLIMITED_USES = "999999"          # the floor the mod keeps the weapons at
LPO_SPORTSWEAR = ("運動服", "運動褲", "運動鞋")   # addItem() refuses these


def lpo_item_catalogue() -> list:
    """Every item id in the client's own settings.cxd, in file order.

    That file is what the client's searchItemType/searchItemData read, so the list
    cannot drift from the game: hat/cloth/shoes/trousers/weapons/items and the
    appearance parts.  Cached - the file never changes while the server runs.
    """
    global LPO_ITEM_CACHE
    if LPO_ITEM_CACHE is not None:
        return LPO_ITEM_CACHE
    ids = []
    import re as _re
    import zlib as _zlib
    for candidate in (GAME_DIR / "settings.cxd", GAME_DIR / "game/settings.cxd"):
        try:
            if not candidate.is_file():
                continue
            xml = _zlib.decompress(candidate.read_bytes()).decode("utf-8", "replace")
            block = _re.search(r"<items>(.*?)</items>", xml, _re.S)
            if not block:
                continue
            for chunk in _re.findall(r'<type name="[^"]+">(.*?)</type>', block.group(1), _re.S):
                ids.extend(_re.findall(r'<item [^>]*id="([^"]+)"', chunk))
            if ids:
                log.info("  LPO item catalogue: %d items from %s" % (len(ids), candidate.name))
                break
        except Exception as exc:                                      # noqa: BLE001
            log.warning("  could not read the item catalogue from %s: %s" % (candidate, exc))
    LPO_ITEM_CACHE = ids
    return ids


LPO_ALL_ITEMS_CACHE = None


def lpo_all_item_rows() -> list:
    """The whole wardrobe as reply rows: [[1, name], ...]."""
    global LPO_ALL_ITEMS_CACHE
    if LPO_ALL_ITEMS_CACHE is None:
        LPO_ALL_ITEMS_CACHE = [[1, name] for name in lpo_item_catalogue()
                               if name not in LPO_SPORTSWEAR]
    return LPO_ALL_ITEMS_CACHE


def lpo_profile_items(prof: dict):
    """The account's own item rows, as the reply wants them, or None.

    Written by the mods preset (every item) or by the client's own addItem/removeItem
    saves; stored as JSON under the profile's `items`.  None means "leave the captured
    array alone", which is what an account that never touched its wardrobe gets.
    """
    import json as _json
    raw = (prof or {}).get("items")
    if raw in (None, ""):
        return None
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except Exception:                                            # noqa: BLE001
            return None
    if not isinstance(raw, (list, tuple)):
        return None
    rows = []
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        if isinstance(row[1], str) and row[1] in LPO_SPORTSWEAR:
            continue
        out = [int(row[0]), str(row[1])]
        if len(row) >= 4:
            out += [int(row[2]), int(row[3])]
        rows.append(out)
    return rows


def lpo_items_json(names) -> str:
    """[[1, name], ...] -> the JSON string the profile stores."""
    import json as _json
    return _json.dumps([[1, n] for n in names], ensure_ascii=False)


def known_players() -> list:
    """(uid, name, profile) for every player this machine knows.

    The accounts are this machine's real players - the only friends a board can
    honestly be built from - and the built-in default profile is the player
    themselves, so it counts even when they have no account record yet.
    """
    rows, seen = [], set()
    for acct in accounts.all_accounts():
        prof = acct.get("profile") or {}
        uid = str(acct.get("uid") or prof.get("uid") or "")
        name = (prof.get("name") or acct.get("login_name")
                or acct.get("email") or "?")
        rows.append((uid, name, prof))
        seen.add(uid)
    me = CURRENT_PLAYER.get("profile") or load_profile()
    uid = str(me.get("uid") or "")
    if uid not in seen:
        rows.append((uid, me.get("name") or "Player", me))
    return rows


FRIENDS_PATH = Path(__file__).resolve().parent / "friends.json"
MAILS_PATH = Path(__file__).resolve().parent / "mails.json"
# Friend requests waiting for the OTHER player's 確定好友 (confirmBeFriend).  Keyed by the
# recipient's account email, holding the uids that asked.  Adding a friend is not instant:
# the request sits here until the recipient accepts it in their Mail panel (the same letter
# the official server sends), which is what makes the friendship.
PENDING_PATH = Path(__file__).resolve().parent / "pending.json"


def _store_load(path: Path) -> dict:
    """Read one of the small per-account stores (friends/mails), never raising."""
    try:
        if path.is_file():
            data = json.loads(path.read_text("utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as exc:                                     # noqa: BLE001
        log.error(f"  could not read {path.name}: {exc}")
    return {}


def _store_save(path: Path, data: dict) -> None:
    try:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, path)
    except Exception as exc:                                     # noqa: BLE001
        log.error(f"  could not write {path.name}: {exc}")


def _me_email() -> str:
    return str(CURRENT_PLAYER.get("email") or "").strip().lower()


def _me_uid() -> str:
    return str((CURRENT_PLAYER.get("profile") or load_profile()).get("uid") or "")


def my_friend_uids() -> list:
    return [str(u) for u in (_store_load(FRIENDS_PATH).get(_me_email()) or [])]


def _set_friends(uids: list) -> None:
    store = _store_load(FRIENDS_PATH)
    store[_me_email()] = uids
    _store_save(FRIENDS_PATH, store)


def _account_email_for_uid(uid: str) -> str:
    for acct in accounts.all_accounts():
        prof = acct.get("profile") or {}
        if str(acct.get("uid") or prof.get("uid") or "") == str(uid):
            return str(acct.get("email") or "").strip().lower()
    return ""


def pending_requests(email: str = "") -> list:
    """The uids that asked THIS account to be their friend and are not answered yet."""
    key = (email or _me_email()).strip().lower()
    return [str(u) for u in (_store_load(PENDING_PATH).get(key) or [])]


def _pending_add(recipient_uid: str, requester_uid: str) -> bool:
    """Record one request on the RECIPIENT's account - false if it cannot be / already is."""
    email = _account_email_for_uid(recipient_uid)
    if not email or not requester_uid or email == _me_email():
        return False
    store = _store_load(PENDING_PATH)
    rows = [str(u) for u in (store.get(email) or [])]
    if requester_uid in rows:
        return False
    rows.append(requester_uid)
    store[email] = rows
    _store_save(PENDING_PATH, store)
    return True


def _pending_remove(email: str, requester_uid: str) -> bool:
    """Answer one request: drop the requester from that account's pending list."""
    email = (email or "").strip().lower()
    requester_uid = str(requester_uid or "")
    store = _store_load(PENDING_PATH)
    rows = [str(u) for u in (store.get(email) or [])]
    if not requester_uid or requester_uid not in rows:
        return False
    store[email] = [u for u in rows if u != requester_uid]
    _store_save(PENDING_PATH, store)
    return True


def _request_object(raw_body: bytes) -> dict:
    """The decoded request dict that names its service in `type`.

    The client packs its requests as an ECMA array (`reqestList`), so the
    values arrive nested - [ [ {"0": {...the request...}} ] ] - and the
    request itself sits inside a dict keyed "0".  Dig through lists and
    keyed wrappers until a dict with `type` turns up (the same nesting
    _collect_pairs already walks for the older handlers).
    """
    def dig(value, depth=0):
        if depth > 6:
            return None
        if isinstance(value, dict):
            if value.get("type"):
                return value
            for v in value.values():
                found = dig(v, depth + 1)
                if found:
                    return found
        elif isinstance(value, (list, tuple)):
            for v in value:
                found = dig(v, depth + 1)
                if found:
                    return found
        return None

    for value in request_values(raw_body):
        found = dig(value)
        if found:
            return found
    return {}


def _num_str(v) -> str:
    """AMF numbers arrive as floats - '10003.0' has to read as '10003'."""
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else str(v)
    if isinstance(v, (int, str)):
        return str(v).strip()
    return ""


def _int_or(v, default: int = 0) -> int:
    """An integer field where 0 is a REAL value, not "missing".

    `int(row.get("type") or 1)` reads as "1 when the field is absent", but `0 or 1`
    is 1 - so a stored type 0 (a plain letter) was handed to the Mail panel as a
    type 1, and updateView draws the 確認朋友 button on every type-1 row.  A plain
    letter therefore offered the player a button that adds a friendship nobody
    asked for, and the letter it "answered" could never be the one it came from.
    """
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return int(default)


def _as_list(v) -> list:
    """AMF arrays may arrive as strict lists OR ECMA arrays (numeric-keyed dicts)."""
    if isinstance(v, (list, tuple)):
        return list(v)
    if isinstance(v, dict):
        return [v.get(i, v.get(str(i))) for i in range(len(v))]
    return []


def _request_uid(raw_body: bytes) -> str:
    """A friend uid from a request whose `data` is the uid (or [uid, msg])."""
    data = _as_list(_request_object(raw_body).get("data"))
    return _num_str(data[0]) if data else _num_str(_request_object(raw_body).get("data"))


def _fid(uid: str) -> int:
    try:
        return int(float(uid))
    except (TypeError, ValueError):
        return 0


def _mutual_friend_names(their_uid: str) -> list:
    """Names of the players who are friends with BOTH this player and `their_uid`.

    The AddFriend panel's 共同朋友 box is fed from the search reply: RemoteService's
    findFriends branch takes the row, splices off the five fields and the sixteen
    appearance parts, and reads whatever is left as `flist` (a list of names), then
    AddFriend.showSearchResult does `flist.length` on it.  A reply without that
    element leaves `flist` undefined - and that TypeError kills the rest of
    showSearchResult, including the line that hides the page arrows.
    """
    their_email = _account_email_for_uid(their_uid)
    if not their_email:
        return []
    store = _store_load(FRIENDS_PATH)
    mine = {str(u) for u in (store.get(_me_email()) or [])}
    names = {str(u): n for u, n, _p in known_players()}
    out, seen = [], set()
    for uid in (store.get(their_email) or []):
        uid = str(uid)
        if uid in mine and uid not in seen:
            seen.add(uid)
            out.append(names.get(uid) or "?")
    return out


def find_friends_reply(raw_body: bytes) -> bytes:
    """findFriends2 - the AddFriend panel's search over the local accounts.

    Reply rows are [uid, name, sex, gameLv, createDate, *16 appearance parts, mutual
    friends] - the shape RemoteService's findFriends branch reads, including the
    trailing list it keeps as `flist` for the 共同朋友 button.
    """
    args = _as_list(_request_object(raw_body).get("data"))

    def _s(i: int) -> str:
        v = args[i] if i < len(args) else ""
        return _num_str(v) if i == 0 else (str(v).strip() if v is not None else "")

    want_id, want_email, want_name = _s(0), _s(1).lower(), _s(2)
    if want_id == "0":                     # empty id field means "no id filter",
        want_id = ""                       # and an all-empty search finds nothing
    try:
        want_sex = int(float(args[3])) if len(args) > 3 and args[3] is not None else 0
    except (TypeError, ValueError):
        want_sex = 0
    rows = []
    if want_id or want_email or want_name:
        me = _me_uid()
        for acct in accounts.all_accounts():
            prof = acct.get("profile") or {}
            uid = str(acct.get("uid") or prof.get("uid") or "")
            name = (prof.get("name") or acct.get("login_name")
                    or acct.get("email") or "?")
            if not uid or uid == me:
                continue
            if want_id and want_id not in ("0", uid):
                continue
            if want_email and want_email not in str(acct.get("email") or "").lower():
                continue
            if want_name and want_name.lower() not in str(name).lower():
                continue
            try:
                sex = int(prof.get("sex") or 1)
            except (TypeError, ValueError):
                sex = 1
            if want_sex in (1, 2) and sex != want_sex:
                continue
            rows.append([uid, name, str(sex), valid_title(prof.get("gameLv")),
                         str(prof.get("createDate") or "")] + cloth_parts(prof)
                        + [_mutual_friend_names(uid)])
    log.info(f"  findFriends: {len(rows)} match(es)"
             + (", mutual friends %s" % [len(r[-1]) for r in rows] if rows else ""))
    return amf0.encode([amf0.AmfObject({"response": "findFriends", "list": rows})])


def request_be_friend_reply(raw_body: bytes) -> bytes:
    """requestBeFriend (data=[uid, msg]): ASK to be friends - it is NOT the friendship.

    The official flow is a request the other player has to accept, and the acceptance
    is confirmBeFriend (the Mail panel's 確定好友 button on the letter).  So the request
    is recorded on the RECIPIENT's account (pending.json) and delivered as the same
    type-1 letter the official server sends - their Mail panel shows the button and
    pressing it is what adds the friendship.
    """
    obj = _request_object(raw_body)
    data = _as_list(obj.get("data"))
    uid = _num_str(data[0]) if data else _num_str(obj.get("data"))
    msg = str(obj.get("msg") or (data[1] if len(data) > 1 else "") or "").strip()
    me_uid = _me_uid()
    pending = False
    delivered = False
    if uid and uid != me_uid:
        pending = _pending_add(uid, me_uid)
        # The client always sends its own invitation text (messageEdit's literal); this is
        # the fallback for a request that arrived without one.
        delivered = _deliver_mail(uid, msg or "我誠意邀請你成為我的朋友。", kind=1)
    log.info(f"  requestBeFriend: {me_uid or '?'} -> {uid or '?'} pending="
             f"{'yes' if pending else 'no'} letter={'sent' if delivered else 'not sent'}"
             f" (waits for their 確定好友)")
    return amf0.encode([amf0.AmfObject({"response": "requestBeFriend",
                                        "fid": _fid(uid),
                                        "pending": "1" if pending else "0"})])


def confirm_be_friend_reply(raw_body: bytes) -> bytes:
    """confirmBeFriend (data=uid): the Mail panel's 確定好友 - THIS makes the friendship.

    Accepting the request adds the requester to this player's friends, adds this player
    to the requester's (the game's friendship is mutual), clears the pending request, and
    consumes the letter the request arrived in.
    """
    uid = _request_uid(raw_body)
    added = False
    me_uid = _me_uid()
    consumed = 0
    if uid and uid != me_uid:
        uids = my_friend_uids()
        if uid not in uids:
            uids.append(uid)
            _set_friends(uids)
            added = True
        _pending_remove(_me_email(), uid)
        other = _account_email_for_uid(uid)
        if other and me_uid:
            store = _store_load(FRIENDS_PATH)
            theirs = [str(u) for u in (store.get(other) or [])]
            if me_uid not in theirs:
                theirs.append(me_uid)
                store[other] = theirs
                _store_save(FRIENDS_PATH, store)
                log.info(f"  confirmBeFriend: {me_uid} added to {other}'s friends too")
        if other:
            _pending_remove(other, me_uid)
        consumed = _consume_request_letters(uid)
    log.info(f"  confirmBeFriend: {uid or '?'} -> {len(my_friend_uids())} friend(s)"
             f"{' (added)' if added else ''}"
             f"{', request letter consumed' if consumed else ''}")
    return amf0.encode([amf0.AmfObject({"response": "confirmBeFriend",
                                        "fid": _fid(uid)})])


def delete_my_friend_reply(raw_body: bytes) -> bytes:
    """deleteMyFriend (data=uid): drop the uid from this player's friends."""
    uid = _request_uid(raw_body)
    uids = [u for u in my_friend_uids() if u != uid]
    _set_friends(uids)
    log.info(f"  deleteMyFriend: {uid or '?'} -> {len(uids)} friend(s)")
    return amf0.encode([amf0.AmfObject({"response": "deleteMyFriend",
                                        "fid": _fid(uid)})])


def _next_mail_id(store: dict) -> int:
    top = 0
    for rows in store.values():
        for row in rows or []:
            try:
                top = max(top, int(row.get("mid") or 0))
            except (TypeError, ValueError):
                continue
    return top + 1


def _deliver_mail(to_uid: str, text: str, kind: int = 1, from_uid: str = "") -> bool:
    """Write one letter into the recipient's mailbox - their Mail panel reads it.

    `kind` is the letter's `type`, and the panel keys its buttons off it: 0 = plain
    letter (Reply), 1 = a friend request (the 確定好友 / add-friend button), 2 = an
    item gift.  A friend request has to arrive as type 1 or the other player is never
    offered the button that accepts it.
    """
    target = _account_email_for_uid(to_uid)
    sender = from_uid or _me_uid()
    if not target or target == _me_email():
        return False
    store = _store_load(MAILS_PATH)
    rows = store.get(target) or []
    rows.append({"mid": _next_mail_id(store), "from": sender,
                 "date": time.strftime("%Y-%m-%d"), "read": 0, "type": int(kind),
                 "message": text, "can_reply": 1})
    store[target] = rows
    _store_save(MAILS_PATH, store)
    return True


def _consume_request_letters(requester_uid: str) -> int:
    """Drop the friend-request letter(s) an accepted request arrived in.

    The letter's whole purpose was to carry the 確定好友 button, and the client asks
    `checkMail` again the moment the confirm goes out (Mail.afConfirmFriendLetter sets
    `checkInMailAgain`, showMailsEdit re-reads the mailbox).  Leaving the row behind
    made that re-read draw the very same type-1 letter - still unread, still with the
    button - so pressing 確認朋友 looked like it had done nothing at all and the mailbox
    kept asking for an answer already given.  Only type-1 letters from THAT sender go;
    a plain letter (type 0) or an item gift (type 2) from them is left alone.
    """
    email = _me_email()
    uid = _num_str(requester_uid)
    store = _store_load(MAILS_PATH)
    rows = store.get(email) or []
    keep = [r for r in rows
            if not (_int_or(r.get("type"), 0) == 1
                    and _num_str(r.get("from")) == uid)]
    removed = len(rows) - len(keep)
    if removed and uid:
        store[email] = keep
        _store_save(MAILS_PATH, store)
        return removed
    return 0


def mail_to_friend_reply(raw_body: bytes) -> bytes:
    """mailToFriend (data=[uid...], msg=text): deliver into each recipient's store.

    Every recipient is a local account, so the letter is written straight into
    that account's mails.json entry - open the game as them and the owl glows.
    """
    obj = _request_object(raw_body)
    uids = [_num_str(u) for u in _as_list(obj.get("data"))]
    uids = [u for u in uids if u]
    text = str(obj.get("msg") or "")
    sent = 0
    for uid in uids:
        if _deliver_mail(uid, text, kind=1):
            sent += 1
    log.info(f"  mailToFriend: delivered to {sent} of {len(uids)} recipient(s)")
    return amf0.encode([amf0.AmfObject({"response": "mailToFriend"})])


def check_mail_reply() -> bytes:
    """checkMail: ulist = the senders' records, list = the mail rows.

    Row shape [mid, uid, date, read, type, message, can_reply] and ulist rows
    [uid, name, *16 appearance parts] - exactly what the Mail panel reads.
    """
    rows = _store_load(MAILS_PATH).get(_me_email()) or []
    try:
        rows = sorted(rows, key=lambda r: int(r.get("mid") or 0), reverse=True)
    except Exception:                                            # noqa: BLE001
        rows = list(rows)
    senders = {str(r.get("from") or "") for r in rows}
    known = {str(u): (n, p) for u, n, p in known_players()}
    ulist = []
    for uid in sorted(senders):
        if not uid:
            continue
        name, prof = known.get(uid) or (None, None)
        if name is None:
            # The sender is gone from this machine (a deleted account, an old
            # uid): the Mail panel still draws a character for every letter it
            # shows, and setCharacter() on a missing record throws #1009 and
            # wedges the whole panel - so answer with a placeholder record
            # instead of leaving the sender out of the ulist.
            name, prof = "?", {}
        ulist.append([uid, name] + cloth_parts(prof))
    out = []
    for r in rows:
        out.append([int(r.get("mid") or 0), _fid(str(r.get("from") or "")),
                    str(r.get("date") or ""), _int_or(r.get("read"), 0),
                    _int_or(r.get("type"), 1), str(r.get("message") or ""),
                    _int_or(r.get("can_reply"), 0)])
    log.info(f"  checkMail: {len(out)} mail(s) %s"
             % ([[int(x[0]), int(x[4])] for x in out] if out else ""))
    return amf0.encode([amf0.AmfObject({"response": "checkMail",
                                        "ulist": ulist, "list": out})])


def _mail_id_from(raw_body: bytes) -> int:
    data = _request_object(raw_body).get("data")
    if isinstance(data, (list, tuple, dict)):
        data = _as_list(data)
        data = data[0] if data else 0
    try:
        return int(float(data))
    except (TypeError, ValueError):
        return 0


def read_mail_reply(raw_body: bytes) -> bytes:
    """readMail (data=mid): mark it read - the panel already holds the text."""
    mid = _mail_id_from(raw_body)
    store = _store_load(MAILS_PATH)
    rows = store.get(_me_email()) or []
    changed = False
    for r in rows:
        if int(r.get("mid") or 0) == mid and not int(r.get("read") or 0):
            r["read"] = 1
            changed = True
    if changed:
        store[_me_email()] = rows
        _store_save(MAILS_PATH, store)
    return amf0.encode([amf0.AmfObject({"response": "readMail", "mid": mid})])


def delete_mail_reply(raw_body: bytes) -> bytes:
    """deleteMail (data=mid): the bin button."""
    mid = _mail_id_from(raw_body)
    store = _store_load(MAILS_PATH)
    store[_me_email()] = [r for r in (store.get(_me_email()) or [])
                          if int(r.get("mid") or 0) != mid]
    _store_save(MAILS_PATH, store)
    return amf0.encode([amf0.AmfObject({"response": "deleteMail", "mid": mid})])


def have_new_email_reply() -> bytes:
    """haveNewEmail / checkNewEmail: the owl's unread count."""
    rows = _store_load(MAILS_PATH).get(_me_email()) or []
    total = sum(1 for r in rows if not int(r.get("read") or 0))
    log.info(f"  haveNewEmail: {total} unread")
    return amf0.encode([amf0.AmfObject({"response": "haveNewEmail",
                                        "total": str(total)})])


def friend_result_reply(raw_body: bytes) -> bytes:
    """The end-of-game slots: [[uid, name, score, *16 appearance parts], ...]."""
    pairs = {}
    for value in request_values(raw_body):
        _collect_pairs(value, pairs)
    try:
        gid = int(float(pairs.get("gid") or 0))
    except (TypeError, ValueError):
        gid = 0
    try:
        glv = int(float(pairs.get("glv") or 0))
    except (TypeError, ValueError):
        glv = 0
    rows = [[uid, name, best_level_score(uid, gid, glv)] + cloth_parts(prof)
            for uid, name, prof in known_players()]
    rows.sort(key=lambda row: row[2], reverse=True)
    log.info("  friends board (gid=%s glv=%s): %d player(s) %s"
             % (gid, glv, len(rows), [r[1] for r in rows]))
    return amf0.encode([amf0.AmfObject({"response": "friendResultInGame",
                                        "list": rows})])


def friends_reply(service_lower: str) -> bytes:
    """getMyFriends / getMyFriends2: [[uid, name, sex, *16 appearance parts]].

    Only the player's own friends - the uids added through the AddFriend
    panel's search (findFriends -> requestBeFriend), stored per account in
    friends.json.  It used to list every account on the machine, which made
    the Mail panel show "friends" the player had never added.
    """
    me = _me_uid()
    uids = set(my_friend_uids())
    rows = [[uid, name, str(prof.get("sex") or "1")] + cloth_parts(prof)
            for uid, name, prof in known_players()
            if str(uid) in uids and str(uid) != me]
    response = "getMyFriends2" if "2" in service_lower else "getMyFriends"
    log.info(f"  {response}: {len(rows)} player(s)")
    return amf0.encode([amf0.AmfObject({"response": response, "list": rows})])


def save_level_scores(reqs: list) -> None:
    """Keep what setScore2 reports: one game level's best score for this player.

    The row is [gid, glv, first, firstDate, last, lastDate, highest, highestDate,
    ...] and the end-of-game board reads exactly that highest score back - so
    without keeping it every friend scores 0 for ever.
    """
    for req in reqs:
        if str(req.get("type") or "").lower() != "setscore2":
            continue
        data = req.get("data")
        # The online client sends this as an AMF ECMA array - a dict with numeric
        # keys - not a STRICT_ARRAY, so the shape check below dropped every score
        # and the end-of-game board showed 0 for ever.
        if isinstance(data, dict):
            data = [data.get(i, data.get(str(i))) for i in range(15)]
        if not isinstance(data, (list, tuple)) or len(data) < 3:
            continue
        try:
            gid = int(float(data[0]))
            glv = int(float(data[1]))
        except (TypeError, ValueError):
            continue
        best = 0
        for value in ((data[6] if len(data) > 6 else None), data[4], data[2]):
            try:
                best = max(best, int(float(value)))
            except (TypeError, ValueError):
                continue
        uid = str((CURRENT_PLAYER.get("profile") or {}).get("uid") or "")
        if not uid and CURRENT_PLAYER.get("email"):
            for acct in accounts.all_accounts():
                if acct.get("email") == CURRENT_PLAYER.get("email"):
                    uid = str(acct.get("uid") or "")
                    break
        remember_level_score(uid, gid, glv, best)
        # The rank board's score column is fed from the ACCOUNT's gameResult (the
        # six values the old setScore carried: initS, initD, highS, highD,
        # recentS, recentD), but the online client only ever sends setScore2 -
        # so translate the row here or every player's board score stays 0.
        email = CURRENT_PLAYER.get("email")
        if email:
            def _num(i):
                try:
                    return int(float(data[i]))
                except (TypeError, ValueError, IndexError):
                    return 0

            def _txt(i):
                try:
                    return str(data[i])
                except IndexError:
                    return ""

            row = [_num(2), _txt(3), _num(6), _txt(7), _num(4), _txt(5)]
            try:
                accounts.set_game_result(email, gid, glv, row)
            except Exception as exc:                                  # noqa: BLE001
                log.error("  level score: could not update gameResult: %s" % exc)
        log.info(f"  level score: gid={gid} glv={glv} best={best} uid={uid or '?'}")


def store_level_scores(raw_body: bytes) -> None:
    """File every setScore2 in a request - it usually rides in a batch.

    The MMO's save call goes through dispatch_service, not the cloud games' save
    batch, so this is where the row actually arrives.
    """
    reqs = []
    for value in request_values(raw_body):
        reqs.extend(value if isinstance(value, list) else [value])
    save_level_scores([r for r in reqs if isinstance(r, dict)])


def merge_friend_reply(raw_body: bytes, reply: bytes) -> bytes:
    """Answer a friends request that rode along in a batch.

    RemoteService accumulates requests and sends them as one ARRAY, and only the
    first type is dispatched - so a friendResultInGame packed behind another call
    came back with no `list` at all and the footer board drew "-----" in every
    slot.
    """
    low = (raw_body or b"").lower()
    kinds = []
    if b"friendresultingame" in low:
        kinds.append("friendresultingame")
    if b"getmyfriends2" in low:
        kinds.append("getmyfriends2")
    elif b"getmyfriends" in low:
        kinds.append("getmyfriends")
    for kind in ("findfriends2", "requestbefriend", "confirmbefriend",
                 "deletemyfriend", "mailtofriend", "checkmail", "readmail",
                 "deletemail", "havenewemail"):
        if kind.encode() in low:
            kinds.append(kind)
    if not kinds:
        return reply
    try:
        ours = [v for v in amf0.decode(reply) if isinstance(v, dict)]
    except Exception:                                                 # noqa: BLE001
        ours = []
    have = {str(v.get("response") or "").lower() for v in ours}
    added = False
    for kind in kinds:
        if kind in have:
            continue
        if kind == "friendresultingame":
            blob = friend_result_reply(raw_body)
        elif kind.startswith("getmyfriends"):
            blob = friends_reply(kind)
        elif kind == "findfriends2":
            blob = find_friends_reply(raw_body)
        elif kind == "requestbefriend":
            blob = request_be_friend_reply(raw_body)
        elif kind == "confirmbefriend":
            blob = confirm_be_friend_reply(raw_body)
        elif kind == "deletemyfriend":
            blob = delete_my_friend_reply(raw_body)
        elif kind == "mailtofriend":
            blob = mail_to_friend_reply(raw_body)
        elif kind == "checkmail":
            blob = check_mail_reply()
        elif kind == "readmail":
            blob = read_mail_reply(raw_body)
        elif kind == "deletemail":
            blob = delete_mail_reply(raw_body)
        else:
            blob = have_new_email_reply()
        try:
            for value in amf0.decode(blob):
                if isinstance(value, dict):
                    ours.append(value)
                    added = True
        except Exception:                                             # noqa: BLE001
            pass
    if not added:
        return reply
    return amf0.encode(ours)


CURRENT_PLAYER = {"email": "", "profile": None}   # whoever logged in last
QUIET = False                # true while probing offsets: a failed decode is expected


# What each rank board counts.  The two "months" spellings are the service names
# the client uses; both boards read the same account fields here, because the mirror
# keeps one record per account rather than a monthly archive.
RANK_METRICS = {
    "coinsrank": ("coins", "Coins"),
    "coinrank": ("coins", "Coins"),          # the service spells it without the s
    "crystalsrank": ("totalCrystals", "Crystals"),
    "crystalrank": ("totalCrystals", "Crystals"),
    "itemsrank": ("totalItems", "Items"),
    "itemrank": ("totalItems", "Items"),
    "scorerank": ("score", "Score"),
    "mazerank": ("mazeRec", "Maze"),
}


def _rank_value(prof: dict, merged: dict, metric: str) -> int:
    """One account's standing in whatever the board counts."""
    if metric == "score":
        total = 0
        for row in prof.get("gameResult") or []:
            try:
                total += int(row[2])
            except (TypeError, ValueError, IndexError):
                continue
        if not total:
            # Accounts that played before the setScore2 -> gameResult bridge
            # existed only have their scores in level_scores.json - count those
            # too, or their board stays 0 until they replay every level.
            uid = str(prof.get("uid") or "")
            saved = level_scores().get(uid) or {}
            for key, value in saved.items():
                try:
                    total += int(float(value))
                except (TypeError, ValueError):
                    continue
        return total
    if metric == "mazeRec":
        # A maze record like "20260917:3,20260918:5" counts its entries.
        rec = str(merged.get("mazeRec") or prof.get("mazeRec") or "")
        return len([x for x in rec.replace(";", ",").split(",") if x.strip()])
    try:
        return int(float(str(merged.get(metric) or prof.get(metric) or 0)))
    except (TypeError, ValueError):
        return 0


def _month_value(prof: dict, merged: dict, acct: dict, metric: str) -> int:
    """What the month added for one account, for the boards' 本月 views."""
    month_tag = time.strftime("%Y%m")
    if metric in ("score",):
        total = 0
        for game in (prof.get("gameResult") or []):
            if not isinstance(game, list):
                continue
            for row in game:
                if isinstance(row, list) and len(row) > 3:
                    try:
                        if str(row[3] or "").startswith(month_tag):
                            total += int(row[2] or 0)
                    except (TypeError, ValueError):
                        continue
        if not total:
            # pre-bridge scores live in level_scores.json without dates, so the
            # month view falls back to counting them all - better than a blank board
            return _rank_value(prof, merged, "score")
        return total
    if metric == "mazeRec":
        rec = str(merged.get("mazeRec") or prof.get("mazeRec") or "")
        return len([x for x in rec.replace(";", ",").split(",")
                    if x.strip() and x.strip().startswith(month_tag)])
    base = (acct or {}).get("monthBase")
    if not isinstance(base, dict) or base.get("m") != month_tag:
        return 0
    field = {"coins": "coins", "totalItems": "totalItems",
             "totalCrystals": "totalCrystals"}.get(metric)
    if not field or field not in base:
        return 0
    try:
        return max(0, _rank_value(prof, merged, metric) - int(base.get(field) or 0))
    except (TypeError, ValueError):
        return 0


def rank_rows_for(metric: str, month: bool = False) -> list:
    """Every account on this machine, ordered by what the board counts.

    Same sources the player card uses: the profile for the MMO fields, `progress`
    merged in, and the level scores summed for the score board.  With `month` the
    board counts only what this month added (the boards' 本月 view).
    """
    rows = []
    for acct in accounts.all_accounts():
        prof = dict(acct.get("profile") or {})
        merged = dict(prof)
        for k, v in (accounts.get_progress(acct) or {}).items():
            if str(v) in ("", "None"):
                continue
            for key in DEFAULT_PROFILE:
                if key.lower() == str(k).lower():
                    merged[key] = v
        rows.append({
            "name": str(prof.get("name") or acct.get("login_name") or ""),
            "login_name": str(acct.get("login_name") or ""),
            "uid": str(prof.get("uid") or acct.get("uid") or ""),
            "value": (_month_value(prof, merged, acct, metric) if month
                      else _rank_value(prof, merged, metric)),
            "coins": _rank_value(prof, merged, "coins"),
            "crystals": _rank_value(prof, merged, "totalCrystals"),
            "items": _rank_value(prof, merged, "totalItems"),
        })
    rows.sort(key=lambda r: (-r["value"], r["name"]))
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return rows


def lpo_rank_reply(service_type: str, profile: dict = None) -> bytes:
    """One board, built from the accounts on this machine.

    The rows carry positional keys as well as named ones: the notice board proved
    that these panels read rows POSITIONALLY (index 1 = the name line, and so on),
    and a row missing the index it reads throws #2007 mid-draw - the freeze this
    replaces.  `self` is the player's own place, 'No' when they are not on the board,
    which is the value the publisher's own empty answer used.

    Named `lpo_rank_reply` so it cannot shadow the LP2/LP3 `rank_reply` above:
    both used to be `rank_reply`, the later definition won, and LP2/LP3's own
    board then called this one with its game string as `profile` and died with
    "'str' object has no attribute 'get'" - the missing LP2/LP3 leaderboard.
    """
    if profile is None:
        profile = CURRENT_PLAYER.get("profile") or load_profile()
    low = service_type.lower()
    metric = "scorerank"
    for key, (field, _label) in RANK_METRICS.items():
        if key in low:
            metric = field if key != "scorerank" else "score"
            metric_key = key
            break
    else:
        metric_key = "scorerank"
    metric = RANK_METRICS[metric_key][0]
    month = "month" in low
    rows = rank_rows_for(metric, month)

    # The panel builds each row's Character from the player's appearance parts, so the
    # profile behind every row is needed here, keyed the way the row carries it.
    prof_by_uid = {}
    for _uid, _name, _prof in known_players():
        if _uid:
            prof_by_uid[str(_uid)] = _prof

    me = str((profile or {}).get("name") or "")
    mine = next((r for r in rows if me and r["name"] == me), None)
    mine_obj = None
    out = []
    if os.environ.get("LPO_RANK_PROBE") == "1":
        # Probe row: markers on every text-capable slot; parts stay real so the
        # row's Character still builds.  The screenshot maps marker -> widget.
        r0 = rows[0] if rows else {"uid": "0", "name": "?", "value": "0",
                                   "rank": "1", "login_name": "?"}
        prof0 = prof_by_uid.get(r0["uid"]) or {}
        probe = ["11", "22", "1"]
        probe += cloth_parts(prof0)
        probe += ["33", "44", "55", "66", "77"]
        log.info(f"  ranks: PROBE row -> {probe}")
        return amf0.encode([amf0.AmfObject({
            "response": service_type,
            "rank": [probe], "list": [probe], "rows": [probe],
            "count": "1",
            "self": [list(probe)],
            "myRank": "1", "myRankNo": "1",
            "url": "/notice/content/board.xml",
        })])
    for r in rows:
        # Probe map (k10) established the widget order: slot 0 -> the NAME box,
        # slot 1 -> the (invisible) photo, slot 2 -> the score/medal widget.
        # Parts stay [3..18] so the row's Character builds, rank rides after.
        prof = prof_by_uid.get(r["uid"]) or {}
        sex = str(prof.get("sex") or "1")
        arr = [r["name"], "", str(r["value"])]
        arr += cloth_parts(prof)
        arr += [str(r["rank"]), sex, r["login_name"], "", ""]
        out.append(arr)
        if mine is r:
            mine_obj = list(arr)
    log.info(f"  ranks: {service_type} ({metric}) -> {len(out)} row(s), "
             f"self={'#' + str(mine['rank']) if mine else 'No'}")
    return amf0.encode([amf0.AmfObject({
        "response": service_type,
        "rank": out,
        "list": out,
        "rows": out,
        "count": str(len(out)),
        # ARRAY, not a number: RemoteService/serviceResponse coerces this to Array
        # and throws #1034 on a numeric string, which left the board undrawn.
        "self": [mine_obj] if mine_obj is not None else "No",
        # the rank number on its own, under names nothing else uses
        "myRank": str(mine["rank"]) if mine else "No",
        "myRankNo": str(mine["rank"]) if mine else "No",
        # rankingui.swf carries a urlTEXT field, and the notice board showed these
        # panels load their content from a URL the reply hands them - so point it at
        # something the mirror really serves rather than leaving it null.
        "url": "/notice/content/board.xml",
    })])


def score_rank_reply(service_type: str, raw_body: bytes, profile: dict = None) -> bytes:
    """The mini-games' 積分榜: one game, one level, the players' best scores.

    The client's tabs call getMonthScoreRank / getTotalScoreRank with
    `data: [gameID, gameLv]` and re-render the same panel.  Answering with the
    general score board (params ignored) made every tab look dead: the press
    registered, the rows never changed.
    """
    if profile is None:
        profile = CURRENT_PLAYER.get("profile") or load_profile()
    game_id, game_lv = 0, 0
    try:
        parsed = amf0.decode(amf_payload_of(raw_body))
        for item in (parsed if isinstance(parsed, list) else [parsed]):
            data = item.get("data") if isinstance(item, dict) else None
            if isinstance(data, list) and len(data) >= 2:
                game_id, game_lv = int(float(data[0])), int(float(data[1]))
                break
    except Exception:                                            # noqa: BLE001
        pass
    key = "%s-%s" % (game_id, game_lv)
    scores = level_scores()
    rows = []
    for uid, name, prof in known_players():
        entry = scores.get(str(uid)) or {}
        value = 0
        # both spellings: setScore2 has saved "<gid>-0" for the first level while
        # the board asks for "<gid>-1"
        for k in (key, "%s-%s" % (game_id, game_lv - 1)):
            try:
                value = max(value, int(float(entry.get(k) or 0)))
            except (TypeError, ValueError):
                continue
        rows.append({"uid": str(uid), "name": str(name), "value": value, "prof": prof})
    rows.sort(key=lambda r: (-r["value"], r["name"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    me = str((profile or {}).get("name") or "")
    mine = next((r for r in rows if me and r["name"] == me), None)
    mine_obj = None
    out = []
    for r in rows:
        prof = r["prof"] or {}
        sex = str(prof.get("sex") or "1")
        arr = [r["name"], "", str(r["value"])]
        arr += cloth_parts(prof)
        arr += [str(r["rank"]), sex, r["name"], "", ""]
        out.append(arr)
        if mine is r:
            mine_obj = list(arr)
    log.info(f"  ranks: {service_type} game={game_id} lv={game_lv} -> {len(out)} row(s), "
             f"self={'#' + str(mine['rank']) if mine else 'No'}")
    return amf0.encode([amf0.AmfObject({
        "response": service_type,
        "rank": out,
        "list": out,
        "rows": out,
        "count": str(len(out)),
        "self": [mine_obj] if mine_obj is not None else "No",
        "myRank": str(mine["rank"]) if mine else "No",
        "myRankNo": str(mine["rank"]) if mine else "No",
        "url": "/notice/content/board.xml",
    })])


def maze_reply(profile: dict) -> bytes:
    """The daily-maze gate.  The real server answers once a day; here it is a setting,
    open every day by default."""
    val = (profile or {}).get("maze_open", True)
    if val is None or val == "":
        val = True                # never set -> the default, open every day
    if isinstance(val, str):          # the profile keeps everything as text
        open_today = val.strip().lower() not in ("false", "0", "", "no", "off")
    else:
        open_today = bool(val)
    log.info(f"  maze: answering canPlayMaze -> {open_today}")
    return amf0.encode([amf0.AmfObject({"response": "canPlayMaze", "result": open_today})])


CLOUD_LOGIN_TEMPLATE = {
    # every field LP1 / LP2 / LP3 read out of a loginSuccess (their decompiled handlers)
    "response": "loginSuccess",
    "loginName": "", "name": "", "sex": "1", "schoolName": "", "schoolType": "0",
    "classLv": "", "className": "",
    "score": "0", "gems": "", "cards": "", "gameCards": "", "gameResult": [],
    "ending": 0, "language": "0", "fullscreen": "0",
    "screen_quality": "1", "sound_level": "1",
}


def amf_payload_of(packet: bytes) -> bytes:
    """The AMF body inside a gateway packet - skips the envelope when there is one.

    The games send a full packet (version, counts, target, response, length, body);
    decoding that whole thing as bare values misreads it, so the body is taken out
    first and the raw bytes are only used as a fallback.
    """
    try:
        if len(packet) < 10 or packet[0] != 0:
            return packet
        off = 6
        for _ in range(2):                       # target, then response
            n = struct.unpack(">H", packet[off:off + 2])[0]
            off += 2 + n
        n = struct.unpack(">I", packet[off:off + 4])[0]
        off += 4
        if 0 < n <= len(packet) - off:
            return packet[off:off + n]
    except Exception:                                            # noqa: BLE001
        pass
    return packet


def cloud_requests(raw_body: bytes):
    """Unwrap real requests without discarding positional data or batched writes.

    LP2 sends login credentials inside data:[username,password]. Flattening scalar
    properties lost these values. Probing arbitrary byte offsets also interpreted
    string bytes as packet counts and could spend seconds parsing garbage.
    """
    found = []

    def visit(value, depth=0):
        if depth > 16:
            return
        if isinstance(value, dict):
            normalized = {str(k).lower(): v for k, v in value.items()}
            if any(k in normalized for k in ("type", "loginname", "password")):
                found.append(normalized)
            else:
                for child in value.values():
                    visit(child, depth + 1)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child, depth + 1)

    try:
        # Cloud Flash clients use an AMF0 envelope with no headers. Bare AMF
        # values are useful to protocol callers too, but must not be parsed as
        # another envelope or searched at arbitrary offsets.
        if raw_body[:4] in (b'\x00\x00\x00\x00', b'\x00\x03\x00\x00'):
            if len(raw_body) < 6:
                return []
            count = struct.unpack('>H', raw_body[4:6])[0]
            offset = 6
            for _ in range(count):
                for _ in range(2):
                    size = struct.unpack('>H', raw_body[offset:offset + 2])[0]
                    offset += 2 + size
                size = struct.unpack('>I', raw_body[offset:offset + 4])[0]
                offset += 4
                value, end = amf0.decode_one(raw_body, offset)
                if end > len(raw_body):
                    return []
                if size != 0xffffffff and end != offset + size:
                    return []
                visit(value)
                offset = end
        else:
            for value in amf0.decode(raw_body):
                visit(value)
    except (ValueError, IndexError, struct.error, RecursionError):
        return []
    return found


def resolve_login_account(typed: str):
    """Which account the player means when they type `typed` in the game.

    The games' login page is a single name box with no email field, so a player
    types the login name they chose on the accounts page.  Accept, in order: the
    login name, the full email address, then the profile's player name or the part
    before the @.  The last two only count when exactly one account matches, so an
    ambiguous name can never silently open someone else's profile.
    """
    if not typed:
        return None
    exact = accounts.get_by_login(typed)
    if exact:
        return exact
    exact = accounts.get(typed)
    if exact:
        return exact
    want = accounts.normalize(typed)
    hits = []
    for acct in accounts.all_accounts():
        addr = accounts.normalize(acct.get("email"))
        pname = accounts.normalize((acct.get("profile") or {}).get("name") or "")
        if want == addr.split("@", 1)[0] or (pname and want == pname):
            hits.append(acct)
    return hits[0] if len(hits) == 1 else None


# How many levels each of LP1's seventeen games has, read straight out of the
# game's own gameSpec table in start.swf.  The report panel sizes its rows from
# gameSpec and the client sizes user.gameDat from our gameResult, so the two have
# to agree or the whole 個人成績表 fills with undefined.
LP1_LEVELS = [5, 5, 6, 5, 3, 4, 3, 3, 4, 3, 4, 6, 6, 5, 4, 3, 3]
GEM_COUNT = 8                       # setGame() sums gems 0-4 and 5-7


def blank_row():
    """One level's report record: initS, initD, highS, highD, recentS, recentD.

    Empty date strings keep str2Date() (which needs 8 characters) returning null,
    so the panel shows a blank row rather than a bogus date.
    """
    return [0, "", 0, "", 0, ""]


# LP2's mini-games: the level count per game and each level's fullScore, counted
# from the client's own initGameSpec (index.swf).  20 games, 106 levels.
LP2_LEVELS = (
    (100, 150, 200, 250, 300),
    (100, 150, 200, 250, 300, 350, 400),
    (100, 150, 200, 250, 300, 400),
    (100, 200, 300, 400, 500),
    (100, 150, 200, 240, 300, 340, 600),
    (100, 150, 200, 250, 300),
    (100, 150, 200, 250, 300, 350),
    (100, 200, 300, 400, 500),
    (100, 150, 200, 250, 300, 350, 400),
    (100, 200, 300, 400, 500),
    (150, 270, 390, 510),
    (100, 150, 200, 250, 300, 350),
    (100, 200, 240, 270, 320, 400),
    (150, 300, 450, 600),
    (100, 250, 400, 600),
    (100, 150, 200, 250, 300, 350),
    (100, 200, 300, 400),
    (160, 240, 320, 400),
    (150, 350, 400, 600),
    (100, 200, 300, 400, 500, 600),
)

# LP2's whole save record, in the order its own saveUserData passes them to
# PrinceSystem.updateUserInfo.  The client sends all nine in one call.
LP2_USER_INFO_FIELDS = ("equipment", "bossQue", "defeatedBoss", "firstHint",
                        "quality", "musicvolume", "score", "language", "extra")


def _lp2_saved(prog: dict, key: str):
    """One saved field.  Client saves land lower-cased, the panel writes the camelCase
    spelling, so both are tried."""
    prog = prog or {}
    for k in (key, key.lower()):
        if prog.get(k) not in (None, ""):
            return prog[k]
    return None


def _lp2_ints(raw):
    """A stored list, a JSON list or a comma-joined string -> a list of ints."""
    if raw in (None, ""):
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:                                            # noqa: BLE001
            return [int(float(x)) for x in raw.split(",") if str(x).strip()]
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for v in raw:
        try:
            out.append(int(float(v)))
        except (TypeError, ValueError):
            out.append(0)
    return out


def lp2_gem_board(prog: dict) -> list:
    """The 10 能量 gems, by gem id.  Always 10 slots: the client's gemSpec is exactly
    that long and Report indexes gemID-1, so a short save must not shorten the board."""
    vals = _lp2_ints(_lp2_saved(prog, "gemReport"))
    return (vals + [0] * 10)[:10]


# LP2's item catalogue, counted from the client's own initItemSpec (index.swf):
# 6 traders, 36 items, ids "trader-item".  The player's board is `itemReport`, rows of
# [name, amount]; Report.setItemBoard splits the name on "-" and keeps amount as the
# count the trader screen shows.
GAME_POINTS = "999999"        # 積分: the card panels charge 100-400 per card
LP1_POINTS = "999999"        # 積分: the 部首咭 cards cost 100-160 each
LP3_LEVEL_MAXSCORES = [[125, 250, 375, 500], [150, 300, 450], [100, 110, 180, 195, 280, 375], [100, 100, 200, 300, 400], [100, 150, 200, 250, 280, 320], [125, 150, 240, 360, 400], [300, 400, 500], [100, 150, 180, 270, 320, 420], [140, 260, 325, 390], [200, 420, 600], [120, 240, 360, 480], [100, 200, 200, 300, 400], [120, 240, 360, 480], [105, 210, 315, 420], [150, 300, 450, 600], [100, 200, 300], [100, 200, 300, 400, 500], [100, 150, 200], [100, 150, 200], [100, 100, 100], [50, 90, 140, 200, 270, 350], [100, 150, 200], [420, 540, 648], [50, 75, 100, 125, 150, 175, 200]]


LP3_BOSSES_DEFEATED = "3"    # what killBoss() stops counting at
LP3_CARD_FLOOR = "999"      # what an unlimited-cards account keeps its counts at
LP3_LEVEL_COUNTS = [4, 3, 6, 5, 6, 5, 3, 6, 4, 3, 4, 5, 4, 4, 4, 3, 5, 3, 3, 3, 6, 3, 3, 7]


LP2_ITEMS = ['1-0', '1-1', '1-2', '1-3', '1-4', '2-0', '2-1', '2-2', '2-3', '2-4', '3-0', '3-1', '3-2', '3-3', '3-4', '4-0', '4-1', '4-2', '4-3', '4-4', '5-0', '5-1', '5-2', '5-3', '5-4', '6-0', '6-1', '6-2', '6-3', '6-4', '6-5', '6-6', '6-7', '6-8', '6-9', '6-10']
LP2_UNLIMITED_AMOUNT = "999"


def lp2_unlimited_on(prog: dict) -> bool:
    """Has the unlimited-items mod been applied to this account?"""
    prog = prog or {}
    return str(prog.get("lp2unlimited") or prog.get("lp2Unlimited") or "0") == "1"


def lp2_all_item_rows(amount: str = LP2_UNLIMITED_AMOUNT) -> list:
    """The whole catalogue as reply rows: [[id, amount], ...]."""
    return [[i, int(amount)] for i in LP2_ITEMS]


def lp2_item_board(prog: dict) -> list:
    """The item rows the client keeps as [name, amount] (a name is 'trader-item')."""
    raw = _lp2_saved(prog, "itemReport")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:                                            # noqa: BLE001
            return []
    rows = []
    for row in (raw if isinstance(raw, (list, tuple)) else []):
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            try:
                rows.append([str(row[0]), int(float(row[1]))])
            except (TypeError, ValueError):
                continue
    return rows


def lp2_defeated_boss(prog: dict) -> str:
    """The 4 boss slots, 0/1.  The client's own default record is 4 (SaveLoadSystem),
    and it reads this as a comma string and int()s every entry, so a short value has to
    be padded here or every boss past its last slot reads undefined."""
    raw = _lp2_saved(prog, "defeatedBoss")
    vals = []
    for v in str(raw or "").split(","):
        v = v.strip()
        if v == "":
            continue
        try:
            vals.append(str(int(float(v))))
        except ValueError:
            continue
    return ",".join((vals + ["0"] * 4)[:4])


def lp2_boss_que(prog: dict) -> str:
    """The boss queue: 4 rows of 4, rows split on "," and values on ":" - the shape the
    client's own twoDArray2Str writes and str2TwoDArray reads back."""
    raw = str(_lp2_saved(prog, "bossQue") or "")
    rows = []
    for row in raw.split(","):
        vals = [v.strip() for v in row.split(":") if v.strip() != ""]
        fixed = []
        for v in vals:
            try:
                fixed.append(str(int(float(v))))
            except ValueError:
                fixed.append("0")
        rows.append((fixed + ["0"] * 4)[:4])
    while len(rows) < 4:
        rows.append(["0"] * 4)
    return ",".join(":".join(r) for r in rows[:4])


def lp3_game_result(acct) -> list:
    """LP3's gameResult board, padded to its own 24-game / 102-level table.

    The client indexes it as [game][level] and reads row[2] (the high score) to decide
    whether the NEXT level is available, so every level needs its own row.
    """
    stored = (acct or {}).get("gameResult3")
    board = []
    for gid, count in enumerate([len(r) for r in LP3_LEVEL_MAXSCORES]):
        have = stored[gid] if isinstance(stored, list) and gid < len(stored) else []
        row_in = have if isinstance(have, list) else []
        board.append([list(row_in[j]) if j < len(row_in) and isinstance(row_in[j], list)
                      else blank_row() for j in range(count)])
    return board


def lp2_blank_score_report() -> list:
    """Every game and level, unplayed: score 0 with an empty date."""
    return [[[0, "", 0, "", 0, ""] for _ in levels] for levels in LP2_LEVELS]


def lp2_score_report(prog: dict) -> list:
    """The 20xN score board.  A stored board of the right shape wins; anything else is
    merged over a blank board so the reply always matches the client's own spec."""
    board = lp2_blank_score_report()
    raw = _lp2_saved(prog, "scoreReport")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:                                            # noqa: BLE001
            raw = None
    if not isinstance(raw, (list, tuple)):
        return board
    for g, levels in enumerate(LP2_LEVELS):
        if g >= len(raw) or not isinstance(raw[g], (list, tuple)):
            continue
        for lv in range(len(levels)):
            row = raw[g][lv] if lv < len(raw[g]) else None
            if isinstance(row, (list, tuple)) and len(row) >= 6:
                board[g][lv] = [row[0], str(row[1] or ""), row[2], str(row[3] or ""),
                                row[4], str(row[5] or "")]
    return board


def lp2_merge_board(who: str, key: str, gem_id, amount) -> bool:
    """One setGem/setItem call -> the stored board.  setGem's data is [gemID, amount]."""
    if not who:
        return False
    acct = accounts.get(who) or {}
    prog = accounts.get_progress(acct)
    if key == "gemreport":
        board = lp2_gem_board(prog)
        try:
            idx = int(float(gem_id)) - 1
            board[idx] = int(float(amount))
        except (TypeError, ValueError, IndexError):
            return False
    else:
        board = lp2_item_board(prog)
        name = str(gem_id)
        try:
            new_amount = int(float(amount))
        except (TypeError, ValueError):
            return False
        # Unlimited-items accounts: the client subtracts locally and saves the result,
        # so hold the count at the floor here rather than seeding it once.
        if lp2_unlimited_on(prog) and new_amount < int(LP2_UNLIMITED_AMOUNT):
            new_amount = int(LP2_UNLIMITED_AMOUNT)
        for row in board:
            if row[0] == name:
                row[1] = new_amount
                break
        else:
            board.append([name, new_amount])
    accounts.set_progress(who, key, json.dumps(board))
    return True


def lp2_merge_score_row(who: str, args) -> bool:
    """One LP2 setScore call -> the stored board.  data is [game, level, initS, initD,
    highS, highD, latestS, latestD] with game/level 1-based (Report.setScore)."""
    if not who or not isinstance(args, (list, tuple)) or len(args) < 8:
        return False
    try:
        g, lv = int(float(args[0])) - 1, int(float(args[1])) - 1
        if not (0 <= g < len(LP2_LEVELS)) or not (0 <= lv < len(LP2_LEVELS[g])):
            return False
        acct = accounts.get(who) or {}
        board = lp2_score_report(accounts.get_progress(acct))
        board[g][lv] = [int(float(args[2])), str(args[3] or ""),
                        int(float(args[4])), str(args[5] or ""),
                        int(float(args[6])), str(args[7] or "")]
        accounts.set_progress(who, "scorereport", json.dumps(board))
        log.info(f"  LP2 score saved: game {g + 1} level {lv + 1} -> "
                 f"{board[g][lv][2]} for {who}")
        return True
    except (TypeError, ValueError) as e:
        log.warning(f"  LP2 score row not saved: {e}")
        return False


def save_progress_batch(reqs, game: str = "") -> bool:
    """Store everything a save batch carries; True if anything was kept.

    Both games send several {type, data} requests in one call, and the score rows
    and the progress fields (gems, items, cards, cardSequence, process, equipment,
    the totals ...) all arrive this way.  The games read them back from the login
    reply, so anything dropped here is progress lost at the next login.

    LP2 needs unpacking on the way in: its whole record rides in one updateUserInfo
    call (nine args, see LP2_USER_INFO_FIELDS) and its gems/items/scores arrive as
    per-id or per-level pairs.  Its setScore is 1-based, LP1's is 0-based, so the two
    games must not share one row store - hence the `game` argument.
    """
    who = CURRENT_PLAYER.get("email")
    lp2 = str(game or "").lower().startswith("prince2")
    # Each title's 積分 and per-level rows go to that title's own key - the reply
    # field names are unchanged, only the stored key is (see SCORE_KEYS/BOARD_KEYS).
    score_key = score_field(game)
    board_key = board_field(game) or "gameResult"
    kept = []
    for r in reqs:
        field = str(r.get("type") or "").lower()
        if field == "setscore":
            ok = (lp2_merge_score_row(who, r.get("data")) if lp2
                  else store_score_row(r.get("data"), board_key))
            if ok:
                kept.append("setScore")
        elif field == "updateuserinfo" and lp2:
            data = r.get("data")
            if isinstance(data, (list, tuple)) and who:
                for name, val in zip(LP2_USER_INFO_FIELDS, data):
                    if isinstance(val, (list, tuple, dict)):
                        continue
                    key = str(name).lower()
                    if key == "score" and score_key:
                        key = score_key       # LP2's own 積分, not the shared one
                    accounts.set_progress(who, key, val)
                    kept.append(name)
        elif field in ("setgem", "setitem") and lp2:
            data = r.get("data")
            if isinstance(data, (list, tuple)) and len(data) >= 2:
                if lp2_merge_board(who, field, data[0], data[1]):
                    kept.append(field)
        elif field in PROGRESS_FIELDS and who:
            try:
                key = score_key if (field == "score" and score_key) else field
                accounts.set_progress(who, key, r.get("data"))
                kept.append(field)
            except Exception as e:                     # never break the reply
                log.error(f"  could not save '{field}': {e}")
    if kept:
        log.info(f"  saved for {who or '-'}: {', '.join(kept)}")
    return bool(kept)


def lp1_game_result(acct) -> list:
    """The gameResult board for one account, padded to the full 17-game table."""
    stored = (acct or {}).get("gameResult")
    board = []
    for i, levels in enumerate(LP1_LEVELS):
        have = stored[i] if isinstance(stored, list) and i < len(stored) else []
        row_in = have if isinstance(have, list) else []
        board.append([list(row_in[j]) if j < len(row_in) and isinstance(row_in[j], list)
                      else blank_row() for j in range(levels)])
    return board


def store_score_row(args, board_key: str = "gameResult") -> bool:
    """Save one level's score row that the client sent with `setScore`.

    saveMark() sends data:[gameIndex, level, initS, initD, highS, highD,
    recentS, recentD] with the game and level already zero-based.  `board_key` is
    the asking title's OWN board (see BOARD_KEYS) - LP1 and LP3 used to write into
    one shared `gameResult` array, so a level played in LP1 showed up in LP3.
    """
    email = CURRENT_PLAYER.get("email")
    if not email or not isinstance(args, (list, tuple)) or len(args) < 8:
        return False
    try:
        row = [int(args[2]), str(args[3]), int(args[4]), str(args[5]),
               int(args[6]), str(args[7])]
        accounts.set_game_result(email, int(args[0]), int(args[1]), row, board_key)
    except (TypeError, ValueError) as e:
        log.warning(f"  score row not saved: {e}")
        return False
    log.info(f"  score saved: game {int(args[0]) + 1} level {int(args[1])} "
             f"-> {row[0]}/{row[2]}/{row[4]} for {email} ({board_key})")
    return True


def lp3_zero_state() -> dict:
    """LP3's state fields at the lengths the game's own default user uses, all zero.

    From the CD's PrinceSystem.createUserText default user: gems 10, gameCards 50,
    cards 12, items 8, process 1, cardSequence 20.  LP3 runs each through
    Utils.str2nArray and int()s every entry, and it unlocks a card panel entry only
    when gameCards[cardId - 1] > 0 - so zeros here mean a fully locked card book.
    """
    lengths = (("gems", 10), ("gameCards", 50), ("cards", 12),
               ("items", 8), ("process", 1), ("cardSequence", 20))
    out = {}
    for key, count in lengths:
        zeroes = ",".join(["0"] * count)
        out[key] = zeroes
        out[key.lower()] = zeroes
    return out


# ── Mods ─────────────────────────────────────────────────────────────────────
# All four games keep their progress on this server (the account's `progress`
# dict, handed back with the next login), so a mod is a value written there -
# no client patch, no save file.  Every preset spells out the fields and values
# it writes; the lengths are the games' own, the same ones lp3_zero_state and
# LP1_LEVELS/GEM_COUNT use, because a short array reads as `undefined` past its
# last slot.
#
# Only presets whose shape is known from the games' own code live here.  LP1's
# `cards` string, LP2's `equipment` and LPO's weapon/costume lists are not - the
# panel's field editor writes those by hand until a save from the real client
# pins the format.
MODS_PRESETS = (
    {
        "id": "lp1_levels", "game": "LP1",
        "label": "Every level cleared",
        "detail": "stars = a 3 for each of the %d levels" % len(LP1_LEVELS),
        "progress": {"stars": ",".join(["3"] * len(LP1_LEVELS))},
        # The level select gates on the gameResult rows - a row with a score clears its
        # level - so stars alone left every game but the first locked.
        "game_result": {"all_games": True, "high": 999},
    },
    {
        "id": "lp1_points", "game": "LP1",
        "label": "Max out the points (積分)",
        "detail": "lp1score = %s.  The 部首咭 panel charges 積分 per card (100-160 each) and "
                  "shows this as 總分, so every card can be bought - and what the client "
                  "buys it saves back as cards/gameCards, which the server keeps.  LP1's "
                  "own key, so it no longer shows up in LP2 or LP3"
                  % LP1_POINTS,
        "progress": {"lp1score": LP1_POINTS},
    },
    {
        "id": "lp1_gems", "game": "LP1",
        "label": "All gems",
        "detail": "gems = the %d counters at 999" % GEM_COUNT,
        "progress": {"gems": ",".join(["999"] * GEM_COUNT)},
    },
    {
        "id": "lp1_scores", "game": "LP1",
        "label": "Max every level's score",
        "detail": "all %d score rows: best 999 (drives the total and the rank board)"
                  % len(LP1_LEVELS),
        "game_result": {"all_games": True, "high": 999},
    },
    {
        "id": "lpo_items", "game": "LPO",
        "label": "Every item obtained",
        "detail": "the whole wardrobe - every item in the client's own settings.cxd, "
                  "weapons and consumables included - written to the player record's "
                  "`items`, which the login reply hands to the client's own parser",
        "profile": {"items": lambda: lpo_items_json(lpo_item_catalogue())},
    },
    {
        "id": "lpo_unlimited", "game": "LPO",
        "label": "Unlimited weapon use",
        "detail": "unlimitedUse = 1: the equipped weapons' remaining uses "
                  "(left_total/right_total, which the maze decrements) are held at "
                  "%s at every login and on every save" % LPO_UNLIMITED_USES,
        "profile": {"unlimitedUse": "1",
                    "left_total": LPO_UNLIMITED_USES,
                    "right_total": LPO_UNLIMITED_USES},
    },
    {
        "id": "lp2_bosses", "game": "LP2",
        "label": "Every boss defeated",
        "detail": "defeatedBoss = the 4 slots at 1. The client gates the map's "
                  "progress on hasDefeatedBoss(stage), so every stage opens",
        "progress": {"defeatedBoss": "1,1,1,1"},
    },
    {
        "id": "lp2_items", "game": "LP2",
        "label": "Every item obtained",
        "detail": "itemReport = all %d items of the six traders, at %s each (the ids "
                  "come from the client's own initItemSpec)" % (len(LP2_ITEMS),
                                                               LP2_UNLIMITED_AMOUNT),
        "progress": {"itemReport": "[%s]" % ", ".join(
            '["%s", %s]' % (i, LP2_UNLIMITED_AMOUNT) for i in LP2_ITEMS)},
    },
    {
        "id": "lp2_unlimited", "game": "LP2",
        "label": "Unlimited item use",
        "detail": "lp2unlimited = 1: every item's count is held at %s on every save, "
                  "so using one never runs it out (the client subtracts locally)"
                  % LP2_UNLIMITED_AMOUNT,
        "progress": {"lp2unlimited": "1",
                     "itemReport": "[%s]" % ", ".join(
                         '["%s", %s]' % (i, LP2_UNLIMITED_AMOUNT) for i in LP2_ITEMS)},
    },
    {
        "id": "lp2_points", "game": "LP2",
        "label": "Max out the points (積分)",
        "detail": "score = %s (the points the shop and the card panels charge), written "
                  "to LP2's own key so the other two titles keep their own"
                  % GAME_POINTS,
        "progress": {"lp2score": GAME_POINTS},
    },
    {
        "id": "lp2_gems", "game": "LP2",
        "label": "All gems",
        "detail": "gemReport = the 10 energy gems at 999 - the board the login hands "
                  "to the client's Report (it reads gemID-1)",
        "progress": {"gemReport": ",".join(["999"] * 10)},
    },
    {
        "id": "lp2_levels", "game": "LP2",
        "label": "Every level cleared",
        "detail": "scoreReport = full marks on all %d levels of the 20 mini-games, "
                  "every date 2020-01-01 so injected state stays recognisable"
                  % sum(len(g) for g in LP2_LEVELS),
        # Built from the same spec the reply is sized by, so the two cannot drift.
        "progress": {"scoreReport": json.dumps(
            [[[fs, "2020-01-01 00:00:00", fs, "2020-01-01 00:00:00",
               fs, "2020-01-01 00:00:00"] for fs in levels]
             for levels in LP2_LEVELS])},
    },
    {
        "id": "lp3_cards", "game": "LP3",
        "label": "Every card unlocked",
        "detail": "gameCards = 50 slots at %s (BuyCard shows a card as owned when "
                  "gameCards[id-1] > 0)" % LP3_CARD_FLOOR,
        "progress": {"gameCards": ",".join([LP3_CARD_FLOOR] * 50)},
    },
    {
        "id": "lp3_levels", "game": "LP3",
        "label": "Every level unlocked",
        "detail": "process = each of the %d games' own level count (read from the "
                  "client's Setting.miniGameSetting), so every level is available"
                  % len(LP3_LEVEL_COUNTS),
        # The gate is the gameResult board (GameBar.showLevel compares each level's
        # high score against its maxscore), not `process`.  `board` names LP3's own
        # board, so writing it no longer unlocks the same levels in LP1.
        "game_result": {"scores": LP3_LEVEL_MAXSCORES, "board": "gameResult3"},
    },
    {
        "id": "lp3_unlimited", "game": "LP3",
        "label": "Unlimited cards",
        "detail": "lp3unlimited = 1: every card count is held at %s on every save, so "
                  "using a card never runs it out" % LP3_CARD_FLOOR,
        "progress": {"lp3unlimited": "1",
                     "gameCards": ",".join([LP3_CARD_FLOOR] * 50)},
    },
    {
        "id": "lp3_points", "game": "LP3",
        "label": "Max out the points (積分)",
        "detail": "score = %s.  The card panels charge 積分 per card (the earlier "
                  "screenshot showed 所需積分 400) and show it as 分數, so every card can "
                  "be bought; written to LP3's own key, so the other two titles keep "
                  "their own"
                  % GAME_POINTS,
        "progress": {"lp3score": GAME_POINTS},
    },
    {
        "id": "lp3_bosses", "game": "LP3",
        "label": "Every boss defeated",
        "detail": "process = 3, which is exactly what the client's own killBoss() counts "
                  "up to (it increments process[0] until it reaches 3).  The 4 boss "
                  "cards in the card panel only open for purchase at 3, so pair this "
                  "with Max out the points.",
        "progress": {"process": LP3_BOSSES_DEFEATED},
    },
    {
        "id": "lp3_gems", "game": "LP3",
        "label": "All gems",
        "detail": "gems = the 10 counters at 999",
        "progress": {"gems": ",".join(["999"] * 10)},
    },
    {
        "id": "lpo_levels", "game": "LPO",
        "label": "Every level unlocked",
        "detail": "unlockLevels = 1: the login reply reports full marks on every "
                  "level of all 45 games, so no level is greyed out (levels "
                  "unlock when the previous level's best >= its fullScore)",
        "progress": {"unlockLevels": "1"},
    },
    {
        "id": "lpo_coins", "game": "LPO",
        "label": "Coins maxed",
        "detail": "coins = 999999 on the player profile",
        "profile": {"coins": "999999"},
    },
    {
        "id": "lpo_crystals", "game": "LPO",
        "label": "Every crystal maxed",
        "detail": "totalCrystals + crystal0..4 = 9999",
        "profile": {"totalCrystals": "9999", "crystal0": "9999", "crystal1": "9999",
                    "crystal2": "9999", "crystal3": "9999", "crystal4": "9999"},
    },
)


# What each game can actually hold, field by field - read off the clients' own
# code (LP1 start.swf/card.swf, LP2 index.swf + start.swf's User prototype,
# LP3's saveMark, the online client's login4 reply), not guessed.  This is the
# reference the panel shows next to the field editor: a preset can only be
# written where the *shape* of the value is known, so LP2's record fields (and
# every player's own currency there) are listed but not preset - one real save
# from that game is what pins their layout.
MODS_FIELDS = (
    ("LP1", "星願小王子", (
        ("lp1score", "progress", "LP1's own 積分 (總分) - the card panel's balance, split "
                                 "off from the other two titles"),
        ("stars", "progress", "one 0-3 per level, %d values" % len(LP1_LEVELS)),
        ("gems", "progress", "%d counters, comma-separated" % GEM_COUNT),
        ("cards", "progress", "the card ids the player owns, comma-separated"),
        ("ending", "progress", "the ending flag"),
    )),
    ("LP2", "星願外傳", (
        ("lp2score", "progress", "LP2's own 積分 - the points its shop and card panels "
                                 "charge, split off from the other two titles"),
        ("firstHint", "progress", "1 = the hint has already been shown"),
        ("quality", "progress", "graphics setting"),
        ("musicvolume", "progress", "music setting"),
        ("winmode", "progress", "window mode"),
        ("language", "progress", "language"),
        ("extra", "progress", "spare slot the client keeps"),
        ("equipment", "progress", "the weapon list - shape comes from the client's record"),
        ("bossQue", "progress", "the queued bosses"),
        ("defeatedBoss", "progress", "the bosses already beaten"),
        ("setGem", "progress", "per gem id: gemID, amount (the client sends this)"),
        ("setItem", "progress", "per item id: itemID, amount"),
        ("gemReport", "progress", "the 10 energy gems, by gem id (the login sends it)"),
        ("scoreReport", "progress", "per game and level: init/highest/latest score+date"),
        ("itemReport", "progress", "the item rows the client keeps: name, amount"),
    )),
    ("LP3", "星願歷奇", (
        ("lp3score", "progress", "LP3's own 積分 (分數) - the card panels' balance, split "
                                 "off from the other two titles"),
        ("gems", "progress", "10 counters"),
        ("gameCards", "progress", "50 slots - any value above 0 unlocks that panel entry"),
        ("cards", "progress", "12 slots"),
        ("items", "progress", "8 slots"),
        ("process", "progress", "how far the story has gone"),
        ("cardSequence", "progress", "20 slots"),
        ("tGem", "progress", "the gem total the header shows"),
        ("tItem", "progress", "the item total"),
        ("tCard", "progress", "the card total"),
        ("tCard2", "progress", "the second card total"),
    )),
    ("LPO", "小王子 Online", (
        ("coins", "profile", "the coin count"),
        ("totalCrystals", "profile", "crystals overall"),
        ("crystal0", "profile", "crystals in the first world"),
        ("crystal1", "profile", "crystals in the second world"),
        ("crystal2", "profile", "crystals in the third world"),
        ("crystal3", "profile", "crystals in the fourth world"),
        ("crystal4", "profile", "crystals in the fifth world"),
        ("eventData", "profile", "the event counter"),
        ("left_total", "profile", "the left total the client keeps"),
        ("right_total", "profile", "the right total"),
        ("mazeRec", "profile", "the maze record"),
    )),
)


def mods_preset(preset_id: str):
    """The preset with this id, or None."""
    for p in MODS_PRESETS:
        if p["id"] == preset_id:
            return p
    return None


def apply_mods(email: str, preset_id: str = "", fields=None):
    """Write a preset (or plain field values) into one account's saved progress.

    `profile` presets go through the account's player record instead - coins and
    crystals are profile fields, not progress ones.

    Returns (account, written): `written` is exactly what was stored, so the caller
    can report what happened rather than assume the write landed.
    """
    if not isinstance(fields, dict):
        fields = {}
    written = {}
    preset = mods_preset(preset_id) if preset_id else None
    if preset:
        fields = dict(preset.get("progress") or {})
    for key, value in (fields or {}).items():
        key = str(key).strip()
        if not key:
            continue
        # set_progress keeps the value verbatim: a number typed into the field
        # editor would reach the client as 999.0 where it expects "999", and the
        # client's comma-split would then see a single slot.
        text = value() if callable(value) else value
        text = text if isinstance(text, str) else str(text)
        # The three titles' 積分 are one concept to the person using the panel but
        # three separate stores (SCORE_KEYS), so a typed "score" writes all three -
        # the same number everywhere, which is what the panel means by it - while
        # each title still reads only its own key from then on.
        if key.lower() == "score":
            for gkey in SCORE_KEYS.values():
                accounts.set_progress(email, gkey, text)
                written[gkey] = text
            continue
        # Where the value belongs depends on the field: coins and the crystals are
        # player-record (profile) fields, everything else is saved progress.  The
        # panel used to send every typed field to `progress`, so an LPO field typed
        # by hand landed where nothing reads it.
        if key.lower() in {k.lower() for k in DEFAULT_PROFILE} and \
                key.lower() not in PROGRESS_FIELDS:
            accounts.update(email, {key: text})
        else:
            accounts.set_progress(email, key, text)
        written[key] = text
    if preset and preset.get("profile"):
        profile_fields = {k: (v() if callable(v) else v)
                          for k, v in preset["profile"].items()}
        accounts.update(email, profile_fields)
        written.update(profile_fields)
    if preset and preset.get("game_result"):
        # LP1's report panel and its rank row are fed from the account's
        # gameResult, not from `progress`: the row is the six values the client
        # sends with setScore (initS, initD, highS, highD, recentS, recentD).
        spec = preset["game_result"]
        board_key = str(spec.get("board") or "gameResult")
        game = int(spec.get("game") or 0)
        high = int(spec.get("high") or 0)
        today = time.strftime("%Y%m%d")
        levels = int(spec.get("levels") or 0)
        if spec.get("scores"):
            # One row per level with that level's own threshold as the high score - the
            # client unlocks level N only when level N-1 reached its maxscore.
            count = 0
            for gid, row in enumerate(spec["scores"]):
                for level, sc in enumerate(row):
                    accounts.set_game_result(email, gid, level,
                                             [0, "", int(sc), today, int(sc), today],
                                             board_key)
                    count += 1
            written[board_key] = "%d rows at each level's maxscore" % count
        elif spec.get("all_games"):
            # Every game's every level.  The first version wrote one game's rows, so
            # "Every level cleared" unlocked nothing past the first game.
            table = spec.get("table") or LP1_LEVELS
            count = 0
            for gid, nlevels in enumerate(table):
                for level in range(int(nlevels)):
                    accounts.set_game_result(email, gid, level,
                                             [0, "", high, today, high, today],
                                             board_key)
                    count += 1
            written[board_key] = "%d rows at %d (all %d games)" % (count, high,
                                                                   len(table))
        else:
            for level in range(levels):
                accounts.set_game_result(email, game, level,
                                         [0, "", high, today, high, today],
                                         board_key)
            written[board_key] = "%d rows at %d" % (levels, high)
    if written:
        log.info("  mods: wrote %s for %s"
                 % (", ".join(sorted(written)), email))
    else:
        log.warning("  mods: nothing written for %s (preset=%r)" % (email, preset_id))
    return accounts.get(email) or {}, written


def cloud_login_reply(raw_body: bytes, target: str = "") -> bytes:
    """Answer Prince1|2|3_personal.serviceRequest.

    The real server decides whether an account exists and whether the password is
    right.  Locally there is nothing to check: any name and password are accepted,
    and if the name matches an account made on the accounts page, that account's
    profile is what the game receives - so the website is the register/login form.
    """
    reqs = cloud_requests(raw_body)
    first = reqs[0] if reqs else {}
    kind = str(first.get("type") or "").lower()
    name = str(first.get("loginname") or first.get("loginName") or "").strip()
    args = first.get("data")
    if kind == "login" and not name and isinstance(args, (list, tuple)) and args:
        name = str(args[0] or "").strip()
    game = (str(target).split("_")[0] or "cloud") if target else "cloud"
    if not kind and (name or first.get("password")):
        kind = "login"                     # credentials with no readable type is still a login
    log.info(f"  {game}: type={kind or '?'} name={name!r}")

    if kind in ("login", "checklogin", "validatelogin", "resumelogin", "weblogin"):
        acct = resolve_login_account(name)
        if not acct:
            # Same rule as the online client: an account has to exist on this machine
            # (made on the accounts page) before any game will log in.
            log.info(f"  cloud login: '{name}' is not an account made on the accounts page"
                     " - refused")
            return login_fail_reply(target)
        email = accounts.normalize(acct.get("email"))
        profile = acct.get("profile") or {}
        log.info(f"  cloud login: '{name}' -> {email} - serving that profile")
        payload = dict(CLOUD_LOGIN_TEMPLATE)
        payload["loginName"] = name or profile.get("name") or "Player"
        payload["name"] = profile.get("name") or payload["loginName"]
        payload["sex"] = profile.get("sex") or "1"
        payload["schoolName"] = profile.get("school_name") or ""
        payload["schoolType"] = profile.get("school_level") or "0"
        payload["classLv"] = profile.get("class_name") or ""
        payload["className"] = profile.get("class_no") or ""
        if game.lower() == "prince1":
            # The client reads every one of these out of the login reply; `stars`
            # was missing entirely, which made str2NumArray(undefined, ",") fail
            # inside the login handler and left user.stars undefined for the whole
            # session.  gameResult is what the 個人成績表 is built from.
            #
            # The saved copy wins over the profile: LP1 sends stars/gems/cards back
            # with saveProgress the same way LP2 and LP3 do, and those land in the
            # account's `progress`.  Reading only the profile meant a player's own
            # stars and gems never came back, and a mod written to progress never
            # reached the client either.
            lp1_saved = accounts.get_progress(acct) if acct else {}

            def lp1_array(key, length):
                """A saved array fitted to LP1's own slot count.

                Same reasoning as LP3's arrays: a short string splits short and the
                client reads `undefined` past the end, and an empty one would send a
                blank first slot."""
                val = lp1_saved.get(key) or profile.get(key) or ""
                parts = [p if str(p).strip() != "" else "0" for p in str(val).split(",")]
                if len(parts) < length:
                    parts += ["0"] * (length - len(parts))
                elif len(parts) > length:
                    parts = parts[:length]
                return ",".join(parts)

            payload["stars"] = lp1_array("stars", len(LP1_LEVELS))
            payload["gems"] = lp1_array("gems", GEM_COUNT)
            payload["cards"] = lp1_saved.get("cards") or profile.get("cards") or ""
            payload["card"] = payload["cards"]
            payload["gem"] = payload["gems"]
            # 積分 - the 部首咭 panel's 總分, and what its cards are bought with.  This
            # was never sent: the reply kept the captured account's 0, so the panel
            # always showed 總分 0 and no card could be bought however the profile was
            # set.  LP1's own key first (see SCORE_KEYS), then the legacy shared
            # copy an account may still hold.
            payload["score"] = (read_score(lp1_saved, profile, "prince1")
                                or payload.get("score") or "0")
            payload["gameCards"] = ""
            payload["ip"] = ""
            payload["message"] = ""
            payload["gameResult"] = lp1_game_result(acct)
        if game.lower() == "prince2":
            prog = accounts.get_progress(acct) if acct else {}
            # LP2's loadUserDataFromDB and Report constructor expect this schema,
            # not LP1's login object. Null boards ask Report to create its full
            # correctly sized blank records from the game's own specifications, so
            # a board is only sent once the player has actually saved one.
            def lp2_saved(key, default):
                """LP2 saves land in `progress` under the lower-cased request type
                (save_progress_batch lower-cases it), but this reply reads the
                client's camelCase names - so try both spellings.  Without the
                fallback the boss queue, the defeated-boss list and the hint flag
                always came back empty and the player fought every boss again."""
                for k in (key, key.lower()):
                    val = prog.get(k)
                    if val not in (None, ""):
                        return val
                return default

            payload.update({
                "username": name, "password": "", "gender": payload["sex"],
                "school": payload["schoolName"], "edLevel": payload["schoolType"],
                "classLevel": payload["classLv"] or "0",
                # Built from the store, always sized to the client's own spec: the
                # reply's loadUserDataFromDB walks all three by .length and hands them
                # to Report(), so nulls here left every gem and every level blank.
                "scoreReport": lp2_score_report(prog),
                "gemReport": lp2_gem_board(prog),
                "itemReport": lp2_item_board(prog),
                "equipment": lp2_saved("equipment", ""),
                "bossQue": lp2_boss_que(prog),
                "defeatedBoss": lp2_defeated_boss(prog),
                "firstHint": lp2_saved("firstHint", "1"),
                "quality": lp2_saved("quality", "0"),
                "musicvolume": lp2_saved("musicvolume", "0"),
                "extra": lp2_saved("extra", "0"),
                "language": lp2_saved("language", payload.get("language") or "0"),
                # LP2's own 積分 (SCORE_KEYS) - not LP1's and not LP3's.
                "score": (read_score(prog, profile, "prince2")
                          or payload.get("score") or "0"),
            })
        elif game.lower() == "prince3":
            # LP3 saves its state field by field (gems, items, cards, cardSequence,
            # process ...) as comma-joined strings and reads them back from here.
            prog = accounts.get_progress(acct) if acct else {}
            # LP3 runs each of these through Utils.str2nArray(val, ",") and then int()s
            # every entry, so a slot holds a card only when its value is non-zero.  A
            # card panel entry is unlocked iff gameCards[cardId - 1] > 0.
            #
            # Two things matter here:
            #  * the lengths are the game's own defaults, from the CD's
            #    PrinceSystem.createUserText default user: gems 10, gameCards 50,
            #    cards 12, items 8, process 1, cardSequence 20.  An empty string
            #    splits into [""] - a one-element array - so everything past the
            #    first slot reads undefined.
            #  * never fall back to what the captured reply carried: that is the
            #    account the response was recorded from, which is why a brand-new
            #    login arrived with somebody else's cards already unlocked.
            zero_state = lp3_zero_state()

            def lp3_saved(key, length):
                """One saved array, padded/trimmed to the game's own slot count.

                A short string splits into a shorter array and every later slot
                reads `undefined`, and the mods panel writes 8 gems for LP1 and 10
                for LP3 under the same key - so the length is enforced here rather
                than trusted from the store."""
                saved = prog.get(key)
                if saved in (None, ""):
                    saved = prog.get(key.lower())
                if saved in (None, ""):
                    saved = zero_state[key]
                parts = str(saved).split(",")
                if len(parts) < length:
                    parts += ["0"] * (length - len(parts))
                elif len(parts) > length:
                    parts = parts[:length]
                return ",".join(parts)

            saved_defaults = (("gems", 10), ("gameCards", 50), ("cards", 12),
                          ("items", 8), ("process", 1), ("cardSequence", 20))
            for key, length in saved_defaults:
                payload[key] = lp3_saved(key, length)
            # The totals ride in saveMark with the rest of the batch and are read
            # back out of this reply; nothing else in the protocol carries them, so
            # without these the header's totals read 0 for ever.
            for key in ("tGem", "tItem", "tCard", "tCard2"):
                saved = prog.get(key)
                if saved in (None, ""):
                    saved = prog.get(key.lower())
                payload[key] = saved if saved not in (None, "") else "0"
            payload["gameResult"] = lp3_game_result(acct)
            # LP3's own 積分 (SCORE_KEYS) - the card panels' 分數.
            payload["score"] = (read_score(prog, profile, "prince3")
                                or payload.get("score") or "0")
        CURRENT_PLAYER["email"] = email or ""
        CURRENT_PLAYER["profile"] = profile
        return amf0.encode([amf0.AmfObject(payload)])

    # A save batch arrives as several requests in one call - saveMark() sends
    # gems/tGem/score/setScore together, and saveProgress() sends the rest - so
    # scan them all, store what they carry, then answer once.
    # setScore2 carries the per-level best the end-of-game friends board reads
    # back, so it is filed before the plain setScore branch below.
    if any(str(r.get("type") or "").lower() == "setscore2" for r in reqs):
        save_level_scores(reqs)
        return amf0.encode([amf0.AmfObject({"response": "requestSuccess"})])

    if any(str(r.get("type") or "").lower() == "setscore"
           or str(r.get("type") or "").lower() in PROGRESS_FIELDS for r in reqs):
        save_progress_batch(reqs, game)
        return amf0.encode([amf0.AmfObject({"response": "requestSuccess"})])

    if kind.startswith("getrank"):
        return rank_reply(kind, game)
    return build_generic_ok_response()


def _requests_in(raw_body: bytes):
    """How many requests the client packed into one body, or None if unknown.

    A RemoteService body is a STRICT_ARRAY, so the count sits in the four bytes
    after the 0x0a marker - once the packet header is skipped.
    """
    body, _ = _amf_body_slice(raw_body)
    try:
        if body and body[0] == 0x0A and len(body) >= 5:
            return struct.unpack("!I", body[1:5])[0]
    except Exception:                                                 # noqa: BLE001
        pass
    return None


def merge_login_reply(raw_body: bytes, reply: bytes, request_count=None) -> bytes:
    """Make sure a `login4` that rode in a batch is answered.

    Exactly the maze's trap: RemoteService sends an ARRAY of requests and only the
    first type is dispatched, so when the client's login call rides along behind
    something else it got the generic answer and the game sat at 登入中 forever.
    """
    if b"login4" not in (raw_body or b"").lower():
        return reply
    try:
        ours = list(amf0.decode(reply))
    except Exception:                                                 # noqa: BLE001
        ours = []
    for value in ours:
        if isinstance(value, dict) and str(value.get("response")) in (
                "loginSuccess", "loginFail", "e055", "e080"):
            return reply                      # it was answered after all
    try:
        login = list(amf0.decode(serve_captured(
            "login4", CAPTURED_BODIES.get("login4", b""), raw_body)))
    except Exception as exc:                                          # noqa: BLE001
        log.error(f"  could not build the login reply: {exc}")
        return reply
    answers = [v for v in ours] + [v for v in login if isinstance(v, dict)]
    asked = request_count if request_count is not None else _requests_in(raw_body)
    if asked == 1:
        # Nothing else rode along: the answer has to be element 0.  Appending it
        # after the generic reply left the client reading index 0 - the log looked
        # right and the game still refused to log in.
        log.info("  login4 was the only request - answered it on its own")
        return amf0.encode([v for v in login if isinstance(v, dict)] or answers)
    log.info("  login4 was riding in a batch - answered it as well")
    return amf0.encode(answers)


def merge_maze_reply(raw_body: bytes, reply: bytes) -> bytes:
    """Make sure a `canPlayMaze` in the request is always answered.

    RemoteService accumulates requests and sends them as one ARRAY, and
    `extract_service_type` only reads the first element.  When the toy-forest map
    asks for the maze gate after anything else, the gate used to go unanswered -
    the client read `result` as undefined and kept the door shut no matter what the
    setting said.  Merge the gate's answer into whatever else was answered.
    """
    if b"canplaymaze" not in (raw_body or b"").lower():
        return reply
    try:
        maze = amf0.decode(maze_reply(CURRENT_PLAYER.get("profile")))
    except Exception as exc:                                          # noqa: BLE001
        log.error(f"  could not build the maze reply: {exc}")
        return reply
    try:
        ours = amf0.decode(reply)
    except Exception:                                                 # noqa: BLE001
        return amf0.encode(maze)          # the gate matters more than the rest
    answers = list(maze)
    for value in ours:
        if isinstance(value, dict) and str(value.get("response")) == "canPlayMaze":
            continue
        answers.append(value)
    return amf0.encode(answers)


def login_fail_reply(service: str = "") -> bytes:
    """The answer to a login whose name has no account on this machine.

    The client knows `loginFail` (lib.swf lists it next to `loginSuccess`) and
    routes answers by response name, so no profile is ever served for a name that
    was not created on the accounts page.
    """
    log.info("  login -> loginFail (no account, guest logins are off)")
    # The client's login handler (lib.swf) names `info` next to `MSGalert` and
    # `loginFail`, so the alert text is read off that field - an "error" field alone
    # left the user staring at a form that looked like it was still logging in.
    msg = "沒有這個帳號，請先到帳號頁面註冊。"
    return amf0.encode([amf0.AmfObject({
        "response": "loginFail",
        "result": False,
        "info": msg,
        "msg": msg,
        "message": msg,
        "error": msg,
        "alert": msg,
    })])


def serve_captured(service: str, body: bytes, raw_body: bytes = b"") -> bytes:
    """What the client gets for a captured service - accounts aware."""
    low = (raw_body or b"").lower()
    if any(b"prince%d_personal" % n in low for n in (1, 2, 3)):
        # Keep the game name.  The answer differs per game (LP3's card book, LP1/LP2
        # shapes), and without a target cloud_login_reply falls back to its generic
        # branch - which is how a brand-new LP3 login arrived holding the captured
        # template's already-unlocked cards.
        for n in (1, 2, 3):
            if b"prince%d_personal" % n in low:
                return cloud_login_reply(raw_body, "Prince%d_personal" % n)
        return cloud_login_reply(raw_body)
    if service.startswith("canplaymaze"):
        return maze_reply(CURRENT_PLAYER.get("profile"))
    if "login" not in service:
        return render_body(service, body)
    email, _password = login_credentials(raw_body)
    if email:
        acct = resolve_login_account(email)
        if acct:
            log.info(f"  login: '{email}' ok (uid {acct['uid']}, "
                     f"name {acct.get('profile', {}).get('name')!r}) - serving that account"
                     " [password not checked: this is the local mirror]")
            prof = dict(acct.get("profile") or {})
            # The LP1 lesson, for the online client: a save lands in the account's
            # `progress` (persist_player_update, set_progress, the Mods panel) while
            # this reply is built from the profile - so merge the saved copy in,
            # keeping the profile's own spelling of each name.
            for k, v in (accounts.get_progress(acct) or {}).items():
                if str(v) in ("", "None"):
                    continue
                for key in DEFAULT_PROFILE:
                    if key.lower() == str(k).lower():
                        prof[key] = v
                        break
            CURRENT_PLAYER["email"] = acct["email"]
            CURRENT_PLAYER["profile"] = prof
            return render_body(service, body, prof)
        # No account with that name: this mirror does not let anyone in.  The guest
        # profile is gone on purpose - an account has to be created on the accounts
        # page (/web) first, and that page is where its profile, worlds, stats and
        # the billboard are edited.  `loginFail` is the answer the client knows: it
        # sits in the same constant table as `loginSuccess` in lib.swf, and the
        # client picks its handler by response name.
        log.info(f"  login: '{email}' is not an account made on the accounts page - refused")
        CURRENT_PLAYER["email"] = ""
        CURRENT_PLAYER["profile"] = None
        return login_fail_reply(service)
    log.info("  login: could not read a login name from this body - refused")
    CURRENT_PLAYER["email"] = ""
    CURRENT_PLAYER["profile"] = None
    return login_fail_reply(service)


def render_body(key: str, body: bytes, profile: dict = None) -> bytes:
    """Captured body -> what the client actually receives (optionally for one account)."""
    if SENSITIVE_STRINGS:                       # scrub the real account everywhere
        try:
            decoded = amf0.decode(body)
            walked = [_walk_replace(v) for v in decoded]
            if walked != decoded:
                body = amf0.encode(walked)
        except Exception:
            pass
    if "login" in key:
        body = apply_profile(body, profile)
    return body


# Capture the real account's identity, then scrub every captured response.
for _t in list(CAPTURED_BODIES.keys()):
    if "login" in _t:
        _collect_identity(CAPTURED_BODIES[_t], _t)
if SENSITIVE_STRINGS:
    log.info(f"  identity scrub active: {len(SENSITIVE_STRINGS)} captured string(s) "
             f"replaced with profile values ({', '.join(sorted(SENSITIVE_STRINGS.values()))})")


def world_states(permission) -> list:
    perm = int(permission or 0)
    return [{"bit": 1 << b, "index": b, "name": n, "file": f, "name_eng": e,
             "unlocked": bool(perm & (1 << b))} for b, n, f, e in WORLDS]


def profile_summary() -> dict:
    """What the admin page shows: profile + derived world state."""
    perm = int(PROFILE.get("permission", 0))
    return {
        "profile": {k: PROFILE.get(k, DEFAULT_PROFILE.get(k)) for k in
                    list(DEFAULT_PROFILE.keys())},
        "worlds": [{"bit": 1 << b, "index": b, "name": n, "file": f, "name_eng": e,
                    "unlocked": bool(perm & (1 << b))} for b, n, f, e in WORLDS],
        "permission": perm,
        "info": {
            "port": PORT,
            "game_dir": str(GAME_DIR),
            "captured": sorted(CAPTURED_BODIES.keys()),
            "forwarding": FORWARD_UNKNOWN,
            "hosts_redirect": _hosts_has_redirect(),
            "sensitive_replaced": sorted(SENSITIVE_STRINGS.values()),
        },
    }


def _amf_body_slice(raw) -> tuple:
    """The AMF body inside a gateway packet, plus how long it claims to be.

    Layout: version(2) flags(2) count(2) target_len(2) target resp_len(2) resp
    body_len(4) body.  Anything shorter or malformed comes back whole.
    """
    try:
        raw = bytes(raw or b"")
        off = 6
        tlen = struct.unpack("!H", raw[off:off + 2])[0]
        off += 2 + tlen
        rlen = struct.unpack("!H", raw[off:off + 2])[0]
        off += 2 + rlen
        blen = struct.unpack("!I", raw[off:off + 4])[0]
        off += 4
        if 0 <= off <= len(raw) and off + blen <= len(raw):
            return raw[off:off + blen], blen
    except Exception:                                                 # noqa: BLE001
        pass
    return raw, len(raw or b"")


def _hosts_has_redirect() -> bool:
    try:
        txt = Path("/etc/hosts").read_text("utf-8", "replace")
    except Exception:
        return False
    return any("little-prince.com.hk" in ln and not ln.strip().startswith("#")
               for ln in txt.splitlines())

def forward_to_real_server(amf_body: bytes) -> bytes:
    """Forward an AMF request body to the real server and return the response body."""
    import urllib.request
    try:
        # Build a full AMF packet to send to the real server
        target = "PrinceOnline.serviceRequest"
        response = ""
        pkt = struct.pack("!HHH", 0, 0, 1)
        pkt += encode_raw_string(target)
        pkt += encode_raw_string(response)
        pkt += struct.pack("!I", len(amf_body))
        pkt += amf_body
        
        req = urllib.request.Request(
            "http://203.90.228.97/littleprince/amfservice/gateway.php",
            data=pkt,
            headers={"Content-Type": "application/x-amf"}
        )
        resp = urllib.request.urlopen(req, timeout=15)
        data = resp.read()
        
        # Extract body from response packet
        off = 6
        slen = struct.unpack("!H", data[off:off+2])[0]
        off += 2 + slen
        slen = struct.unpack("!H", data[off:off+2])[0]
        off += 2 + slen
        blen = struct.unpack("!I", data[off:off+4])[0]
        off += 4
        body = data[off:off+blen]
        
        # Save this capture for future offline use
        _type = "unknown"
        idx = 0
        while idx < len(amf_body) - 10:
            if amf_body[idx:idx+2] == b'\x00\x04' and amf_body[idx+2:idx+6] == b'type':
                if amf_body[idx+6] == 0x02:
                    sl = struct.unpack("!H", amf_body[idx+7:idx+9])[0]
                    if sl < 100 and idx+9+sl <= len(amf_body):
                        _type = amf_body[idx+9:idx+9+sl].decode("utf-8", errors="replace")
                        break
            idx += 1
        
        if _type not in CAPTURED_BODIES and len(body) > 5:
            CAPTURED_BODIES[_type.lower()] = body
            body_path = os.path.join(_CAPTURE_DIR, f"{_type}.bin")
            with open(body_path, "wb") as f:
                f.write(body)
            log.info(f"  -> Auto-captured '{_type}' ({len(body)}b)")
        
        return body
    except Exception as e:
        log.error(f"  -> Forward failed: {e}")
        return b'\x03\x00\x08response\x02\x00\x02ok\x00\x00\x09'

# ─── The castle hall's 佈告欄 (billboard) ──────────────────────────────────────
# The board's rows are NOT baked into this file.  They live in notices.json next
# to server.py and are edited on the admin page (/admin, "Billboard" section).
# An absent or empty file is a VALID board - that is the shipped state, so the
# panel opens with nothing on it until the operator adds something at /admin.
NOTICES_PATH = LPO_DIR / "notices.json"
NOTICE_PAGE = 8            # the panel shows notice0..notice7, i.e. eight a page
_NOTICE_LOCK = threading.Lock()


def _notice_int(value, default, lo=None, hi=None) -> int:
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        n = default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


# ─── The card editor's layout ───────────────────────────────────────────────
# The card itself is still ONE PNG at /notice/content/<id>.png (the panel's loader
# only makes a display object out of swf/jpg/png/gif).  The layout below is what the
# admin page's editor lets the operator move and style; it is kept WITH THE ROW in
# notices.json so reopening the editor restores every position, colour and font and
# the card can be re-rendered later.  A row with no layout is perfectly valid: the
# game then gets whatever card was uploaded for it, or the blank one.
LAYOUT_MAX_TEXTS = 24
LAYOUT_MAX_SRC = 4_000_000        # a downscaled picture, base64'd (~900 px JPEG)
LAYOUT_MAX_FRAMES = 8             # frames in one animated billboard strip
LAYOUT_MAX_FRAME_SRC = 400_000    # one downscaled motion frame, base64'd


def _layout_str(value, maxlen=400) -> str:
    text = "" if value is None else str(value)
    return text[:maxlen]


def _layout_num(value, default=0.0, lo=0.0, hi=100000.0) -> float:
    try:
        n = float(str(value).strip())
    except (TypeError, ValueError):
        n = float(default)
    if n != n or n in (float("inf"), float("-inf")):
        n = float(default)
    return round(max(lo, min(hi, n)), 2)


def _layout_colour(value, default: str) -> str:
    text = _layout_str(value, 40).strip()
    if re.fullmatch(r"#[0-9A-Fa-f]{3,8}", text):
        return text
    if re.fullmatch(r"rgba?\([0-9.,%\s]{3,40}\)", text):
        return text
    if text.lower() in ("transparent", "none"):
        return text.lower()
    return default


def _layout_one_of(value, allowed, default):
    return value if value in allowed else default


def notice_layout_clean(value):
    """The card editor's layout for one row, or None.

    Every field is coerced and clamped; anything malformed is dropped rather than
    raising, because a broken layout must never be a reason the board stops working
    (the panel's rows are positional and a failure here is what wedged it before).
    """
    if not isinstance(value, dict):
        return None
    card = value.get("card") if isinstance(value.get("card"), dict) else {}
    head = value.get("head") if isinstance(value.get("head"), dict) else {}
    out = {
        "v": 1,
        "card": {
            "bg": _layout_colour(card.get("bg"), "#fcf8ec"),
            "bg2": _layout_colour(card.get("bg2"), "#f1e3bd"),
            "grad": _layout_one_of(card.get("grad"), ("none", "v", "h", "r"), "none"),
            "pattern": _layout_one_of(card.get("pattern"), ("none", "dots", "grid",
                                                            "stripes"), "none"),
            "patternColor": _layout_colour(card.get("patternColor"), "#cec4aa"),
            "border": _layout_colour(card.get("border"), "#cec4aa"),
            "borderW": _layout_num(card.get("borderW"), 3, 0, 40),
            "radius": _layout_num(card.get("radius"), 0, 0, 200),
        },
        "head": {
            "on": bool(head.get("on", True)),
            "h": _layout_num(head.get("h"), 72, 0, 400),
            "band": _layout_colour(head.get("band"), "#f4ecd6"),
            "rule": _layout_colour(head.get("rule"), "#d9c891"),
            "text": _layout_colour(head.get("text"), "#6b5423"),
            "family": _layout_str(head.get("family"), 200) or "sans-serif",
            "size": _layout_num(head.get("size"), 28, 6, 200),
            "weight": _layout_num(head.get("weight"), 600, 100, 900),
            "align": _layout_one_of(head.get("align"), ("left", "center", "right"),
                                    "left"),
            "pad": _layout_num(head.get("pad"), 44, 0, 300),
            "title": _layout_str(head.get("title"), 80),
        },
        "image": None,
        "texts": [],
        "motion": None,
    }
    img = value.get("image")
    if isinstance(img, dict) and _layout_str(img.get("src"), 16).startswith("data:image/"):
        out["image"] = {
            "src": _layout_str(img.get("src"), LAYOUT_MAX_SRC),
            "x": _layout_num(img.get("x"), 0, -4000, 4000),
            "y": _layout_num(img.get("y"), 0, -4000, 4000),
            "w": _layout_num(img.get("w"), 200, 8, 4000),
            "h": _layout_num(img.get("h"), 150, 8, 4000),
            "fit": _layout_one_of(img.get("fit"), ("contain", "cover", "fill"), "contain"),
            "radius": _layout_num(img.get("radius"), 6, 0, 400),
            "border": _layout_num(img.get("border"), 1, 0, 40),
            "borderColor": _layout_colour(img.get("borderColor"), "#e3d9c0"),
            "opacity": _layout_num(img.get("opacity"), 1, 0, 1),
        }
    texts = value.get("texts")
    if isinstance(texts, list):
        for item in texts[:LAYOUT_MAX_TEXTS]:
            if not isinstance(item, dict):
                continue
            out["texts"].append({
                "text": _layout_str(item.get("text"), 2000),
                "x": _layout_num(item.get("x"), 0, -4000, 4000),
                "y": _layout_num(item.get("y"), 0, -4000, 4000),
                "w": _layout_num(item.get("w"), 300, 8, 4000),
                "family": _layout_str(item.get("family"), 200) or "sans-serif",
                "size": _layout_num(item.get("size"), 22, 4, 400),
                "weight": _layout_num(item.get("weight"), 400, 100, 900),
                "italic": bool(item.get("italic")),
                "shadow": bool(item.get("shadow")),
                "color": _layout_colour(item.get("color"), "#3a2f1c"),
                "align": _layout_one_of(item.get("align"), ("left", "center", "right"),
                                        "left"),
                "lh": _layout_num(item.get("lh"), 1.45, 0.6, 4),
            })
    out["motion"] = notice_motion_clean(value.get("motion"))
    return out


def notice_motion_clean(value):
    """The animated billboard's strip: the frames the editor will repaint, or None.

    Motion is a property of the LAYOUT (it is what the editor needs to re-render the
    card), not of the AMF row - `notices_reply` still sends exactly the positional
    shape the panel reads.  A row with no motion is None and behaves exactly as
    before; a malformed one is dropped rather than raising, for the same reason the
    rest of the layout is: a broken layout must never be why the board stops drawing.
    """
    if not isinstance(value, dict):
        return None
    frames = value.get("frames")
    if not isinstance(frames, list):
        return None
    keep = []
    for item in frames[:LAYOUT_MAX_FRAMES]:
        text = item if isinstance(item, str) else ""
        if text[:16].startswith("data:image/") and len(text) <= LAYOUT_MAX_FRAME_SRC:
            keep.append(text)
    if len(keep) < 2:
        return None
    return {"on": bool(value.get("on", True)), "count": len(keep), "frames": keep}


def notice_clean(row, index: int = 0) -> dict:
    """One row, exactly the fields the panel and the admin editor share."""
    row = row if isinstance(row, dict) else {}
    return {
        "id": _notice_int(row.get("id"), index + 1, 1),
        "createDate": str(row.get("createDate") or row.get("date") or "")[:20],
        "title": str(row.get("title") or "")[:80],
        "stars": _notice_int(row.get("stars"), 5, 0, 5),
        "body": str(row.get("body") or row.get("content") or "")[:1200],
        "new": bool(row.get("new")),
        "art": _notice_int(row.get("art"), 2, 1, 3),
        "layout": notice_layout_clean(row.get("layout")),
    }


def load_notices() -> list:
    """The board as stored, in board order.

    Read on every request, so saving on the admin page shows up in the game
    without restarting the server.  No file (or an unreadable one) is simply an
    empty board - never an error and never a generic reply, because the panel
    treats a shapeless answer as a reason to stop drawing.
    """
    for path in (NOTICES_PATH, GAME_DIR / "notices.json"):
        try:
            if not path.is_file():
                continue
            raw = json.loads(path.read_text("utf-8", "replace") or "{}")
        except Exception as e:                                        # noqa: BLE001
            log.warning(f"  notices: {path} unreadable ({e}) - board stays empty")
            continue
        rows = raw.get("notices") if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            continue
        return [notice_clean(r, i) for i, r in enumerate(rows) if isinstance(r, dict)]
    return []


def save_notices(rows) -> list:
    """Write the whole board, in board order (that is what /admin posts)."""
    if not isinstance(rows, list):
        raise ValueError("notices must be a list of rows")
    cleaned = [notice_clean(r, i) for i, r in enumerate(rows) if isinstance(r, dict)]
    with _NOTICE_LOCK:
        NOTICES_PATH.write_text(
            json.dumps({"notices": cleaned}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    return cleaned


def notices_payload() -> dict:
    """What the admin page shows: the rows plus the shape of the board."""
    rows = load_notices()
    return {"notices": rows, "count": len(rows), "page_size": NOTICE_PAGE,
            "pages": max(1, (len(rows) + NOTICE_PAGE - 1) // NOTICE_PAGE),
            "path": str(NOTICES_PATH), "empty": not rows,
            "content_dir": str(NOTICE_CONTENT_DIR),
            "images": notice_images()}


# ─── The board's artwork: one PNG per notice, uploaded on the accounts page ───
# The detail view does not read its text out of the reply - Notice/loadNoticeContent()
# hands `response.url` to SOL::ResLoader, which loads it and AddFriend-style code then
# `news.addChild(...)`s the result.  ResLoader.as decides HOW from the file extension:
#
#     public var displayType:Array = ["swf","jpg","png","gif"];
#
# Only those four go through a Loader (so getData() returns a display OBJECT); every
# other extension is read with a URLLoader in BINARY mode, so getData() returns a
# ByteArray - and `addChild(ByteArray)` throws, which is why the .xml URL that used to
# be answered here left the detail panel empty.  The URL therefore ends in .png, the
# image the operator uploaded (already a DisplayObject when it arrives).
NOTICE_CONTENT_DIR = LPO_DIR / "notice_content"      # USER DATA - excluded from the pack
# The blank card the panel gets when a notice has no uploaded artwork.  A card with a
# real title is rendered ONCE at build time (tools/make_notice_blank.py) and shipped in
# the pack, because the player's machine has no font/imaging library the server may use.
NOTICE_BLANK_PATH = LPO_DIR / "notice_blank.png"


def _plain_card_png(width: int = 694, height: int = 510,
                    bg=(252, 248, 236), line=(206, 196, 170), edge: int = 4,
                    band=(244, 236, 214), rule=(217, 200, 145),
                    ink=(203, 182, 130), faint=(231, 221, 196)) -> bytes:
    """A laid-out blank notice card - the last-resort empty state.

    Written by hand (stdlib zlib + the PNG chunks) because the pack must not depend on an
    imaging library on the player's machine, and the panel needs SOMETHING it can
    addChild: an empty container, a 404 or a ByteArray all leave it wedged.

    Deliberately a card and not a white rectangle: a header band across the top (where the
    title sits on a real card), a rule under it, a title bar and two muted placeholder
    bars standing in for the body.  The shipped notice_blank.png - the same layout with the
    actual word 公告 drawn in a real font - is preferred; see _notice_blank().

    694x510 is the notice panel's real content viewport (notice.swf: the detail overlay's
    `news` container sits at panel (42.3, 80.1), the scrollbar rail starts at x 737 and the
    publisher's own scroll config says t_view = 510), so the card fills the board instead
    of floating in a cream border.
    """
    HEAD = 72
    rows = []
    for y in range(height):
        if y < edge or y >= height - edge:
            row = bytearray(bytes(line) * width)
        else:
            row = bytearray(bytes(bg) * width)
        row[0:edge * 3] = bytes(line) * edge
        row[(width - edge) * 3:width * 3] = bytes(line) * edge
        rows.append(row)

    def band_rows(y0: int, y1: int, x0: int, x1: int, colour) -> None:
        for y in range(max(edge, y0), min(height - edge, y1)):
            rows[y][x0 * 3:x1 * 3] = bytes(colour) * (x1 - x0)

    band_rows(edge, edge + HEAD, edge, width - edge, band)          # header band
    band_rows(edge + HEAD, edge + HEAD + 3, edge, width - edge, rule)   # rule under it
    band_rows(edge + 27, edge + 48, 45, 280, ink)                   # where the title goes
    band_rows(200, 216, 45, 648, faint)                             # body placeholders
    band_rows(240, 256, 45, 560, faint)
    band_rows(280, 296, 45, 613, faint)

    raw = bytearray()
    for y in range(height):
        raw += b"\x00" + bytes(rows[y])      # filter type 0 (None) + one RGB scanline

    def _chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    head = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)   # 8-bit truecolour RGB
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", head)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + _chunk(b"IEND", b""))


def _notice_blank() -> bytes:
    """The shipped titled blank card when the pack carries it, else the drawn one."""
    try:
        data = NOTICE_BLANK_PATH.read_bytes()
        if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 200:
            return data
    except Exception:                                                 # noqa: BLE001
        pass
    return _plain_card_png()


FALLBACK_NOTICE_PNG = _notice_blank()


def _content_id(value) -> str:
    """A notice id that is safe as a file name (ids are small integers)."""
    return re.sub(r"[^0-9A-Za-z_-]", "", str(value or ""))[:24]


def notice_image_path(nid) -> Path:
    return NOTICE_CONTENT_DIR / ((_content_id(nid) or "empty") + ".png")


def notice_images() -> dict:
    """{notice id: byte size} for the notices that have an uploaded card."""
    out = {}
    try:
        for p in sorted(NOTICE_CONTENT_DIR.glob("*.png")):
            out[p.stem] = p.stat().st_size
    except Exception as exc:                                          # noqa: BLE001
        log.error(f"  notices: could not list {NOTICE_CONTENT_DIR.name}: {exc}")
    return out


def save_notice_image(nid, png: bytes) -> dict:
    """Store one notice's card.  Empty bytes clear it.  Returns a status payload."""
    stem = _content_id(nid) or "empty"
    path = notice_image_path(stem)
    if not png:
        try:
            if path.is_file():
                path.unlink()
        except OSError as exc:
            return {"error": f"could not remove the card: {exc}"}
        return {"id": stem, "bytes": 0, "cleared": True}
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        return {"error": "that is not a PNG image"}
    if len(png) > 4 * 1024 * 1024:
        return {"error": "the image is larger than 4 MB"}
    try:
        NOTICE_CONTENT_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".png.tmp")
        tmp.write_bytes(png)
        os.replace(tmp, path)
    except Exception as exc:                                          # noqa: BLE001
        log.error(f"  notices: could not store {path.name}: {exc}")
        return {"error": f"could not store the card: {exc}"}
    log.info(f"  notices: card {path.name} -> {len(png)} bytes")
    return {"id": stem, "bytes": len(png), "url": f"/notice/content/{path.name}"}


def notice_image_bytes(nid) -> bytes:
    """The uploaded card for one notice, else the blank card (never nothing)."""
    try:
        path = notice_image_path(nid)
        if path.is_file():
            data = path.read_bytes()
            if data[:8] == b"\x89PNG\r\n\x1a\n":
                return data
            log.warning(f"  notices: {path.name} is not a PNG - serving the blank card")
    except Exception as exc:                                          # noqa: BLE001
        log.error(f"  notices: could not read the card for {nid}: {exc}")
    return FALLBACK_NOTICE_PNG


def notice_content_url(row: dict) -> str:
    """Where the panel fetches one notice's own content.

    Notice/loadNoticeContent() does not read the text out of the reply - it hands
    this URL to SOL::ResLoader, which loads it with a Loader/URLLoader and the panel
    then addChild()s the result.  The extension picks which: only swf/jpg/png/gif go
    through a Loader (a real display object), everything else comes back as a
    ByteArray that addChild() refuses.  So .png it is, and the image is drawn by the
    accounts page (text and/or a picture composed into one canvas).
    """
    nid = _content_id(row.get("id"))
    # A relative path resolves against the host the client is already talking to, so
    # the mirror serves it itself, and every notice gets a card - a notice with no
    # uploaded image is answered with a blank one instead of an empty panel.
    return f"/notice/content/{nid or 'empty'}.png"



def notices_reply(service_lower: str, raw_body: bytes = b"") -> bytes:
    """getNotices / readNotice - the castle hall's 佈告欄.

    notice.swf (PrinceOnline.castle.Notice) holds eight card clips (notice0..notice7)
    and reads createDate, star0..star5, title and photo off each row, so the reply is
    a `list` of objects - the shape getMyFriends and checkMail already use here, with
    `response` naming the service so the client's dispatch matches it.

    The publisher's own server still answers this service, but its PHP 8 handler
    faults before it ever builds a list ("Creating default object from empty value",
    PrinceOnline.php:122), and the mirror's generic {"response":"ok"} is what froze
    the panel.  The rows come from notices.json, written on the admin page.
    """
    rows = []
    for notice in load_notices():
        nid, date, title = notice["id"], notice["createDate"], notice["title"]
        stars, new, body = notice["stars"], notice["new"], notice["body"]
        row = amf0.AmfObject({
            # The panel (notice.swf -> PrinceOnline.castle.Notice.showList) reads the
            # row POSITIONALLY, in this order - proved with numbered markers on the
            # running client: the date line drew index 1, the title band index 2, the
            # star row index 3, and index 6 is fed to the card clip's gotoAndStop
            # (a string there throws ArgumentError #2109 "Frame label X not found").
            # Missing/undefined values throw TypeError #2007 at TextField/set text(),
            # which is what left the board blank and the panel wedged.
            "0": nid,
            "1": date,                    # createDate line, top-left of the card
            "2": title,                   # the title band
            "3": stars,                   # how many stars the card draws
            "4": body,                    # the text the card opens with
            "5": "1" if new else "0",      # read/unread flag
            "6": notice["art"],           # card artwork: frame 2 is the mailbox (1 gears, 3 other)
            "7": "", "8": "", "9": "", "10": "", "11": "",
            # named copies as well: the detail view and any future reader gets them
            "id": str(nid),
            "createDate": date,
            "title": title,
            "photo": "",
            "content": body,
            "new": "1" if new else "0",
            "star0": str(stars), "star1": str(stars), "star2": str(stars),
            "star3": str(stars), "star4": str(stars), "star5": str(stars),
        })
        rows.append(row)
    if service_lower.startswith("readnotice"):
        # Opening one card: same row shape, so the detail view has something to read.
        want = ""
        try:
            peek_src, _ = _amf_body_slice(raw_body)
            peek = amf0.decode(peek_src)
            for item in (peek if isinstance(peek, list) else [peek]):
                if isinstance(item, dict):
                    want = str(item.get("noticeid") or item.get("id") or "")
        except Exception:                                            # noqa: BLE001
            want = ""
        picked = rows[0] if rows else amf0.AmfObject({})
        for row in rows:
            if want and str(row.get("id")) == want:
                picked = row
                break
        log.info(f"  notices: readNotice id={want or '(none)'} -> '{picked.get('title')}'")
        log.info(f"  notices: readNotice -> url {notice_content_url(picked)}")
        return amf0.encode([amf0.AmfObject({
            "response": "readNotice",
            "list": [picked],
            "url": notice_content_url(picked),   # the panel loads this
            "content": picked.get("content") or picked.get("body") or "",
            "title": picked.get("title", ""),
            "createDate": picked.get("createDate", ""),
        })])
    if not rows:
        # An EMPTY board must still draw a panel body.  notice.swf builds its eight
        # card clips from `list`, so a zero-row list leaves the modal showing the
        # 告示板 title over a blurred room and nothing else - which reads as a freeze
        # (the user's words: "if its empty it just froze it").  One placeholder row
        # whose fields are all present gives the panel something to draw and says
        # what to do about it.  It is a UI empty state, not data: notices.json stays
        # untouched and the placeholder disappears the moment a real row exists.
        rows = [amf0.AmfObject({
            "0": "", "1": "", "2": "暫無公告", "3": "0", "4": "管理員還未新增公告。",
            "5": "0", "6": "1", "7": "", "8": "", "9": "", "10": "", "11": "",
            "id": "", "createDate": "", "title": "暫無公告", "photo": "",
            "content": "管理員還未新增公告。", "new": "0",
            "star0": "0", "star1": "0", "star2": "0",
            "star3": "0", "star4": "0", "star5": "0",
        })]
        log.info("  notices: getNotices -> empty board, serving the empty-state card")
    else:
        log.info(f"  notices: getNotices -> {len(rows)} row(s), {NOTICE_PAGE} per page")
    return amf0.encode([amf0.AmfObject({
        "response": "getNotices",
        "list": rows,          # the panel's own container name
        "notices": rows,       # same rows under the other plausible name
        # Opening the board also runs FlowCtrl/loadNoticeContent, so this reply needs
        # a URL too - the first row's, which is what it preloads.
        "url": notice_content_url(rows[0]) if rows else "",
    })])


CLIENT_RANK_RESPONSES = {
    # Exactly the response names the client's RemoteService router matches on.
    "getcoinsrank", "getmonthcoinsrank", "getmonthscorerank", "gettotalscorerank",
    "getitemsrank", "getmonthitemsrank", "getmazerank", "getmonthmazerank",
    "getcrystalsrank", "getmonthcrystalsrank",
}


def rank_reply_name(service_type: str) -> str:
    """Echo the rank response name the CLIENT routes on, not the one it requested.

    The crystal board's total tab requests `getCrystalsRank2` while its own router
    matches `getCrystalsRank`, so the reply was dropped and the tab looked dead.
    """
    if service_type.endswith("2") and service_type[:-1].lower() in CLIENT_RANK_RESPONSES:
        return service_type[:-1]
    return service_type


def dispatch_service(service_type: str, target: str, raw_body: bytes = b"") -> bytes:
    """Dispatch based on service type. Use captured replay for known types,
    forward to real server for unknown types (and auto-capture the response)."""
    service_lower = service_type.lower() if service_type else "unknown"
    
    log.info(f"  Dispatch: service='{service_type}' target='{target}'")

    # The cloud games (LP1/LP2/LP3) call Prince1|2|3_personal.serviceRequest on this
    # same gateway.  Answer here, before the captured set is consulted: their types
    # ('login', 'getRank') would otherwise partial-match 'login4' and serve the MMO's
    # reply.
    low_probe = (str(target or "") + "|" + str(service_type or "")).lower().encode() \
        + (raw_body or b"").lower()
    # The daily-maze gate, whatever target it arrives on.  It must be answered
    # before the Prince1/2/3 login branch, which would otherwise swallow it and
    # reply with a login object - and the client then reads `result` as undefined
    # and keeps the maze shut.
    if service_lower.startswith("canplaymaze"):
        return maze_reply(CURRENT_PLAYER.get("profile"))

    # The mini-games' 積分榜 (score board): getMonthScoreRank / getTotalScoreRank
    # carry `data: [gameID, gameLv]` and each tab re-renders the same panel.  Must
    # come before the generic rank branch, which answers with the general score
    # board - that made every game/level tab look dead (the press registered but
    # the rows never changed).
    if service_lower.startswith(("getmonthscorerank", "gettotalscorerank")):
        return score_rank_reply(service_type, raw_body)

    # The castle's rank boards.  Must be answered before the captured set is
    # consulted: there is no useful capture for these (the publisher's own answer is
    # an empty list), and the generic {"response":"ok"} left the board undrawn.


    if "rank" in service_lower and any(
            k in service_lower for k in RANK_METRICS):
        return lpo_rank_reply(rank_reply_name(service_type),
                              CURRENT_PLAYER.get("profile"))

    # The castle hall's 佈告欄.  Must be answered before the captured set is
    # consulted: there is no notice capture, so it used to fall through to the
    # generic {"response":"ok"} - and that is what froze the panel solid (frames
    # stop, keys and clicks dead, the client's own polling stops with it).
    if service_lower.startswith("getnotice") or service_lower.startswith("readnotice"):
        return notices_reply(service_lower, raw_body)

    # Prince3's activation handshake has to be answered before the login branch
    # below: it travels on the same Prince3_personal target, so the login handler
    # would otherwise swallow it and reply with a login object.
    if b"prince3" in low_probe:
        activation = lp3_activation_reply(service_lower)
        if activation:
            return activation

    if any(b"prince%d_personal" % n in low_probe for n in (1, 2, 3)):
        return cloud_login_reply(raw_body, target)

    # The captured monthly rank replies hold empty lists, which is exactly why the
    # MMO's board showed nothing.  Compile the board from the local accounts instead.
    if service_lower.startswith("getmonth") and "rank" in service_lower:
        return lpo_rank_reply(service_lower)

    # The friends data the mini-games' 1st/2nd/3rd board is drawn from.  It has to
    # be answered before the captured set is consulted: the capture for
    # getMyFriends holds {list: []}, which is exactly the blank board being fixed.
    if service_lower.startswith("friendresultingame"):
        return friend_result_reply(raw_body)
    if service_lower in ("getmyfriends", "getmyfriends2"):
        return friends_reply(service_lower)

    # The Mail panel (the room's owl) and the AddFriend panel: a real friends
    # list per account plus a tiny local mail store.  These must be answered
    # before the captured set - the getMyFriends/checkMail captures hold empty
    # lists, and the "everyone is your friend" fallback is what made the Mail
    # panel list people the player never added.
    if service_lower.startswith("findfriends"):
        return find_friends_reply(raw_body)
    if service_lower == "requestbefriend":
        return request_be_friend_reply(raw_body)
    if service_lower == "confirmbefriend":
        return confirm_be_friend_reply(raw_body)
    if service_lower == "deletemyfriend":
        return delete_my_friend_reply(raw_body)
    if service_lower == "mailtofriend":
        return mail_to_friend_reply(raw_body)
    if service_lower == "checkmail":
        return check_mail_reply()
    if service_lower == "readmail":
        return read_mail_reply(raw_body)
    if service_lower == "deletemail":
        return delete_mail_reply(raw_body)
    if service_lower in ("havenewemail", "checknewemail"):
        return have_new_email_reply()

    # setScore2 keeps one game level's best score, and the end-of-game friends
    # board reads exactly that number back.  It arrives on the MMO's own path
    # (here), which never went through the cloud games' save batch - so the score
    # was dropped and every player stayed on 0 for ever.
    if b"setscore2" in (raw_body or b"").lower():
        try:
            store_level_scores(raw_body)
        except Exception as exc:                                      # noqa: BLE001
            log.error(f"  could not store setScore2: {exc}")
        if service_lower == "setscore2":
            return amf0.encode([amf0.AmfObject({"response": "requestSuccess"})])

    # whatever the game reports about the player is stored first, so a re-login
    # gets the progress back (gems, coins, scores, items)
    try:
        persist_player_update(raw_body, service_lower)
    except Exception as e:                                  # never break a request
        log.error(f"  could not store the player update: {e}")
    
    # Try exact match in captured bodies
    if service_lower in CAPTURED_BODIES:
        log.info(f"  -> Captured replay '{service_lower}' ({len(CAPTURED_BODIES[service_lower])}b)")
        body = CAPTURED_BODIES[service_lower]
        return serve_captured(service_lower, body, raw_body)
    
    # Try partial match
    for key in CAPTURED_BODIES:
        if key in service_lower or service_lower in key:
            log.info(f"  -> Partial captured match '{key}' ({len(CAPTURED_BODIES[key])}b)")
            body = CAPTURED_BODIES[key]
            return serve_captured(service_lower, body, raw_body)
    
    # Unknown service.  Default: answer locally (nothing leaves this machine).
    if not FORWARD_UNKNOWN:
        log.info(f"  -> '{service_lower}' not captured; answering locally (LPO_FORWARD=1 to query the real server)")
        # Say what it actually asked for.  Without this the only evidence is a
        # generic answer that worked, and there is nothing to look up.
        try:
            # Decode the BODY, not the packet: the packet starts with the version,
            # the target string and the response id, so walking it from byte 0 hits a
            # letter of 'PrinceOnline...' and reports 'unsupported AMF0 marker 0x72' -
            # a scary line for a request that parsed perfectly well.
            peek_src, _ = _amf_body_slice(raw_body)
            peek = amf0.decode(peek_src)
            names = set()
            for item in (peek if isinstance(peek, list) else [peek]):
                if isinstance(item, dict):
                    names.update(str(k) for k in item.keys())
                    if item.get("type"):
                        names.add("type=" + str(item.get("type")))
            log.info("     it asked for: %s" % sorted(names)[:14])
        except Exception as exc:                                      # noqa: BLE001
            # Keep the bytes.  A body we cannot read is the one thing that cannot be
            # diagnosed from a log line, and it is exactly what the publisher's Flash
            # client sent (Ruffle's equivalent decoded fine).
            log.info("     (its body could not be read: %d bytes - %s)" % (len(raw_body or b""), exc))
            try:
                _dumpdir = os.path.join(os.path.dirname(_CAPTURE_DIR), "unreadable")
                os.makedirs(_dumpdir, exist_ok=True)
                dump = os.path.join(_dumpdir, "unreadable_%d.bin" % int(time.time()))
                with open(dump, "wb") as fh:
                    fh.write(raw_body or b"")
                log.info("     saved it to %s" % dump)
                log.info("     first bytes: %s" % (raw_body or b"")[:64].hex())
            except Exception:                                         # noqa: BLE001
                pass
        return build_generic_ok_response()
    log.info(f"  -> Forwarding '{service_lower}' to real server")
    body = forward_to_real_server(raw_body)
    return serve_captured(service_lower, body, raw_body)

# ─── HTTP Server ─────────────────────────────────────────────────────────────

# MIME type mapping for Flash game files
MIME_TYPES = {
    ".swf": "application/x-shockwave-flash",
    ".cxd": "application/octet-stream",
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".xml": "application/xml; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flv": "video/x-flv",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".wasm": "application/wasm",
    ".map": "application/json",
}

# ─── Website sessions (accounts site at /web) ────────────────────────────────

SESSIONS = {}          # token -> email


def _session_token(handler) -> str:
    """The session cookie value, or '' when there is none."""
    cookie = handler.headers.get("Cookie", "") or ""
    for part in cookie.split(";"):
        name, _, value = part.strip().partition("=")
        if name == "lpo_session":
            return value
    return ""


def _session_email(handler) -> str:
    return SESSIONS.get(_session_token(handler), "")


class LittlePrinceHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler that serves game files and AMF gateway."""
    
    # Suppress default stderr logging
    def log_message(self, format, *args):
        pass
    
    def send_json(self, obj, status=200, cookie=None):
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        # These answers are live state, not documents.  Without this the browser
        # heuristically caches them, so the portal kept reading a "not downloaded"
        # verdict from before the download and the card stayed greyed out - while
        # the POST that started the download (never cached) worked fine.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(payload)

    def serve_cloud_install(self, query):
        """Server-rendered download page for one cloud game - no JavaScript.

        The portal's own progress bar needs fetch().  When that does not land - an
        old browser, a blocked request, a cached "not installed" - the user sees
        absolutely nothing.  This page is plain HTML with a meta refresh, so any
        browser can watch the download and drop into the game when it finishes.
        """
        from urllib.parse import parse_qs
        code = (parse_qs(query or "").get("code") or [""])[0].strip().upper()
        # the online client has no pack URL - it is fetched from its own manifest -
        # but its card links here exactly like the other three, so it must pass
        # this guard instead of 404ing with "unknown game".
        if code not in PACK_SOURCES and code != "LPO":
            self.send_error(404, "unknown game")
            return
        name = CLOUD_NAMES.get(code, code)

        info = cloud_state_reply()["games"].get(code, {})
        S = ui_text()

        def send_page(refresh, icon, barclass, fill, pct_html, sub, bytes_line,
                      msg, msgclass):
            body = (DOWNLOAD_PAGE
                    .replace("@@refresh@@", refresh)
                    .replace("@@name@@", name)
                    .replace("@@icon@@", icon)
                    .replace("@@sub@@", sub)
                    .replace("@@pct@@", pct_html)
                    .replace("@@barclass@@", barclass)
                    .replace("@@fill@@", fill)
                    .replace("@@bytes@@", bytes_line)
                    .replace("@@msg@@", msg)
                    .replace("@@msgclass@@", msgclass)
                    .replace("@@back@@", S["back"]))
            payload = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(payload)

        if info.get("ready"):
            # Installed: keep it quiet and plain.  The player pressed a button and
            # is waiting for the game - a big panel with an icon, a percentage and a
            # button is just noise between them and playing.
            body = (LAUNCH_PAGE
                    .replace("@@name@@", name)      # CLOUD_NAMES already carries the code
                    .replace("@@what@@", S["loading"])
                    .replace("@@url@@", launch_url(code))
                    .replace("@@accent@@", LAUNCH_ACCENT.get(code, "#e8c98a"))
                    .replace("@@back@@", S["back"]))
            payload = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(payload)
            return

        retry = (parse_qs(query or "").get("retry") or [""])[0] == "1"
        if retry:
            with CLOUD_LOCK:                       # the user asked to try again
                CLOUD_DOWNLOADS.pop(code, None)
                CLOUD_ATTEMPTS.pop(code, None)
        live = CLOUD_DOWNLOADS.get(code) or {}
        stopped = False
        # never auto-retry a failure: it would hammer the mirror once a second
        if live.get("state") not in ("downloading", "error"):
            if CLOUD_ATTEMPTS.get(code, 0) >= CLOUD_ATTEMPT_LIMIT:
                stopped = True                     # say so instead of looping
            else:
                CLOUD_ATTEMPTS[code] = CLOUD_ATTEMPTS.get(code, 0) + 1
                start_cloud_game(code)
                live = CLOUD_DOWNLOADS.get(code) or {}
        state_name = live.get("state")
        phase = live.get("phase") or "download"
        total = live.get("total") or 0
        done = live.get("done") or 0
        pct = int(100.0 * done / total) if total else 0
        failed = live.get("error") or ""

        if stopped:
            # three finished attempts and it still does not verify: stop looping,
            # say what we know, and let the user decide
            refresh, icon = "", ICON_CROSS
            barclass, fill, pct_html = "", "100%", ""
            sub, bytes_line = S["not_done"], ""
            missing_n = info.get("missing") or 0
            if missing_n:
                msg = S["not_done_missing"] % missing_n
            else:
                msg = S["not_done_other"]
            msg += ('<br/><br/><a class="back" href="/cloud/install?code='
                    + code + '&amp;retry=1">' + S["retry"] + '</a>')
            msgclass = "bad"
        elif state_name == "downloading":
            refresh = '<meta http-equiv="refresh" content="1">'
            icon = ICON_DOWN
            if phase == "unpack":
                # every byte is in; it is writing them to disk now.  Showing "100%"
                # here is what made it look like it was still downloading forever.
                barclass, fill = "busy", "30%"
                pct_html, sub = S["unpacking"], S["unpacking_sub"]
                bytes_line = (S["unpacking_bytes"] % (total / 1048576.0)) if total else ""
                msg = S["unpacking_msg"]
            elif phase == "files":
                barclass, fill = "", "%d%%" % max(pct, 1)
                pct_html, sub = "%d%%" % pct, S["files_sub"]
                bytes_line = S["files_bytes"] % (done, total)
                msg = S["files_msg"]
            else:
                barclass, fill = "", "%d%%" % max(pct, 1)
                pct_html = ("%d%%" % pct) if total else "&hellip;"
                sub = S["downloading"]
                bytes_line = ("%.1f MB / %.1f MB" % (done / 1048576.0, total / 1048576.0)
                              ) if total else S["connecting"]
                msg = S["download_msg"]
            if failed and phase == "download":
                msg = S["source_failed"]
            msgclass = ""
        elif state_name == "error":
            refresh, icon = "", ICON_CROSS
            barclass, fill, pct_html = "", "100%", ""
            sub, bytes_line = S["failed"], ""
            # no meta refresh here on purpose: an auto-reload would retry the mirror
            # every second.  Offer the retry instead and let the user choose.
            msg = ((failed or S["failed_msg"])
                   + '<br/><br/><a class="back" href="/cloud/install?code='
                   + code + '&amp;retry=1">' + S["retry"] + '</a>')
            msgclass = "bad"
        else:
            # it finished between the readiness check above and here
            send_page('<meta http-equiv="refresh" content="1;url=%s">' % launch_url(code),
                      ICON_TICK, "", "100%", "", S["loading_sub"], S["loading"],
                      S["loading_msg"], "")
            return

        send_page(refresh, icon, barclass, fill, pct_html, sub, bytes_line, msg, msgclass)

    def serve_admin_page(self):
        """Retired: the admin panel is part of the accounts page now.

        Everything it did lives at /web - the billboard and the LPO client folder
        are rail entries there, and they need a signed-in account.  Old links and
        bookmarks still land somewhere useful.
        """
        self.send_response(302)
        self.send_header("Location", "/web")
        self.end_headers()

    def serve_cloud(self, rel):
        """Static files from the mirrored cloud portal (cloud/<here>).

        A file under patches/<here> wins.  Those are the small client fixes we ship
        - LP2's logout, for one - and they are served from beside the mirror so the
        mirror itself stays the publisher's build, which is what the client check
        compares against.
        """
        rel = rel.split("?")[0].split("#")[0].strip("/")
        root = CLOUD_DIR.resolve()
        target = CLOUD_DIR / rel
        if rel == "" or target.is_dir():
            target = target / "index.html"
            rel = (rel + "/" if rel else "") + "index.html"
        try:
            patch = (PATCH_DIR / rel).resolve()
            patch.relative_to(PATCH_DIR.resolve())
        except Exception:
            patch = None
        if patch is not None and patch.is_file():
            log.info("patch served: %s" % rel)
            self.serve_file(patch)
            return
        try:
            target = target.resolve()
            target.relative_to(root)                      # no escaping the mirror
        except Exception:
            self.send_error(404, "not in the local mirror")
            return
        if not target.is_file():
            self.send_error(404, "not in the local mirror")
            return
        self.serve_file(target)

    def serve_package_file(self, rel):
        """Serve a file from the package's lpo/web folder (player + page)."""
        base = PACKAGE_WEB.resolve()
        try:
            target = (base / rel).resolve()
        except Exception:
            self.send_error(400, "Bad path")
            return
        if not str(target).startswith(str(base)) or not target.is_file():
            # An avatar the browser asks for and this machine cannot draw is the
            # one 404 here that is not a missing file: say what to do about it
            # instead of leaving a blank picture on the page.  (This used to call
            # log() on the logging.Logger, which is a TypeError, so the request
            # died with a traceback instead of this 404.)
            if rel.startswith("avatars/") and not avatar.available():
                log.warning("  404 %s - the character cannot be drawn: %s"
                            % (rel, avatar.why_not()))
            else:
                log.info("  404 %s" % rel)
            self.send_error(404, "Not Found: %s" % rel)
            return
        self.serve_file(target)

    def serve_crossdomain(self):
        """Allow the client (loaded from another host) to reach this server."""
        self.send_response(200)
        self.send_header("Content-Type", "application/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(CROSSDOMAIN)))
        self.send_header("Cache-Control", "no-store")
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(CROSSDOMAIN)

    def serve_notice_content(self, token: str):
        """One notice's content, at the URL the panel was handed.

        `.png` is the board's own card (the image uploaded on the accounts page, or the
        blank one when nothing was uploaded).  Anything else keeps the old XML answer -
        other panels ask for a named resource there and their loader wants XML.
        """
        if token.lower().endswith(".png"):
            self.serve_notice_image(token)
            return
        want = token.rsplit(".", 1)[0]
        row = None
        for notice in load_notices():
            if str(notice.get("id")) == want:
                row = notice
                break
        if row is None and want == "empty":
            row = {"title": "暫無公告", "body": "管理員還未新增公告。",
                   "createDate": "", "stars": 0}
        if row is None and not want.isdigit():
            # A named resource the panels ask for (the rank boards use one).  Answering
            # with valid XML keeps their loader happy; a 404 is what wedges them.
            row = {"title": "", "body": "", "createDate": "", "stars": 0}
        if row is None:
            log.info(f"  notices: content {token} -> 404 (no such notice)")
            self.send_error(404, "no such notice")
            return
        title = str(row.get("title") or "")
        date = str(row.get("createDate") or "")
        body = str(row.get("body") or "")
        stars = int(row.get("stars") or 0)
        esc = (lambda t: str(t).replace("&", "&amp;").replace("<", "&lt;")
               .replace(">", "&gt;"))
        text = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                "<notice>"
                f"<id>{esc(want)}</id>"
                f"<title>{esc(title)}</title>"
                f"<createDate>{esc(date)}</createDate>"
                f"<stars>{stars}</stars>"
                f"<content>{esc(body)}</content>"
                f"<body>{esc(body)}</body>"
                "</notice>\n")
        data = text.encode("utf-8")
        log.info(f"  notices: content {token} -> {len(data)}b xml ('{title}')")
        self.send_response(200)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def serve_notice_image(self, token: str):
        """The board's card for one notice (the uploaded PNG, or the blank card)."""
        want = token.rsplit(".", 1)[0]
        data = notice_image_bytes(want)
        if not notice_images().get(want) and want != "empty":
            # Nothing was uploaded for this one: the blank card is a UI empty state,
            # not the notice's artwork.
            log.info(f"  notices: card {token} -> no upload, serving the blank card")
        else:
            log.info(f"  notices: card {token} -> {len(data)}b png")
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        # The panel caches by URL inside ResLoader, so a re-upload is picked up by
        # reopening the board; the HTTP cache must never hand back an older card.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def serve_site_page(self):
        for page in (LPO_DIR / "web.html", GAME_DIR / "web.html"):
            if page.is_file():
                self.serve_file(page)
                return
        self.send_error(404, "web.html missing")

    def read_json_body(self, content_length: int) -> dict:
        raw = self.rfile.read(content_length) if content_length else b""
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return {}

    def send_cors_headers(self):
        """Send CORS headers for Flash compatibility."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
    
    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()
    
    def do_POST(self):
        """Handle POST requests — primarily AMF gateway."""
        path = unquote(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        content_type = self.headers.get("Content-Type", "")

        # ── the portal asking for a game it does not have yet ──
        if path.rstrip("/") == "/web/api/cloud_download":
            data = self.read_json_body(content_length)
            code = str(data.get("code") or "").upper()
            result = start_cloud_game(code)
            self.send_json(result, status=200 if result.get("ok") else 400)
            return

        # ── and asking for all of them at once ──
        if path.rstrip("/") == "/web/api/cloud_download_all":
            started, left_alone = [], []
            for code in ("LP1", "LP2", "LP3", "LPO"):
                one = (cloud_state_reply().get("games") or {}).get(code) or {}
                if one.get("ready"):
                    left_alone.append([code, "already here"])
                    continue
                if one.get("downloading"):
                    left_alone.append([code, "already downloading"])
                    continue
                result = start_cloud_game(code)
                (started if result.get("ok") else left_alone).append(
                    [code, "" if result.get("ok") else str(result.get("error") or "could not start")])
            log.info("cloud: download all - started %s, left alone %s"
                     % ([c for c, _ in started], [(c, why) for c, why in left_alone]))
            self.send_json({"ok": True, "started": [c for c, _ in started],
                            "left": [[c, w] for c, w in left_alone]} if started
                           else {"ok": False,
                                 "error": (left_alone[0][1] if left_alone else "nothing to do"),
                                 "left": left_alone})
            return

        # ── accounts website API ──
        if path.rstrip("/") in ("/web/api/register", "/web/api/login", "/web/api/logout",
                                "/web/api/me", "/web/api/password",
                                "/web/api/delete", "/web/api/link", "/web/api/mods"):
            data = self.read_json_body(content_length)
            route = path.rstrip("/")
            try:
                if route == "/web/api/register":
                    prof = dict(DEFAULT_PROFILE)
                    for key in DEFAULT_PROFILE:
                        if key in data and key != "permission" and data[key] not in (None, ""):
                            prof[key] = str(data[key])
                    if "permission" in data:
                        prof["permission"] = max(0, min(0xFFFF, int(data["permission"])))
                    acct = accounts.create(data.get("email", ""), data.get("password", ""),
                                           prof, name=data.get("name"),
                                           login_name=data.get("login_name"))
                    token = secrets.token_urlsafe(24)
                    SESSIONS[token] = acct["email"]
                    log.info(f"  account created: {acct['email']} "
                             f"(login name {acct.get('login_name') or '-'}, uid {acct['uid']})")
                    self.send_json({"account": accounts.public(acct),
                                    "worlds": world_states(acct["profile"].get("permission", 0))},
                                   status=201,
                                   cookie=f"lpo_session={token}; Path=/; HttpOnly; Max-Age=86400")
                elif route == "/web/api/login":
                    acct = accounts.verify(data.get("email", ""), data.get("password", ""))
                    if not acct:
                        self.send_json({"error": "wrong login name or password"}, status=401)
                    else:
                        token = secrets.token_urlsafe(24)
                        SESSIONS[token] = acct["email"]
                        log.info(f"  website sign-in: {acct['email']}")
                        self.send_json({"account": accounts.public(acct),
                                        "worlds": world_states(acct["profile"].get("permission", 0))},
                                       cookie=f"lpo_session={token}; Path=/; HttpOnly; Max-Age=86400")
                elif route == "/web/api/logout":
                    self.send_json({"ok": True},
                                   cookie="lpo_session=; Path=/; Max-Age=0")
                elif route == "/web/api/link":
                    email = _session_email(self)
                    acct = accounts.get(email) if email else None
                    if not acct:
                        self.send_json({"error": "not signed in"}, status=401)
                    else:
                        other = accounts.verify(data.get("name", ""), data.get("password", ""),
                                                touch=False)
                        if not other:
                            self.send_json({"error": "that account name and password do not match a local account"},
                                           status=403)
                        elif accounts.normalize(other["email"]) == accounts.normalize(email):
                            self.send_json({"error": "a local account cannot link to itself"}, status=400)
                        else:
                            acct = accounts.update(email, {"linked_account": other["email"]},
                                                   profile_keys=set(DEFAULT_PROFILE.keys()))
                            log.info(f"  account linked: {email} <- {other['email']}")
                            self.send_json({"account": accounts.public(acct),
                                            "worlds": world_states(acct["profile"].get("permission", 0))})
                elif route == "/web/api/delete":
                    if not _session_email(self):
                        self.send_json({"error": "sign in first"}, status=401)
                    else:
                        target = data.get("email", "")
                        gone = accounts.delete(target)
                        log.info(f"  account deleted: {target} (found={gone})")
                        self.send_json({"ok": gone, "deleted": target,
                                        "accounts": [a.get("email") for a in accounts.all_accounts()]})
                elif route == "/web/api/password":
                    email = _session_email(self)
                    acct = accounts.get(email) if email else None
                    if not acct:
                        self.send_json({"error": "not signed in"}, status=401)
                    else:
                        if not accounts.check_password(data.get("old", ""), acct.get("pw", {})):
                            self.send_json({"error": "the current password is wrong"}, status=403)
                        else:
                            accounts.set_password(email, data.get("new", ""))
                            self.send_json({"ok": True})
                elif route == "/web/api/mods":
                    # All four games read their progress back from this server, so a
                    # mod is a write here.  Sign-in is required; the page picks which
                    # of the local accounts gets it.
                    session = _session_email(self)
                    if not session:
                        self.send_json({"error": "sign in first"}, status=401)
                    else:
                        target = accounts.normalize(data.get("email") or session)
                        if not accounts.get(target):
                            raise ValueError("no account %s" % target)
                        acct, written = apply_mods(target, data.get("preset") or "",
                                                   data.get("fields"))
                        if not written:
                            self.send_json(
                                {"ok": False, "email": acct.get("email"),
                                 "error": "nothing written - unknown preset %r"
                                          % (data.get("preset") or "",
                                             ),
                                 "progress": accounts.get_progress(acct)},
                                status=400)
                        else:
                            self.send_json({"ok": True, "email": acct.get("email"),
                                            "written": sorted(written),
                                            "progress": accounts.get_progress(acct)})
                else:                                   # /web/api/me — edit
                    session = _session_email(self)
                    acct = accounts.get(session) if session else None
                    if not acct:
                        self.send_json({"error": "not signed in"}, status=401)
                    else:
                        patch = dict(data.get("profile", data))
                        if "login_name" in data:
                            patch["login_name"] = data["login_name"]
                        target = accounts.normalize(data.get("target") or session)
                        if patch.get("email") and accounts.normalize(patch["email"]) != target:
                            acct = accounts.rename(target, patch["email"])
                            if accounts.normalize(target) == accounts.normalize(session):
                                token = _session_token(self)
                                if token:
                                    SESSIONS[token] = acct["email"]
                            target = acct["email"]
                            patch.pop("email", None)
                        acct = accounts.update(target, patch,
                                              profile_keys=set(DEFAULT_PROFILE.keys()))
                        email = target
                        log.info(f"  account updated: {email}")
                        self.send_json({"account": accounts.public(acct),
                                        "worlds": world_states(acct["profile"].get("permission", 0))})
            except ValueError as e:
                self.send_json({"error": str(e)}, status=400)
            except Exception as e:
                log.error(f"  website API error: {e}")
                self.send_json({"error": str(e)}, status=500)
            return

        # ── admin API (accounts page, signed in): a notice's own card ──
        # The page draws the card (the uploaded picture and/or the typed text) into a
        # canvas and posts the finished PNG here; the game then loads it from
        # /notice/content/<id>.png.  Composing it in the browser is what keeps this
        # server free of any imaging library - the pack has to run on the player's
        # machine with nothing but Python's standard library.
        if path.rstrip("/").endswith("/web/api/admin/notice_image"):
            if not _session_email(self):
                self.send_json({"error": "sign in first"}, status=401)
                return
            body = self.rfile.read(content_length) if content_length else b"{}"
            try:
                data = json.loads(body.decode("utf-8") or "{}")
            except Exception as e:                                     # noqa: BLE001
                self.send_json({"error": f"bad request: {e}"}, status=400)
                return
            blob = str((data or {}).get("png") or "")
            if blob.startswith("data:"):
                blob = blob.split(",", 1)[-1]
            try:
                png = base64.b64decode(blob, validate=False) if blob else b""
            except Exception as e:                                     # noqa: BLE001
                self.send_json({"error": f"could not read the image: {e}"}, status=400)
                return
            out = save_notice_image((data or {}).get("id"), png)
            if out.get("error"):
                self.send_json(out, status=400)
                return
            out["images"] = notice_images()
            self.send_json(out)
            return

        # ── admin API (accounts page, signed in): the castle-hall billboard ──
        if path.rstrip("/").endswith("/web/api/admin/notices"):
            if not _session_email(self):
                self.send_json({"error": "sign in first"}, status=401)
                return
            body = self.rfile.read(content_length) if content_length else b"{}"
            try:
                data = json.loads(body.decode("utf-8") or "{}")
                rows = data.get("notices") if isinstance(data, dict) else data
                saved = save_notices(rows)
                log.info(f"  billboard saved: {len(saved)} notice row(s) -> {NOTICES_PATH}")
                self.send_json(notices_payload())
            except Exception as e:
                log.error(f"  billboard save failed: {e}")
                self.send_json({"error": str(e)}, status=400)
            return

        # ── admin API (accounts page, signed in): the LPO client folder ──
        if path.rstrip("/").endswith("/web/api/admin/game_dir"):
            if not _session_email(self):
                self.send_json({"error": "sign in first"}, status=401)
                return
            body = self.rfile.read(content_length) if content_length else b"{}"
            try:
                data = json.loads(body.decode("utf-8") or "{}")
                self.send_json(set_game_dir(data.get("path", "")))
            except ValueError as e:
                log.info(f"  client folder rejected: {e}")
                self.send_json({"error": str(e)}, status=400)
            except Exception as e:
                log.error(f"  client folder failed: {e}")
                self.send_json({"error": str(e)}, status=500)
            return

        log.info(f"POST {path} ({content_length} bytes, type={content_type})")
        
        # Check if this is an AMF gateway request
        is_gateway = (
            path == GATEWAY_PATH or
            "amfservice" in path or
            "gateway" in path or
            "amf" in content_type.lower()
        )
        
        if is_gateway:
            self.handle_amf_gateway(content_length)
        else:
            # Unknown POST — return generic OK
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(b"OK")
    
    def handle_amf_gateway(self, content_length: int):
        """Handle AMF gateway requests."""
        try:
            # Read the request body
            body = self.rfile.read(content_length)
            log.info(f"  AMF body: {len(body)} bytes (contents not logged)")
            if os.environ.get("LPO_DUMP_SAVES"):
                # Opt-in (LPO_DUMP_SAVES=1 in the environment): print what the client
                # actually sent.  Pinning the layout of the fields that are stored but
                # not yet unpacked (LP2's setGem/setItem/updateUserInfo record, LPO's
                # items/cloth arrays, LP1's cards) needs exactly one real save body.
                try:
                    dump = cloud_requests(body)
                except Exception:                                        # noqa: BLE001
                    dump = None
                if dump:
                    log.info("  DUMP %s" % json.dumps(dump, default=str)[:4000])
            
            # Parse the AMF0 request.  The parser walks the header and the body together and
            # grumbles at markers it does not expect on the way, even when it recovers and
            # reads the request correctly - so stay quiet through it and only speak up if
            # nothing came out.
            global QUIET
            if len(body) < 8:                       # the probe the cloud games open with
                log.info("  empty AMF request -> empty AMF packet")
                self.send_response(200)
                self.send_header("Content-Type", "application/x-amf")
                self.send_header("Content-Length", "6")
                self.end_headers()
                self.wfile.write(b"\x00\x00\x00\x00\x00\x00")
                return
            QUIET = True
            try:
                parsed = parse_amf0_request(body)
            except Exception as exc:                # a bad packet must not break the reply
                QUIET = False
                log.warning("  could not parse this AMF request (%s) - answering an empty "
                            "AMF packet" % exc)
                self.send_response(200)
                self.send_header("Content-Type", "application/x-amf")
                self.send_header("Content-Length", "6")
                self.end_headers()
                self.wfile.write(b"\x00\x00\x00\x00\x00\x00")
                return
            finally:
                QUIET = False
            if not parsed.get("bodies"):
                log.warning("  this request did not parse as an AMF packet (%d bytes)" % len(body))
            log.info(f"  Parsed: ver={parsed.get('version')} bodies={parsed.get('body_count')}")
            
            # Log body details
            for i, b in enumerate(parsed.get("bodies", [])):
                target = b.get("target", "")
                resp_id = b.get("response_id", "")
                value = b.get("value")
                log.info(f"  Body[{i}]: target='{target}' resp_id='{resp_id}'")
                if isinstance(value, dict):
                    log.info(f"    keys: {list(value.keys())}")
                    st = value.get("type") or value.get("Type") or ""
                    if st:
                        log.info(f"    type='{st}'")
                elif isinstance(value, list):
                    log.info(f"    array of {len(value)} items")
            
            # Extract service type
            service_type, target, response_id = extract_service_type(parsed)
            log.info(f"  Service: type='{service_type}' target='{target}' resp_id='{response_id}'")
            
            # Build response target: /N/onResult
            resp_num = extract_response_number(response_id)
            response_target = f"/{resp_num}/onResult"
            
            # The request bytes themselves - the parser does not keep them, and both
            # the login lookup and the cloud games' [{type:...}] need the real thing.
            raw_body = body or (parsed["bodies"][0].get("raw_body", b"")
                                if parsed.get("bodies") else b"")
            # How many requests this packet carries.  RemoteService packs them into
            # one ARRAY and the client maps answers back by position, so the count
            # decides whether a login answer may be appended or has to stand alone.
            first_value = parsed["bodies"][0].get("value") if parsed.get("bodies") else None
            request_count = len(first_value) if isinstance(first_value, list) else 1
            
            # Dispatch the service handler
            body_data = dispatch_service(service_type, target, raw_body)
            if body_data is None:
                # A handler that fell through used to crash the whole gateway on
                # len(None) and kill the client's login.  Answer the generic reply and
                # say so, rather than dropping the connection.
                log.error(f"  dispatch returned nothing for service='{service_type}' "
                          f"target='{target}' - answering the generic reply")
                body_data = build_generic_ok_response()
            # The client sends an ARRAY of requests (RemoteService.send calls with
            # `reqestList`), and only the first type is used for dispatch - so the
            # daily-maze gate rode along behind another request, went unanswered, and
            # the door stayed shut however the setting was set.  Answer it whenever
            # it is anywhere in the request.
            body_data = merge_maze_reply(raw_body, body_data)
            # and the same for the login itself
            body_data = merge_login_reply(raw_body, body_data, request_count)
            # and for the friends board / friends list
            body_data = merge_friend_reply(raw_body, body_data)
            
            # Build the full AMF0 response packet
            response_packet = encode_amf0_response(response_target, "null", body_data)
            
            log.info(f"  Response: {len(response_packet)} bytes | target='{response_target}'")
            
            # Send the response.
            #
            # Connection: close is load-bearing: Ruffle's NetConnection treats
            # the HTTP stream as the message and only hands the AMF payload to
            # the game when the stream ENDS.  With keep-alive the reply sat in
            # the buffer until a 15s idle timeout, so every request - the board
            # worst of all, because it shows a spinner - looked like a hang.
            # Closing also keeps the read-until-close launcher relays (macOS
            # proxy, Windows fake server) from blocking on this socket.
            self.send_response(200)
            self.send_header("Content-Type", "application/x-amf")
            self.send_header("Content-Length", str(len(response_packet)))
            self.send_header("Connection", "close")
            self.close_connection = True
            self.send_header("Set-Cookie", "PHPSESSID=local_session_12345; path=/")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(response_packet)
            
        except Exception as e:
            log.error(f"AMF gateway error: {e}")
            log.error(traceback.format_exc())
            
            # Try to send a generic OK response even on error
            try:
                body_data = build_generic_ok_response()
                response_packet = encode_amf0_response("/1/onResult", "", body_data)
                self.send_response(200)
                self.send_header("Content-Type", "application/x-amf")
                self.send_header("Content-Length", str(len(response_packet)))
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(response_packet)
            except:
                self.send_response(500)
                self.end_headers()
    
    def do_GET(self):
        """Handle GET requests — serve static files."""
        path = unquote(self.path)
        clean_path = path.split("?")[0].split("#")[0]
        # Log every fetch: which SWF the client asks for, and when, is the only way
        # to tell "the client never requested the panel" from "the panel failed".
        log.info(f"GET {clean_path}")

        # ── accounts website ──
        if clean_path.rstrip("/") in ("/web", "/web/index.html", "/web/index.php"):
            self.serve_site_page()
            return
        # ── a notice's own content, at the URL the panel is given ──
        # The detail view does not read the text out of the reply: Notice/
        # loadNoticeContent() hands `response.url` to SOL::ResLoader, which fetches
        # it with a URLLoader.  With no url the loader got null, threw TypeError
        # #1009 at lastIndexOf and left the panel wedged - the user's "when i press
        # it it just froze too".  So each notice answers at its own path, and the
        # panel loads that.
        if clean_path.startswith("/notice/content/"):
            self.serve_notice_content(clean_path.rsplit("/", 1)[-1])
            return
        # ── which cloud games are on this machine (the portal asks before starting) ──
        if clean_path.rstrip("/") == "/web/api/cloud_state":
            self.send_json(cloud_state_reply())
            return
        if clean_path.rstrip("/") == "/web/api/me":
            email = _session_email(self)
            acct = accounts.get(email) if email else None
            if not acct:
                self.send_json({"error": "not signed in"}, status=401)
            else:
                payload = accounts.public(acct)
                prof = acct.get("profile") or {}
                url, _path = avatar_ensure(prof)
                payload["avatar_url"] = url
                head, _hp = avatar_ensure(prof, "head")
                payload["avatar_head_url"] = head
                self.send_json({"account": payload,
                                "worlds": world_states(acct.get("profile", {}).get("permission", 0))})
            return
        if clean_path.rstrip("/") == "/web/api/recent":
            email = _session_email(self)
            acct = accounts.get(email) if email else None
            if not acct:
                self.send_json({"error": "not signed in"}, status=401)
            else:
                self.send_json({"recent": recent_play_rows(acct)})
            return
        if clean_path.rstrip("/") == "/web/api/account":
            if not _session_email(self):
                self.send_json({"error": "sign in first"}, status=401)
                return
            want = (parse_qs(path.split("?", 1)[1] if "?" in path else "").get("email") or [""])[0]
            acct = accounts.get(want)
            if not acct:
                self.send_json({"error": f"no account {want}"}, status=404)
                return
            self.send_json({"account": accounts.public(acct),
                            "worlds": world_states(acct.get("profile", {}).get("permission", 0))})
            return

        if clean_path.rstrip("/") == "/web/api/accounts":
            email = _session_email(self)
            if not email:
                self.send_json({"error": "sign in first"}, status=401)
                return
            self.send_json({"accounts": [{"email": a.get("email"), "uid": a.get("uid"),
                                          "login_name": a.get("login_name") or "",
                                          "created": a.get("created"),
                                          "last_login": a.get("last_login"),
                                          "name": a.get("profile", {}).get("name", ""),
                                          "linked_account": a.get("profile", {}).get("linked_account", "")}
                                         for a in accounts.all_accounts()]})
            return

        # ── mods: the saved progress of one account + the preset catalogue ──
        if clean_path.rstrip("/") == "/web/api/mods":
            email = _session_email(self)
            if not email:
                self.send_json({"error": "sign in first"}, status=401)
                return
            want = (parse_qs(path.split("?", 1)[1] if "?" in path else "").get("email")
                    or [email])[0]
            acct = accounts.get(want)
            if not acct:
                self.send_json({"error": "no account %s" % want}, status=404)
                return
            prof = acct.get("profile") or {}
            self.send_json({
                "email": acct.get("email"),
                "login_name": acct.get("login_name") or "",
                "name": prof.get("name", ""),
                "progress": accounts.get_progress(acct),
                "profile": {k: prof.get(k, "") for k in
                            ("coins", "totalItems", "totalCrystals", "crystal0", "crystal1",
                             "crystal2", "crystal3", "crystal4", "eventData")},
                "presets": [{"id": p["id"], "game": p["game"], "label": p["label"],
                             "detail": p["detail"],
                             "fields": sorted(list(p.get("progress") or {})
                                              + list(p.get("profile") or {}))}
                            for p in MODS_PRESETS],
                "accounts": [{"email": a.get("email"), "login_name": a.get("login_name") or "",
                              "name": (a.get("profile") or {}).get("name", "")}
                             for a in accounts.all_accounts()],
                "known_fields": [{"game": g, "title": title,
                                  "fields": [{"name": n, "store": s, "note": note}
                                             for (n, s, note) in fs]}
                                 for (g, title, fs) in MODS_FIELDS],
            })
            return

        # ── the mods HUD: the values the game window is playing with ──
        #    Read-only and small: the browser's own page polls this for the strip
        #    along its top edge, so it shows the account the game last signed in as
        #    and the numbers that account will be handed at the next login.
        if clean_path.rstrip("/") == "/web/api/hud":
            # The game window polls this without a session (the publisher's browser
            # holds no cookie for the site), so keep it to the machine itself: the
            # server binds 0.0.0.0, and this would otherwise hand any caller on the
            # LAN the last player's name, coins and gems.
            peer = (getattr(self, "client_address", None) or ("",))[0]
            if peer not in ("127.0.0.1", "::1", "localhost"):
                self.send_json({"error": "loopback only"}, status=403)
                return
            who = CURRENT_PLAYER.get("email") or ""
            acct = accounts.get(who) if who else None
            prof = (acct or {}).get("profile") or {}
            prog = accounts.get_progress(acct) if acct else {}
            self.send_json({
                "ok": True,
                "email": who,
                "login_name": (acct or {}).get("login_name") or "",
                "name": prof.get("name") or "",
                "profile": {k: str(prof.get(k, "") or "") for k in
                            ("coins", "totalItems", "totalCrystals", "crystal0", "crystal1",
                             "crystal2", "crystal3", "crystal4")},
                "progress": {str(k): str(v) for k, v in (prog or {}).items()
                             if str(k).lower() in ("stars", "gems", "cards", "gamecards",
                                                   "cardsequence", "process", "equipment",
                                                   "items", "tgem", "titem", "tcard",
                                                   "tcard2")},
            })
            return

        # ── the browser player ──
        #    /play and the game's own URL /LP/Po/ used to serve the install-free
        #    Ruffle page.  The pack is Flash-only now: the game runs in the
        #    publisher's own Flash browser and the Ruffle page is OFF, because the
        #    client misbehaves under Ruffle (the multiplayer result screen among
        #    others) and users were seeing those bugs.  Swap the serve below back to
        #    play.html to bring the Ruffle player back - that page loads the browser
        #    build of Ruffle from web/ruffle/, which no longer ships (28 MB of dead
        #    weight once the pack went Flash-only), so re-add it first.
        #    The URL keeps the page on the same origin as the gateway, so a
        #    Flash player's calls are not cross-site from the browser's point of view.
        # ── the publisher's cloud portal (LP1/LP2/LP3), mirrored locally ──
        #    Their own Flash browser opens /LP/personal/, so serving it here means
        #    that browser plays the local copies: no binding, no internet.
        # the cloud games ask the portal for a file's size; the publisher answers
        # with an empty legacy result, so answer the same instead of 404ing it
        if clean_path.endswith("totalSize.php"):
            body = b"&totalSize=0&fileSizeArr=&nomoreresult=true"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if clean_path.startswith("/LP/personal/"):
            self.serve_cloud(clean_path[len("/LP/personal/"):])
            return
        # plain-HTML installer: the portal card links here so a browser without
        # working fetch() still gets a progress bar and an automatic launch
        if clean_path.rstrip("/") == "/cloud/install":
            self.serve_cloud_install(self.path.split("?", 1)[1] if "?" in self.path else "")
            return
        # ── the real-Flash player, for the publisher's browser (Pepper Flash) ──
        #    A plain <object>/<embed>, no Ruffle.  /play stays the install-free
        #    Ruffle page for ordinary browsers.
        if clean_path.rstrip("/") in ("/play-flash", "/play_flash",
                                      "/LP/Po/flash", "/flash"):
            if not next(GAME_DIR.glob("*.swf"), None):
                self.serve_package_file("no_game_files.html")
                return
            self.serve_package_file("play_flash.html")
            return
        if clean_path.rstrip("/") in ("/play", "/play.html", "/LP/Po", "/LP/Po/index.html", ""):
            if not next(GAME_DIR.glob("*.swf"), None):
                self.serve_package_file("no_game_files.html")
                return
            self.serve_package_file("play_off.html")
            return
        # ── the Mods panel: pick a game, pick an account, write progress ──
        if clean_path.rstrip("/") in ("/mods", "/mods.html"):
            self.serve_package_file("mods.html")
            return
        if clean_path.startswith("/web/") and not clean_path.startswith("/web/api"):
            # This prefix mirrors the whole web folder, which is how the Ruffle page
            # stayed reachable at /web/play.html after /play was switched off.
            if clean_path[len("/web/"):].lstrip("/") in ("play.html", "play"):
                self.serve_package_file("play_off.html")
                return
            self.serve_package_file(clean_path[len("/web/"):])
            return
        if clean_path.rstrip("/") in ("/crossdomain.xml", "/clientaccesspolicy.xml"):
            self.serve_crossdomain()
            return

        # ── admin UI ──
        if clean_path.rstrip("/") == "/admin":
            self.serve_admin_page()             # 302 -> /web, where the panel lives
            return
        if clean_path.rstrip("/").endswith("/web/api/admin/notices"):
            if not _session_email(self):
                self.send_json({"error": "sign in first"}, status=401)
                return
            self.send_json(notices_payload())
            return
        if clean_path.rstrip("/").endswith("/web/api/admin/game_dir"):
            if not _session_email(self):
                self.send_json({"error": "sign in first"}, status=401)
                return
            self.send_json(game_dir_payload())
            return

        # ── the player card: one account's stats and standing ──
        if clean_path.rstrip("/").endswith("/web/api/games"):
            who = _session_email(self)
            if not who:
                self.send_json({"error": "sign in first"}, status=401)
                return
            want = (parse_qs(path.split("?", 1)[1] if "?" in path else "").get("email")
                    or [who])[0]
            try:
                self.send_json(player_card_payload(want))
            except ValueError as e:
                self.send_json({"error": str(e)}, status=404)
            return

        # Strip leading /
        if clean_path.startswith("/"):
            clean_path = clean_path[1:]
        
        # Strip LP/Po/ prefix (original web path)
        if clean_path.startswith("LP/Po/"):
            clean_path = clean_path[6:]
        elif clean_path == "LP/Po" or clean_path.startswith("LP/Po?"):
            clean_path = ""
        clean_path = os.path.normpath(clean_path)

        # Security: prevent directory traversal
        if ".." in clean_path:
            self.send_error(403, "Forbidden")
            return

        # Security: never serve server internals / captures over HTTP
        blocked_parts = {"captures", "tools", "screenshots"}
        blocked_names = {"profile.json", "server.py", "amf0.py", "admin.html",
                         "web.html", "accounts.py", "accounts.json",
                         "notices.json", "notices.json.tmp"}
        head = clean_path.split(os.sep)[0]
        if (head in blocked_parts
                or os.path.basename(clean_path) in blocked_names
                or clean_path.endswith((".py", ".log", ".orig", ".bak", ".json", ".sh"))):
            log.warning(f"  blocked request for internal file: {clean_path}")
            self.send_error(403, "Forbidden")
            return
        
        # Build file path
        file_path = GAME_DIR / clean_path

        # LPO client fixes (the maze door, lib.swf's multiplayer address) ship in
        # lpo/patches/ and win over the client folder's copy - the client folder
        # stays the publisher's build.  The md5 goes into the log for every
        # lib*.swf so the launcher log proves which build the client loaded: the
        # publisher's copy points at 210.184.92.155 and never touches the relay.
        if file_path.suffix.lower() in (".swf", ".cxd", ".xml"):
            candidates = ["lib/lib.swf", clean_path] if clean_path == "lib.swf" else [clean_path]
            for candidate_rel in candidates:
                try:
                    lpo_patch = (LPO_PATCH_DIR / candidate_rel).resolve()
                    lpo_patch.relative_to(LPO_PATCH_DIR.resolve())
                    if lpo_patch.is_file():
                        if os.path.basename(candidate_rel).startswith("lib"):
                            import hashlib
                            log.info("lpo patch served: %s (md5 %s)" % (
                                candidate_rel,
                                hashlib.md5(lpo_patch.read_bytes()).hexdigest()))
                        else:
                            log.info("lpo patch served: %s" % candidate_rel)
                        self.serve_file(lpo_patch)
                        return
                except Exception:
                    pass

        if file_path.is_file():
            if os.path.basename(clean_path).startswith("lib") and clean_path.endswith(".swf"):
                import hashlib
                log.warning("serving the game folder's own %s (md5 %s) - the package "
                            "patch is missing, so the client may talk to the "
                            "publisher instead of the local relay"
                            % (clean_path, hashlib.md5(file_path.read_bytes()).hexdigest()))
            self.serve_file(file_path)
        elif clean_path == "" or clean_path.endswith("/"):
            # Serve index
            for index_name in ["index.html", "index.swf"]:
                index_path = GAME_DIR / index_name
                if index_path.is_file():
                    self.serve_file(index_path)
                    return
            self.send_error(404, "Not Found")
        else:
            # Try with .swf extension
            swf_path = GAME_DIR / (clean_path + ".swf")
            try:
                lpo_patch = (LPO_PATCH_DIR / (clean_path + ".swf")).resolve()
                lpo_patch.relative_to(LPO_PATCH_DIR.resolve())
                if lpo_patch.is_file():
                    log.info("lpo patch served: %s.swf" % clean_path)
                    self.serve_file(lpo_patch)
                    return
            except Exception:
                pass
            if swf_path.is_file():
                self.serve_file(swf_path)
            else:
                self.send_error(404, f"Not Found: {clean_path}")
    
    def serve_file(self, file_path: Path):
        """Serve a static file with correct MIME type."""
        try:
            suffix = file_path.suffix.lower()
            content_type = MIME_TYPES.get(suffix, "application/octet-stream")
            file_size = file_path.stat().st_size
            
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_size))
            # Our own pages change often, and so do the files we patch (LP2's client
            # carries the logout fix) - a cached movie means a fix the player cannot
            # see.  The portal's card art and its stylesheet change just as often and
            # a browser that keeps an hour-old copy shows the player the OLD card
            # while the package has the new one, so they are no-store too.  None of
            # this is expensive on a local server.
            if suffix in (".html", ".htm", ".swf", ".js", ".xml", ".css",
                          ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
                          ".ico", ".json"):
                self.send_header("Cache-Control", "no-store, must-revalidate")
            else:
                self.send_header("Cache-Control", "public, max-age=3600")
            self.send_cors_headers()
            self.end_headers()
            
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    
        except Exception as e:
            log.error(f"Error serving {file_path}: {e}")
            self.send_error(500, str(e))

class ReusableTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

# ─── Main ────────────────────────────────────────────────────────────────────

def ensure_client_extras() -> None:
    """Write the few client files the game asks for but no pack ships.

    index.swf reads version.txt; a client installed from the CD-era pack does not
    have it, so the request 404s.  webversion.txt is the same four bytes, so copy
    that rather than inventing a value.
    """
    try:
        want = Path(GAME_DIR) / "version.txt"
        src = Path(GAME_DIR) / "webversion.txt"
        if not want.exists() and src.is_file():
            want.write_bytes(src.read_bytes())
            log.info("client: wrote version.txt from webversion.txt - index.swf asks for it "
                     "and every pack leaves it out")
    except Exception as exc:                                          # noqa: BLE001
        log.info("client: could not write version.txt (%s)" % str(exc)[:60])


def auto_repair_stale_clients(delay=25.0):
    """Patch a wrong-version client by itself, once the server is up.

    The games are the cloud versions now, so a client left over from the CD (the one
    that asks for a serial) is simply the wrong build, and putting the publisher's back
    is a handful of files - not the pack.  A game that is not installed at all is left
    alone: that download is a real one and stays the player's decision.
    """
    def work():
        time.sleep(delay)                      # let the server settle first
        for _try in range(3):
            try:
                report = cloud_state_reply(fresh=True)
            except Exception as exc:                                  # noqa: BLE001
                log.info("cloud: could not check for old client files (%s)" % str(exc)[:60])
                time.sleep(30)
                continue
            games = report.get("games") or {}
            todo = [(code, len(one.get("stale") or []))
                    for code, one in sorted(games.items())
                    if (one.get("stale") or []) and not (one.get("missing") or 0)
                    and not one.get("downloading")]
            for code, count in todo:
                log.info("cloud %s: the installed client is an old build (%d file(s)) - "
                         "patching it without being asked" % (code, count))
                try:
                    start_cloud_download(code, repair=True, repair_count=count)
                except Exception as exc:                              # noqa: BLE001
                    log.info("cloud %s: could not patch the client (%s)"
                             % (code, str(exc)[:60]))
            return

    threading.Thread(target=work, daemon=True).start()


def main():
    """Start the Little Prince Online server."""
    swf_count = len(list(GAME_DIR.glob("**/*.swf")))
    log.info(f"  Client files: {GAME_DIR}  ({swf_count} SWF)")
    if swf_count == 0:
        log.info("  No game files found - put the Little Prince Online client in")
        log.info("  lpo/game/ or write its path into lpo/game_dir.txt (the website,")
        log.info("  /web, still works without them).")
    
    log.info("=" * 60)
    log.info("  Little Prince Online (星願小王子 Online) Server")
    log.info(f"  Serving: {GAME_DIR}")
    log.info(f"  Gateway: {GATEWAY_PATH}")
    log.info(f"  Address: http://{HOST}:{PORT}")
    log.info(f"  SWF files: {swf_count}")
    log.info("=" * 60)
    log.info(f"  Accounts website : http://localhost:{PORT}/web")
    log.info(f"  Default profile  : http://localhost:{PORT}/admin")
    log.info(f"  Load game: ruffle http://localhost:{PORT}/index.swf")
    log.info("  Press Ctrl+C to stop")
    log.info("=" * 60)
    
    server = ReusableTCPServer((HOST, PORT), LittlePrinceHandler)

    # A CD-era client asks for a serial, so the game looks downloaded but cannot be
    # played.  Fix that quietly; anything actually absent stays the player's call.
    auto_repair_stale_clients()
    ensure_client_extras()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Server shutting down...")
        server.shutdown()

if __name__ == "__main__":
    main()
