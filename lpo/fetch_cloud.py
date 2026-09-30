#!/usr/bin/env python3
"""Fetch or repair the mirrored cloud games (LP1 / LP2 / LP3).

The three games in `cloud/` are the publisher's own cloud builds, served from
their URLs so their Flash browser - or the bundled Ruffle player - loads them
without a connection to the real site.  This tool makes that mirror verifiable
and repairable:

    python fetch_cloud.py --check            report missing or wrong-sized files
    python fetch_cloud.py                    download whatever is missing
    python fetch_cloud.py --cloud D:\\other    work on a mirror somewhere else
    python fetch_cloud.py --list             show the manifest

Files come straight from the publisher (http://www1.little-prince.com.hk/LP/
personal/...).  If the hosts file currently redirects that name to this machine,
the downloader resolves the real address over DNS-over-HTTPS and keeps the
original Host header, exactly like the Little Prince Online fetcher does.
"""
import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    from fetch_client import resolve_base                              # noqa: E402
except Exception:                                                      # noqa: BLE001
    resolve_base = None

DEFAULT_CLOUD = HERE.parent / "cloud"
DEFAULT_BASE = "http://www1.little-prince.com.hk/LP/personal/"
MANIFEST = "files.txt"


def read_manifest(cloud: Path):
    """[(relative path, size)] from the shipped list."""
    path = cloud / MANIFEST
    if not path.exists():
        return []
    # MUST be read as UTF-8 explicitly.  The manifest holds Chinese file names
    # (LP2/game11/複製 -pvo/...), and Path.read_text() with no encoding uses the
    # *locale* code page - UTF-8 on Linux, but cp950 on a Chinese Windows, where
    # it raises UnicodeDecodeError.  That silently made every game look
    # uninstalled there, so the portal never turned a card to "play" and the
    # installer restarted the same download forever.
    text = None
    for enc in ("utf-8", "cp950", "big5", "cp1252"):
        try:
            text = path.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        text = path.read_text(encoding="utf-8", errors="replace")
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "\t" not in line:
            continue
        rel, _, size = line.rpartition("\t")
        try:
            rows.append((rel, int(size)))
        except ValueError:
            continue
    return rows


def check(cloud: Path):
    """(missing, wrong size) against the manifest."""
    missing, wrong = [], []
    for rel, size in read_manifest(cloud):
        target = cloud / rel
        if not target.exists():
            missing.append(rel)
        elif size and target.stat().st_size != size:
            wrong.append(rel)
    return missing, wrong


CLIENTS = "client.txt"


def read_clients(cloud: Path):
    """[(code, file, size, md5)] - the files that carry the game's client.

    These have to be the publisher's build.  The CD ships its own client for each
    game - a registration shell that asks for a serial - and for some of them the
    CD file is exactly the *same size* as the publisher's, so a size check cannot
    tell them apart.  Only a hash can.
    """
    path = cloud / CLIENTS
    rows = []
    if not path.exists():
        return rows
    # UTF-8 explicitly, like the manifest: no locale surprises on Windows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        code, name, size, digest = parts
        try:
            rows.append((code, name, int(size), digest.strip().lower()))
        except ValueError:
            continue
    return rows


def client_bad(cloud: Path, code: str):
    """The client files of `code` that are not the publisher's build."""
    bad = []
    for c, name, size, digest in read_clients(cloud):
        if c != code:
            continue
        target = cloud / code / name
        try:
            data = target.read_bytes()
        except OSError:
            bad.append(name)
            continue
        if len(data) != size or hashlib.md5(data).hexdigest() != digest:
            bad.append(name)
    return bad


def fetch(cloud: Path, base=DEFAULT_BASE, log=print, only=None):
    """Download every missing or wrong-sized file.  Returns (ok, failed)."""
    host_header = ""
    if resolve_base:
        base, host_header = resolve_base(base, log=log)
    if host_header:
        log("the redirect is active - downloading from the real address instead")
    rows = read_manifest(cloud)
    if not rows:
        log("no manifest at %s" % (cloud / MANIFEST))
        return 0, []
    ok, failed = 0, []
    for rel, size in rows:
        target = cloud / rel
        if only and rel not in only:
            continue
        if target.exists() and (not size or target.stat().st_size == size):
            ok += 1
            continue
        url = base + rel
        try:
            req = urllib.request.Request(url)
            if host_header:
                req.add_header("Host", host_header)
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                status = r.status
            if status != 200 or not data:
                failed.append((rel, "http %s" % status))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            ok += 1
            log("  fetched %-34s %8d bytes" % (rel, len(data)))
        except Exception as exc:                                       # noqa: BLE001
            failed.append((rel, str(exc)[:60]))
    return ok, failed


def main() -> int:
    ap = argparse.ArgumentParser(description="verify or repair the cloud mirror")
    ap.add_argument("--cloud", default=str(DEFAULT_CLOUD), help="the cloud folder")
    ap.add_argument("--base", default=DEFAULT_BASE, help="publisher's base URL")
    ap.add_argument("--check", action="store_true", help="report only, download nothing")
    ap.add_argument("--list", action="store_true", help="print the manifest")
    args = ap.parse_args()

    cloud = Path(args.cloud)
    if args.list:
        for rel, size in read_manifest(cloud):
            print("%-40s %10d" % (rel, size))
        return 0

    missing, wrong = check(cloud)
    print("%s: %d files in the manifest" % (cloud, len(read_manifest(cloud))))
    print("missing: %d    wrong size: %d" % (len(missing), len(wrong)))
    for rel in (missing + wrong)[:20]:
        print("   %s" % rel)
    if args.check:
        return 1 if (missing or wrong) else 0

    if not missing and not wrong:
        print("nothing to fetch - the mirror is complete")
        return 0
    ok, failed = fetch(cloud, base=args.base)
    print("in place: %d    could not fetch: %d" % (ok, len(failed)))
    for rel, why in failed[:10]:
        print("   %s (%s)" % (rel, why))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
