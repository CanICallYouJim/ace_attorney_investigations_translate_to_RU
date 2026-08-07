"""Извлечь строковые таблицы в редактируемый work/strings.json.

Сюжетные реплики лежат в скриптах и вынимаются extract.py. А имена в плашке
говорящего, названия и описания улик, профили персонажей, кнопки логики и варианты
ответа лежат отдельно — в строковых таблицах Unity Localization. Это второй,
независимый пласт текста, и без него улики в органайзере остаются английскими.

Профили персонажей отдельной таблицы не имеют: они лежат в тех же `gk2_item_name`
и `gk2_item_text`, что и улики — в Ace Attorney профиль это такой же предмет
в органайзере.

Формат записи таблицы: `m_TableData: [{m_Id, m_Localized, m_Metadata}]`, ключ —
числовой `m_Id`, общий для всех языков. Немецкое значение кладём рядом с английским
для справки: немцы решали ровно те же задачи, и подсмотреть бывает полезно —
например, Knight у них Springer, то есть шахматный конь.

Скрипт не затирает уже сделанный перевод: если английский оригинал записи
не изменился, поле "ru" переносится из прошлого запуска.

    python tools/extract_strings.py
"""
from __future__ import annotations

import collections

import UnityPy

from common import (HOST_STRINGS, HOST_STRINGS_MAIN, WORK, bundle, load_json, save_json)

OUT = WORK / "strings.json"

# Английские бандлы и их немецкие двойники: содержимое берём из первых, писать будем во вторые.
PAIRS = [("strings_eng_main", HOST_STRINGS_MAIN), ("strings_eng", HOST_STRINGS)]

# Таблицы первой игры. Она вне объёма перевода (другой формат скриптов, и её целиком
# покрывает известный фанатский русификатор), поэтому в работу их не берём.
SKIP_PREFIX = ("gk1_",)


def read_tables(bundle_key: str) -> dict[str, dict[int, str]]:
    """Имя таблицы без языкового суффикса -> {m_Id: строка}."""
    env = UnityPy.load(str(bundle(bundle_key)))
    out: dict[str, dict[int, str]] = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        tree = obj.read_typetree()
        name = tree["m_Name"].rsplit("_", 1)[0]
        out[name] = {row["m_Id"]: row["m_Localized"] for row in tree["m_TableData"]}
    return out


def main() -> int:
    previous = (load_json(OUT, default={}) or {}).get("tables", {})

    tables: dict[str, dict] = {}
    for eng_key, host_key in PAIRS:
        eng = read_tables(eng_key)
        host = read_tables(host_key)
        for name, rows in sorted(eng.items()):
            if name.startswith(SKIP_PREFIX):
                continue
            was = previous.get(name, {})
            entries = {}
            for key, english in rows.items():
                old = was.get(str(key))
                keep = bool(old) and old.get("en") == english
                entries[str(key)] = {
                    "en": english,
                    "de": host.get(name, {}).get(key, ""),
                    "ru": old["ru"] if keep else "",
                    "status": old.get("status", "pending") if keep else "pending",
                }
            tables[name] = entries

    save_json(OUT, {"source": "gk2 eng", "tables": tables})

    total = sum(len(v) for v in tables.values())
    done = sum(1 for v in tables.values() for e in v.values() if e["ru"])
    lines = collections.Counter(
        e["en"].count("\n") + 1 for v in tables.values() for e in v.values() if e["en"])

    print(f"таблиц:          {len(tables)}")
    print(f"записей:         {total}")
    print(f"уже переведено:  {done}")
    print(f"строк в записи:  {dict(sorted(lines.items()))}")
    print(f"\n-> {OUT}")
    print("\nкрупнейшие таблицы:")
    for name, rows in sorted(tables.items(), key=lambda kv: -len(kv[1]))[:8]:
        filled = sum(1 for e in rows.values() if e["ru"])
        print(f"   {len(rows):5d}  {filled:5d} готово  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
