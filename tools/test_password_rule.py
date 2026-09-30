#!/usr/bin/env python3
"""The 8-character rule, and that a password set before it still works."""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

PKG = Path.home() / "Downloads/littleprince-patcher"
sys.path.insert(0, str(PKG / "lpo"))
import accounts                                                        # noqa: E402

BASE = "http://127.0.0.1:8080"
FAILS = []


def check(label, got, want):
    ok = got == want
    print("%-58s %s" % (label, "ok" if ok else "FAILED (%r != %r)" % (got, want)))
    if not ok:
        FAILS.append(label)


def api(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


print("1. the website refuses what the game could not type")
def reg(email, pw):
    return api("/web/api/register", {"email": email, "password": pw, "name": "Tester",
                                     "sex": "1", "birth": "2000-01-01", "school_name": "",
                                     "school_level": "3", "class_name": "0", "class_no": "-"})

st, body = reg("toobig@local.test", "abcdefghij")          # 10 characters
check("10 characters -> refused", st, 400)
print("      message: %s" % body.get("error"))
check("   and it says why", "8" in (body.get("error") or ""), True)

st, body = reg("symbols@local.test", "ab!cd")
check("punctuation -> refused", st, 400)

st, body = reg("eight@local.test", "abcd1234")             # exactly 8, letters+digits
check("8 letters/digits -> accepted", st in (200, 201), True)

print("\n2. that account verifies with what the game can send")
check("verify('abcd1234')", bool(accounts.verify("eight@local.test", "abcd1234")), True)
# the game's box stops at the eighth character, so 9 typed there means 8 here
check("a 9-character input matches its first 8 (the game's box truncates)",
      bool(accounts.verify("eight@local.test", "abcd12345")), True)
check("a genuinely wrong password is refused",
      accounts.verify("eight@local.test", "abcd9999"), None)

print("\n3. a password stored before the rule (hashed whole, 15 characters)")
LEGACY = "longpassword123"
acct = accounts.get("legacy@local.test")
if not acct:
    data = json.loads((PKG / "lpo/accounts.json").read_text()) if (PKG / "lpo/accounts.json").exists() else {"accounts": []}
    data.setdefault("accounts", []).append({
        "email": "legacy@local.test", "uid": "0999", "created": "2026-01-01 00:00:00",
        "last_login": None, "pw": accounts._hash(LEGACY),      # the old, whole-string hash
        "profile": {"email": "legacy@local.test", "name": "Legacy", "permission": 511}})
    (PKG / "lpo/accounts.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))

check("the full 15-character password still works", bool(accounts.verify("legacy@local.test", LEGACY)), True)
stored = accounts.get("legacy@local.test")["pw"]
check("   and is now stored in the 8-character form", "len" in stored, True)
check("the game's 8-character input now works", bool(accounts.verify("legacy@local.test", LEGACY[:8])), True)
check("a wrong password is still refused", accounts.verify("legacy@local.test", "nottheright"), None)

# clean up: remove every test row from accounts.json
import json as _json
path = PKG / "lpo/accounts.json"
if path.exists():
    data = _json.loads(path.read_text())
    keep = [a for a in data.get("accounts", [])
            if not a.get("email", "").endswith("@local.test")]
    data["accounts"] = keep
    path.write_text(_json.dumps(data, ensure_ascii=False, indent=2))
print("test accounts left in accounts.json: %d" % len(keep))
print("\n%s" % ("all checks passed" if not FAILS else "FAILURES: %s" % FAILS))
sys.exit(1 if FAILS else 0)
