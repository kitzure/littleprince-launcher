#!/bin/bash
# ===========================================================================
#  Build the macOS zip.
#
#  Includes everything a Mac needs and leaves out the Windows-only pieces:
#    * browser/            the publisher's Windows Flash browser (204 MB)
#    * patches/            Windows patcher output
#    * Start.bat, Start_Server_GUI.pyw, *.exe launchers
#    * cloud/LP*/start.exe the CD games' Windows projectors
#
#  NOTE: launcher_ui.py at the root IS the Mac's window as well - the macOS
#  launcher (macos/launcher_gui.py) imports it and draws the same window the
#  Windows entry point does.  Do not add it to the -x list below, or the Mac
#  pack ships a launcher that cannot open a window.
#
#  Usage:  bash macos/build_mac_zip.sh [output.zip]
# ===========================================================================
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
NAME="$(basename "$ROOT")"
OUT="${1:-$HOME/Downloads/littleprince-macos.zip}"

cd "$ROOT/.."

echo "packing $NAME -> $OUT"
rm -f "$OUT"

# The user's own data stays out: accounts.json holds their accounts (with
# password hashes) and notices.json holds their billboard rows.  accounts.json
# is recreated on the first registration, and an absent notices.json is a
# valid empty board.
zip -r -q -y "$OUT" "$NAME" \
    -x "$NAME/browser/*" \
    -x "$NAME/patches/*" \
    -x "$NAME/Start.bat" \
    -x "$NAME/Start_Server_GUI.pyw" \
    -x "$NAME/cloud/LP*/start.exe" \
    -x "$NAME/**/__pycache__/*" \
    -x "$NAME/.git/*" \
    -x "$NAME/**/.DS_Store" \
    -x "$NAME/lpo/accounts.json" \
    -x "$NAME/lpo/notices.json"

echo
echo "written: $OUT"
ls -lh "$OUT"
echo
echo "Contents that matter on a Mac:"
unzip -l "$OUT" | grep -E 'launcher_ui.py|LittlePrinceLauncher.command|macos/(launcher_gui|mac_relay|setup_runtime|README)|macos/runtime/PepperFlashPlayer.plugin/Contents/(Info.plist|MacOS)' | head -12
echo
echo "Remind the user: unzip first, then double-click LittlePrinceLauncher.command"
echo "(right-click -> Open the first time if macOS asks about an unidentified developer)."
