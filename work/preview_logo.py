from PIL import Image
from pathlib import Path
p=Path('outputs/vraelix-premium-site/assets/logo-wordmark-black.png')
im=Image.open(p).convert('RGBA')
bg=Image.new('RGBA',im.size,'white'); bg.alpha_composite(im); bg.convert('RGB').save('work/logo-preview.jpg',quality=95)
a=im.getchannel('A')
print('size',im.size,'bbox',a.getbbox(),'nonzero',sum(1 for v in a.getdata() if v),'max',a.getextrema()[1])
