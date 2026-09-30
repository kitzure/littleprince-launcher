import xml.etree.ElementTree as ET
t = ET.parse('/home/yoke/lpo_build/afxml/addfriend.xml')
r = t.getroot()
tags = r.find('tags')
sprites = {}
for el in tags:
    if el.get('type') == 'DefineSpriteTag':
        sprites[el.get('spriteId')] = el

for sid in ('202',):
    el = sprites[sid]
    print("SPRITE", sid, "frames", el.get('frameCount'))
    sub = el.find('subTags')
    frame = 1
    for it in sub:
        ty = it.get('type')
        if ty == 'FrameLabelTag':
            print("  label", it.get('name'), "at frame", frame)
        if ty == 'ShowFrameTag':
            frame += 1
    # placements with names
    print("  -- named placements --")
    for it in sub:
        if it.get('name'):
            print("   ", it.get('type'), it.get('name'), "char=", it.get('characterId'))
