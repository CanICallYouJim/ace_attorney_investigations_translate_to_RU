import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from PyInstaller.archive.readers import CArchiveReader

root = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent
exe = root / 'dist/release/AAI2-RU.exe'
tree = root / 'dist/release/patcher'
archive = CArchiveReader(str(exe))
checked = 0
for path in (tree / 'data').rglob('*'):
    if path.is_file():
        name = str(path.relative_to(tree)).replace('/', '\\')
        assert archive.extract(name) == path.read_bytes(), name
        checked += 1
assert checked > 400
changed = {}
for case in range(1, 6):
    rel = f'work/case{case}.json'
    old = json.loads(subprocess.check_output(['git', 'show', f'd64a416:{rel}'], cwd=root))
    new = json.loads((root / rel).read_text(encoding='utf-8'))
    before = {row['id']: row.get('ru') for row in old['entries']}
    packed = json.loads((tree / f'data/case{case}.json').read_text(encoding='utf-8'))
    shipped = {(row['file'], row['block'], row['index']): row['ru'] for row in packed['entries']}
    edits = [row for row in new['entries'] if row.get('ru') != before.get(row['id'])]
    for row in edits:
        assert shipped[row['file'], row['block'], row['index']] == row['ru'], row['id']
    changed[str(case)] = len(edits)
env = os.environ.copy()
env['PATH'] = str(Path(env.get('SystemRoot', r'C:\Windows')) / 'System32')
env.pop('PYTHONPATH', None)
results = {}
with tempfile.TemporaryDirectory(prefix='aai2-release-smoke-') as temp:
    for name, args in [('check', ['--check']), ('text_build', ['--no-graphics', '--build-only', str(Path(temp) / 'build')])]:
        with (out / f'exe_{name}.log').open('wb') as log:
            run = subprocess.run([str(exe), *args, '--no-pause'], cwd=temp, env=env, stdout=log, stderr=subprocess.STDOUT)
        results[name] = run.returncode
        assert run.returncode == 0, f'{name}: {run.returncode}'
result = {'source_dev': '867af0d', 'size': exe.stat().st_size, 'sha256': hashlib.sha256(exe.read_bytes()).hexdigest(), 'embedded_files_checked': checked, 'changed_segments_by_case': changed, 'smoke': results}
(out / 'exe_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
