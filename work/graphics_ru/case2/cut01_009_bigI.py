import sys, numpy as np, cv2
from PIL import Image
from scipy import ndimage as nd
S=sys.argv[1]; SX=float(sys.argv[2])  # финал 13 октября: 1.5 522 742; BOT=int(sys.argv[3]); CX=float(sys.argv[4])
p3=np.asarray(Image.open('work/graphics_masks/drafts/cut01_009_p3.png').convert('RGB')).astype(float)
p4=np.asarray(Image.open('work/graphics_masks/drafts/cut01_009_p4.png').convert('RGB')).astype(float)
x0,y0,x1,y1=668,432,786,560
g=p4[y0:y1,x0:x1]; bgc=np.median(p3[440:560,700:780].reshape(-1,3),0)
diff=np.abs(g-bgc).max(-1)
m=diff>14; lab,n=nd.label(m); sz=nd.sum(m,lab,range(1,n+1)); m=lab==(np.argmax(sz)+1); m=nd.binary_fill_holes(m)
alpha=np.clip(nd.gaussian_filter(m.astype(float),0.7),0,1)
ys,xs=np.where(m); gy0,gy1,gx0,gx1=ys.min(),ys.max()+1,xs.min(),xs.max()+1
glyph=g[gy0:gy1,gx0:gx1]; al=alpha[gy0:gy1,gx0:gx1]
TOP=200-15; H=BOT-TOP; SY=H/glyph.shape[0]; Wd=int(glyph.shape[1]*SX)
G=cv2.resize(glyph.astype(np.float32),(Wd,H),interpolation=cv2.INTER_CUBIC); A=cv2.resize(al.astype(np.float32),(Wd,H),interpolation=cv2.INTER_LINEAR)
print('глиф',glyph.shape,'->',G.shape,'SY',round(SY,2))
out=p3.copy(); ox=int(round(CX-Wd/2)); oy=TOP
# где можно рисовать: ровный фон вывески в p3 (не слон)
reg=p3[oy:oy+H,ox:ox+Wd]
flat=(np.abs(reg-bgc).max(-1)<14)&(nd.generic_filter(reg.mean(-1),np.std,size=5)<6)
flat=nd.binary_opening(flat,iterations=1); lb,nn=nd.label(flat); sz=nd.sum(flat,lb,range(1,nn+1)); flat=np.isin(lb,np.where(sz>2000)[0]+1); fa=np.clip(nd.gaussian_filter(flat.astype(float),0.8),0,1)*flat.astype(float)
a=(A*fa)[...,None]
out[oy:oy+H,ox:ox+Wd]=reg*(1-a)+G*a
Image.fromarray(np.clip(out+0.5,0,255).astype(np.uint8)).save('work/graphics_masks/drafts/cut01_009_p5.png')
Image.fromarray(np.clip(out+0.5,0,255).astype(np.uint8)).crop((640,150,1000,640)).resize((720,980)).save(f'{S}/c009p5.png')
