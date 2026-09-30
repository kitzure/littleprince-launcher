#!/usr/bin/env python3
"""
Little Prince Online - client downloader.

Fetches the official game files straight from the publisher's server into a local
folder, so players do not have to find an installed copy of the game.

    python fetch_client.py                     # download into lpo/game
    python fetch_client.py --dest D:\\lp\\game
    python fetch_client.py --check             # verify an existing folder, no downloads
    python fetch_client.py --base http://other.host/LP/Po/

Files already present with the right size are skipped, part-downloaded files are
resumed with a range request, and every .swf is checked for a Flash header so an
error page can never be mistaken for a game file.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json as _json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Only ever used when the hosts redirect is active AND DNS-over-HTTPS cannot be
# reached - i.e. the address really has to be guessed.
FALLBACK_IPS = ("203.90.228.97",)

DEFAULT_BASE = "http://www1.little-prince.com.hk/LP/Po/"
HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "client_files.txt"
DEFAULT_DEST = HERE / "game"
RETRIES = 3
TIMEOUT = 60
CHUNK = 256 * 1024
UA = "littleprince-launcher/1.1 (+local server)"


def read_manifest(path=MANIFEST):
    """[(relative path, size)] from the manifest."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rel, _, size = line.rpartition("\t")
        if rel and size.isdigit():
            rows.append((rel.replace("\\", "/"), int(size)))
    return rows


def _url(base, rel):
    return base + "/".join(urllib.parse.quote(p) for p in rel.split("/"))


def _looks_like_flash(chunk: bytes) -> bool:
    return chunk[:3] in (b"FWS", b"CWS", b"ZWS")


def _head_of(path: Path, n=3) -> bytes:
    try:
        with open(path, "rb") as fh:
            return fh.read(n)
    except OSError:
        return b""


def _size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return -1


def _host_of(url):
    return urllib.parse.urlsplit(url).hostname or ""


def _resolves_to_loopback(host):
    """True when the name currently points at this machine (hosts redirect on)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    addrs = [i[4][0] for i in infos if i[4]]
    return bool(addrs) and all(a.startswith(("127.", "::1")) for a in addrs)


def _real_ip(host):
    """Ask a public resolver, because the local one is redirected."""
    for url in ("https://1.1.1.1/dns-query?name=%s&type=A" % host,
                "https://dns.google/resolve?name=%s&type=A" % host):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/dns-json",
                                                       "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = _json.loads(r.read().decode("utf-8", "replace"))
            for ans in data.get("Answer", []):
                ip = str(ans.get("data", ""))
                if ans.get("type") == 1 and ip and not ip.startswith("127."):
                    return ip
        except Exception:
            continue
    return ""


def resolve_base(base, log=print):
    """The hosts redirect makes the publisher's name point at 127.0.0.1, so a plain
    download would hit the local server (which has no files yet).

    Detect that and talk to the real address instead, keeping the Host header, so
    downloading works whether or not the redirect is on.  Returns (base, host).
    """
    host = _host_of(base)
    if not host or not _resolves_to_loopback(host):
        return base, ""
    log("  note: %s currently points at this PC (the hosts redirect is on)," % host)
    log("        so the official address would reach the local server instead.")
    ip = _real_ip(host)
    if not ip and host.endswith("little-prince.com.hk"):
        ip = FALLBACK_IPS[0]
        log("        DNS-over-HTTPS unavailable - using the known address %s" % ip)
    if ip:
        split = urllib.parse.urlsplit(base)
        log("        downloading straight from the publisher instead: %s" % ip)
        return "%s://%s%s" % (split.scheme, ip, split.path), host
    log("        could not work out the real address - press Revert hosts in the")
    log("        window (or run without the hosts redirect) and try again.")
    return base, host


def fetch_file(base, dest: Path, rel, size, cancel=None, chunk_cb=None, host_header=""):
    """Download one file. Returns ('ok'|'skipped', bytes) or raises."""
    target = dest / rel
    if _size_of(target) == size:
        if not rel.lower().endswith(".swf") or _looks_like_flash(_head_of(target)):
            return "skipped", 0
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    have = _size_of(part)
    if have > size:                       # nonsense leftover
        part.unlink(missing_ok=True)
        have = 0
    headers = {"User-Agent": UA}
    if host_header:
        headers["Host"] = host_header
    mode = "wb"
    if have > 0:
        headers["Range"] = "bytes=%d-" % have
        mode = "ab"
    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(_url(base, rel), headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r, open(part, mode) as fh:
                got = 0
                while True:
                    if cancel is not None and cancel.is_set():
                        raise KeyboardInterrupt("cancelled")
                    block = r.read(CHUNK)
                    if not block:
                        break
                    fh.write(block)
                    got += len(block)
                    if chunk_cb is not None:
                        chunk_cb(len(block))
            if _size_of(part) != size:
                raise IOError("size %d, expected %d" % (_size_of(part), size))
            if rel.lower().endswith(".swf") and not _looks_like_flash(_head_of(part)):
                part.unlink(missing_ok=True)
                raise IOError("not a Flash file (server sent something else)")
            os.replace(part, target)
            return "ok", got
        except KeyboardInterrupt:
            raise
        except Exception as e:            # noqa: BLE001 - report and retry
            last = e
            if attempt < RETRIES:
                time.sleep(1.5 * attempt)
                have = _size_of(part)
                have = have if have > 0 else 0
                headers = {"User-Agent": UA}
                if host_header:
                    headers["Host"] = host_header
                mode = "wb"
                if have > 0:
                    headers["Range"] = "bytes=%d-" % have
                    mode = "ab"
    raise IOError(str(last))


def fetch(dest=None, base=DEFAULT_BASE, manifest=MANIFEST, workers=6,
          progress=None, cancel=None, only=None, log=None):
    """Download the client. progress(dict) is called as it goes.

    Returns a summary dict: total/ok/skipped/failed/bytes/notes.
    """
    rows = read_manifest(manifest)
    if only:
        rows = [r for r in rows if only in r[0]]
    dest = Path(dest or DEFAULT_DEST)
    dest.mkdir(parents=True, exist_ok=True)
    total_bytes = sum(s for _, s in rows)
    state = {"files": 0, "ok": 0, "skipped": 0, "failed": [], "bytes": 0,
             "total": len(rows), "total_bytes": total_bytes, "current": "", "notes": []}
    lock = threading.Lock()
    notes = []

    def say(msg):
        notes.append(str(msg))
        with lock:
            state["notes"] = list(notes)
        if log is not None:
            log(msg)

    # if the hosts redirect is on, the publisher's name points at this PC - go to
    # the real address instead, so the download still works
    base, host_header = resolve_base(base, log=say)

    def report(name=""):
        with lock:
            state["current"] = name
            if progress is not None:
                try:
                    progress(dict(state))
                except Exception:
                    pass

    def work(row):
        rel, size = row
        report(rel)
        try:
            kind, got = fetch_file(base, dest, rel, size, cancel=cancel,
                                   chunk_cb=None, host_header=host_header)
        except KeyboardInterrupt:
            raise
        except Exception as e:            # noqa: BLE001
            with lock:
                state["failed"].append((rel, str(e)))
                state["files"] += 1
            report(rel)
            return
        with lock:
            state["files"] += 1
            state["bytes"] += got if kind == "ok" else 0
            state[kind] += 1
        report(rel)

    workers = max(1, min(16, workers))
    if workers == 1:
        for row in rows:
            work(row)
    else:
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(work, rows))
    report("")
    return state


def check(dest=None, manifest=MANIFEST, progress=None):
    """Report what an existing folder is missing, without downloading anything."""
    rows = read_manifest(manifest)
    dest = Path(dest or DEFAULT_DEST)
    missing, wrong, present = [], [], 0
    for rel, size in rows:
        f = dest / rel
        have = _size_of(f)
        if have == size and (not rel.lower().endswith(".swf")
                             or _looks_like_flash(_head_of(f))):
            present += 1
        elif have < 0:
            missing.append(rel)
        else:
            wrong.append(rel)
        if progress is not None and (present + len(missing) + len(wrong)) % 25 == 0:
            progress({"checked": present + len(missing) + len(wrong), "total": len(rows)})
    return {"present": present, "missing": missing, "wrong": wrong, "total": len(rows)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Download the Little Prince Online client")
    ap.add_argument("--dest", help="folder to download into (default lpo/game)")
    ap.add_argument("--base", default=os.environ.get("LPO_CLIENT_BASE", DEFAULT_BASE),
                    help="where the client files are served from")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--check", action="store_true", help="only verify, do not download")
    ap.add_argument("--only", help="download just the entries containing this text")
    args = ap.parse_args(argv)

    if args.check:
        res = check(args.dest)
        print("present %d / %d, missing %d, wrong size %d"
              % (res["present"], res["total"], len(res["missing"]), len(res["wrong"])))
        for rel in (res["missing"][:10] + res["wrong"][:10]):
            print("   ", rel)
        return 0

    rows = read_manifest()
    print("Downloading the Little Prince Online client from")
    print("   ", args.base)
    print("   ", len(rows), "files, %.0f MB" % (sum(s for _, s in rows) / 1e6))
    started = time.time()

    def show(st):
        pct = 100.0 * st["bytes"] / st["total_bytes"] if st["total_bytes"] else 0
        sys.stdout.write("\r  %3d/%d files  %5.1f%%  %s          "
                         % (st["files"], st["total"], pct, st["current"][:38]))
        sys.stdout.flush()

    st = fetch(args.dest, base=args.base, workers=args.workers, progress=show,
               only=args.only, log=print)
    print()
    took = time.time() - started
    print("done: %d new, %d already there, %d failed, %.0f MB in %.0fs"
          % (st["ok"], st["skipped"], len(st["failed"]), st["bytes"] / 1e6, took))
    for rel, err in st["failed"][:10]:
        print("   failed:", rel, "-", err)
    return 1 if st["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
