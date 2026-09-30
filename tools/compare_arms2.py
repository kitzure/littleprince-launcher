#!/usr/bin/env python3
"""Scale-normalised side by side: game art (left) vs our render (right).

Both are cropped to the character and resized to the same height, so the arm-to-body
gaps can be compared.  Cropping the render must happen on the ALPHA bbox, before
flattening on white - flattening first makes getbbox() return the whole canvas and
the comparison turns into two different zooms.
"""
from PIL import Image

REF_BOX = (44, 8, 139, 208)          # the boy in the game screenshot (no shadow)
H = 460

ref = Image.open('/home/yoke/.hermes/cache/images/img_4f6e308b9980.webp').convert('RGB')
ref = ref.crop(REF_BOX)
ref = ref.resize((max(1, int(ref.width * H / ref.height)), H), Image.LANCZOS)

src = Image.open('/tmp/lpo_avatar/look_default.png')
alpha_box = src.getbbox()                      # alpha bbox, before flattening
mine = Image.new('RGBA', src.size, (255, 255, 255, 255))
mine.alpha_composite(src)
mine = mine.convert('RGB').crop(alpha_box)
mine = mine.resize((max(1, int(mine.width * H / mine.height)), H), Image.LANCZOS)

out = Image.new('RGB', (ref.width + mine.width + 16, H), (255, 255, 255))
out.paste(ref, (0, 0))
out.paste(mine, (ref.width + 16, 0))
out.save('/tmp/lpo_avatar/compare_arms2.png')
print('wrote compare_arms2.png', out.size, '| left = game art, right = ours')
print('target %s  ours %s (both %d px tall)' % (ref.size, mine.size, H))
