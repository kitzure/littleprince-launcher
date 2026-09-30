#!/bin/bash
# What does LP1 ask for through the redirect now?  The request log is the real evidence:
# a Prince1 service call means it got past boot; nothing means it is still stuck.
set -u
CH=$(ls ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome | tail -1)
FLAGS="--host-resolver-rules=MAP www.little-prince.com.hk 127.0.0.1,MAP www1.little-prince.com.hk 127.0.0.1,MAP little-prince.com.hk 127.0.0.1"

unshare -r -m -n bash -c "
  ip link set lo up
  mount --bind /tmp/p2/ns_hosts4 /etc/hosts
  cd ~/Downloads/littleprince-patcher || exit 1
  python3 lpo/server.py > /tmp/p2/req_online.log 2>&1 &
  O=\$!
  python3 fake_server.py > /tmp/p2/req_fake.log 2>&1 &
  F=\$!
  for i in \$(seq 60); do curl -sf -o /dev/null http://127.0.0.1:8080/play && break; sleep 0.5; done
  timeout 120 '$CH' --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
      --window-size=900,640 --virtual-time-budget=45000 "$FLAGS" \
      --screenshot=/tmp/p2/lp1_ns.png \
      'http://www.little-prince.com.hk/LP/personal/LP1/' > /tmp/p2/chrome_out.txt 2>&1
  echo \"screenshot: \$(stat -c%s /tmp/p2/lp1_ns.png 2>/dev/null || echo 0) bytes\"
  kill \$O \$F 2>/dev/null
"
