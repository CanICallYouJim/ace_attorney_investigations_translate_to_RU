"""Read-only audit; results stay in work/."""
import sys, json, re, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from common import load_entries, load_json, WORK
from extract_strings import read_tables, PAIRS
from check_len import plain_text, is_demo_placeholder
import carriers as C

out = {'script_latin': [], 'table_latin': [], 'untranslated_tables': [], 'missing_live_rows': [], 'changed_sources': [], 'live_host_mismatch': []}
entries = load_entries()
out['scripts_total'] = len(entries)
out['scripts_empty'] = sum(not e.get('ru') for e in entries)
for e in entries:
    ru = plain_text(e.get('ru', ''))
    if re.search('[A-Za-z]', ru):
        out['script_latin'].append({'id': e['id'], 'ru': ru, 'demo': is_demo_placeholder(e)})
tables = load_json(WORK / 'strings.json')['tables']
keys = load_json(WORK / 'table_keys.json')
for t, rows in tables.items():
    for mid, e in rows.items():
        item = {'table': t, 'id': mid, 'key': keys.get(t, {}).get(mid), 'en': e['en'], 'ru': e.get('ru', '')}
        if not item['ru']:
            out['untranslated_tables'].append(item)
        elif re.search('[A-Za-z]', re.sub('<[^>]*>|\{[^}]*\}', '', item['ru'])):
            out['table_latin'].append(item)
out['live_tables'] = {}
for engkey, hostkey in PAIRS:
    eng, host = read_tables(engkey), read_tables(hostkey)
    for t, rows in eng.items():
        out['live_tables'][t] = len(rows)
        if t.startswith('gk1_'): continue
        for mid, en in rows.items():
            e = tables.get(t, {}).get(str(mid))
            if e is None: out['missing_live_rows'].append([t, mid, en]); continue
            if e['en'] != en: out['changed_sources'].append([t, mid, en])
            expected = e.get('ru') or en
            actual = C.decode(host.get(t, {}).get(mid, ''), C.chosen_map())
            if expected != actual: out['live_host_mismatch'].append({'table':t,'id':mid,'expected':expected,'actual':actual})
(WORK / 'qa_global_20261101_data.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print({k: len(v) if isinstance(v, (list,dict)) else v for k,v in out.items()})
print('Non-demo script Latin:', collections.Counter(w for e in out['script_latin'] if not e['demo'] for w in re.findall('[A-Za-z]+(?:[-\u2019\x27][A-Za-z0-9]+)*', e['ru'])))
print('Table Latin:')
for e in out['table_latin']: print(e['table'], e['key'], repr(e['ru']))
