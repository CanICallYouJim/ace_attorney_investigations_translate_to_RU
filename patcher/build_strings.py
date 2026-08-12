"""Собрать строковые таблицы русского слота: имена в плашке, улики, профили, интерфейс.

Второй конвейер, парный к build.py. Тот собирает сюжетные реплики из скриптов,
этот — строковые таблицы: `gk2_common_nametag` (имя в плашке говорящего),
`gk2_item_name` и `gk2_item_text` (названия и описания улик, а также профили
персонажей — отдельной таблицы у них нет), логика, варианты ответа, интерфейс.

Принцип тот же, что у build.py, и он важен: **содержимое берётся из английских
таблиц**, поверх кладётся русский перевод из work/strings.json. Всё непереведённое
уезжает в слот английским, а не немецким — немецкий русскому игроку бесполезен.
Таблицы первой игры тоже переписываются английскими, хотя мы их не переводим.

Русский текст, как и в скриптах, пишется кодами-носителями (tools/carriers.py):
на родных кодах 16 букв сидит письменность Борджинии, отобрать их нельзя,
см. docs/font-atlas.md.

    python tools/build_strings.py            # собрать в work/build/, игру не трогать
    python tools/build_strings.py --install  # собрать и установить (игра должна быть закрыта)
"""
from __future__ import annotations

import argparse
import shutil
import sys

import UnityPy

from bundle_io import write_string_tables
import carriers as C
from common import (HOST_STRINGS, HOST_STRINGS_MAIN, WORK, bundle, game_is_running,
                    load_json, sha256)
from extract_strings import PAIRS, read_tables

STAGE = WORK / "build"


def plan(translations: dict) -> dict[str, dict[str, dict[int, str]]]:
    """Что положить в каждый бандл: {логическое имя бандла: {таблица: {id: значение}}}.

    Значение — русское, если оно есть в work/strings.json, иначе английское.
    """
    carriers = C.chosen_map()
    out: dict[str, dict[str, dict[int, str]]] = {}

    for eng_key, host_key in PAIRS:
        english = read_tables(eng_key)
        per_table: dict[str, dict[int, str]] = {}
        for name, rows in english.items():
            ru_rows = translations.get(name, {})
            values: dict[int, str] = {}
            for key, text in rows.items():
                ru = (ru_rows.get(str(key)) or {}).get("ru")
                values[key] = C.encode(ru, carriers) if ru else text
            per_table[name] = values
        out[host_key] = per_table
    return out


def count_russian(translations: dict) -> tuple[int, int]:
    total = sum(len(v) for v in translations.values())
    done = sum(1 for v in translations.values() for e in v.values() if e.get("ru"))
    return done, total


def verify(built, host_key: str, translations: dict, table_names) -> list[str]:
    """Перечитать собранный бандл и сверить с тем, что заказывали.

    Сверяем именно обратным раскодированием носителей: так проверяется и то, что
    строка доехала, и что подмена букв обратима.
    """
    problems: list[str] = []
    env = UnityPy.load(str(built))
    carriers = C.chosen_map()
    expected = sum(1 for t in table_names
                   for e in translations.get(t, {}).values() if e.get("ru"))
    seen = 0
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        tree = obj.read_typetree()
        name = tree["m_Name"].rsplit("_", 1)[0]
        got = {r["m_Id"]: r["m_Localized"] for r in tree["m_TableData"]}
        for key, entry in translations.get(name, {}).items():
            if not entry.get("ru"):
                continue
            seen += 1
            back = C.decode(got.get(int(key), ""), carriers)
            if back != entry["ru"]:
                problems.append(f"{name} {key}: в бандле {back!r}, ожидали {entry['ru']!r}")
    if expected and seen != expected:
        problems.append(f"{host_key}: до бандла доехало {seen} строк из {expected}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--install", action="store_true", help="установить собранные бандлы в игру")
    args = ap.parse_args()

    data = load_json(WORK / "strings.json")
    if not data:
        print("нет work/strings.json — сначала tools/extract_strings.py", file=sys.stderr)
        return 1
    translations = data["tables"]

    done, total = count_russian(translations)
    print(f"переведено записей:   {done} из {total}")

    todo = plan(translations)
    outputs: list[tuple[str, object]] = []
    problems: list[str] = []

    for host_key, per_table in todo.items():
        src = bundle(host_key)
        out = STAGE / src.name
        tables, rows, size = write_string_tables(src, per_table, out)
        print(f"{host_key:18} таблиц {tables:3d}, строк переписано {rows:5d}, {size:,} байт")
        problems += verify(out, host_key, translations, per_table)
        outputs.append((host_key, out))

    if problems:
        print(f"\nпроблемы ({len(problems)}):", file=sys.stderr)
        for line in problems[:10]:
            print("  ", line, file=sys.stderr)
        return 1

    print("\nOK — перевод в бандлах читается обратно, непереведённое английское.")

    if not args.install:
        print("\n(это черновая сборка; для установки в игру запусти с --install)")
        return 0

    if game_is_running():
        print("\nGK12.exe запущен — закрой игру, файлы бандла заблокированы.", file=sys.stderr)
        return 1

    for host_key, out in outputs:
        dst = bundle(host_key)
        shutil.copy2(out, dst)
        print(f"установлено: {dst.name}  SHA-256 {sha256(dst)[:16]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
