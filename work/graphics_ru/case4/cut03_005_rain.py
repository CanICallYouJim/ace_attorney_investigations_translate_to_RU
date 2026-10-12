import sys, json; sys.path.insert(0,'tools')
from pathlib import Path
import numpy as np, paste_art, cv2
from PIL import Image
from scipy import ndimage as nd
S=sys.argv[1]
q=json.load(open('work/graphics_ai/codex.json',encoding='utf-8')); b=q['cut03_005_дождь']['box']
p2=Image.open('work/graphics_masks/drafts/cut03_005_p2.png').convert('RGBA'); al=p2.copy()
g={"art":str(Path('work/graphics_ai/case4/cut03_005_дождь_codex_1.png').resolve()),"вырезка":b,"зона":[[0,0,b[2]-b[0],b[3]-b[1]]],"край":1}
paste_art.plate(al,g,Path('.'))
P=np.asarray(p2).astype(float); A=np.asarray(al).astype(float)
R=np.asarray(Image.open('work/graphics_masks/drafts/hold/case4/cut03_005.png').convert('RGB')).astype(float)
E=np.asarray(Image.open('work/graphics_en/case4/cut03_005.png').convert('RGB')).astype(float)
old=nd.binary_dilation((R.mean(-1)<95)|(E.mean(-1)<95),iterations=4); new=nd.binary_dilation(P[...,:3].mean(-1)<110,iterations=3)
Aink=nd.binary_dilation(A[...,:3].mean(-1)<110,iterations=4)
blot=old&~new&~Aink; blot[:, :1690]=False; blot[1000:]=False
poly=np.zeros(blot.shape,np.uint8); cv2.fillPoly(poly,[np.array([[1690,0],[1905,0],[1852,993],[1690,976]],np.int32)],1); blot&=poly.astype(bool)
wgt=nd.gaussian_filter(blot.astype(float),1.5)[...,None]
out=P*(1-wgt)+A*wgt
row=out[2:3,1785:1875].copy(); dark=row[...,:3].mean(-1)<120
for yy in (0,1): out[yy,1785:1875][dark[0]]=row[0][dark[0]]      # буква упирается в край кадра
Image.fromarray(np.clip(out+0.5,0,255).astype(np.uint8),'RGBA').save('work/graphics_masks/drafts/cut03_005_p3.png')
bx=(1640,0,1920,1080)
ims=[Image.open(p).convert('RGB').crop(bx) for p in ['work/graphics_en/case4/cut03_005.png','work/graphics_masks/drafts/cut03_005_p3.png']]
W=Image.new('RGB',(570,1080)); [W.paste(im,(i*290,0)) for i,im in enumerate(ims)]; W.save(f'{S}/fx/cut03_005_стяг4.png')
