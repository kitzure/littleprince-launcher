#!/usr/bin/env python3
"""Protocol-level checks for the appearance work - on a throwaway accounts file.

1. the 16 appearance slots are stored when the client reports them, and come back
   in the account record;
2. the login4 reply's `cloth` array is the account's own outfit, not the capture's;
3. an account with no `cards` key still builds a player card (the crash);
4. every account on this machine can be drawn.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

PKG = '/home/yoke/Downloads/littleprince-launcher/lpo'
sys.path.insert(0, PKG)

import accounts                                                  # noqa: E402

tmp = tempfile.mkdtemp(prefix='lpo_appearance_')
accounts.ACCOUNTS_PATH = Path(tmp) / 'accounts.json'
with open(accounts.ACCOUNTS_PATH, 'w') as fh:
    json.dump({'accounts': []}, fh)

import amf0                                                      # noqa: E402
import server                                                    # noqa: E402

assert str(accounts.ACCOUNTS_PATH).startswith(tmp), 'the real store is still wired up!'
print('sandbox store:', accounts.ACCOUNTS_PATH)

# ── 1. register an account and report an outfit the way the client does ──
acct = accounts.create('av@local.test', 'abcd1234',
                       dict(server.DEFAULT_PROFILE, name='Test Player'),
                       name='Test Player')
server.CURRENT_PLAYER.update({'email': acct['email'], 'profile': acct['profile']})

body = amf0.encode([[amf0.AmfObject({'type': 'hair', 'data': '髮1'}),
                     amf0.AmfObject({'type': 'cloth', 'data': '王子服'}),
                     amf0.AmfObject({'type': 'shoes', 'data': '王子鞋'}),
                     amf0.AmfObject({'type': 'nose', 'data': '鼻3'})]])
kept = server.persist_player_update(body, 'setCloth')
profile = accounts.get(acct['email'])['profile']
print('saved:', kept, {k: profile.get(k) for k in ('hair', 'cloth', 'shoes', 'nose')})
assert profile.get('hair') == '髮1', profile.get('hair')
assert profile.get('cloth') == '王子服'
assert profile.get('shoes') == '王子鞋'
assert profile.get('nose') == '鼻3'

# ── 2. the login4 reply spells the account's parts into `cloth` ──
captured = open(os.path.join(PKG, 'captures', 'bodies', 'login4.bin'), 'rb').read()
out = server.apply_profile(captured, profile)
decoded = amf0.decode(out)
cloth = None
for v in decoded:
    if isinstance(v, dict) and 'cloth' in v:
        cloth = v['cloth']
print('reply cloth:', cloth)
assert cloth[:4] == ['', '髮1', '耳1', '面珠1'], cloth
assert cloth[12:15] == ['王子服', '運動褲', '王子鞋'], cloth[12:15]
assert cloth[7] == '鼻3', cloth[7]

# a default account still gets the publisher's own default outfit
out2 = server.apply_profile(captured, dict(server.DEFAULT_PROFILE))
cloth2 = [v['cloth'] for v in amf0.decode(out2) if isinstance(v, dict) and 'cloth' in v][0]
print('default cloth:', cloth2)
assert cloth2[1] == '髮3' and cloth2[12] == '運動服' and cloth2[0] == '', cloth2

# ── 3. the player card builds for an account with no `cards` ──
accounts.create('bare@local.test', 'abcd1234',
                {'uid': '10999', 'name': 'Bare', 'permission': 0}, name='Bare')
payload = server.player_card_payload('bare@local.test')
print('bare card games:', [(g['game'], len(g['stats'])) for g in payload['games']],
      'avatar_url:', payload['avatar_url'])
assert payload['avatar_url'], 'no avatar rendered for the bare account'
assert server.player_card_payload(acct['email'])['avatar_url']

# ── 4. every account draws, and its look is what it wears ──
for a in accounts.all_accounts():
    prof = a.get('profile') or {}
    url, path = server.avatar_ensure(prof)
    assert url and path and os.path.exists(path), (a['email'], url, path)
    print('  %-24s %s' % (a['email'], url))

# two different outfits must not share a file
u1, _ = server.avatar_ensure(dict(server.DEFAULT_PROFILE))
u2, _ = server.avatar_ensure(dict(server.DEFAULT_PROFILE, hair='髮1'))
assert u1 != u2
print('ALL PROTOCOL CHECKS PASSED')
