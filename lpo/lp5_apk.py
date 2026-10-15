#!/usr/bin/env python3
"""Build the local 星夜重圓 (Starwish Reunion, com.Starwish.LP1 v1.13) APK - no Java.

The publisher's APK (www.little-prince.com.hk/littleprince/Download/com.Starwish.LP1.apk)
calls http://reunion.little-prince.com.hk/ for every php/Ajax request.  This:

  1. rewrites that address in Assembly-CSharp.dll to the launcher's own server as
     the Android emulator sees it (http://10.0.2.2:<port>/), same length, padded
     with ./ segments, so no other byte of the assembly moves;
  2. repacks the APK with every stored entry 4-byte aligned (what zipalign does);
  3. signs it with a JAR (v1) signature made here, in Python: a 2048-bit RSA key
     generated once per machine and kept in <package>/lp5/.  v1 is all Android
     needs for an app that targets an API this old, so no JDK, apksigner or
     uber-apk-signer is involved.

    python lp5_apk.py IN.apk OUT.apk [--host http://10.0.2.2:8080/]
"""
import argparse
import base64
import hashlib
import io
import json
import secrets
import struct
import sys
import time
import zipfile
from pathlib import Path

DLL = "assets/bin/Data/Managed/Assembly-CSharp.dll"
DOMAIN = "http://reunion.little-prince.com.hk/"
HERE = Path(__file__).resolve().parent
KEY_FILE = HERE.parent / "lp5" / "signing-key.json"


# ─── the address patch ────────────────────────────────────────────────────────

def patch_domain(dll: bytearray, new: str):
    """Global's server address (two copies in the #US heap) -> `new`, same length."""
    if len(new) > len(DOMAIN):
        raise ValueError("the address must be at most %d characters" % len(DOMAIN))
    pad = len(DOMAIN) - len(new)
    padded = new.rstrip("/") + "/" + "./" * (pad // 2) + ("/" if pad % 2 else "")
    if len(padded) != len(DOMAIN):
        raise ValueError("could not pad %r to %d characters" % (new, len(DOMAIN)))
    old_b, new_b = DOMAIN.encode("utf-16-le"), padded.encode("utf-16-le")
    count = dll.count(old_b)
    if not count:
        raise ValueError("the publisher's address is not in this assembly - not v1.13?")
    dll[:] = dll.replace(old_b, new_b)
    return count, padded


# ─── RSA and DER, just enough for a JAR signature ────────────────────────────

def _is_probable_prime(n, rounds=40):
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits):
    while True:
        c = secrets.randbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if _is_probable_prime(c):
            return c


def _der_len(n):
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _tlv(tag, body):
    return bytes([tag]) + _der_len(len(body)) + body


def _int(v):
    b = v.to_bytes(max(1, (v.bit_length() + 8) // 8), "big")   # room for the sign bit
    return _tlv(0x02, b)


def _seq(*parts):
    return _tlv(0x30, b"".join(parts))


def _set(*parts):
    return _tlv(0x31, b"".join(parts))


def _oid(dotted):
    nums = [int(x) for x in dotted.split(".")]
    out = bytes([40 * nums[0] + nums[1]])
    for n in nums[2:]:
        chunk = [n & 0x7F]
        n >>= 7
        while n:
            chunk.append(0x80 | (n & 0x7F))
            n >>= 7
        out += bytes(reversed(chunk))
    return _tlv(0x06, out)


NULL = b"\x05\x00"
OID_RSA = "1.2.840.113549.1.1.1"
OID_SHA256_RSA = "1.2.840.113549.1.1.11"
OID_SHA256 = "2.16.840.1.101.3.4.2.1"
OID_SHA1 = "1.3.14.3.2.26"
OID_DATA = "1.2.840.113549.1.7.1"
OID_SIGNED = "1.2.840.113549.1.7.2"
OID_CN = "2.5.4.3"
SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")
SHA1_PREFIX = bytes.fromhex("3021300906052b0e03021a05000414")


def _rsa_sign(key, data: bytes, sha1=False) -> bytes:
    """PKCS#1 v1.5 with SHA-256 (or SHA-1, for the JAR signature itself)."""
    n, d = key["n"], key["d"]
    k = (n.bit_length() + 7) // 8
    t = (SHA1_PREFIX + hashlib.sha1(data).digest() if sha1
         else SHA256_PREFIX + hashlib.sha256(data).digest())
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")


def _name(cn):
    return _seq(_set(_seq(_oid(OID_CN), _tlv(0x0C, cn.encode("utf-8")))))


def _utc(t):
    return _tlv(0x17, time.strftime("%y%m%d%H%M%SZ", time.gmtime(t)).encode())


def _gentime(year):
    return _tlv(0x18, ("%04d1231235959Z" % year).encode())


def make_key(cn="Little Prince Launcher (local build)"):
    """A fresh RSA-2048 key and a self-signed certificate for it."""
    e = 65537
    while True:
        p, q = _prime(1024), _prime(1024)
        phi = (p - 1) * (q - 1)
        if p != q and phi % e:
            break
    n = p * q
    key = {"n": n, "e": e, "d": pow(e, -1, phi)}
    spki = _seq(_seq(_oid(OID_RSA), NULL),
                _tlv(0x03, b"\x00" + _seq(_int(n), _int(e))))
    alg = _seq(_oid(OID_SHA256_RSA), NULL)
    serial = secrets.randbits(63) | 1
    tbs = _seq(_tlv(0xA0, _int(2)), _int(serial), alg, _name(cn),
               _seq(_utc(time.time() - 86400), _gentime(2075)), _name(cn), spki)
    cert = _seq(tbs, alg, _tlv(0x03, b"\x00" + _rsa_sign(key, tbs)))
    key.update(cert=cert, serial=serial, cn=cn)
    return key


def load_key(path: Path = KEY_FILE):
    """The machine's signing key - made once, so updates install over each other."""
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {"n": int(raw["n"]), "e": int(raw["e"]), "d": int(raw["d"]),
                "cert": base64.b64decode(raw["cert"]), "serial": int(raw["serial"]),
                "cn": raw["cn"]}
    key = make_key()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"n": str(key["n"]), "e": key["e"], "d": str(key["d"]),
                                "cert": base64.b64encode(key["cert"]).decode(),
                                "serial": str(key["serial"]), "cn": key["cn"]}),
                    encoding="utf-8")
    return key


def _pkcs7(key, sf: bytes) -> bytes:
    """A detached PKCS#7 SignedData over the .SF file (CERT.RSA).

    SHA-1 throughout the JAR signature: the app's minSdk is 9, and Android before
    4.3 (API 18) only verifies SHA-1 JAR signatures.
    """
    sha = _seq(_oid(OID_SHA1), NULL)
    signer = _seq(_int(1), _seq(_name(key["cn"]), _int(key["serial"])), sha,
                  _seq(_oid(OID_RSA), NULL), _tlv(0x04, _rsa_sign(key, sf, sha1=True)))
    signed = _seq(_int(1), _set(sha), _seq(_oid(OID_DATA)),
                  _tlv(0xA0, key["cert"]), _set(signer))
    return _seq(_oid(OID_SIGNED), _tlv(0xA0, signed))


# ─── manifest files ───────────────────────────────────────────────────────────

def _wrap(line: str) -> bytes:
    """A manifest line, wrapped at 72 bytes with continuation lines."""
    raw = line.encode("utf-8")
    out, first = [], True
    while raw:
        width = 72 if first else 71
        out.append((b"" if first else b" ") + raw[:width])
        raw = raw[width:]
        first = False
    return b"\r\n".join(out) + b"\r\n"


def _b64sha(data):
    return base64.b64encode(hashlib.sha1(data).digest()).decode()


def sign_entries(entries, key):
    """{name: bytes} -> the three META-INF files of a v1 signature."""
    head = b"Manifest-Version: 1.0\r\nCreated-By: 1.0 (Little Prince Launcher)\r\n\r\n"
    sections, manifest = [], head
    for name, data in entries:
        sec = _wrap("Name: " + name) + _wrap("SHA1-Digest: " + _b64sha(data)) + b"\r\n"
        sections.append((name, sec))
        manifest += sec
    sf = (b"Signature-Version: 1.0\r\nCreated-By: 1.0 (Little Prince Launcher)\r\n"
          + _wrap("SHA1-Digest-Manifest: " + _b64sha(manifest))
          + _wrap("SHA1-Digest-Manifest-Main-Attributes: " + _b64sha(head)) + b"\r\n")
    for name, sec in sections:
        sf += _wrap("Name: " + name) + _wrap("SHA1-Digest: " + _b64sha(sec)) + b"\r\n"
    return manifest, sf, _pkcs7(key, sf)


# ─── the build ────────────────────────────────────────────────────────────────

def build(src_apk, out_apk, host, log=print, key=None):
    """Patch, repack (aligned) and sign.  Returns the padded address used."""
    key = key or load_key()
    src = zipfile.ZipFile(str(src_apk))
    dll = bytearray(src.read(DLL))
    count, padded = patch_domain(dll, host)
    log("  server address: %d copies -> %s" % (count, padded))
    entries = []
    for info in src.infolist():
        name = info.filename
        if name.startswith("META-INF/") and name.upper().endswith(
                (".SF", ".RSA", ".DSA", ".EC", "MANIFEST.MF")):
            continue                                  # the publisher's signature
        if name.endswith("/"):
            continue
        data = bytes(dll) if name == DLL else src.read(info)
        entries.append((info, data))
    manifest, sf, rsa = sign_entries([(i.filename, d) for i, d in entries], key)
    tmp = Path(str(out_apk) + ".part")
    with open(tmp, "wb") as fh:
        with zipfile.ZipFile(fh, "w") as dst:
            def put(name, data, stored, date_time=(2016, 6, 25, 0, 0, 0), attr=0):
                zi = zipfile.ZipInfo(name, date_time=date_time)
                zi.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
                zi.external_attr = attr
                if stored:                            # zipalign: data on a 4-byte boundary
                    start = fh.tell() + 30 + len(name.encode("utf-8"))
                    zi.extra = b"\x00" * ((4 - start % 4) % 4)
                dst.writestr(zi, data)
            put("META-INF/MANIFEST.MF", manifest, False)
            put("META-INF/CERT.SF", sf, False)
            put("META-INF/CERT.RSA", rsa, False)
            for info, data in entries:
                put(info.filename, data, info.compress_type == zipfile.ZIP_STORED,
                    info.date_time, info.external_attr)
    tmp.replace(out_apk)
    log("  signed (v1, %d entries) -> %s" % (len(entries), Path(out_apk).name))
    return padded


def main():
    ap = argparse.ArgumentParser(description="build the local 星夜重圓 APK")
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--host", default="http://10.0.2.2:8080/")
    a = ap.parse_args()
    build(a.src, a.dst, a.host)
    return 0


if __name__ == "__main__":
    sys.exit(main())
