"""Optional avatar renderer setup, installed only inside this launcher folder."""
import importlib
import os
from pathlib import Path
import subprocess
import sys

LOCAL_PACKAGES = Path(__file__).resolve().parent / 'python-deps'


def enable_local_packages():
    path = str(LOCAL_PACKAGES)
    if LOCAL_PACKAGES.is_dir() and path not in sys.path:
        sys.path.insert(0, path)
    importlib.invalidate_caches()


def pillow_ready():
    enable_local_packages()
    try:
        from PIL import Image
        Image.new('RGBA', (1, 1))
        return True
    except (ImportError, OSError):
        return False


def install_args():
    exe = Path(sys.executable)
    # Start.bat prefers pythonw; its sibling prints useful pip status into the GUI.
    if exe.name.lower() == 'pythonw.exe' and exe.with_name('python.exe').is_file():
        exe = exe.with_name('python.exe')
    return [str(exe), '-m', 'pip', 'install', '--disable-pip-version-check',
            '--no-input', '--only-binary=:all:', '--upgrade', '--target',
            str(LOCAL_PACKAGES), 'Pillow>=10,<13']


def install_pillow(note):
    """Call after user consent. Never change global/user Python packages."""
    try:
        args = install_args()
        note('Installing avatar support inside the launcher folder...')
        proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                encoding='utf-8', errors='replace',
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        for line in proc.stdout:
            if line.strip():
                note(line.rstrip())
        code = proc.wait()
        if code:
            note('Avatar support installation failed (pip exit %d). '
                 'Check internet access and retry from the launcher menu.' % code)
            return False
        if not pillow_ready():
            note('Pillow installed but cannot load in this Python. '
                 'Restart the launcher and retry avatar support setup.')
            return False
        note('Avatar support ready. Open website portraits update automatically.')
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        note('Could not install avatar support: %s. '
             'The games still work; retry from the launcher menu.' % exc)
        return False
