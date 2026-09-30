#!/bin/bash
# Does LP1 get past its loading screen now?  Servers in a namespace with the publisher's
# hostnames pointed at them, and Chromium told to resolve those names to loopback itself
# (inside a namespace it does its own DNS and ignores a bind-mounted /etc/hosts).
set -u
CH=$(ls ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome | tail -1)
cat > /tmp/p2/ns_hosts4 <<'EOF'
127.0.0.1   localhost
127.0.0.1   www.little-prince.com.hk little-prince.com.hk www1.little-prince.com.hk
EOF
FLAGS="--host-resolver-rules=MAP www.little-prince.com.hk 127.0.0.1,MAP www1.little-prince.com.hk 127.0.0.1,MAP little-prince.com.hk 127.0.0.1"

unshare -r -m -n bash -c "
  ip link set lo up
  mount --bind /tmp/p2/ns_hosts4 /etc/hosts
  cd ~/Downloads/littleprince-patcher || exit 1
  python3 lpo/server.py > /tmp/p2/lp1_online.log 2>&1 &
  O=\$!
  python3 fake_server.py > /tmp/p2/lp1_fake.log 2>&1 &
  F=\$!
  for i in \$(seq 60); do curl -sf -o /dev/null http://127.0.0.1:8080/play && break; sleep 0.5; done
  CHROME_FLAGS='$FLAGS' node /tmp/p2/shot_cdp.js '$CH' \
      'http://www.little-prince.com.hk/LP/personal/LP1/' /tmp/p2/lp1_final.png 40000 \
      > /tmp/p2/lp1_final.json 2>&1
  kill \$O \$F 2>/dev/null
"
python3 - <<'PY'
import json
d = json.load(open("/tmp/p2/lp1_final.json"))
print("screenshot: %d bytes" % d.get("bytes", 0))
print("404s:", [e for e in d.get("http_errors", []) if "favicon" not in e] or "none")
print("console:")
for c in d.get("console", []):
    s = str(c).replace("%c", "").strip()
    if any(k in s for k in ("Ruffle instance", "Loading SWF", "loadProgress", "AMF", "error")):
        print("   ", s[:140])
PY
echo "═══ what the game asked the servers ═══"
grep -aE "POST|empty AMF|cloud game service|method:|-> responded" /tmp/p2/lp1_fake.log | tail -12
echo "═══ online server ═══"
grep -aE "ok|response|error|unknown" /tmp/p2/lp1_online.log | tail -8
