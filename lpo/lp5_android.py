"""星夜重圓 (Starwish Reunion) - the Android side: emulator, APK, OBB, level bundles.

星夜重圓 only ever shipped as an Android/iOS app (Unity 5.3), so the launcher plays it
in Google's Android emulator.  Everything is fetched on demand, nothing ships with
the launcher:

  * Android SDK pieces from dl.google.com, into %LOCALAPPDATA%\\Android\\Sdk (the
    standard place - an SDK already there is used as it is): the command-line tools
    (their native `android.exe` installs the rest, no Java), platform-tools (adb),
    the emulator and the Android 9 x86 system image.  Only after the player has
    read and accepted Google's SDK licences on the portal.
  * the game from the publisher's own server (www.little-prince.com.hk/littleprince/
    Download/): com.Starwish.LP1.apk and the OBB zip, plus the 29 level bundles
    from reunion.little-prince.com.hk, into <package>/lp5/.
  * the APK patched to call this launcher's server (lp5_apk.py, signed in Python).

Then launch(): boot the emulator (its own AVD, console port 5580), install the APK and
the OBB once, and start the game.  The emulator is a native window; the launcher's
server answers the game (lp5.py) at 10.0.2.2:<port>, the PC as the emulator sees it.
"""
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

import lp5
import lp5_apk

HERE = Path(__file__).resolve().parent
ROOT = lp5.ROOT
DOWNLOADS = ROOT / "downloads"
SDK = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Android" / "Sdk"
ANDROID = SDK / "cmdline-tools" / "latest" / "bin" / "android.exe"
ADB = SDK / "platform-tools" / "adb.exe"
EMULATOR = SDK / "emulator" / "emulator.exe"
SYSIMG = SDK / "system-images" / "android-28" / "default" / "x86"
AVD_HOME = Path(os.environ.get("ANDROID_AVD_HOME") or (Path.home() / ".android" / "avd"))
AVD = "littleprince_reunion"
CONSOLE_PORT = 5580
SERIAL = "emulator-%d" % CONSOLE_PORT
PACKAGE = "com.Starwish.LP1"
OBB = "main.29.com.Starwish.LP1.obb"
CONSENT = ROOT / "android-licences-accepted.json"

REPO = "https://dl.google.com/android/repository/"
REPO_XML = REPO + "repository2-3.xml"
SYSIMG_XML = REPO + "sys-img/android/sys-img2-3.xml"
PUBLISHER = "http://www.little-prince.com.hk/littleprince/Download/"
BUNDLE_ORIGIN = "http://reunion.little-prince.com.hk/AssetBundles/android/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) littleprince-launcher/1.0"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

JOB = {"state": "idle", "phase": "", "percent": 0, "error": "", "log": []}
_JOB_LOCK = threading.Lock()
_HOOKS = {"log": print, "port": 8080}


def configure(**hooks):
    _HOOKS.update(hooks)


def log(msg):
    with _JOB_LOCK:
        JOB["log"].append(time.strftime("%H:%M:%S ") + msg)
        del JOB["log"][:-40]
    try:
        _HOOKS["log"]("lp5: " + msg)
    except Exception:                                                 # noqa: BLE001
        print(msg)


def _phase(text, percent=None):
    with _JOB_LOCK:
        JOB["phase"] = text
        if percent is not None:
            JOB["percent"] = int(percent)


# ─── what is here ────────────────────────────────────────────────────────────

def apk_path(port=None):
    return ROOT / ("StarwishReunion-local-%d.apk" % int(port or _HOOKS["port"]))


def avd_dir():
    return AVD_HOME / (AVD + ".avd")


def parts(port=None):
    """Each piece, present or not."""
    bundles, total = lp5.bundles_state()
    return {
        "licences": CONSENT.is_file(),
        "android_cli": ANDROID.is_file(),
        "adb": ADB.is_file(),
        "emulator": EMULATOR.is_file(),
        "system_image": (SYSIMG / "system.img").is_file(),
        "avd": (avd_dir() / "config.ini").is_file() and (AVD_HOME / (AVD + ".ini")).is_file(),
        "apk_download": (DOWNLOADS / "com.Starwish.LP1.apk").is_file(),
        "obb": (DOWNLOADS / OBB).is_file(),
        "bundles": bundles == total, "bundle_count": "%d/%d" % (bundles, total),
        "apk_built": apk_path(port).is_file(),
    }


def state(port=None, probe=True):
    """`probe` asks adb whether the emulator is up - skipped for the portal's
    every-few-seconds poll."""
    have = parts(port)
    ready = all(v for k, v in have.items() if isinstance(v, bool))
    with _JOB_LOCK:
        job = {k: (list(v) if isinstance(v, list) else v) for k, v in JOB.items()}
    return {"ready": ready, "parts": have, "job": job,
            "missing": [k for k, v in have.items() if v is False],
            "running": _emulator_up() if (probe and have["adb"]) else False}


# ─── licences ────────────────────────────────────────────────────────────────

def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def licences():
    """Google's licence texts for the packages the setup installs (from their index)."""
    repo = _get(REPO_XML).decode("utf-8")
    sysimg = _get(SYSIMG_XML).decode("utf-8")
    out = []
    for lid in ("android-sdk-license", "android-sdk-preview-license"):
        m = re.search(r'<license id="%s" type="text">(.*?)</license>' % lid, repo, re.S)
        if m:
            out.append({"id": lid, "text": html.unescape(m.group(1)).strip()})
    used = sorted(set(re.findall(r'<uses-license ref="([^"]+)"', _pkg_block(repo, "emulator")
                                 + _pkg_block(repo, "platform-tools")
                                 + _pkg_block(repo, "cmdline-tools;latest")
                                 + _pkg_block(sysimg, "system-images;android-28;default;x86"))))
    return {"licences": [l for l in out if l["id"] in used] or out,
            "packages": ["cmdline-tools;latest", "platform-tools", "emulator",
                         "system-images;android-28;default;x86"],
            "size_mb": 155 + 8 + 460 + 440}


def _pkg_block(xml, path):
    m = re.search(r'<remotePackage path="%s">(.*?)</remotePackage>' % re.escape(path), xml, re.S)
    return m.group(1) if m else ""


def accept_licences(texts):
    """Record that the player accepted these exact texts (by their hash)."""
    ROOT.mkdir(parents=True, exist_ok=True)
    CONSENT.write_text(json.dumps({"accepted": time.strftime("%Y-%m-%d %H:%M:%S"),
                                   "sha1": {l["id"]: hashlib.sha1(l["text"].encode()).hexdigest()
                                            for l in texts}}, indent=1), encoding="utf-8")


# ─── downloads ───────────────────────────────────────────────────────────────

def _download(url, target, label, lo, hi, sha1=None, timeout=120):
    """Fetch `url` into `target` (via .part), reporting lo..hi percent."""
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    digest = hashlib.sha1()
    with urllib.request.urlopen(req, timeout=timeout) as r, open(part, "wb") as fh:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            digest.update(chunk)
            got += len(chunk)
            if total:
                _phase("%s %d/%d MB" % (label, got >> 20, total >> 20),
                       lo + (hi - lo) * got / total)
    if total and got != total:
        raise IOError("%s: only %d of %d bytes arrived" % (label, got, total))
    if sha1 and digest.hexdigest() != sha1:
        raise IOError("%s: checksum does not match Google's index" % label)
    part.replace(target)


def _cmdline_tools(lo, hi):
    repo = _get(REPO_XML).decode("utf-8")
    block = _pkg_block(repo, "cmdline-tools;latest")
    for arc in re.findall(r"<archive>(.*?)</archive>", block, re.S):
        if "<host-os>windows</host-os>" in arc:
            url = re.search(r"<url>([^<]+)</url>", arc).group(1)
            sha1 = re.search(r"<checksum[^>]*>(\w+)</checksum>", arc).group(1)
            break
    else:
        raise IOError("no Windows command-line tools in Google's index")
    zpath = Path(tempfile.gettempdir()) / url
    _download(REPO + url, zpath, "Android command-line tools", lo, hi, sha1=sha1)
    _phase("Unpacking the command-line tools", hi)
    dest = SDK / "cmdline-tools" / "latest"
    tmp = SDK / "cmdline-tools" / "_unpack"
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(tmp)
    inner = tmp / "cmdline-tools"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(inner if inner.is_dir() else tmp), str(dest))
    shutil.rmtree(tmp, ignore_errors=True)
    zpath.unlink(missing_ok=True)


def _sdk_install(packages, lo, hi):
    """`android sdk install` - Google's native CLI, licences already accepted by the
    player on the portal (the CLI itself does not ask)."""
    cmd = [str(ANDROID), "--sdk=%s" % SDK, "sdk", "install"] + packages
    log("installing %s" % " ".join(packages))
    _phase("Installing %s" % ", ".join(p.split("/")[0] for p in packages), lo)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, creationflags=NO_WINDOW,
                            env=dict(os.environ, NO_COLOR="1"))
    step = 0
    for raw in iter(proc.stdout.readline, b""):
        line = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", raw.decode("utf-8", "replace")).strip()
        if line:
            step += 1
            _phase("Installing the Android SDK: " + line[:70], min(hi - 1, lo + step))
    if proc.wait():
        raise IOError("android sdk install failed (exit %d)" % proc.returncode)


def _write_avd():
    """The emulator's device: a 1280x800 landscape tablet on Android 9 x86."""
    d = avd_dir()
    d.mkdir(parents=True, exist_ok=True)
    (AVD_HOME / (AVD + ".ini")).write_text(
        "avd.ini.encoding=UTF-8\npath=%s\npath.rel=avd\\%s.avd\ntarget=android-28\n"
        % (d, AVD), encoding="utf-8")
    cfg = {"AvdId": AVD, "avd.ini.displayname": "Little Prince - Starwish Reunion",
           "abi.type": "x86", "hw.cpu.arch": "x86", "hw.cpu.ncore": "4",
           "image.sysdir.1": "system-images\\android-28\\default\\x86\\",
           "tag.id": "default", "tag.display": "Default Android System Image",
           "target": "android-28", "PlayStore.enabled": "no",
           "hw.device.manufacturer": "Google", "hw.device.name": "pixel_c",
           "hw.lcd.width": "1280", "hw.lcd.height": "800", "hw.lcd.density": "213",
           "hw.initialOrientation": "landscape", "showDeviceFrame": "no",
           "hw.ramSize": "2048", "vm.heapSize": "192M", "hw.gpu.enabled": "yes",
           "hw.gpu.mode": "host", "hw.keyboard": "yes", "hw.sdCard": "yes",
           "sdcard.size": "512 MB", "disk.dataPartition.size": "6442450944",
           "hw.audioOutput": "yes", "hw.audioInput": "no", "fastboot.forceColdBoot": "no"}
    (d / "config.ini").write_text("".join("%s = %s\n" % kv for kv in cfg.items()),
                                  encoding="utf-8")


def _game_files(lo, hi):
    apk = DOWNLOADS / "com.Starwish.LP1.apk"
    if not apk.is_file():
        _download(PUBLISHER + "com.Starwish.LP1.apk", apk, "The game (APK)", lo, lo + 8)
    obb = DOWNLOADS / OBB
    if not obb.is_file():
        zpath = DOWNLOADS / "com.Starwish.LP1.zip"
        if not zpath.is_file():
            _download(PUBLISHER + "com.Starwish.LP1.zip", zpath, "Game data (OBB)",
                      lo + 8, lo + 40, timeout=300)
        _phase("Unpacking the game data", lo + 40)
        with zipfile.ZipFile(zpath) as zf:
            member = next(n for n in zf.namelist() if n.endswith(OBB))
            with zf.open(member) as src, open(str(obb) + ".part", "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
        Path(str(obb) + ".part").replace(obb)
        zpath.unlink()
    names = [n for n in lp5.BUNDLE_NAMES if not (lp5.BUNDLES / (n + ".unity3d")).is_file()]
    for i, n in enumerate(names):
        span = (hi - lo - 42) / max(1, len(names))
        _download(BUNDLE_ORIGIN + n + ".unity3d", lp5.BUNDLES / (n + ".unity3d"),
                  "Level %s (%d of %d)" % (n, i + 1, len(names)),
                  lo + 42 + span * i, lo + 42 + span * (i + 1), timeout=600)


def setup(port=None):
    """Fetch and build everything that is missing.  Runs on its own thread."""
    port = int(port or _HOOKS["port"])
    if not CONSENT.is_file():
        raise PermissionError("the Android SDK licences have not been accepted")
    have = parts(port)
    SDK.mkdir(parents=True, exist_ok=True)
    if not have["android_cli"]:
        _cmdline_tools(1, 15)
    need = [p for p, ok in (("platform-tools", have["adb"]), ("emulator", have["emulator"]),
                            ("system-images/android-28/default/x86", have["system_image"]))
            if not ok]
    if need:
        _sdk_install(need, 16, 55)
    if not parts(port)["avd"]:
        _phase("Creating the Android 9 device", 56)
        _write_avd()
        log("created the emulator device %s" % AVD)
    _game_files(57, 95)
    if not apk_path(port).is_file():
        _phase("Building the local copy of the game", 96)
        lp5_apk.build(DOWNLOADS / "com.Starwish.LP1.apk", apk_path(port),
                      "http://10.0.2.2:%d/" % port, log=log)
    _phase("Ready", 100)


# ─── running it ──────────────────────────────────────────────────────────────

def _adb(*args, timeout=120, check=False):
    r = subprocess.run([str(ADB), "-s", SERIAL] + list(args), capture_output=True,
                       timeout=timeout, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
    out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
    if check and r.returncode:
        raise IOError("adb %s: %s" % (" ".join(args[:2]), out[-200:]))
    return out


def _emulator_up():
    try:
        return _adb("shell", "getprop", "sys.boot_completed", timeout=8).strip() == "1"
    except Exception:                                                 # noqa: BLE001
        return False


def _short_copy(path):
    """adb cannot open paths past Windows' 260-character limit, and the launcher may
    live deep in a folder tree - hand it a copy in the temp folder."""
    tmp = Path(tempfile.gettempdir()) / ("lp5-" + path.name)
    if not tmp.is_file() or tmp.stat().st_size != path.stat().st_size:
        shutil.copyfile(str(path), str(tmp))
    return tmp


def launch(port=None):
    """Boot the emulator if needed, install once, start the game."""
    port = int(port or _HOOKS["port"])
    if not _emulator_up():
        _phase("Starting the Android emulator", 10)
        log("starting the emulator (%s on %s)" % (AVD, SERIAL))
        # its own output goes to lp5/emulator.log - the only clue when it closes itself
        emu_log = open(str(ROOT / "emulator.log"), "wb")
        subprocess.Popen([str(EMULATOR), "-avd", AVD, "-port", str(CONSOLE_PORT),
                          "-no-boot-anim", "-gpu", "host"],
                         cwd=str(EMULATOR.parent), stdin=subprocess.DEVNULL,
                         stdout=emu_log, stderr=subprocess.STDOUT,
                         creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        deadline = time.time() + 300
        while not _emulator_up():
            if time.time() > deadline:
                raise IOError("the emulator did not finish booting in 5 minutes")
            time.sleep(3)
            _phase("Android is booting ...", min(60, 10 + (300 - (deadline - time.time())) / 5))
    apk = apk_path(port)
    sha = hashlib.sha1(apk.read_bytes()).hexdigest()
    marker = "/sdcard/littleprince-launcher-apk.txt"
    installed = "package:" in _adb("shell", "pm", "path", PACKAGE)
    if not installed or _adb("shell", "cat", marker).strip() != sha:
        _phase("Installing the game", 65)
        short = _short_copy(apk)
        out = _adb("install", "-r", str(short), timeout=600)
        if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in out:  # another build signed differently
            log("an app signed by someone else is installed - replacing it")
            _adb("uninstall", PACKAGE)
            out = _adb("install", str(short), timeout=600)
        short.unlink(missing_ok=True)
        if "Success" not in out:
            raise IOError("installing the APK failed: %s" % out[-200:])
        _adb("shell", "echo %s > %s" % (sha, marker))
        log("installed %s" % apk.name)
    obb_dir = "/sdcard/Android/obb/%s/" % PACKAGE
    if OBB not in _adb("shell", "ls", obb_dir):
        _phase("Copying the game data into Android (143 MB)", 75)
        _adb("shell", "mkdir", "-p", obb_dir)
        short = _short_copy(DOWNLOADS / OBB)
        _adb("push", str(short), obb_dir + OBB, timeout=900, check=True)
        short.unlink(missing_ok=True)
        log("copied the OBB")
    _phase("Starting 星夜重圓", 95)
    _adb("shell", "monkey", "-p", PACKAGE, "-c", "android.intent.category.LAUNCHER", "1")
    log("started %s on %s" % (PACKAGE, SERIAL))
    _phase("Playing", 100)


def _run(job, port):
    try:
        with _JOB_LOCK:
            JOB.update(state="working", error="", percent=0)
        if job in ("setup", "play"):
            setup(port)
        if job == "play":
            launch(port)
        with _JOB_LOCK:
            JOB["state"] = "done"
    except Exception as exc:                                          # noqa: BLE001
        log("failed: %s" % exc)
        with _JOB_LOCK:
            JOB.update(state="error", error=str(exc)[:200])


def start(job, port=None):
    """Run 'setup' or 'play' in the background; the portal polls state()."""
    with _JOB_LOCK:
        if JOB["state"] == "working":
            return {"ok": True, "started": False}
        JOB.update(state="working", phase="", percent=0, error="")
    threading.Thread(target=_run, args=(job, port), daemon=True).start()
    return {"ok": True, "started": True}
