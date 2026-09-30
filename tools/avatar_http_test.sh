#!/bin/bash
# HTTP-level check: sign-in, the player card, and the rendered avatar over HTTP.
set -u
BASE=http://127.0.0.1:8977
J=/tmp/lpo_avatar/http_test

rm -f $J.cookie
echo "== register =="
curl -s -c $J.cookie -o $J.reg -w '%{http_code}\n' -X POST $BASE/web/api/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"httptest@local.test","password":"abcd1234","login_name":"httptest","name":"Http Test"}'
python3 -c "import json;d=json.load(open('$J.reg'));print('  account:',d.get('account',{}).get('email'),'uid',d.get('account',{}).get('uid'))"

echo "== me =="
curl -s -b $J.cookie -o $J.me -w '%{http_code}\n' $BASE/web/api/me
AV1=$(python3 -c "import json;print(json.load(open('$J.me'))['account'].get('avatar_url'))")
echo "  avatar_url: $AV1"

echo "== player card =="
curl -s -b $J.cookie -o $J.card -w '%{http_code}\n' $BASE/web/api/games
python3 -c "
import json; d=json.load(open('$J.card'))
print('  name:', d.get('name'), 'avatar_url:', d.get('avatar_url'))
print('  games:', [(g['game'], len(g['stats'])) for g in d.get('games',[])])
print('  board rows:', len(d.get('board',{}).get('rows',[])))
print('  character note:', (d.get('avatar',{}) or {}).get('note','')[:70])
"

echo "== the picture itself =="
curl -s -b $J.cookie -o $J.av1.png -w '  %{http_code} %{content_type} %{size_download} bytes\n' "$BASE$AV1"
python3 -c "
from PIL import Image; im=Image.open('$J.av1.png'); print('  rendered:', im.size, im.mode)
"

echo "== change the outfit on the site, and the URL must move =="
curl -s -b $J.cookie -o $J.save -w '  save %{http_code}\n' -X POST $BASE/web/api/me \
  -H 'Content-Type: application/json' \
  -d '{"profile":{"hair":"髮1","cloth":"王子服","trousers":"王子褲","shoes":"王子鞋"}}'
curl -s -b $J.cookie -o $J.me2 $BASE/web/api/me
AV2=$(python3 -c "import json;print(json.load(open('$J.me2'))['account'].get('avatar_url'))")
echo "  avatar_url now: $AV2"
[ "$AV1" != "$AV2" ] && echo "  URL CHANGED (as it must)" || echo "  !! URL DID NOT CHANGE"
curl -s -o $J.av2.png -w '  %{http_code} %{content_type} %{size_download} bytes\n' "$BASE$AV2"

echo "== the pages =="
curl -s $BASE/web -o $J.page.html -w '  /web %{http_code} %{size_download} bytes\n'
grep -c 'home-avatar' $J.page.html | sed 's/^/  home-avatar refs: /'
grep -c 'avatar_url' $J.page.html | sed 's/^/  avatar_url refs: /'
curl -s $BASE/web/avatars/default.png -o /dev/null -w '  default.png %{http_code} %{content_type} %{size_download}\n'
echo "== internal files must stay unreachable =="
for p in /web/avatars/../../accounts.json /avatar/rig.json /web/../../server.py; do
  curl -s -o /dev/null -w "  $p -> %{http_code}\n" "$BASE$p"
done
