"""Баннеры ваты на map13: «Сахарная вата» — буквы принятого стяга cut03_005, «Рваное облачко» — Segoe Script Bold."""
import sys, numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as nd
S=sys.argv[1]
E=np.asarray(Image.open('work/graphics_masks/drafts/hold/maps/map13.png').convert('RGB')).astype(float)   # с небом/розами
EN=np.asarray(Image.open('work/graphics_en/maps/map13.png').convert('RGB')).astype(float)
OUT=E.copy(); H,W=E.shape[:2]
word=np.load('work/graphics_ru/maps/_data/word_vata_d.npy')[::-1,::-1]          # 180°: читается сверху вниз
BANNERS={
 'L':dict(poly=[[0,212],[74,280],[74,648],[0,590]], thick=(0,34,280,575), мин_x=4, script=(40,66,280,480), pic=(20,64,520,620)),
 'R':dict(poly=[[2808,276],[2880,232],[2880,600],[2808,646]], thick=(2815,2856,290,584), script=(2856,2880,250,460), pic=(2832,2880,500,615)),
}
def put(arr,oy,ox):
    a=np.zeros((H,W),np.float32); h,w=arr.shape
    sy0,sx0=max(0,-oy),max(0,-ox); dy0,dx0=max(0,oy),max(0,ox)
    hh=min(h-sy0,H-dy0); ww=min(w-sx0,W-dx0)
    a[dy0:dy0+hh,dx0:dx0+ww]=arr[sy0:sy0+hh,sx0:sx0+ww]; return a
def zone(b):
    x0,x1,y0,y1=b; m=np.zeros((H,W),bool); m[y0:y1,x0:x1]=True; return m
for nm,c in BANNERS.items():
    P=np.zeros((H,W),np.uint8); cv2.fillPoly(P,[np.array(c['poly'],np.int32)],1); P=P.astype(bool)
    L=EN.mean(-1)
    thick=zone(c['thick'])&P&(L<120)&~(zone(c['pic'])&(EN[...,0]>EN[...,2]+5))   # палочка ваты (оливковая) — не буква
    stick=zone(c['pic'])&(EN[...,0]>EN[...,2]+5)&(L<170)
    thick=nd.binary_dilation(thick,iterations=2)&P&~stick
    sc=zone(c['script'])&P&(L<185)&(EN[...,2]>EN[...,0]+15)&~zone(c['pic'])
    sc=nd.binary_dilation(sc,iterations=2)&P
    col_t=np.median(EN[zone(c['thick'])&P&(L<70)],0); col_s=np.median(EN[zone(c['script'])&P&(L<150)&(EN[...,2]>EN[...,0]+20)],0)
    hole=thick|sc
    clean=(P&~nd.binary_dilation(hole,iterations=3)).astype(float)
    fill=np.zeros_like(E)
    for sg in (6,12,24):
        num=nd.gaussian_filter(EN*clean[...,None],(sg,sg,0)); den=nd.gaussian_filter(clean,sg)
        ok=(den>0.05)&hole&(fill.sum(-1)==0); fill[ok]=(num/np.maximum(den,1e-6)[...,None])[ok]
    OUT[hole]=fill[hole]
    # «Сахарная вата»
    x0,x1,y0,y1=c['thick']; ys_,xs_=np.where(zone(c['thick'])&P&(L<100)); k=(ys_.max()-ys_.min())/word.shape[0]; w=cv2.resize(word.astype(np.float32),(max(1,int(word.shape[1]*k)),int(word.shape[0]*k)),interpolation=cv2.INTER_AREA)
    ys,xs=np.where(zone(c['thick'])&P&(L<100)); cx=(xs.min()+xs.max())/2; cy=(ys.min()+ys.max())/2
    oy=int(round(cy-w.shape[0]/2)); ox=int(round(cx-w.shape[1]/2))
    ox=max(ox, c.get('мин_x', ox))   # левый баннер: строка целиком на флаге (замечание 13 октября)
    a=put(w,oy,ox)*P
    OUT=OUT*(1-a[...,None])+col_t*a[...,None]
    # «Рваное облачко»
    x0,x1,y0,y1=c['script']; ys,xs=np.where(zone(c['script'])&P&(L<185)&(EN[...,2]>EN[...,0]+15)&~zone(c['pic']))
    span=ys.max()-ys.min(); thick_px=xs.max()-xs.min()
    F=ImageFont.truetype('C:/Windows/Fonts/segoescb.ttf',200)
    im=Image.new('L',(2000,320),0); ImageDraw.Draw(im).text((10,10),'Рваное облачко',font=F,fill=255)
    arr=np.asarray(im); yy,xx=np.where(arr>0); arr=arr[yy.min():yy.max()+1,xx.min():xx.max()+1]
    rot=np.rot90(arr,-1)          # читается сверху вниз, верх букв вправо
    s=min(span/rot.shape[0], thick_px/rot.shape[1])
    r2=cv2.resize(rot.astype(np.float32)/255,(max(1,int(rot.shape[1]*s)),max(1,int(rot.shape[0]*s))),interpolation=cv2.INTER_AREA)
    cxs=(xs.min()+xs.max())/2; cys=(ys.min()+ys.max())/2
    oy=int(round(cys-r2.shape[0]/2)); ox=int(round(cxs-r2.shape[1]/2))
    a=put(r2,oy,ox)*P
    OUT=OUT*(1-a[...,None])+col_s*a[...,None]
    print(nm,'k',round(k,3),'цвет букв',col_t.round(),'скрипт',col_s.round(),'вата',w.shape,'облачко',r2.shape,'масштаб',round(s,3))
Image.fromarray(np.clip(OUT+0.5,0,255).astype(np.uint8)).save('work/graphics_masks/drafts/map13_p2.png')
im=Image.open('work/graphics_masks/drafts/map13_p2.png'); en=Image.open('work/graphics_en/maps/map13.png').convert('RGB')
tiles=[en.crop((0,200,110,660)),im.crop((0,200,110,660)),en.crop((2770,200,2880,660)),im.crop((2770,200,2880,660))]
C=Image.new('RGB',(4*230,920))
for i,t in enumerate(tiles): C.paste(t.resize((220,920)),(i*230,0))
C.save(f'{S}/map13_vata.png')
