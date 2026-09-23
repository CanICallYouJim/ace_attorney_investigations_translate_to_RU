"""Буквы в зелёных кружках схемы площади дела 1: R/P/K → Л/П/К.

Инициалы по именам в каждом языке (немцы T/P/S, французы L/P/V, японцы 外/大/内):
Ладьин, Президент, Конев — по глоссарию. Буквы шрифтом не набираются: английские —
монолиния с круглыми концами и острыми углами, у установленных шрифтов такой
кириллицы нет. Поэтому П и Л чертятся штрихом по замеру английских (штрих 8/98
диаметра, прописная 19..79 из 98), а К — английская K, в этом рисунке она
совпадает с русской. Старая буква снимается внутри диска: всё осветлённое против
зелёного диска перекрашивается в его цвет (фон ровный, у всех языков один).

    .venv\Scripts\python.exe tools\discs.py

Картинки: cut00_02b, cutobj00_004, logic00_013_s, itm00_004_01_l.
Пишет в work/graphics_ru/case1/. Лист — tools/sheet.py <имя>.
"""
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
EN="work/graphics_en/case1/"; RU="work/graphics_ru/case1/"
# геометрия в долях диаметра диска (замер по 98-px диску cut00_02b): штрих 8/98,
# прописная 19..79, П — стойки 27..34 и 66..73; концы круглые, углы острые
W=8/98
def glyph(ch):
    t,b=22.5/98,75.5/98; l,r=30.5/98,69.5/98
    if ch=="П": return [[(l,b),(l,t),(r,t),(r,b)]]
    if ch=="Л": return [[(25.5/98,b),(35.5/98,t),(r,t),(r,b)]]
def draw_letter(d, ch, x0, y0, D, S):
    w=W*D*S
    for poly in glyph(ch):
        pts=[(x0*S+px*D*S, y0*S+py*D*S) for px,py in poly]
        for a,bq in zip(pts,pts[1:]): d.line([a,bq],fill=255,width=round(w))
        for p in (pts[0],pts[-1]): d.ellipse((p[0]-w/2,p[1]-w/2,p[0]+w/2,p[1]+w/2),fill=255)
        for p in pts[1:-1]:  # острый угол: квадрат на стыке
            d.rectangle((p[0]-w/2,p[1]-w/2,p[0]+w/2,p[1]+w/2),fill=255)
def discs_of(A):
    r,g,b,a=[A[...,i] for i in range(4)]
    green=(g>120)&(r<120)&(b<120)&(g-r>60)
    filled=ndimage.binary_fill_holes(green)
    lab,k=ndimage.label(filled)
    out=[]
    for sl in ndimage.find_objects(lab):
        h=sl[0].stop-sl[0].start; w=sl[1].stop-sl[1].start
        if h>=14 and abs(h-w)<=2: out.append((sl[1].start,sl[0].start,max(h,w)))
    return out
def which(A,x0,y0,D):
    s=A[y0:y0+D,x0:x0+D,:3].astype(int); wm=(s[...,0]>150)&(s[...,1]>150)
    yy,xx=np.mgrid[0:D,0:D]; inside=(yy-D/2)**2+(xx-D/2)**2<(0.42*D)**2
    wm&=inside
    return wm
def run(name, letters):
    im=Image.open(EN+name+".png").convert("RGBA"); A=np.asarray(im).copy()
    ds=sorted(discs_of(A))
    print(name, ds)
    S=8
    for (x0,y0,D),ch in zip(ds,letters):
        if ch=="К": continue
        s=A[y0:y0+D,x0:x0+D]
        yy,xx=np.mgrid[0:D,0:D]; rr=np.hypot(yy-(D-1)/2,xx-(D-1)/2)
        ring=(rr<0.44*D)&(s[...,1].astype(int)-s[...,0]>150)
        G=np.median(s[ring][:,:3],axis=0).astype(int)
        inside=rr<0.43*D
        tint=inside&((s[...,0].astype(int)-G[0])>12)
        s[tint,:3]=G   # снять старую букву: всё осветлённое внутри диска — в зелёный
        m=Image.new("L",(D*S,D*S),0); draw_letter(ImageDraw.Draw(m),ch,0,0,D,S)
        m=np.asarray(m.resize((D,D),Image.LANCZOS)).astype(float)/255
        for c in range(3): s[...,c]=(s[...,c]*(1-m)+255*m).round().astype(np.uint8)
        A[y0:y0+D,x0:x0+D]=s
    Image.fromarray(A).save(RU+name+".png")
# буквы по порядку дисков (сортировка по x): задаётся глазами по английским
import sys
jobs={"cut00_02b":"ЛПК","itm00_004_01_l":"ЛПК","logic00_013_s":"ЛПК","cutobj00_004":"КЛП"}
for n,l in jobs.items(): run(n,l)
