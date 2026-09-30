#!/bin/bash
# LP1 in an ordinary browser, through the redirect: does it still sit on "loading"?
set -u
CH=$(ls ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome | tail -1)
cat > /tmp/p2/ns_hosts3 <<'EOF'
127.0.0.1   localhost
127.0.0.1   www.little-prince.com.hk little-prince.com.hk www1.little-prince.com.hk
EOF

unshare -r -m -n bash -c '
  ip link set lo up
  mount --bind /tmp/p2/ns_hosts3 /etc/hosts
  cd ~/Downloads/littleprince-patcher || exit 1
  python3 lpo/server.py > /tmp/p2/ns_lp_online.log 2>&1 &
  ONLINE=$!
  python3 fake_server.py > /tmp/p2/ns_lp_fake.log 2>&1 &
  FAKE=$!
  for i in $(seq 60); do curl -sf -o /dev/null http://127.0.0.1:8080/play && break; sleep 0.5; done

  echo "--- the probe LP1 opens with, to each server ---"
  printf "  online 8080: %s\n" "$(curl -s -o /tmp/p2/probe1.bin -w "%{http_code} %{size_download}b" -X POST --data-binary "" -H "Content-Type: application/x-amf" http://127.0.0.1:8080/littleprince/amfservice/gateway.php)"
  printf "  cd-box  80 : %s\n" "$(curl -s -o /tmp/p2/probe2.bin -w "%{http_code} %{size_download}b" -X POST --data-binary "" -H "Content-Type: application/x-amf" http://127.0.0.1/littleprince/amfservice/gateway.php)"
  echo "  reply bytes: $(xxd -p /tmp/p2/probe2.bin | head -c 30)"

  echo "--- LP1 in a normal browser (Ruffle), 30 s ---"
  CHROME_FLAGS="--host-resolver-rules=MAP www.little-prince.com.hk 127.0.0.1,MAP www1.little-prince.com.hk 127.0.0.1,MAP little-prince.com.hk 127.0.0.1" \
  node /tmp/p2/shot_cdp.js '"$CH"' "http://www.little-prince.com.hk/LP/personal/LP1/" /tmp/p2/lp1_after_fix.png 30000 > /tmp/p2/lp1_after_fix.json 2>&1
  python3 - <<PY
import json
d = json.load(open("/tmp/p2/lp1_after_fix.json"))
print("  screenshot: %d bytes" % d.get("bytes", 0))
print("  404s:", [e for e in d.get("http_errors", []) if "favicon" not in e] or "none")
print("  console (last):")
for c in d.get("console", [])[-6:]:
    print("     ", str(c)[:150])
PY
  echo "--- the cd server log ---"
  grep -aE "empty AMF|cloud game service|AMF ERROR|unknown method|method:" /tmp/p2/ns_lp_fake.log | tail -8
  kill $ONLINE $FAKE 2>/dev/null
'
