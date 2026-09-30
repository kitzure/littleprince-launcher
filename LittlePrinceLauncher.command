#!/bin/bash
# ===========================================================================
#  Little Prince Launcher (macOS)
#
#  Double-click this file.  It opens the launcher window, which starts the
#  local servers and plays the games through the Flash runtime kept inside
#  this folder.  No administrator rights are needed - nothing here touches
#  the hosts file or a system folder.
#
#  If macOS refuses to run it, right-click it and choose Open once.
# ===========================================================================
set -u
cd "$(dirname "$0")" || exit 1

PY=""
for candidate in /usr/local/bin/python3 /opt/homebrew/bin/python3 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
done

if [ -z "$PY" ]; then
    osascript -e 'display dialog "Python 3 is needed for the launcher.\n\nThe free build from python.org includes the graphics toolkit the window uses." buttons {"Open python.org", "Quit"} default button 1 with title "Little Prince Launcher"' >/dev/null 2>&1 \
        && open "https://www.python.org/downloads/macos/"
    exit 1
fi

# Apple's command line Python has no Tk; the launcher falls back to a console
# window in that case, so only mention it rather than refusing to start.
if ! "$PY" -c 'import tkinter' >/dev/null 2>&1; then
    echo "Note: this Python has no tkinter, so the launcher will run in this"
    echo "window instead of a graphical one.  The games work exactly the same."
    echo "Install the python.org build for the graphical window."
    echo
else
    TKVER=$("$PY" -c 'import tkinter; print(tkinter.TkVersion)' 2>/dev/null)
    case "$TKVER" in
        8.5*)
            echo "Note: this Python uses the old system Tk ($TKVER).  Its window can come"
            echo "up empty on current macOS.  If that happens, run this instead:"
            echo "    \"$PY\" macos/launcher_gui.py --console"
            echo "or install the python.org build (Tk 8.6) and use this file again."
            echo
            ;;
    esac
fi

exec "$PY" macos/launcher_gui.py "$@"
