import xml.etree.ElementTree as ET
t = ET.parse('/home/yoke/lpo_build/afxml/addfriend.xml')
r = t.getroot()
tags = r.find('tags')

parent = {}
for p in r.iter():
    for c in p:
        parent[c] = p

sprites = {}
for el in tags:
    if el.get('type') == 'DefineSpriteTag':
        sprites[el.get('spriteId')] = el


def dump(sid, depth=0):
    el = sprites[sid]
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
        print(" " * depth, "  ", ty, "name=", nm, "char=", ch, extra)


print("=== sprite 185 ===")
dump('185')
print("=== sprite 184 ===")
dump('184')
print("=== placements of 185/184/202/183 ===")
for el in r.iter('item'):
    if el.get('type') != 'PlaceObject2Tag':
        continue
    ch = el.get('characterId')
    if ch in ('185', '184', '202', '183', '179'):
        p = parent.get(el)
        while p is not None and p.get('type') != 'DefineSpriteTag':
            p = parent.get(p)
        print("char", ch, "in sprite", p.get('spriteId') if p is not None else 'ROOT',
              "name=", el.get('name'), "depth=", el.get('depth'))
