#!/bin/bash
# The chain the cloud games really use: the packet goes to the publisher's own
# hostname on port 80 (which the hosts redirect points here), the CD-box server
# recognises the Prince service and hands it to the online server, which answers
# loginSuccess.  Everything below runs in a private namespace.
set -u
cat > /tmp/p2/ns_hosts2 <<'EOF'
127.0.0.1   localhost
127.0.0.1   www.little-prince.com.hk little-prince.com.hk www1.little-prince.com.hk
EOF

unshare -r -m -n bash -c '
  ip link set lo up
  mount --bind /tmp/p2/ns_hosts2 /etc/hosts
  cd ~/Downloads/littleprince-patcher || exit 1
  python3 lpo/server.py > /tmp/p2/ns_online.log 2>&1 &
  ONLINE=$!
  LPO_PORT=8080 python3 fake_server.py > /tmp/p2/ns_fake.log 2>&1 &
  FAKE=$!
  for i in $(seq 60); do curl -sf -o /dev/null http://127.0.0.1:8080/play && break; sleep 0.5; done
  echo "online server up: $(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8080/play)"
  echo "cd server on port 80: $(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:80/ | head -c 3)"
  echo
  echo "--- the game asks its own hostname, exactly as LP1 does ---"
  python3 /tmp/p2/test_cloud_login.py 2>&1 | head -20
  echo
  echo "--- what the CD server saw ---"
  grep -aE "cloud game service|method:" /tmp/p2/ns_fake.log | tail -6
  echo "--- what the online server answered ---"
  grep -aE "Prince[123]:|cloud login" /tmp/p2/ns_online.log | tail -6
  kill $ONLINE $FAKE 2>/dev/null
'
