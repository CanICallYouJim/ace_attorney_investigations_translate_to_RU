"""Общие пути и хелперы для всех скриптов локализации AAI2."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
BACKUP = PROJECT / "backup"
WORK = PROJECT / "work"
DOCS = PROJECT / "docs"

GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Ace Attorney Investigations Collection")
BUNDLES = GAME / "GK12_Data" / "StreamingAssets" / "aa" / "StandaloneWindows64"
CATALOG = GAME / "GK12_Data" / "StreamingAssets" / "aa" / "catalog.json"

# Бандлы, которые мы читаем и/или модифицируем.
# Имена содержат хеш сборки — если игра обновится, они поменяются, поэтому резолвим по префиксу.
SCRIPT_LANGS = ("eng", "fre", "ger", "jpn", "kor", "sim", "tra")

BUNDLE_PREFIXES = {
    **{f"script_{lang}": f"gk2_scriptmessage_{lang}_assets_all_" for lang in SCRIPT_LANGS},
    **{f"gk1_script_{lang}": f"gk1_scriptmessage_{lang}_assets_all_" for lang in SCRIPT_LANGS},
    "strings_eng": "localization-string-tables-english(en)_assets_all_",
    "strings_fre": "localization-string-tables-french(fr)_assets_all_",
    # Вопреки названию, в группе "_trial_" лежат основные строковые таблицы игры
    # (имена говорящих, названия улик, кнопки логики) — она в разы больше обычной.
    "strings_eng_main": "localization-string-tables-english(en)_trial_assets_all_",
    "strings_fre_main": "localization-string-tables-french(fr)_trial_assets_all_",
    "locales": "localization-locales_assets_all_",
}

# Бандлы, которые мы реально пишем -> их бэкапим.
MODIFIED = ["script_fre", "strings_fre", "locales"]

# Дело N в GK2 — это файлы sce{N-1}_*, а также логика и предметы с тем же индексом.
# Пользователь проходит дело 2, то есть sce1 / logic01 / itm01.
CASE = 2
CASE_PREFIXES = (f"sce{CASE-1}_", f"logic{CASE-1:02d}", f"itm{CASE-1:02d}")

# Файлы, где блоки состоят из чистых бинарных данных без текста: они одинаковы во всех
# семи локализациях, переводить в них нечего. Токенизатор на них ругается — это ожидаемо.
BINARY_ONLY_FILES = {"map0a.bytes", "map0c.bytes"}


def in_case_scope(filename: str) -> bool:
    return filename.lower().startswith(CASE_PREFIXES)


def bundle(name: str) -> Path:
    """Путь к бандлу по логическому имени, с резолвом хеша в имени файла."""
    prefix = BUNDLE_PREFIXES[name]
    matches = sorted(BUNDLES.glob(prefix + "*.bundle"))
    if not matches:
        raise FileNotFoundError(f"нет бандла с префиксом {prefix!r} в {BUNDLES}")
    if len(matches) > 1:
        raise RuntimeError(f"неоднозначный префикс {prefix!r}: {[m.name for m in matches]}")
    return matches[0]


def read_scripts(bundle_key: str) -> dict[str, bytes]:
    """Все TextAsset'ы скриптового бандла: имя файла (lowercase) -> сырые байты."""
    import UnityPy

    env = UnityPy.load(str(bundle(bundle_key)))
    out: dict[str, bytes] = {}
    for path, obj in env.container.items():
        data = obj.read()
        script = data.m_Script
        raw = script.encode("utf-8", "surrogateescape") if isinstance(script, str) else bytes(script)
        out[path.split("/")[-1].lower()] = raw
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def game_is_running() -> bool:
    """Игра держит хэндлы на .bundle — писать в них можно только когда она закрыта."""
    import subprocess

    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq GK12.exe", "/NH"],
        capture_output=True, text=True, encoding="cp866", errors="replace",
    ).stdout
    return "GK12.exe" in out
