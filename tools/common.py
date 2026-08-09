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

# Слот-носитель: русский подменяет собой этот язык и становится обычным пунктом
# в игровом меню. Взят немецкий, а не французский, потому что немецкая локализация
# сохраняет привычные имена (Edgeworth, Kay, Gumshoe), а французская переименовывает
# весь состав (Benjamin Hunter, Cléa, Tektiv). Пока строковые таблицы не переведены,
# именно эти имена стоят в плашке говорящего и в названиях улик.
HOST = "ger"
HOST_SCENARIO_DIR = f"Assets/GK2/Scenario/_{HOST}/"

STRING_TABLE_PREFIXES = {
    "eng": "localization-string-tables-english(en)",
    "fre": "localization-string-tables-french(fr)",
    "ger": "localization-string-tables-german(de)",
    "jpn": "localization-string-tables-japanese(ja)",
    "kor": "localization-string-tables-korean(ko)",
    "sim": "localization-string-tables-chinese(simplified)(zh)",
    "tra": "localization-string-tables-chinese(traditional)(zh-tw)",
}

BUNDLE_PREFIXES = {
    **{f"script_{lang}": f"gk2_scriptmessage_{lang}_assets_all_" for lang in SCRIPT_LANGS},
    **{f"gk1_script_{lang}": f"gk1_scriptmessage_{lang}_assets_all_" for lang in SCRIPT_LANGS},
    **{f"strings_{lang}": f"{p}_assets_all_" for lang, p in STRING_TABLE_PREFIXES.items()},
    # Вопреки названию, в группе "_trial_" лежат основные строковые таблицы игры
    # (имена говорящих, названия улик, кнопки логики) — она в разы больше обычной.
    **{f"strings_{lang}_main": f"{p}_trial_assets_all_" for lang, p in STRING_TABLE_PREFIXES.items()},
    "locales": "localization-locales_assets_all_",
}

# Логические имена бандлов слота-носителя — ими пользуются сборка и проверки.
HOST_SCRIPT = f"script_{HOST}"
HOST_STRINGS = f"strings_{HOST}"
HOST_STRINGS_MAIN = f"strings_{HOST}_main"

# Бандлы, которые мы реально пишем -> их бэкапим.
# HOST_STRINGS_MAIN — там лежат имена в плашке, названия улик и профили,
# то есть основная часть строковых таблиц; см. комментарий к BUNDLE_PREFIXES.
MODIFIED = [HOST_SCRIPT, HOST_STRINGS, HOST_STRINGS_MAIN, "locales"]

# Дело N в GK2 — это файлы sce{N-1}_*, а также логика и предметы с тем же индексом.
# В работе два дела: 2 (sce1 / logic01 / itm01) и 3 (sce2 / logic02 / itm02).
# Перевод каждого лежит в своём work/case{N}.json, а бандл собирается из всех сразу —
# он в игре один, и сборка только одного дела стёрла бы перевод другого.
CASES = (2, 3)

# Файлы, где блоки состоят из чистых бинарных данных без текста: они одинаковы во всех
# семи локализациях, переводить в них нечего. Токенизатор на них ругается — это ожидаемо.
BINARY_ONLY_FILES = {"map0a.bytes", "map0c.bytes"}


def case_prefixes(case: int) -> tuple[str, ...]:
    return (f"sce{case-1}_", f"logic{case-1:02d}", f"itm{case-1:02d}")


ALL_CASE_PREFIXES = tuple(p for case in CASES for p in case_prefixes(case))


def in_case_scope(filename: str) -> bool:
    return filename.lower().startswith(ALL_CASE_PREFIXES)


def case_of(filename: str) -> int | None:
    """Какому делу принадлежит файл сценария; None — вне объёма перевода."""
    low = filename.lower()
    for case in CASES:
        if low.startswith(case_prefixes(case)):
            return case
    return None


def case_json(case: int) -> Path:
    return WORK / f"case{case}.json"


def load_entries(case: int | None = None) -> list[dict]:
    """Сегменты дела или всех дел сразу — из work/case{N}.json."""
    entries: list[dict] = []
    for one in (CASES if case is None else (case,)):
        data = load_json(case_json(one))
        if data:
            entries.extend(data["entries"])
    return entries


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
