import xml.etree.ElementTree as ET
t = ET.parse('/home/yoke/lpo_build/afxml/addfriend.xml')
r = t.getroot()
tags = r.find('tags')
sprites = {}
for el in tags:
    if el.get('type') == 'DefineSpriteTag':
        sprites[el.get('spriteId')] = el


def dump(sid, depth=0, limit=None):
    el = sprites.get(sid)
    if el is None:
        print(" " * depth, "SPRITE", sid, "(not a sprite)")
        return
    print(" " * depth, "SPRITE", sid, "frames", el.get('frameCount'))
    sub = el.find('subTags')
    if sub is None:
        return
    for it in sub:
        ty = it.get('type')
        nm = it.get('name')
        ch = it.get('characterId') or it.get('symbolId')
        extra = ''
        if ty == 'FrameLabelTag':
            extra = '  <-LABEL ' + (it.get('name') or '')
        if ty in ('DoActionTag', 'DoInitActionTag'):
            extra = '  <-ACTION'
        print(" " * depth, "  ", ty, "name=", nm, "char=", ch, extra)


for sid in ('153', '127', '118', '142', '156'):
    dump(sid)
    print()

# who places 153 /127 / their .btn
parent = {}
for p in r.iter():
    for c in p:
        parent[c] = p
for want in ('153', '127'):
    for el in r.iter('item'):
        if el.get('type') in ('PlaceObject2Tag', 'PlaceObject3Tag') and el.get('characterId') == want:
            p = parent.get(el)
            while p is not None and p.get('type') != 'DefineSpriteTag':
                p = parent.get(p)
            print("char", want, "placed in sprite", p.get('spriteId') if p is not None else 'ROOT',
                  "name=", el.get('name'))
