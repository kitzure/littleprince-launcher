#!/bin/bash
# Refresh the scratch mirror from the current pack (never the other way round) and
# restart the scratch server on $1.  The pack's own user data is never copied in.
set -e
PORT="${1:-8977}"
SRC=/home/yoke/Downloads/littleprince-launcher
DEST=/tmp/lpo_scratch
# stop whatever is on this port (the scratch server only)
pkill -f "bb_serve.py $PORT" 2>/dev/null || true
sleep 1
rm -rf "$DEST"
mkdir -p "$DEST"
cp -r "$SRC/lpo" "$DEST/lpo"
rm -f "$DEST/lpo/accounts.json" "$DEST/lpo/notices.json" \
      "$DEST/lpo/mails.json" "$DEST/lpo/level_scores.json" "$DEST/lpo/friends.json"
rm -rf "$DEST/lpo/notice_content"
ln -sfn "$SRC/cloud" "$DEST/cloud"
cd "$DEST/lpo"
nohup python3 /home/yoke/lpo_build/bb_serve.py "$PORT" "$DEST/lpo" \
      > "/tmp/bb$PORT.log" 2>&1 &
for i in $(seq 1 40); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/web" || true)
  if [ "$code" = "200" ]; then echo "scratch server up on $PORT (fresh copy)"; exit 0; fi
  sleep 0.5
done
echo "!! server did not come up"; tail -20 "/tmp/bb$PORT.log"; exit 1
