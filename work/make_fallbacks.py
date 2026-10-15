from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
p=Path('outputs/vraelix-premium-site/assets')
# Premium fallback while the source film is being prepared for the web.
poster=Image.new('RGB',(1200,630),(18,18,17))
d=ImageDraw.Draw(poster)
serif=ImageFont.truetype(r'C:\Windows\Fonts\georgia.ttf',24)
large=ImageFont.truetype(r'C:\Windows\Fonts\georgia.ttf',80)
sans=ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf',13)
d.text((76,74),'VRAELIX',font=serif,fill=(245,244,240))
d.line((76,135,1124,135),fill=(83,82,78),width=1)
d.text((74,202),'Build what',font=large,fill=(245,244,240))
d.text((74,286),'moves you forward.',font=large,fill=(245,244,240))
d.text((78,482),'DIGITAL  ·  BUSINESS  ·  TECHNOLOGY',font=sans,fill=(180,178,172))
poster.save(p/'hero-poster.png',optimize=True)
poster.resize((960,504),Image.Resampling.LANCZOS).save(p/'hero-poster.webp','WEBP',quality=85,method=6)
