"""Приёмочный тест парсера ` TPS`: разбор и сборка обязаны давать байт-в-байт исходник.

Гоняется по всем скриптовым файлам GK2 на всех семи языках — 2847 файлов, включая
японский, корейский и китайский, то есть весь диапазон длин и наборов символов.

GK1 сюда не входит осознанно: у первой игры скрипты в другом формате (не ` TPS`),
и в задачу перевода дела 2 из GK2 она не входит.

    python tools/test_tps.py
"""
from __future__ import annotations

import sys
from collections import Counter

from common import SCRIPT_LANGS, read_scripts
import tps as T


def main() -> int:
    total = failed_parse = failed_rt = 0
    rec_sizes: Counter[int] = Counter()
    problems: list[str] = []

    for lang in SCRIPT_LANGS:
        files = read_scripts(f"script_{lang}")
        for name, raw in sorted(files.items()):
            total += 1
            try:
                parsed = T.parse(raw)
            except T.TpsError as exc:
                failed_parse += 1
                problems.append(f"{lang}/{name}: разбор — {exc}")
                continue
            rec_sizes[parsed.record_size] += 1
            if T.build(parsed) != raw:
                failed_rt += 1
                problems.append(f"{lang}/{name}: round-trip не совпал")
        print(f"  gk2/{lang}: {len(files)} файлов")

    print(f"\nвсего файлов:        {total}")
    print(f"ошибок разбора:      {failed_parse}")
    print(f"ошибок round-trip:   {failed_rt}")
    print(f"ширина записи:       {dict(rec_sizes)}")

    if problems:
        print("\nпроблемы (первые 20):")
        for line in problems[:20]:
            print("  ", line)
        return 1

    print("\nOK — разбор и сборка обратимы на всём корпусе.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
