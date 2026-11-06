import json, struct, re, collections
from audit_stream import Bundle, Slice, Reader, SerializedFile, GAME, WORK
path=GAME/'GK12_Data/data.unity3d'; b=Bundle(path)
files={n['name']:SerializedFile(Reader(Slice(b,n)),name=n['name']) for n in b.nodes if n['flags']&4}
def resolve(sf,ptr):
    target=sf
    if ptr.m_FileID:
        target=files[sf.externals[ptr.m_FileID-1].name]
    return target.objects[ptr.m_PathID]
scan=json.loads((WORK/'audit_complete_20261101_v2/data.unity3d.json').read_text(encoding='utf-8'))
strs=collections.defaultdict(list)
for cab,pid,kind,field,text in scan['strings']:
    if kind=='MonoBehaviour': strs[cab,pid].append(text)
rows=[]; errors=[]
for cab,sf in files.items():
    for obj in sf.objects.values():
        if obj.type.name!='MonoBehaviour': continue
        try:
            head=obj.parse_monobehaviour_head(); script=resolve(sf,head.m_Script).read_typetree()
            go=resolve(sf,head.m_GameObject).read_typetree() if head.m_GameObject.m_PathID else {}
            rows.append(dict(cab=cab,id=obj.path_id,go=head.m_GameObject.m_PathID,name=go.get('m_Name'),active=go.get('m_IsActive'),script=script.get('m_Namespace','')+'.'+script['m_ClassName'],strings=strs[cab,obj.path_id]))
        except Exception as e: errors.append([cab,obj.path_id,str(e)])
(WORK/'audit_complete_20261101_v2/ui_components.json').write_text(json.dumps({'components':rows,'errors':errors},ensure_ascii=False,indent=1),encoding='utf-8')
print('components',len(rows),'errors',errors[:5])
for row in rows:
    if 'TextMeshPro' in row['script'] or row['script'].endswith('.Text'):
        english=[s for s in row['strings'] if re.search(r'[A-Za-z]{2,} [A-Za-z]{2,}',s) and not s.startswith('GUID:')]
        if english:
            siblings=[r for r in rows if r['cab']==row['cab'] and r['go']==row['go'] and ('Local' in r['script'])]
            print(row['cab'],row['id'],row['name'],english,[(r['script'],r['strings']) for r in siblings])
b.close()
