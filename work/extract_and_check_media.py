from pathlib import Path
from zipfile import ZipFile
import shutil,struct
zpath=Path('work/vraelix-silent-media.zip')
out=Path('outputs/vraelix-premium-site/assets')
with ZipFile(zpath) as z:
 print('archive',z.testzip(),[(i.filename,i.file_size) for i in z.infolist()])
 for name in ['vraelix-cinematic.webm','hero-poster.png','hero-poster.webp']:
  target=out/name
  target.write_bytes(z.read(name))

b=(out/'vraelix-cinematic.webm').read_bytes()
# Walk EBML elements to locate the Matroska Tracks element and count track types.
def vint(data,pos,keep_marker=False):
 first=data[pos]; mask=0x80; n=1
 while n<=8 and not(first&mask): mask>>=1;n+=1
 if n>8:return None,None
 value=first if keep_marker else first & (mask-1)
 for i in range(1,n): value=(value<<8)|data[pos+i]
 return value,n
def children(data,start,end):
 pos=start
 while pos<end:
  if pos>=len(data):return
  eid,n=vint(data,pos,True)
  if n is None:return
  size,sn=vint(data,pos+n)
  if size is None:return
  begin=pos+n+sn; stop=min(begin+size,end)
  yield eid,begin,stop
  if stop<=pos:return
  pos=stop
tracks=[]
def walk(data,start,end,level=0):
 for eid,a,c in children(data,start,end):
  if eid==0xAE:
   info={}
   for te,ta,tc in children(data,a,c):
    if te==0x83: info['type']=int.from_bytes(data[ta:tc],'big')
    if te==0x86: info['codec']=data[ta:tc].decode('ascii','ignore')
   tracks.append(info)
  elif eid in (0x18538067,0x1654AE6B):
   walk(data,a,c,level+1)
# unknown-sized Segment handled by common finite-size files; inspect marker IDs as fallback.
for eid,a,c in children(b,0,len(b)):
 if eid==0x18538067: walk(b,a,c)
print('webm tracks',tracks,'bytes',len(b))
