#!/usr/bin/env python3
"""Does progress survive a re-login?  Report a minigame result, then log in and read the
values out of the login4 user array."""
import importlib.util, json, sys, urllib.request, urllib.error
from pathlib import Path

PKG = Path.home() / "Downloads/littleprince-patcher"
sys.path.insert(0, str(PKG / "lpo"))
import amf0                                        # noqa: E402
import accounts                                    # noqa: E402

BASE = "http://127.0.0.1:8080"
EMAIL, PASSWORD = "progress@local.test", "progresspw"


def amf_packet(values, target="/1", response="null"):
    """What the client actually posts: version + counts + target + response + body."""
    import struct
    body = amf0.encode(values)

    def raw_str(t):
        b = t.encode()
        return struct.pack("!H", len(b)) + b

    return (struct.pack("!HHH", 0, 0, 1) + raw_str(target) + raw_str(response)
            + struct.pack("!I", len(body)) + body)


def post(path, payload, raw=False):
    body = payload if raw else json.dumps(payload).encode()
    ctype = "application/x-amf" if raw else "application/json"
    req = urllib.request.Request(BASE + path, data=body,
                                 headers={"Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# 1. an account to attach the progress to
code, out = post("/web/api/register", {"email": EMAIL, "password": PASSWORD,
                                       "name": "Progress Tester", "sex": "1",
                                       "birth": "2000-01-01", "school_name": "",
                                       "school_level": "3", "class_name": "0", "class_no": "-"})
if code != 200:                                      # already registered earlier
    code, out = post("/web/api/login", {"email": EMAIL, "password": PASSWORD})
uid = json.loads(out)["account"]["uid"]
print(f"account {EMAIL} uid={uid} (http {code})")

# 2. what a minigame reports when it finishes
result = {"type": "gameResult", "uid": uid, "score": 1234, "coins": 5000,
          "totalItems": 3, "crystal0": 7, "high": 99}
code, out = post("/littleprince/amfservice/gateway.php",
                 amf_packet([amf0.AmfObject(result)]), raw=True)
print(f"reported a game result -> http {code}")

# 3. what the account file holds now
acct = accounts.get(EMAIL)
prof = acct["profile"]
print("stored in accounts.json:", {k: prof.get(k) for k in
                                   ("coins", "score", "crystal0", "totalItems", "high")})

# 4. log in again and read the user array the game gets
code, out = post("/littleprince/amfservice/gateway.php",
                 amf_packet([amf0.AmfObject({"type": "login4", "loginname": EMAIL,
                                             "password": PASSWORD})]), raw=True)
import struct
def unwrap(packet):
    """Skip the packet envelope and decode the body values."""
    if len(packet) < 6:
        return []
    hdrs, _ = struct.unpack("!H", packet[2:4])[0], None
    off = 6
    def raw_str(o):
        n = struct.unpack("!H", packet[o:o + 2])[0]
        return packet[o + 2:o + 2 + n].decode("utf-8", "replace"), o + 2 + n
    for _ in range(hdrs):
        _, off = raw_str(off); off += 1
        hl = struct.unpack("!I", packet[off:off + 4])[0]; off += 4 + hl
    _, off = raw_str(off)
    _, off = raw_str(off)
    blen = struct.unpack("!I", packet[off:off + 4])[0]; off += 4
    return amf0.decode(packet[off:off + blen])


def find_user(value):
    if isinstance(value, dict):
        if "user" in value:
            return value["user"]
        for v in value.values():
            got = find_user(v)
            if got is not None:
                return got
    elif isinstance(value, (list, tuple)):
        for v in value:
            got = find_user(v)
            if got is not None:
                return got
    return None


decoded = unwrap(out)
user = None
for value in decoded:
    user = find_user(value)
    if user is not None:
        break
if user is None:
    print("could not find the user array in the login4 reply; raw:", out[:120])
else:
    labels = ["uid", "permission", "email", "name", "sex", "birth", "gameLv", "createDate",
              "screen", "lang", "textlang", "volume", "fullscreen", "eventData", "left_total",
              "right_total", "mazeRec", "coins", "totalItems", "totalCrystals",
              "crystal0", "crystal1", "crystal2", "crystal3", "crystal4"]
    print("\nlogin4 says:")
    for i, v in enumerate(user[:len(labels)]):
        if labels[i] in ("coins", "score", "crystal0", "totalItems", "totalCrystals", "uid"):
            print(f"   {labels[i]:14s} {v}")
