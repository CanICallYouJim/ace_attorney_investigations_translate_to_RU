import hashlib,json
import UnityPy
from audit_stream import Bundle,Slice,Reader,SerializedFile,BUNDLES,WORK
report=[]
for prefix in ['gk2_cutdata_trial_','localization-string-tables-english(en)_assets_','gk2_scriptmessage_eng_trial_']:
    path=next(BUNDLES.glob(prefix+'*.bundle')); ordinary=UnityPy.load(str(path))
    expected={o.path_id:(o.type.name,hashlib.sha256(o.get_raw_data()).hexdigest()) for o in ordinary.objects}
    b=Bundle(path);actual={}
    for n in b.nodes:
        if n['flags']&4:
            sf=SerializedFile(Reader(Slice(b,n)),name=n['name'])
            # reverse order ensures random access across compressed blocks
            for o in reversed(list(sf.objects.values())):actual[o.path_id]=(o.type.name,hashlib.sha256(o.get_raw_data()).hexdigest())
    assert actual==expected,path.name
    report.append({'bundle':path.name,'objects':len(expected),'all_raw_sha256_equal':True});b.close()
(WORK/'audit_complete_20261101_v2/reader_validation.json').write_text(json.dumps(report,indent=1),encoding='utf-8')
print(report)
