import sys, numpy as np, cv2
from PIL import Image
from scipy import ndimage as nd
S=sys.argv[1]; K=float(sys.argv[2]); AX,AY,BX,BY=map(float,sys.argv[3:7])
E=np.asarray(Image.open('work/graphics_en/case4/cut03_005.png').convert('RGB')).astype(float)
R=np.asarray(Image.open('work/graphics_masks/drafts/hold/case4/cut03_005.png').convert('RGB')).astype(float)
x0,y0,x1,y1=1690,0,1890,1000
e=E[y0:y1,x0:x1]; r=R[y0:y1,x0:x1]; h,w=e.shape[:2]
POLY=np.array([[1690,0],[1905,0],[1852,993],[1690,976]])-np.array([x0,y0])
def banner_of(a):
    m=np.zeros(a.shape[:2],np.uint8); cv2.fillPoly(m,[POLY.astype(np.int32)],1); return m.astype(bool)
def ink(a):
    B=banner_of(a)
    m=(a.mean(-1)<95)&B
    core=nd.binary_erosion(m,iterations=9)          # толстые буквы; тонкое рукописное «Рваное облачко» не проходит
    lab,n=nd.label(m); keep=np.unique(lab[core]); keep=keep[keep>0]; m=np.isin(lab,keep)
    return nd.binary_dilation(m,iterations=3)
me,mr=ink(e),ink(r)
me=nd.binary_dilation(me,iterations=3); mr=nd.binary_dilation(mr,iterations=3)
cl=(~(me|mr)).astype(float)
def sm(x): return nd.gaussian_filter(x*cl[...,None],(25,25,0))/np.maximum(nd.gaussian_filter(cl,25)[...,None],1e-6)
e=e+(sm(r)-sm(e))                               # свет английского кадра — под черновик
bg=np.where(mr[...,None],e,r)                     # фон: где у черновика буквы — английский кадр
both=me&mr
# где буквы и там, и там: бумага стяга — нормированная свёртка чистых соседей по вертикали (дождь вертикальный)
clean=(~(me|mr)).astype(float)
fill=np.zeros_like(bg); got=np.zeros(bg.shape[:2])
for sg in (8,16,32,64):
    num=nd.gaussian_filter(bg*clean[...,None],(sg,sg,0)); den=nd.gaussian_filter(clean,sg)
    ok=(den>0.05)&(got==0); fill[ok]=(num/np.maximum(den,1e-6)[...,None])[ok]; got[ok]=1
bg=np.where(both[...,None],fill,bg)
# чернила черновика: альфа по тёмности против фона
bgr=cv2.inpaint(np.clip(r,0,255).astype(np.uint8),mr.astype(np.uint8),6,cv2.INPAINT_TELEA).astype(float)
inkc=np.array([28,28,30.])
a=np.clip((bgr.mean(-1)-r.mean(-1))/np.maximum(bgr.mean(-1)-inkc.mean(),1),0,1)*mr
# масштаб K вокруг (AX,AY) черновика -> в (BX,BY)
M=np.array([[K,0,BX-x0-K*(AX-x0)],[0,K,BY-y0-K*(AY-y0)]],np.float32)
aw=cv2.warpAffine(a.astype(np.float32),M,(w,h),flags=cv2.INTER_LINEAR)
aw*=nd.binary_erosion(banner_of(r),iterations=2)
rain=np.clip(bg-nd.gaussian_filter(bg,(5,5,0)),0,None)*0.8   # дождь поверх букв, как в оригинале
out=bg*(1-aw[...,None])+(inkc+rain)*aw[...,None]
F=R.copy(); F[y0:y1,x0:x1]=out
Image.fromarray(np.clip(F+0.5,0,255).astype(np.uint8)).save('work/graphics_masks/drafts/cut03_005_p2.png')
bx=(1640,0,1920,1080)
ims=[Image.fromarray(np.clip(X,0,255).astype(np.uint8)).crop(bx) for X in (E,R,F)]
W=Image.new('RGB',(860,1080)); [W.paste(im,(i*290,0)) for i,im in enumerate(ims)]; W.save(f'{S}/vata_new.png')
