"""Player accounts for the local Little Prince Online server.

Accounts live in accounts.json next to server.py.  Passwords are stored as
pbkdf2_hmac('sha256') hashes with a per-account salt - never in clear text.
The login name is the email address (that is what the game client sends).

Each account carries a full profile dict (same keys as profile.json) so the
game can be served that account's identity, stats and world bits.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
ACCOUNTS_PATH = BASE / "accounts.json"
_LOCK = threading.Lock()
_ITER = 200_000


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize(email: str) -> str:
    return (email or "").strip().lower()


MAX_PW = 8                     # the client's login box accepts no more
PW_CHARS = re.compile(r"^[A-Za-z0-9]+$")

# Progress fields the rank boards count, kept per month so the boards' 本月
# (this-month) view can show the month's gain next to the running total.
MONTH_TRACKED = ("coins", "totalItems", "totalCrystals")


def clean_password(password: str) -> str:
    """Validate a password the way the games' login box limits it.

    The official site asks for "up to 8 letters or digits", and the client's field
    silently stops at the eighth character.  A longer password could therefore be set
    on this site and then never be typed into the game, which locks the account out
    of the game while it still works in the browser - so refuse it here instead.
    """
    pw = (password or "").strip()
    if len(pw) < 4:
        raise ValueError("the password needs at least 4 characters")
    if len(pw) > MAX_PW:
        raise ValueError("the password can be at most %d characters - the game's login "
                         "box stops at 8" % MAX_PW)
    if not PW_CHARS.match(pw):
        raise ValueError("use letters and digits only, as the official site does")
    return pw


MAX_LOGIN = 20
LOGIN_CHARS = re.compile(r"^[A-Za-z0-9._-]+$")


def clean_login_name(login_name: str) -> str:
    """Validate the name a player types into the games' login box.

    Kept deliberately separate from the email: all three games show a single name
    field, and a child is not going to type an email address into it.  Anything
    that looks like an email is refused so the two identifiers cannot collide.
    """
    name = (login_name or "").strip()
    if not name:
        raise ValueError("a login name is required")
    if len(name) < 3:
        raise ValueError("the login name needs at least 3 characters")
    if len(name) > MAX_LOGIN:
        raise ValueError("the login name can be at most %d characters" % MAX_LOGIN)
    if "@" in name:
        raise ValueError("the login name cannot contain @ - that belongs to the email")
    if not LOGIN_CHARS.match(name):
        raise ValueError("use letters, digits, dot, dash or underscore only")
    return name


def _hash(password: str, salt: str = None) -> dict:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), _ITER)
    return {"algo": "pbkdf2_sha256", "iter": _ITER, "salt": salt, "hash": dk.hex()}


def hash_password(password: str, salt: str = None) -> dict:
    """Hash the part the game can send: the first eight characters."""
    rec = _hash((password or "")[:MAX_PW], salt)
    rec["len"] = len(password or "")
    return rec


def _matches(password: str, stored: dict) -> bool:
    """Compare one candidate against a stored hash, exactly as given."""
    if not stored or stored.get("algo") != "pbkdf2_sha256":
        return False
    cand = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                               bytes.fromhex(stored["salt"]), int(stored.get("iter", _ITER)))
    return hmac.compare_digest(cand.hex(), stored.get("hash", ""))


def check_password(password: str, stored: dict) -> bool:
    """Does this candidate match, as the game would send it (eight characters)?"""
    return _matches((password or "")[:MAX_PW], stored)


# ─── storage ────────────────────────────────────────────────────────────────

def _read() -> dict:
    if not ACCOUNTS_PATH.is_file():
        return {"accounts": []}
    try:
        data = json.loads(ACCOUNTS_PATH.read_text("utf-8"))
        if not isinstance(data.get("accounts"), list):
            data["accounts"] = []
        return data
    except Exception:
        return {"accounts": []}


def _write(data: dict):
    tmp = ACCOUNTS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    os.replace(tmp, ACCOUNTS_PATH)


# ─── API ────────────────────────────────────────────────────────────────────

def all_accounts() -> list:
    return _read()["accounts"]


def get(email: str):
    key = normalize(email)
    for a in all_accounts():
        if normalize(a.get("email")) == key:
            return a
    return None


def exists(email: str) -> bool:
    return get(email) is not None


def get_by_login(login_name: str):
    """The account whose login name matches, case-insensitively."""
    key = (login_name or "").strip().lower()
    if not key:
        return None
    for a in all_accounts():
        if (a.get("login_name") or "").strip().lower() == key:
            return a
    return None


def resolve(identifier: str):
    """Which account a typed identifier means: the login name, then the email.

    Every game shows one name box, so this is what the website sign-in and the
    in-game login both go through.
    """
    ident = (identifier or "").strip()
    if not ident:
        return None
    return get_by_login(ident) or get(ident)


def next_uid() -> str:
    nums = []
    for a in all_accounts():
        try:
            nums.append(int(a.get("uid", 0)))
        except (TypeError, ValueError):
            pass
    return str(max(nums + [10000]) + 1)


def create(email: str, password: str, profile: dict, name: str = None,
           login_name: str = None) -> dict:
    email = normalize(email)
    if not email or "@" not in email:
        raise ValueError("a valid email address is required")
    password = clean_password(password)
    login_name = clean_login_name(login_name) if login_name else None
    with _LOCK:
        data = _read()
        if any(normalize(a.get("email")) == email for a in data["accounts"]):
            raise ValueError("that email is already registered")
        if login_name and any((a.get("login_name") or "").strip().lower() == login_name.lower()
                              for a in data["accounts"]):
            raise ValueError("that login name is already taken")
        prof = dict(profile or {})
        prof["email"] = email
        if name:
            prof["name"] = name
        acct = {
            "email": email,
            "login_name": login_name,
            "uid": next_uid(),
            "created": _now(),
            "last_login": None,
            "pw": hash_password(password),
            "profile": prof,
        }
        acct["profile"]["uid"] = acct["uid"]
        acct["profile"].setdefault("createDate", _now())
        data["accounts"].append(acct)
        _write(data)
    return acct


def verify(identifier: str, password: str, touch: bool = True):
    """Return the account when the password matches, else None.

    `identifier` may be the account's login name or its email - the website's
    sign-in box accepts either, mirroring the single name box in the games.
    """
    found = resolve(identifier)
    if not found:
        return None
    key = normalize(found.get("email"))
    with _LOCK:
        data = _read()
        for a in data["accounts"]:
            if normalize(a.get("email")) == key:
                stored = a.get("pw", {})
                if not check_password(password or "", stored):
                    # A password set before the eight-character rule was hashed whole.
                    # The game can only ever send the first eight, so accept the full one
                    # once and rewrite it truncated - nobody has to re-type anything.
                    if not (stored and len(password or "") > MAX_PW and _matches(password, stored)):
                        return None
                    a["pw"] = hash_password(password)
                    _write(data)
                    log_line = "account %s: password stored in the 8-character form" % key
                    try:
                        print("  " + log_line, flush=True)
                    except Exception:                                # noqa: BLE001
                        pass
                if touch:
                    a["last_login"] = _now()
                    _write(data)
                return a
    return None


def update(email: str, patch: dict, profile_keys=None) -> dict:
    """Update profile fields (and optionally the email / password) of an account."""
    key = normalize(email)
    with _LOCK:
        data = _read()
        for a in data["accounts"]:
            if normalize(a.get("email")) != key:
                continue
            prof = a.setdefault("profile", {})
            for k, v in (patch or {}).items():
                if k == "login_name":
                    new = clean_login_name(v)
                    if any(o is not a and (o.get("login_name") or "").strip().lower()
                           == new.lower() for o in data["accounts"]):
                        raise ValueError("that login name is already taken")
                    a["login_name"] = new
                    continue
                if profile_keys is not None and k not in profile_keys:
                    continue
                if k == "permission":
                    prof["permission"] = max(0, min(0xFFFF, int(v)))
                elif k in ("crystal0", "crystal1", "crystal2", "crystal3", "crystal4",
                           "coins", "left_total", "right_total", "totalItems",
                           "totalCrystals", "eventData", "sex", "screenQuality",
                           "language", "textLanguage", "volume", "fullScreen"):
                    prof[k] = str(int(v))
                else:
                    prof[k] = str(v)
            _write(data)
            return a
    raise ValueError("no such account")


def transaction(email: str, mutate) -> dict:
    """Read/mutate/atomically replace one account while holding the save lock.

    The callback edits only this freshly read account. Exceptions abort the whole
    transaction, including private undo metadata, before any file is written.
    """
    key = normalize(email)
    with _LOCK:
        data = _read()
        for acct in data["accounts"]:
            if normalize(acct.get("email")) == key:
                mutate(acct)
                _write(data)
                return acct
    raise ValueError("no such account")


def set_game_result(email: str, game: int, level: int, row: list,
                    board_key: str = "gameResult") -> dict:
    """Record one level's score row on the account.

    LP1's report panel is fed entirely from the login reply's `gameResult`, so if
    the server does not keep these the 個人成績表 can only ever be blank.  The row
    is the six values the client sends with `setScore`:
    initS, initD, highS, highD, recentS, recentD.

    `board_key` names the board this row belongs to: each title keeps its OWN
    (see server.BOARD_KEYS), because LP1 and LP3 used to share one `gameResult`
    array and a level played in one therefore appeared - and unlocked - in the
    other.
    """
    key = normalize(email)
    with _LOCK:
        data = _read()
        for a in data["accounts"]:
            if normalize(a.get("email")) != key:
                continue
            board = a.get(board_key)
            if not isinstance(board, list):
                board = []
            while len(board) <= game:
                board.append([])
            while len(board[game]) <= level:
                board[game].append([0, "", 0, "", 0, ""])
            board[game][level] = list(row)
            a[board_key] = board
            _write(data)
            return a
    raise ValueError("no such account")


def set_progress(email: str, field: str, value) -> dict:
    """Remember one saved field of a game's progress on the account.

    Both LP2 and LP3 send their progress back one field at a time - gems, items,
    cards, cardSequence, process, equipment ... - and expect to get it again with
    the next login.  Nothing was keeping it, so every login started from scratch.
    """
    key = normalize(email)
    with _LOCK:
        data = _read()
        for a in data["accounts"]:
            if normalize(a.get("email")) != key:
                continue
            prog = a.get("progress")
            if not isinstance(prog, dict):
                prog = {}
            # The rank boards show a this-month view next to the all-time one.
            # Keep each counted field's value at the start of the month so the
            # month's gain can be told apart from the running total.
            if str(field) in MONTH_TRACKED:
                month = datetime.now().strftime("%Y%m")
                base = a.get("monthBase")
                if not isinstance(base, dict) or base.get("m") != month:
                    base = {"m": month}
                    a["monthBase"] = base
                old = prog.get(str(field))
                if old is None:
                    old = (a.get("profile") or {}).get(str(field))
                if old is None:
                    old = value
                base.setdefault(str(field), old)
            prog[str(field)] = value
            a["progress"] = prog
            _write(data)
            return a
    raise ValueError("no such account")


def get_progress(account: dict) -> dict:
    """The saved progress fields of an account (empty when none)."""
    prog = (account or {}).get("progress")
    return prog if isinstance(prog, dict) else {}


def set_password(email: str, new_password: str) -> dict:
    new_password = clean_password(new_password)
    key = normalize(email)
    with _LOCK:
        data = _read()
        for a in data["accounts"]:
            if normalize(a.get("email")) == key:
                a["pw"] = hash_password(new_password)
                _write(data)
                return a
    raise ValueError("no such account")


def rename(email: str, new_email: str) -> dict:
    new_email = normalize(new_email)
    if "@" not in new_email:
        raise ValueError("a valid email address is required")
    key = normalize(email)
    with _LOCK:
        data = _read()
        if any(normalize(a.get("email")) == new_email and normalize(a.get("email")) != key
               for a in data["accounts"]):
            raise ValueError("that email is already registered")
        for a in data["accounts"]:
            if normalize(a.get("email")) == key:
                a["email"] = new_email
                a.setdefault("profile", {})["email"] = new_email
                _write(data)
                return a
    raise ValueError("no such account")


def delete(email: str) -> bool:
    key = normalize(email)
    with _LOCK:
        data = _read()
        before = len(data["accounts"])
        data["accounts"] = [a for a in data["accounts"]
                            if normalize(a.get("email")) != key]
        if len(data["accounts"]) != before:
            _write(data)
            return True
    return False


def public(acct: dict, with_profile: bool = True) -> dict:
    """Account without the password material."""
    if not acct:
        return None
    out = {k: acct.get(k) for k in ("email", "login_name", "uid", "created", "last_login")}
    if with_profile:
        out["profile"] = acct.get("profile", {})
    return out
