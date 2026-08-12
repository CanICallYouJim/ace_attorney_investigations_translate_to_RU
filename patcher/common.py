"""Общие пути и хелперы для всех скриптов локализации AAI2."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DOCS = PROJECT / "docs"

# Пути переопределяются переменными окружения — ради патчера (patcher/aai2ru.py),
# который гоняет эти же модули на чужой машине: игра там в другом месте, данные
# перевода лежат рядом с ним, а бэкап должен уехать внутрь папки игры.
# Переменные читаются на импорте, потому что модули берут пути через `from common
# import GAME` — то есть значением, а не ссылкой; переприсваивать потом поздно.
# В обычной работе из репозитория ничего не задано и всё как было.
BACKUP = Path(os.environ.get("AAI2_BACKUP") or PROJECT / "backup")
WORK = Path(os.environ.get("AAI2_WORK") or PROJECT / "work")

GAME = Path(os.environ.get("AAI2_GAME")
            or r"C:\Program Files (x86)\Steam\steamapps\common\Ace Attorney Investigations Collection")
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
    # Скриптовых бандлов на язык ДВА, как и строковых таблиц. Во втором — дело 1
    # и общая механика (логические шахматы, экран проигрыша, реакции «Логики»),
    # то есть текст, который всплывает в любом деле. Найдено 12 августа 2026:
    # бандл не читался вовсе, и немецкий из него доходил до игрока.
    **{f"script_{lang}_trial": f"gk2_scriptmessage_{lang}_trial_assets_all_" for lang in SCRIPT_LANGS},
    # У первой игры бандлов тоже два. Она вне объёма перевода, но её немецкие
    # реплики патчер переписывает английскими: игрок выбрал «Русский», и немецкий
    # текст для него мусор, а английский читается.
    **{f"gk1_script_{lang}": f"gk1_scriptmessage_{lang}_assets_all_" for lang in SCRIPT_LANGS},
    **{f"gk1_script_{lang}_trial": f"gk1_scriptmessage_{lang}_trial_assets_all_"
       for lang in SCRIPT_LANGS},
    **{f"strings_{lang}": f"{p}_assets_all_" for lang, p in STRING_TABLE_PREFIXES.items()},
    # Вопреки названию, в группе "_trial_" лежат основные строковые таблицы игры
    # (имена говорящих, названия улик, кнопки логики) — она в разы больше обычной.
    **{f"strings_{lang}_main": f"{p}_trial_assets_all_" for lang, p in STRING_TABLE_PREFIXES.items()},
    "locales": "localization-locales_assets_all_",
}

# Логические имена бандлов слота-носителя — ими пользуются сборка и проверки.
HOST_SCRIPT = f"script_{HOST}"
HOST_SCRIPT_TRIAL = f"script_{HOST}_trial"
HOST_STRINGS = f"strings_{HOST}"
HOST_STRINGS_MAIN = f"strings_{HOST}_main"

# Оба скриптовых бандла разом: по ним ходят extract, build и проверки.
SCRIPT_PAIR = ((HOST_SCRIPT, "script_eng"), (HOST_SCRIPT_TRIAL, "script_eng_trial"))

# Бандлы, которые мы реально пишем -> их бэкапим.
# HOST_STRINGS_MAIN — там лежат имена в плашке, названия улик и профили,
# то есть основная часть строковых таблиц; см. комментарий к BUNDLE_PREFIXES.
MODIFIED = [HOST_SCRIPT, HOST_SCRIPT_TRIAL, HOST_STRINGS, HOST_STRINGS_MAIN, "locales"]

# Дело N в GK2 — это файлы sce{N-1}_*, а также логика и предметы с тем же индексом.
# В работе два дела: 2 (sce1 / logic01 / itm01) и 3 (sce2 / logic02 / itm02).
# Перевод каждого лежит в своём work/case{N}.json, а бандл собирается из всех сразу —
# он в игре один, и сборка только одного дела стёрла бы перевод другого.
#
# Плюс псевдодело 0 — файлы, которые к делу не привязаны вообще и всплывают в любом:
# реплики логических шахмат, реакции «Логики», экран проигрыша, мини-игра
# с металлоискателем. По имени они не опознаются никак (номера дела в нём нет),
# поэтому перечислены поимённо. Их перевод лежит в work/common.json.
COMMON_CASE = 0
CASES = (COMMON_CASE, 2, 3)

# Общие файлы: имя -> откуда взялось. Список закрытый и проверенный —
# всё остальное в trial-бандле это либо дело 1 (вне объёма), либо японский мусор,
# которого игра не показывает (detailmsg, backup, proper_name).
COMMON_FILES = {
    "mg_metal.bytes",        # мини-игра «металлоискатель», двор тюрьмы в деле 2
    "exam.bytes",            # реплики логических шахмат, все дела вперемешку
    "exam_ask.bytes",        # вопросы там же
    "exam_ask_title.bytes",  # заголовки «Выяснить...»
    "logic_common.bytes",    # «Логика»: реакция на неверную связку
    "game_over.bytes",       # экран проигрыша
}

# Файлы, где блоки состоят из чистых бинарных данных без текста: они одинаковы во всех
# семи локализациях, переводить в них нечего. Токенизатор на них ругается — это ожидаемо.
BINARY_ONLY_FILES = {"map0a.bytes", "map0c.bytes"}


def case_prefixes(case: int) -> tuple[str, ...]:
    """Шаблоны имён дела. У псевдодела 0 их нет — оно задано списком COMMON_FILES."""
    if case == COMMON_CASE:
        return ()
    return (f"sce{case-1}_", f"logic{case-1:02d}", f"itm{case-1:02d}")


ALL_CASE_PREFIXES = tuple(p for case in CASES for p in case_prefixes(case))


def case_of(filename: str) -> int | None:
    """Какому делу принадлежит файл сценария; None — вне объёма перевода.

    Единственное место, где живёт правило «что мы переводим». Все остальные скрипты
    обязаны спрашивать здесь, а не сверять имена своими списками: 12 августа 2026
    ровно на таком расхождении audit_text.py год отчитывался «покрыто» о бандле,
    который сборка не открывала ни разу.
    """
    low = filename.lower()
    if low in COMMON_FILES:
        return COMMON_CASE
    for case in CASES:
        prefixes = case_prefixes(case)
        if prefixes and low.startswith(prefixes):
            return case
    return None


def in_case_scope(filename: str) -> bool:
    return case_of(filename) is not None


def case_json(case: int) -> Path:
    # Псевдодело 0 названо по смыслу, а не номером: "case0" читалось бы как дело 1,
    # у которого файлы sce0_*, и путаница была бы гарантирована.
    return WORK / ("common.json" if case == COMMON_CASE else f"case{case}.json")


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


def read_scripts_all(lang: str = "eng") -> dict[str, bytes]:
    """Все скрипты языка — из ОБОИХ бандлов сразу: имя файла (lowercase) -> байты.

    Бандла два (`..._assets_all_` и `..._trial_assets_all_`), имена файлов в них
    не пересекаются: 399 + 44. Пересечение означало бы, что игра берёт какой-то файл
    из одного бандла, а мы пишем в другой, — поэтому оно ошибка, а не повод объединять.
    """
    out: dict[str, bytes] = {}
    for key in (f"script_{lang}", f"script_{lang}_trial"):
        part = read_scripts(key)
        clash = sorted(set(out) & set(part))
        if clash:
            raise RuntimeError(f"файл есть в обоих бандлах {lang}: {clash[:3]}")
        out.update(part)
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
