import sys, numpy as np, cv2
from PIL import Image
from scipy import ndimage as nd
S=sys.argv[1]; KL=float(sys.argv[2]); KS=float(sys.argv[3])
p='work/graphics_masks/drafts/cut03_017_p2.png'
im=np.asarray(Image.open(p).convert('RGBA')).copy()
x0,y0,x1,y1=700,815,860,930
reg=im[y0:y1,x0:x1,:3].astype(float); L=reg.mean(-1); h,w=L.shape
O0=np.load(f'{S}/Omask.npy'); O=np.zeros((h,w),bool); O[5:5+O0.shape[0],:]=O0[:h-5] if O0.shape[0]>h-5 else O0
O=np.zeros((h,w),bool); O[5:5+O0.shape[0], :O0.shape[1]]=O0
Od=nd.binary_dilation(O,iterations=2)
pap=cv2.inpaint(np.clip(reg,0,255).astype(np.uint8),Od.astype(np.uint8),4,cv2.INPAINT_TELEA).astype(float)
paper=np.where(Od[...,None],nd.gaussian_filter(pap,(2,2,0)),reg)
a=np.clip((paper.mean(-1)-L)/np.maximum(paper.mean(-1)-105,1),0,1)*Od
dark=(paper-reg)*Od[...,None]                       # насколько чернила темнее бумаги
ys,xs=np.where(O); cx=(xs.min()+xs.max())/2; cy=(ys.min()+ys.max())/2
src=np.clip(np.round(2*cx-np.arange(w)).astype(int),0,w-1)
af=a[:,src]; dk=dark[:,src]
pts=np.column_stack(np.where(af>0.3))[:,::-1].astype(np.float32)
(ex,ey),(ea,eb),ang=cv2.fitEllipse(pts)
# ось длинная — по большему из ea/eb
th=np.deg2rad(ang if eb>=ea else ang+90)   # направление длинной оси (OpenCV: угол оси «eb»)
u=np.array([np.sin(th),-np.cos(th)])          # единичный вдоль длинной
v=np.array([np.cos(th),np.sin(th)])
R=np.stack([u,v]); Sc=np.diag([KL,KS]); A=R.T@Sc@R
M=np.hstack([A, (np.array([ex,ey])-A@np.array([ex,ey]))[:,None]]).astype(np.float32)
afw=cv2.warpAffine(af.astype(np.float32),M,(w,h),flags=cv2.INTER_LINEAR)
dkw=cv2.warpAffine(dk.astype(np.float32),M,(w,h),flags=cv2.INTER_LINEAR)
out=paper-dkw
blk=reg.copy(); m=Od|(afw>0.01); blk[m]=out[m]
im[y0:y1,x0:x1,:3]=np.clip(blk+0.5,0,255).astype(np.uint8)
Image.fromarray(im,'RGBA').save('work/graphics_masks/drafts/cut03_017_p4.png')
Image.fromarray(im).convert('RGB').crop((690,780,1000,960)).resize((620,360),Image.LANCZOS).save(f'{S}/O17d.png')
yy,xx=np.where(afw>0.1); print('эллипс',round(ea),round(eb),round(ang),'новая О x',xx.min()+x0,xx.max()+x0,'y',yy.min()+y0,yy.max()+y0)
