import json,re,gc
from pathlib import Path
from PIL import Image,ImageDraw
from UnityPy import Environment
from audit_stream import Bundle,Slice,Reader,SerializedFile,GAME,WORK,BUNDLES
out=WORK/'audit_complete_20261101_v2/visual';out.mkdir(exist_ok=True)
paths=[GAME/'GK12_Data/data.unity3d']+sorted(p for p in BUNDLES.glob('*.bundle') if p.name.startswith(('gk_common_ui','gk_common_ingameui','gk_common_title','gk2_modelitem_assets','gk2_modelitem_trial')))
items=[]; errors=[]; page=0; thumbs=[]
def savepage():
    global page,thumbs
    if not thumbs:return
    sheet=Image.new('RGB',(1400,((len(thumbs)+3)//4)*230),(55,55,55));draw=ImageDraw.Draw(sheet)
    for i,(img,label) in enumerate(thumbs):
        x=(i%4)*350;y=(i//4)*230;sheet.paste(img,(x+(350-img.width)//2,y));draw.text((x+4,y+196),label,fill='white')
    sheet.save(out/f'sheet_{page:02}.jpg');page+=1;thumbs=[]
for p in paths:
    b=Bundle(p);env=Environment()
    for n in b.nodes:env.register_cab(n['name'],Reader(Slice(b,n)))
    for n in b.nodes:
        if not n['flags']&4:continue
        sf=SerializedFile(Reader(Slice(b,n)),parent=env,name=n['name']);env.register_cab(n['name'],sf)
        for obj in sf.objects.values():
            if obj.type.name!='Texture2D':continue
            obj.reset();name=obj.reader.read_aligned_string()
            if re.search(r'(?:_(?:jpn|fre|kor|sim|tra)(?:_|$)|sdf|font|ldr_lll|noise|gradient|areatex|searchtex|shadow)',name,re.I):continue
            try:
                tex=obj.read();im=tex.image.convert('RGBA')
                idx=len(items);im.save(out/f'{idx:04}.png')
                items.append(dict(index=idx,bundle=p.name,cab=n['name'],id=obj.path_id,name=name,size=list(im.size)))
                im.thumbnail((340,190));bg=Image.new('RGBA',im.size,(90,90,90,255));bg.alpha_composite(im)
                thumbs.append((bg.convert('RGB'),f'{idx}: {name[:42]}\n{p.name[:34]}'))
                if len(thumbs)==20:savepage()
            except Exception as e:errors.append([p.name,n['name'],obj.path_id,name,str(e)])
        del sf;gc.collect()
    b.close();print(p.name,len(items),'errors',len(errors),flush=True)
savepage();(out/'index.json').write_text(json.dumps({'items':items,'errors':errors},ensure_ascii=False,indent=1),encoding='utf-8')
