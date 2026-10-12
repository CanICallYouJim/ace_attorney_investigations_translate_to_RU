"""Вклейка правки Codex поверх черновика: python fixpaste.py <out.png> <draft.png> name:case:N[:x0,y0,x1,y1] ... (зона в координатах вырезки)"""
import sys, json
sys.path.insert(0,'tools')
from pathlib import Path
from PIL import Image
import numpy as np, paste_art
q=json.load(open('work/graphics_ai/codex.json',encoding='utf-8'))
out, draft = sys.argv[1], sys.argv[2]
base=Image.open(draft).convert('RGBA'); before=np.asarray(base).copy()
for spec in sys.argv[3:]:
    parts=spec.split(':'); n,case,v=parts[:3]; b=q[n]['box']; w,h=b[2]-b[0],b[3]-b[1]
    zone=[list(map(int,parts[3].split(',')))] if len(parts)>3 else [[0,0,w,h]]
    g={"art":str(Path(f'work/graphics_ai/{case}/{n}_codex_{v}.png').resolve()),"вырезка":b,"зона":zone,"по_разнице":22,"запас":4,"край":3}
    if len(parts)>4 and parts[4]=='nodiff': g.pop('по_разнице')
    r=paste_art.plate(base,g,Path('.')); print(n,{k:r[k] for k in r})
base.save(out)
d=np.abs(np.asarray(base).astype(int)-before.astype(int)).max(-1)>0; ys,xs=np.where(d); print('изменено',d.sum(),(xs.min(),xs.max(),ys.min(),ys.max()) if d.sum() else '')
