#!/bin/bash
# Rebuild a throwaway mirror of the pack's lpo/ dir and run it on $1 (default 8977).
# cloud/ is symlinked (never copy server.py by symlink); the real pack's user data
# files are never read back by the tests - the scratch copy is what the server writes.
set -e
PORT="${1:-8977}"
SRC=/home/yoke/Downloads/littleprince-launcher
DEST=/tmp/lpo_scratch
rm -rf "$DEST"
mkdir -p "$DEST"
cp -r "$SRC/lpo" "$DEST/lpo"
# user data that must never leak from the real pack
rm -f "$DEST/lpo/accounts.json" "$DEST/lpo/notices.json" \
      "$DEST/lpo/mails.json" "$DEST/lpo/level_scores.json" "$DEST/lpo/friends.json"
rm -rf "$DEST/lpo/notice_content"
ln -sfn "$SRC/cloud" "$DEST/cloud"
echo "scratch ready: $DEST/lpo"
ls "$DEST/lpo" | head -5
