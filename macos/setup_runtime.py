#!/usr/bin/env python3
"""
Little Prince Launcher (macOS) - Flash runtime setup.

The publisher ships their own Flash browser for Windows only, so on macOS the
closest equivalent is fetched instead:

  * Chromium M87 (revision 812851) - the last Flash-capable branch. Chromium
    after M87 has the Pepper Flash code removed, so an earlier build is required.
  * Pepper Flash Player 32.0.0.465 - the same version the publisher's Windows
    browser carries. It is already inside this package (runtime/), extracted
    from Adobe's own macOS installer, so nothing has to be installed.

Everything lands in this package's runtime/ folder: no administrator rights, no
/Library changes, no hosts edits. Run with --check to only report what is there.
"""

import argparse
import os
import plistlib
import shutil
import ssl
import stat
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                      # the launcher folder (Start.bat lives here)
RUNTIME = HERE / 'runtime'
PLUGIN = RUNTIME / 'PepperFlashPlayer.plugin'
PLUGIN_BIN = PLUGIN / 'Contents' / 'MacOS' / 'PepperFlashPlayer'

CHROMIUM_REV = '812851'                 # M87 - the last branch with Pepper Flash
CHROMIUM_URL = ('https://commondatastorage.googleapis.com/chromium-browser-snapshots/'
                'Mac/%s/chrome-mac.zip' % CHROMIUM_REV)


def chromiums():
    """Every Chromium.app inside runtime/, newest first."""
    if not RUNTIME.exists():
        return []
    return sorted(RUNTIME.glob('**/Chromium.app'), key=lambda p: -p.stat().st_mtime)


def chromium_binary():
    for app in chromiums():
        exe = app / 'Contents' / 'MacOS' / 'Chromium'
        if exe.exists():
            return exe
    return None


def plugin_version():
    info = PLUGIN / 'Contents' / 'Info.plist'
    if not info.exists():
        return None
    try:
        with info.open('rb') as fh:
            return plistlib.load(fh).get('CFBundleVersion')
    except Exception:
        return None


def plugin_ready():
    return PLUGIN_BIN.exists() and plugin_version() is not None


def rosetta_needed():
    """True when this is an Apple Silicon Mac without Rosetta (M87 is x86_64)."""
    if sys.platform != 'darwin':
        return False
    if os.uname().machine != 'arm64':
        return False
    try:
        return subprocess.run(['arch', '-x86_64', '/usr/bin/true'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=20).returncode != 0
    except Exception:
        return True


def install_rosetta(log=print):
    """Install Rosetta 2 on an Apple Silicon Mac, or explain why we cannot.

    Chromium M87 is x86_64 - there is no arm64 build of it, and no arm64 Pepper
    Flash either (Flash was removed from Chromium after M87) - so the whole Flash
    path on an M-series Mac runs under Rosetta.  Without it macOS refuses to exec
    the browser with '[Errno 86] Bad CPU type in executable', which reads like a
    corrupt download but is only the missing translation layer.
    """
    if not rosetta_needed():
        return True
    log('Rosetta 2 is missing. Chromium M87 and the Flash plugin are Intel')
    log('binaries, so macOS needs Rosetta to run them (macOS may ask for your')
    log('password now).')
    rc = 1
    try:
        rc = subprocess.call(['/usr/sbin/softwareupdate', '--install-rosetta',
                              '--agree-to-license'])
    except Exception as exc:
        log('could not run softwareupdate: %s' % exc)
    if not rosetta_needed():
        log('Rosetta 2 installed.')
        return True
    log('Rosetta 2 is still not available (softwareupdate exited %s).' % rc)
    log('Run this once in Terminal, then press Play again:')
    log('    softwareupdate --install-rosetta --agree-to-license')
    return False


def clear_quarantine(path):
    """A browser plugin that arrives from a download is quarantined; macOS will
    refuse to load it until the flag is gone. No admin rights are needed for a
    file the user owns."""
    try:
        subprocess.run(['xattr', '-dr', 'com.apple.quarantine', str(path)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    except Exception:
        pass


def human(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return '%.1f %s' % (n, unit)
        n /= 1024.0


def _ca_context():
    """A TLS context that can actually verify on a python.org build.

    python.org's Python carries its own OpenSSL and never looks at the macOS
    keychain, so a plain urlopen dies with CERTIFICATE_VERIFY_FAILED until the
    user runs Install Certificates.command.  Prefer certifi - that is the bundle
    the installer script wires up - and only then the default store.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _download_urllib(url, dest, log):
    req = urllib.request.Request(url, headers={'User-Agent': 'LittlePrinceLauncher/1.0'})
    with urllib.request.urlopen(req, timeout=60, context=_ca_context()) as resp, \
            open(dest, 'wb') as fh:
        total = int(resp.headers.get('Content-Length') or 0)
        done = 0
        last = -1
        while True:
            chunk = resp.read(262144)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            pct = int(done * 100 / total) if total else 0
            if pct >= last + 5:
                last = pct
                log('  downloaded %s%s' % (human(done), ' of %s (%d%%)' % (human(total), pct) if total else ''))
    return dest


def _download_curl(url, dest, log):
    """Fallback downloader: /usr/bin/curl verifies against the macOS keychain,
    so it works even on the python.org builds that cannot verify anything.

    Callers pass dest as either a str or a Path, so normalise it here.
    """
    curl = '/usr/bin/curl'
    if not os.path.exists(curl):
        return False
    destp = Path(dest)
    destp.parent.mkdir(parents=True, exist_ok=True)
    log('  python could not fetch it; retrying with the system curl')
    rc = subprocess.call([curl, '-fL', '--retry', '2', '--connect-timeout', '30',
                          '-A', 'LittlePrinceLauncher/1.0', '-o', str(destp), url])
    return rc == 0 and destp.exists() and destp.stat().st_size > 0


def download(url, dest, log=print):
    try:
        return _download_urllib(url, dest, log)
    except Exception as exc:
        log('  download failed: %s' % exc)
        if _download_curl(url, dest, log):
            return dest
        raise SystemExit(
            'Download failed.  If the message above mentions a certificate, this\n'
            'python does not trust any HTTPS site by itself - run this once and\n'
            'try again:\n\n'
            '    /Applications/Python*/Install Certificates.command\n')


def install_chromium(log=print):
    if chromium_binary():
        log('Chromium is already set up.')
        return chromium_binary()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    zip_path = RUNTIME / ('chrome-mac-%s.zip' % CHROMIUM_REV)
    log('Downloading Chromium M87 for macOS (about 150 MB, one time only)...')
    log('  from %s' % CHROMIUM_URL)
    download(CHROMIUM_URL, zip_path, log=log)
    log('Unpacking...')
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError('the download is damaged (%s)' % bad)
        zf.extractall(RUNTIME)
    zip_path.unlink(missing_ok=True)
    exe = chromium_binary()
    if not exe:
        raise RuntimeError('Chromium.app was not found in the downloaded archive')
    clear_quarantine(exe.parent.parent)
    # Chromium ships its helper apps inside; macOS wants the executable bits.
    for p in RUNTIME.rglob('*'):
        if p.is_file() and 'MacOS' in p.parts:
            p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    log('Chromium ready: %s' % exe)
    # An Apple Silicon Mac can download and unpack M87 and still not be able to run
    # it: the browser is x86_64.  Sort Rosetta out here so "Set up Flash runtime"
    # leaves a working browser instead of failing later with Errno 86.
    install_rosetta(log)
    return exe


def report(log=print):
    log('Package folder : %s' % ROOT)
    exe = chromium_binary()
    log('Chromium       : %s' % (exe or 'not set up yet - press "Set up Flash runtime"'))
    if plugin_ready():
        log('Pepper Flash   : %s (%s)' % (plugin_version(), PLUGIN_BIN))
    else:
        log('Pepper Flash   : MISSING - runtime/PepperFlashPlayer.plugin is not complete')
    if sys.platform == 'darwin' and rosetta_needed():
        log('Rosetta 2      : not installed. Chromium M87 and the Flash plugin are '
            'Intel binaries; on an Apple Silicon Mac run:  softwareupdate --install-rosetta')
    return exe, plugin_ready()


def main():
    ap = argparse.ArgumentParser(description='Set up the Flash runtime for the macOS launcher.')
    ap.add_argument('--check', action='store_true', help='only report what is present')
    ap.add_argument('--chromium-only', action='store_true', help='do not touch the Flash plugin')
    args = ap.parse_args()

    if args.check:
        report()
        return 0
    exe, plugin = report()
    if not args.chromium_only and not plugin:
        print('The bundled Flash plugin is incomplete - re-unzip the package.')
    if not exe:
        try:
            install_chromium()
        except Exception as exc:
            print('Could not set up Chromium: %s' % exc)
            return 1
    report()
    return 0


if __name__ == '__main__':
    sys.exit(main())
