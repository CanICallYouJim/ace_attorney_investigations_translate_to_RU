import json,hashlib,gc,collections,sys
from types import SimpleNamespace
from PIL import Image
import numpy as np
from UnityPy import Environment
from audit_stream import Bundle,Slice,Reader,SerializedFile,WORK,BUNDLES
from picture_layer import sprites_by_key,texture_of,model_texture,splash_placed,atlas_sprites
m=json.loads((WORK/'graphics_layers/manifest.json').read_text(encoding='utf-8'))
splash_only='--splash' in sys.argv
if splash_only:m['pictures']=[e for e in m['pictures'] if e.get('kind')=='splash']
output=WORK/'audit_complete_20261101_v2'/('live_splashes.json' if splash_only else 'live_graphics.json')
files=collections.defaultdict(list)
for p in (WORK/'graphics_ru').rglob('*.png'):files[p.stem].append(p)
results=[]
for prefix in sorted({e['bundle'] for e in m['pictures']}):
 p=next(BUNDLES.glob(prefix+'_assets_all_*.bundle'));b=Bundle(p);env=Environment();objs=[];container={}
 for n in b.nodes:env.register_cab(n['name'],Reader(Slice(b,n)))
 for n in b.nodes:
  if n['flags']&4:
   sf=SerializedFile(Reader(Slice(b,n)),parent=env,name=n['name']);env.register_cab(n['name'],sf);objs.extend(sf.objects.values())
   container.update({k:v.deref() for k,v in sf.container.items()})
 wrapper=SimpleNamespace(objects=objs,container=container);sprites=sprites_by_key(wrapper)
 print('BUNDLE',prefix,flush=True)
 for e in m['pictures']:
  if e['bundle']!=prefix:continue
  row={'name':e['name'],'bundle':prefix,'kind':e.get('kind','texture')}
  try:
   if row['kind']=='splash':
    spec=e['spec'];atlas=next(o for o in objs if o.type.name=='SpriteAtlas' and o.peek_name()==spec['атлас'])
    tree=atlas.read_typetree();byid={o.path_id:o for o in objs}
    texture=next(byid[rd['texture']['m_PathID']] for _,rd in tree['m_RenderDataMap'] if rd['texture']['m_PathID'] in byid)
    layer=Image.open(WORK/'graphics_layers'/e['layer']).convert('RGBA')
    ok=splash_placed(wrapper,spec,layer,texture,tree,atlas_sprites(wrapper,tree,spec['атлас']))
    row['status']='match' if ok else 'DIFFERENT';print(row,flush=True);results.append(row)
    output.write_text(json.dumps(results,ensure_ascii=False,indent=1),encoding='utf-8');continue
   png=next(f for f in files[e['name']] if hashlib.sha256(f.read_bytes()).hexdigest()==e['png_sha'])
   if row['kind']=='plate':tex=texture_of(wrapper,sprites[e['key']])
   elif row['kind']=='material':_,tex=model_texture(wrapper,e['key'],e['material']['target_texture'],own=True)
   else:tex=container[e['key']]
   got=tex.read().image.convert('RGBA');want=Image.open(png).convert('RGBA')
   if e.get('flipped'):got=got.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
   row.update(texture=tex.path_id,texture_name=tex.peek_name(),got_size=list(got.size),wanted_size=list(want.size))
   if got.size!=want.size: row['status']='size_difference'
   else:
    d=np.abs(np.asarray(got,dtype=np.int16)-np.asarray(want,dtype=np.int16));rough=int((d.max(-1)>64).sum());mean=float(d.mean())
    row.update(mean=round(mean,4),rough=rough,status='match' if mean<2 and rough<=got.width*got.height//10000 else 'DIFFERENT')
   print(row,flush=True)
  except Exception as ex:row.update(status='ERROR',error=str(ex));print(row,flush=True)
  results.append(row)
  output.write_text(json.dumps(results,ensure_ascii=False,indent=1),encoding='utf-8')
 b.close();del env,objs,container,wrapper;gc.collect()
print(collections.Counter(r['status'] for r in results),flush=True)
