"""Перепись всего текста игры: где он лежит и что из этого мы переводим.

Отвечает на вопрос «а не забыли ли мы ещё какой-нибудь склад текста». Пока
непереведённые куски находились по одному — когда игрок на них натыкался.
Этот скрипт проходит по **всем** бандлам игры и раскладывает найденное
по трём корзинам:

* **наше** — покрыто конвейером (скрипты дел, строковые таблицы слота-носителя);
* **исходники** — тот же текст на других языках, трогать не надо;
* **не покрыто** — вот на это и надо смотреть.

    python tools/audit_text.py            # сводка
    python tools/audit_text.py --details  # + перечень объектов внутри бандлов
    python tools/audit_text.py --md       # готовый кусок для docs/

Скрипт **только читает** игру, ничего не пишет.
"""
from __future__ import annotations

import argparse
import collections
import re

from common import (BUNDLES, CASES, HOST, SCRIPT_LANGS, STRING_TABLE_PREFIXES,
                    load_entries, WORK, load_json)

# Что уже покрыто конвейерами. Ключ — по какому куску имени бандла узнаём.
COVERED_SCRIPTS = f"gk2_scriptmessage_{HOST}_"
COVERED_TABLES = (f"{STRING_TABLE_PREFIXES[HOST]}_assets_all_",
                  f"{STRING_TABLE_PREFIXES[HOST]}_trial_assets_all_")

# Тот же текст на других языках — источники, не работа.
OTHER_LANG = tuple(f"{kind}_{lang}_" for kind in ("gk2_scriptmessage", "gk1_scriptmessage")
                   for lang in SCRIPT_LANGS if lang != HOST)
OTHER_TABLES = tuple(p + "_" for lang, p in STRING_TABLE_PREFIXES.items() if lang != HOST)

# Первая игра — решение пользователя от 9 августа 2026: в объём перевода не входит.
GK1 = ("gk1_",)


def classify(name: str) -> str:
    low = name.lower()
    if low.startswith(COVERED_SCRIPTS):
        return "наше: скрипты"
    if any(low.startswith(p.lower()) for p in COVERED_TABLES):
        return "наше: строковые таблицы"
    if any(p.lower() in low for p in OTHER_LANG) or any(low.startswith(p.lower()) for p in OTHER_TABLES):
        return "исходники: другие языки"
    if low.startswith(GK1):
        return "вне объёма: первая игра"
    return "не покрыто"


def scan_bundle(path):
    """Что за объекты с текстом лежат в бандле: тип -> сколько, плюс примеры."""
    import UnityPy

    env = UnityPy.load(str(path))
    kinds = collections.Counter()
    samples = []
    for obj in env.objects:
        t = obj.type.name
        if t not in ("TextAsset", "MonoBehaviour"):
            continue
        try:
            data = obj.read()
        except Exception:
            continue
        if t == "TextAsset":
            kinds["TextAsset"] += 1
            if len(samples) < 3:
                samples.append(getattr(data, "m_Name", "?"))
        else:
            # Строковые таблицы — это MonoBehaviour с m_TableData.
            try:
                tree = obj.read_typetree()
            except Exception:
                continue
            if "m_TableData" in tree:
                kinds["StringTable"] += 1
                if len(samples) < 3:
                    samples.append(f"{tree.get('m_TableCollectionName','?')} ({len(tree['m_TableData'])})")
    return kinds, samples


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--details", action="store_true", help="перечислить объекты внутри бандлов")
    ap.add_argument("--md", action="store_true", help="вывести таблицей для документации")
    args = ap.parse_args()

    bundles = sorted(BUNDLES.glob("*.bundle"))
    print(f"бандлов в игре: {len(bundles)}\n")

    groups: dict[str, list] = collections.defaultdict(list)
    for path in bundles:
        groups[classify(path.name)].append(path)

    order = ["наше: скрипты", "наше: строковые таблицы", "не покрыто",
             "исходники: другие языки", "вне объёма: первая игра"]
    for key in order:
        paths = groups.get(key, [])
        if not paths:
            continue
        print(f"=== {key}: {len(paths)} бандлов")
        if key == "не покрыто" or args.details:
            for path in paths:
                kinds, samples = scan_bundle(path)
                if not kinds:
                    continue
                short = re.sub(r"_[0-9a-f]{32}\.bundle$", "", path.name)
                what = ", ".join(f"{k}×{v}" for k, v in kinds.items())
                print(f"    {short:60s} {what}")
                if samples:
                    print(f"        {', '.join(str(s) for s in samples)}")
        print()

    # Сколько текста в наших двух конвейерах и сколько переведено.
    print("=== покрытие переводом")
    for case in CASES:
        entries = load_entries(case)
        done = sum(1 for e in entries if e.get("ru"))
        print(f"    дело {case}: {done}/{len(entries)} сегментов скриптов")
    strings = load_json(WORK / "strings.json")
    if strings:
        for tn, table in strings["tables"].items():
            done = sum(1 for v in table.values() if v.get("ru"))
            if done < len(table):
                print(f"    {tn:24s} {done}/{len(table)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
