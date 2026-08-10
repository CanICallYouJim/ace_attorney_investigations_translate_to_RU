"""Проверка: адрес сегмента в polyglot.py означает то же, что в work/caseN.json.

Правило №3 («непонятное место — сперва в другие локализации») стоит на том, что
`polyglot.py "файл|БЛОК|индекс"` показывает **ту самую** реплику, которую мы
переводим. 11 августа 2026 выяснилось, что не показывает: `block_segments`
выбрасывала сегменты без текста, список схлопывался, и индекс уезжал на число
пустых перед ним. В `sce1_c2_06|01001FB0` запрос 32 отдавал реплику 33.

Ошибка тихая — расхождение видно, только если знать оригинал наизусть. Поэтому
проверка сплошная: английский текст из polyglot должен совпасть с полем `en`
того же адреса по всем делам.

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe tools/test_polyglot_index.py
"""
from __future__ import annotations

import collections
import sys

from common import load_entries, read_scripts
from polyglot import resolve


def check(case: int, eng: dict[str, bytes]) -> tuple[int, list[str]]:
    # Метку берём из id, а не из поля block: суффикс повтора «#2» живёт только
    # в id, и без него адрес указывает на первый блок метки.
    by_block: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for e in load_entries(case):
        name, label_spec, _idx = e["id"].split("|")
        by_block[(name, label_spec)].append(e)

    checked, bad = 0, []
    for (name, label_spec), entries in sorted(by_block.items()):
        raw = eng.get(name.lower())
        if raw is None:
            bad.append(f"{name}: файла нет в script_eng")
            continue
        for e in entries:
            idx = e["index"]
            segs = resolve(raw, label_spec, idx)
            if segs is None:
                bad.append(f"{e['id']}: блока нет")
                continue
            got = segs[idx] if 0 <= idx < len(segs) else None
            if got is None:
                bad.append(f"{e['id']}: polyglot молчит, а сегмент есть")
                continue
            if got != e["en"]:
                bad.append(f"{e['id']}:\n     case:     {e['en']!r}\n     polyglot: {got!r}")
            checked += 1
    return checked, bad


def main() -> int:
    eng = read_scripts("script_eng")
    total, failures = 0, []
    for case in (2, 3):
        try:
            checked, bad = check(case, eng)
        except FileNotFoundError:
            print(f"дело {case}: work/case{case}.json не найден, пропущено")
            continue
        print(f"дело {case}: сверено адресов {checked}, расхождений {len(bad)}")
        total += checked
        failures += bad

    if failures:
        print(f"\nРАСХОЖДЕНИЯ ({len(failures)}), первые 10:")
        for line in failures[:10]:
            print("  " + line)
        return 1
    print(f"\nOK — все {total} адресов означают в polyglot.py то же, что в caseN.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
