import json,hashlib
from types import SimpleNamespace
from UnityPy import Environment
from audit_stream import Bundle,Slice,Reader,SerializedFile,WORK,BUNDLES
from picture_layer import sprites_by_key,texture_of,pixels_sha
manifest=json.loads((WORK/'graphics_layers/manifest.json').read_text(encoding='utf-8'))
results=[]
for prefix in ['gk_common_ingameui','gk_common_ingameui_trial']:
 p=next(BUNDLES.glob(prefix+'_assets_all_*.bundle'));b=Bundle(p);env=Environment()
 for n in b.nodes:env.register_cab(n['name'],Reader(Slice(b,n)))
 objs=[]
 for n in b.nodes:
  if n['flags']&4:
   sf=SerializedFile(Reader(Slice(b,n)),parent=env,name=n['name']);objs.extend(sf.objects.values());env.register_cab(n['name'],sf)
 wrapper=SimpleNamespace(objects=objs);sprites=sprites_by_key(wrapper)
 for e in manifest['pictures']:
  if e['bundle']!=prefix or not e['name'].startswith('Sousa_Text'):continue
  spr=sprites[e['key']];tex=texture_of(wrapper,spr);im=tex.read().image
  actual=pixels_sha(im);row={'name':e['name'],'sprite':spr.path_id,'texture':tex.path_id,'texture_name':tex.peek_name(),'original_source_sha':e['texture_sha'],'actual':actual,'equals_original_source':actual==e['texture_sha']}
  im.save(WORK/'audit_complete_20261101_v2/visual'/('live_'+e['name']+'.png'));results.append(row);print(row,flush=True)
 b.close()
(WORK/'audit_complete_20261101_v2/live_plates.json').write_text(json.dumps(results,indent=1),encoding='utf-8')
