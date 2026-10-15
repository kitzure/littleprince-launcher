#!/usr/bin/env python3
"""Fetch or repair 星願思語 (Little Prince 4, the "horoscope" game).

LP4 is the publisher's web build at http://horoscope.little-prince.com.hk/games/
(the same site as www1.little-prince.com.hk/lp4/).  Its old resource folder
lp4/res/ is gone, but every texture, atlas and track still sits beside the SWF in
games/, and the question banks, item tables and battle levels are still answered by
the publisher's PHP.  This copies all of it into <package>/lp4/ so lpo/server.py can
serve the game with no connection:

    python fetch_lp4.py --check      report what is missing
    python fetch_lp4.py              download whatever is missing

The list of files is lp4_files.txt, beside this script.  Nothing account-related is
copied: the publisher's rank tables carry real players' names and stay there.
"""
import argparse
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    from fetch_client import resolve_base                              # noqa: E402
except Exception:                                                      # noqa: BLE001
    resolve_base = None

DEFAULT_DEST = HERE.parent / "lp4"
MANIFEST = HERE / "lp4_files.txt"
ASSET_BASE = "http://horoscope.little-prince.com.hk/"           # games/... lives here
PHP_BASE = "http://www1.little-prince.com.hk/lp4/"              # the PHP back end
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) littleprince-launcher/1.0"


def read_manifest(path: Path = MANIFEST):
    """[(rel, size)] - size 0 means a PHP answer whose bytes may change."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "\t" not in line:
            continue
        rel, _, size = line.rpartition("\t")
        try:
            rows.append((rel, int(size)))
        except ValueError:
            continue
    return rows


def check(dest: Path = DEFAULT_DEST):
    """(missing, wrong size) against the manifest."""
    missing, wrong = [], []
    for rel, size in read_manifest():
        target = dest / rel
        if not target.is_file():
            missing.append(rel)
        elif size and target.stat().st_size != size:
            wrong.append(rel)
    return missing, wrong


def _request(rel):
    """(url, POST data) the publisher answers `rel` with."""
    if rel.startswith("games/"):
        return ASSET_BASE + urllib.parse.quote(rel), None
    if rel == "BackEndEdit/omg.txt":
        return PHP_BASE + rel, None
    name = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    if rel.startswith("_data/qb/"):                   # A1_default.xml -> mode A1
        mode, _, set_name = name.partition("_")
        return (PHP_BASE + "admin/lib/XMLGen/XML_QuestionBank.php",
                {"mode": mode, "setName": set_name or "default", "schoolID": "-1"})
    if rel.startswith("_data/items/"):                # GetShopItem.txt -> method
        return PHP_BASE + "phpServices/ItemManagement.php", {"method": name}
    raise ValueError("no source known for %s" % rel)


def fetch(dest: Path = DEFAULT_DEST, log=print, progress=None, only=None):
    """Download every missing or wrong-sized file.  Returns (ok, [(rel, why)]).

    `progress(done, total)` is called after each file.  With the hosts redirect on,
    the publisher's names point at this PC, so the real address is looked up first
    and the original Host header kept - the same route fetch_cloud.py takes.
    """
    missing, wrong = check(dest)
    todo = [r for r in missing + wrong if only is None or r in only]
    bases = {}
    for base in (ASSET_BASE, PHP_BASE):
        bases[base] = resolve_base(base, log=log) if resolve_base else (base, "")
    import concurrent.futures
    import threading
    lock = threading.Lock()
    counts = {"done": 0, "ok": 0}
    failed = []

    def one(rel):
        try:
            url, form = _request(rel)
            for base, (real, host) in bases.items():
                if url.startswith(base):
                    url = real + url[len(base):]
                    break
            else:
                host = ""
            headers = {"User-Agent": UA}
            if host:
                headers["Host"] = host
            data = urllib.parse.urlencode(form).encode() if form else None
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            head = body[:200].lstrip().lower()
            if not body:
                raise IOError("empty answer")
            if rel.startswith("games/") and not rel.endswith((".xml", ".txt", ".json")) \
                    and (head.startswith(b"<!doctype html") or head.startswith(b"<html")):
                raise IOError("a web page instead of the file")
            if b"<b>notice</b>" in head or b"<b>warning</b>" in head:
                raise IOError("the publisher's PHP answered with an error")
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_name(target.name + ".part")
            part.write_bytes(body)
            part.replace(target)
            with lock:
                counts["ok"] += 1
        except Exception as exc:                                      # noqa: BLE001
            with lock:
                failed.append((rel, str(exc)[:80]))
        with lock:
            counts["done"] += 1
            done = counts["done"]
        if progress is not None:
            progress(done, len(todo))

    # a few at a time: ~580 files, most of them small atlases
    with concurrent.futures.ThreadPoolExecutor(6) as pool:
        list(pool.map(one, todo))
    return counts["ok"], failed


def main():
    ap = argparse.ArgumentParser(description="fetch or check 星願思語 (LP4)")
    ap.add_argument("--dest", default=str(DEFAULT_DEST))
    ap.add_argument("--check", action="store_true", help="report only")
    args = ap.parse_args()
    dest = Path(args.dest)
    missing, wrong = check(dest)
    total = len(read_manifest())
    print("LP4: %d files listed, %d missing, %d the wrong size"
          % (total, len(missing), len(wrong)))
    if args.check or not (missing or wrong):
        return 0

    def show(done, n):
        if done == n or done % 50 == 0:
            print("  %d / %d" % (done, n), flush=True)

    ok, failed = fetch(dest, progress=show)
    print("LP4: %d fetched, %d failed" % (ok, len(failed)))
    for rel, why in failed[:20]:
        print("  %s: %s" % (rel, why))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
