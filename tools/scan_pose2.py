#!/usr/bin/env python3
"""Which authored pose has the left arm DOWN (hand at waist height, like the right)?"""
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, '/tmp/lpo_avatar')
from avbuild import SwfModel, mul                      # noqa: E402

ca = SwfModel('/tmp/lpo_avatar/ca.xml')
labels = []
root = ET.parse('/tmp/lpo_avatar/ca.xml').getroot()
for el in root.iter('item'):
    if el.get('type') != 'DefineSpriteTag' or int(el.get('spriteId')) != 458:
        continue
    frame = 0
    for ch in el.find('subTags'):
        if ch.tag != 'item':
            continue
        if ch.get('type') == 'ShowFrameTag':
            frame += 1
        elif ch.get('type') == 'FrameLabelTag':
            labels.append((frame, ch.get('name')))

HAND, ARM = 92, 99
hm = None
for _d, n, c, m in ca.all_sprites.get(ARM, []):
    if n == 'hand':
        hm = m
box = ca.bbox(HAND) or (0, 0, 0, 0)


def hand_at(arm_matrix):
    acc = mul(arm_matrix, hm)
    cx = (box[0] + box[2]) / 2
    cy = (box[1] + box[3]) / 2
    return (round(acc[0] * cx + acc[1] * cy + acc[4], 1),
            round(acc[2] * cx + acc[3] * cy + acc[5], 1))


rows = []
for idx, name in labels:
    st = ca._live_frame(458, idx)
    arms = {nm: m for _d, nm, _c, m, _a in st if nm in ('left_arm', 'right_arm')}
    if len(arms) < 2:
        continue
    lh, rh = hand_at(arms['left_arm']), hand_at(arms['right_arm'])
    rows.append((name, idx + 1, lh, rh, arms['left_arm'], arms['right_arm']))

print('%-22s %-6s %-16s %-16s' % ('label', 'frame', 'left hand', 'right hand'))
for name, fr, lh, rh, lm, rm in rows:
    flag = '  <== left arm is DOWN' if lh[1] > -50 else ''
    if flag or name in ('nomotion', 'normal', 'walk', 'run', 'g24_stand', 'stand_getobj'):
        print('%-22s %-6d %-16s %-16s%s' % (name, fr, lh, rh, flag))
