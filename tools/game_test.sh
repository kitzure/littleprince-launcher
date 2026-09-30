#!/bin/bash
# OUTER: stage one CD game (hardlinks, same filesystem), install the patched SWFs, run it.
#   $1 = 1 or 3
set -u
TAG="g$1"
PKG=$HOME/Downloads/littleprince-patcher
STAGE="$HOME/Downloads/.gametest/$TAG"      # same fs as the sources -> cp -al works
RUNLOG=/tmp/p2/runlog
mkdir -p "$RUNLOG"
rm -rf "$STAGE"; mkdir -p "$STAGE"

case "$1" in
  1) SRC=$HOME/Downloads/kingdom/content
     SUB=""
     PATTERN="1-Starwish-Legend:index.swf reg.swf start.swf"
     ;;
  3) SRC="$HOME/Downloads/littleprince/pa_full/Prince Adventure"
     SUB="content"
     PATTERN="3-Prince-Adventure:reg.swf login.swf"
     ;;
esac

cp -al "$SRC"/. "$STAGE"/ || { echo "staging failed"; exit 1; }
GDIR="$STAGE/$SUB"

GAME=${PATTERN%%:*}; FILES=${PATTERN#*:}
for f in $FILES; do
  cp "$PKG/games/$GAME/$f" "$GDIR/$f" || echo "  (could not install $f)"
done
echo "source : $SRC"
echo "staged : $STAGE  ($(du -sh "$STAGE" 2>/dev/null | cut -f1))"
echo "files  : $(ls "$GDIR" | wc -l) in $GDIR"
ls "$GDIR"/start.exe >/dev/null 2>&1 || ls "$GDIR"/START.EXE >/dev/null 2>&1 || ls "$SUB"/start.exe >/dev/null 2>&1
echo "exe    : $(ls "$GDIR" | grep -i '^start\.exe$' || echo MISSING)"
for f in $FILES; do echo "  installed $f -> $(md5sum "$GDIR/$f" | cut -c1-32)"; done

WINEXE="\\home\\yoke\\Downloads\\.gametest\\$TAG\\${SUB:+$SUB\\}start.exe"
echo "wine   : Z:$WINEXE"

cp /etc/hosts "$RUNLOG/${TAG}_hosts"
echo "127.0.0.1 www1.little-prince.com.hk little-prince.com.hk www.little-prince.com.hk" >> "$RUNLOG/${TAG}_hosts"
export HOSTSFILE="$RUNLOG/${TAG}_hosts"

unshare -r -m -n bash /tmp/p2/game_test_inner.sh "$TAG" "$GDIR" "$WINEXE" 2>&1 | tail -12
echo "=== real /etc/hosts untouched: $(grep -c little-prince /etc/hosts || true) lines ==="
