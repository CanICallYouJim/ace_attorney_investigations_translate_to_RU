import sys, json, gc, collections
from pathlib import Path
import re, UnityPy
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from common import BUNDLES, WORK, load_json
from audit_text import classify, covered_files, scan_bundle
from publish_release import graphics_progress
covered = covered_files()
rows = []
for p in sorted(BUNDLES.glob('*.bundle')):
    category = classify(p.name, covered)
    row = {'file':p.name, 'bytes':p.stat().st_size,'category':category}
    if category == 'не покрыто' and p.stat().st_size < 30_000_000:
        kinds, samples = scan_bundle(p)
        row.update(kinds=dict(kinds), samples=samples)
        if kinds.get('TextAsset'):
            env = UnityPy.load(str(p))
            row['text_phrases'] = []
            for obj in env.objects:
                if obj.type.name != 'TextAsset': continue
                asset = obj.read()
                raw = asset.m_Script
                if isinstance(raw, bytes): raw = raw.decode('utf-8', errors='replace')
                phrases = re.findall(r'\b[A-Za-z]{2,}(?: [A-Za-z]{2,}){2,}\b', raw)
                if phrases: row['text_phrases'].append({'asset':asset.m_Name,'phrases':phrases})
            del env
        gc.collect()
    else:
        row['inspection'] = 'classified only; not scanned in this bounded pass'
    rows.append(row)
    print(json.dumps(row,ensure_ascii=False),flush=True)
    (WORK/'qa_global_20261101_inventory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print('GRAPHICS',graphics_progress(load_json(WORK/'localized_assets.json')['families'],load_json(WORK/'graphics_layers/manifest.json'),load_json(WORK/'graphics_ru/coverage.json')),flush=True)
print('EXCLUSIONS',collections.Counter(v['kind'] for v in load_json(WORK/'graphics_ru/coverage.json')['excluded'].values()),flush=True)
