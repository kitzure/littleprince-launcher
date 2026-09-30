#!/bin/bash
# Do the cloud games render when their own gateway host answers locally?
# Inside a private namespace: lo up, /etc/hosts pointing both publisher hosts at
# 127.0.0.1, and the online server on port 80 (that is what the client calls).
set -u
CH=$(ls ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome | tail -1)

cat > /tmp/p2/ns_hosts <<'EOF'
127.0.0.1   localhost
127.0.0.1   www.little-prince.com.hk little-prince.com.hk www1.little-prince.com.hk
EOF

mkdir -p /tmp/p2/cloudns
unshare -r -m -n bash -c '
  set -u
  ip link set lo up
  mount --bind /tmp/p2/ns_hosts /etc/hosts
  cd ~/Downloads/littleprince-patcher || exit 1
  LPO_PORT=80 python3 lpo/server.py > /tmp/p2/ns_cloud_server.log 2>&1 &
  SRV=$!
  ok=no
  for i in $(seq 60); do
    if curl -sf -o /dev/null http://127.0.0.1/LP/personal/LP1/; then ok=yes; break; fi
    sleep 0.5
  done
  echo "server ready: $ok  (pid $SRV)"
  if [ "$ok" = no ]; then tail -5 /tmp/p2/ns_cloud_server.log; kill $SRV 2>/dev/null; exit 1; fi
  for g in LP1 LP2 LP3; do
    timeout 100 '"$CH"' --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
      --window-size=900,640 --virtual-time-budget=30000 \
      --screenshot=/tmp/p2/cloudns/$g.png "http://127.0.0.1/LP/personal/$g/" >/dev/null 2>&1
    echo "$g -> $(stat -c%s /tmp/p2/cloudns/$g.png 2>/dev/null || echo FAILED)"
  done
  kill $SRV 2>/dev/null
'
echo "--- gateway traffic seen by the server ---"
grep -aE "gateway|amfservice|404 |Service" /tmp/p2/ns_cloud_server.log | tail -12
