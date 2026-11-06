"""Verify shipped files, all icon sizes, and real frozen CLI builds without Python."""
import hashlib
import io
import json
import os
import struct
import subprocess
import tempfile
import types
from pathlib import Path

import pefile
from PIL import Image
from PyInstaller.archive.readers import CArchiveReader

root = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent
exe = root / "dist/release/AAI2-RU.exe"
tree = root / "dist/release/patcher"
archive = CArchiveReader(str(exe))
keys = {key.replace("\\", "/"): key for key in archive.toc}
files = []
for folder in ("data", "assets"):
    for path in sorted((tree / folder).rglob("*")):
        if path.is_file():
            rel = path.relative_to(tree).as_posix()
            assert archive.extract(keys[rel]) == path.read_bytes(), rel
            files.append(rel)
assert len(files) >= 478, len(files)

def codes(code):
    yield code
    for item in code.co_consts:
        if isinstance(item, types.CodeType):
            yield from codes(item)

pyz = archive.open_embedded_archive(next(k for k in archive.toc if k.endswith(".pyz")))
for module in ("loading_ui", "loading_assets", "loading_audio", "steps"):
    packed = list(codes(pyz.extract(module)))
    source = root / "patcher" / f"{module}.py"
    assert source.read_bytes() == (tree / source.name).read_bytes()
    current = list(codes(compile(source.read_text(encoding="utf-8"), source.name, "exec")))
    assert len(packed) == len(current), module
    for a, b in zip(packed, current):
        assert a.co_code == b.co_code and a.co_names == b.co_names, (module, a.co_name)
        assert [v for v in a.co_consts if not isinstance(v, types.CodeType)] == [v for v in b.co_consts if not isinstance(v, types.CodeType)], (module, a.co_name)

pe = pefile.PE(str(exe))
icons, groups = {}, []
for typ in pe.DIRECTORY_ENTRY_RESOURCE.entries:
    if typ.id not in (3, 14):
        continue
    for resource in typ.directory.entries:
        record = resource.directory.entries[0].data.struct
        raw = pe.get_data(record.OffsetToData, record.Size)
        if typ.id == 3:
            icons[resource.id] = raw
        else:
            groups.append(raw)
expected = Image.open(tree / "assets/installer.ico")
sizes = []
for group in groups:
    count = struct.unpack_from("<HHH", group)[2]
    for n in range(count):
        w, h, colors, reserved, planes, bits, length, ident = struct.unpack_from("<BBBBHHIH", group, 6 + 14 * n)
        single = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", w, h, colors, reserved, planes, bits, length, 22) + icons[ident]
        actual = Image.open(io.BytesIO(single)).convert("RGBA")
        wanted = expected.ico.getimage((w or 256, h or 256)).convert("RGBA")
        assert actual.size == wanted.size and actual.tobytes() == wanted.tobytes(), actual.size
        sizes.append(actual.size)
assert len(sizes) == 9

env = os.environ.copy()
env["PATH"] = str(Path(env.get("SystemRoot", r"C:\Windows")) / "System32")
for name in ("PYTHONPATH", "PYTHONHOME"):
    env.pop(name, None)
results = {}
with tempfile.TemporaryDirectory(prefix="aai2-gui-release-") as temporary:
    for name, args in (
        ("check", ["--check"]),
        ("text", ["--no-graphics", "--build-only", str(Path(temporary) / "text")]),
        ("graphics", ["--build-only", str(Path(temporary) / "graphics"), "--bundle", "gk_common_ingameui_trial"]),
    ):
        with (out / f"exe-{name}.log").open("wb") as log:
            result = subprocess.run([str(exe), *args, "--no-pause"], cwd=temporary, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        results[name] = result.returncode
        assert result.returncode == 0, (name, result.returncode)
        if name != "check":
            results[name + "_files"] = len(list((Path(temporary) / name).iterdir()))
            assert results[name + "_files"] > 0
        print(name, results[name], flush=True)

report = {"bytes": exe.stat().st_size, "sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
          "checked_files": len(files), "icon_sizes": sizes, "checks": results,
          "source_dev": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()}
(out / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False), flush=True)
