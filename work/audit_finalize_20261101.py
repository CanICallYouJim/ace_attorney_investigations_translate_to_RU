import json,re,collections,hashlib
from pathlib import Path
from audit_stream import WORK,GAME
p=WORK/'audit_complete_20261101_v2'
files=sorted(p.glob('*.bundle.json'))+[p/'data.unity3d.json',p/'unity default resources.json']
inventory=[]
for f in files:
 d=json.loads(f.read_text(encoding='utf-8'))
 inventory.append(dict(file=Path(d['file']).name,types=d['types'],objects=sum(d['types'].values()),strings=len(d['strings']),errors=len(d['errors']),raw_schema_fallback=len(d.get('fallback',[]))))
assert len(inventory)==166 and not any(r['errors'] for r in inventory)
data=json.loads((p/'data.unity3d.json').read_text(encoding='utf-8'))
english=next(s[4] for s in data['strings'] if s[0]=='resources.assets' and s[1]==261 and s[3]=='/m_Script/text')
legacy=[]
for line in re.split(r'\\r\\n|\r?\n',english):
 if '=' in line:
  key,value=line.split('=',1);legacy.append({'key':key,'english':value,'status':'untranslated; legacy/mobile-style resource; GK2 display not established','address':'data.unity3d/resources.assets:261'})
assert len(legacy)==20,len(legacy)
components=json.loads((p/'ui_components.json').read_text(encoding='utf-8'))['components']
labels=[r for r in components if r['cab']=='sharedassets4.assets' and r['id'] in [572,574,576,600,659]]
bad=['Sousa_TextCutBG_R_03','Sousa_TextCutBG_R_04','Sousa_TextCutBG_R_05']
live=json.loads((p/'live_graphics.json').read_text(encoding='utf-8'))
splashes={r['name']:r for r in json.loads((p/'live_splashes.json').read_text(encoding='utf-8'))}
for row in live:
 if row['name'] in splashes:row.update(splashes[row['name']])
 if row['name'] in bad:
  row['numeric_status']=row['status'];row['status']='foreign_text_confirmed_visually'
  row['reason']='Dark English text differs from approved Russian PNG, but its full-frame mean<2 and no difference exceeds64. Original texture_sha is NOT a hash of the installed Russian image.'
assert len(live)==246
findings={'installed_graphics':[r for r in live if r['name'] in bad],'legacy_english_resource':legacy,'legacy_gk1_labels':labels,'graphics_visual_review':{'textures':362,'sheets':19,'errors':0},'live_graphics':live}
(WORK/'audit_complete_20261101_findings.json').write_text(json.dumps(findings,ensure_ascii=False,indent=2),encoding='utf-8')
summary={'bundles':164,'additional_serialized_resources':2,'objects':sum(r['objects'] for r in inventory),'string_fields_and_candidates':sum(r['strings'] for r in inventory),'raw_schema_fallback':sum(r['raw_schema_fallback'] for r in inventory),'unread_objects':0,'compiled_literals':63302,'visual_textures':362,'live_graphics_status':dict(collections.Counter(r['status'] for r in live)),'inventory':inventory}
(WORK/'audit_complete_20261101_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print({k:v for k,v in summary.items() if k!='inventory'})
# Enumerate remaining files too; backups are not live resources.
other=[]
for f in sorted(GAME.rglob('*')):
 if not f.is_file() or '_backup_ru' in f.parts:continue
 rel=f.relative_to(GAME).as_posix()
 if f.suffix=='.bundle' or f.name in ('data.unity3d','unity default resources','global-metadata.dat'):continue
 category='binary platform/runtime resource'
 if f.suffix in ('.json','.xml','.config','.info'):
  text=f.read_text(encoding='utf-8-sig',errors='replace');category='configuration/catalog/assembly metadata; no translation table'
  # Preserve auditable content rather than silently discard configuration strings.
  (p/('config_'+f.name+'.txt')).write_text(text,encoding='utf-8')
 elif f.suffix=='.resource':category='external binary stream referenced by serialized assets'
 elif f.suffix=='.dat':category='standard .NET library resources; not a game localization database'
 other.append(dict(path=rel,bytes=f.stat().st_size,category=category))
(WORK/'audit_complete_20261101_other_files.json').write_text(json.dumps(other,ensure_ascii=False,indent=2),encoding='utf-8')
