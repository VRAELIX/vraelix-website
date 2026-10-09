from pathlib import Path
from PIL import Image
src=Path('work')
out=Path('outputs/vraelix-premium-site/assets')
for key, filename in [('founder-profile','founder-profile.jpeg'),('founder-work','founder-work.jpeg'),('founder-coffee','founder-coffee.jpeg')]:
 im=Image.open(src/filename).convert('RGB')
 im.save(out/f'{key}.webp','WEBP',quality=86,method=6)
logo=Image.open(src/'logo-source.png').convert('RGBA')
a=logo.getchannel('A')
for theme,color in [('white',(255,255,255)),('black',(14,14,14))]:
 word=a.crop((170,420,850,530))
 b=Image.new('RGBA',logo.size,(color[0],color[1],color[2],0)); b.putalpha(a)
 b.crop((170,420,850,530)).save(out/f'logo-wordmark-{theme}.png',optimize=True)
 b.crop((350,310,670,420)).save(out/f'logo-mark-{theme}.png',optimize=True)
