"""Проверить переводы строковых таблиц в work/strings.json.

Парная проверка к check_len.py, но лимиты тут другие и на глаз не берутся: у каждой
таблицы своё окно. Описание улики — это не реплика: в окне реплики строго две строки,
а в описании их до пяти.

Поэтому лимиты не зашиты числами, а **замеряются по самой игре** — по английским и
немецким значениям той же таблицы. Немецкий тут главный ориентир, как и для реплик:
у него та же беда с длиной, что у русского, и немцы уже уложились.

    python tools/check_strings.py         # только нарушения
    python tools/check_strings.py --all   # ещё и замеренные лимиты по таблицам
"""
from __future__ import annotations

import argparse
import collections
import re

from common import WORK, load_json

# Запас к замеренному максимуму: у кириллицы своя ширина букв, впритык идти незачем.
SLACK_CHARS = 0

# Подстановки движка: `{0}`, `{1}`. Потеря — дыра в тексте прямо в игре,
# лишняя — исключение форматирования. Набор обязан совпасть с английским.
PLACEHOLDER = re.compile(r"\{\d+\}")

# Разметка TMP: <color="orange">, <size=90%>, <align="center">, <font=...>.
# Проверяем по именам тегов, а не по всей строке: значения атрибутов мы не меняем,
# но открывающий и закрывающий теги обязаны остаться в том же количестве.
TAG = re.compile(r"</?([a-zA-Z]+)")
MARKUP = re.compile(r"<[^<>]+>")

# Записи, где кириллицы быть и не должно. Формат даты в списке сохранений —
# не проза, а шаблон для движка: американское MM/dd меняем на dd.MM, и всё.
# Профиль `gk2_cast21a_00` — неопознанный персонаж: и имя, и плашка в игре
# «???» во всех семи локализациях, переводить там нечего, но и оставлять
# запись непереведённой нельзя — иначе она уйдёт в долг покрытия.
NO_CYRILLIC_OK = {"gk_common_saveload 13325396588036096",
                  "gk2_common_nametag 114549870598",
                  "gk2_item_name 312786076061697"}


def visible(text: str) -> str:
    """Текст без разметки — только то, что реально занимает место в окне.

    Без этого `<font="FOT-MODEMINALARGEPRO-B SDF" material="...">Настройки</font>`
    числится строкой в 96 символов, хотя на экране их девять.
    """
    return MARKUP.sub("", text)


def measured_limits(rows: dict) -> tuple[int, int]:
    """(строк, символов в строке) — максимум по английскому и немецкому значениям."""
    lines = chars = 0
    for entry in rows.values():
        for lang in ("en", "de"):
            text = entry.get(lang) or ""
            if not text:
                continue
            parts = visible(text).split("\n")
            lines = max(lines, len(parts))
            chars = max(chars, max(len(p) for p in parts))
    return lines, chars


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="показать замеренные лимиты")
    args = ap.parse_args()

    data = load_json(WORK / "strings.json")
    if not data:
        print("нет work/strings.json — сначала tools/extract_strings.py")
        return 1

    problems: list[str] = []
    translated = 0
    report: list[tuple[str, int, int, int]] = []

    for table, rows in sorted(data["tables"].items()):
        max_lines, max_chars = measured_limits(rows)
        done = 0
        for key, entry in rows.items():
            ru = entry.get("ru")
            if not ru:
                continue
            done += 1
            translated += 1

            if (not any("а" <= c.lower() <= "я" or c == "ё" for c in ru)
                    and f"{table} {key}" not in NO_CYRILLIC_OK):
                problems.append(f"{table} {key}: в переводе нет кириллицы — {ru[:40]!r}")

            # Теги шрифта в интерфейсе несут гарнитуру, потерять их нельзя.
            if entry["en"].count("<font") != ru.count("<font"):
                problems.append(f"{table} {key}: потерян тег <font> — {ru[:40]!r}")

            # Подстановки движка и остальная разметка TMP — набор обязан совпасть.
            want, got = (sorted(PLACEHOLDER.findall(entry["en"])),
                         sorted(PLACEHOLDER.findall(ru)))
            if want != got:
                problems.append(
                    f"{table} {key}: подстановки {got} вместо {want} — {ru[:40]!r}")

            want_tags = collections.Counter(TAG.findall(entry["en"]))
            got_tags = collections.Counter(TAG.findall(ru))
            if want_tags != got_tags:
                lost = sorted((want_tags - got_tags).elements())
                extra = sorted((got_tags - want_tags).elements())
                problems.append(
                    f"{table} {key}: теги потеряны {lost}, лишние {extra} — {ru[:40]!r}")

            parts = visible(ru).split("\n")
            if len(parts) > max_lines:
                problems.append(
                    f"{table} {key}: {len(parts)} строк, в игре максимум {max_lines}")
            for part in parts:
                if len(part) > max_chars + SLACK_CHARS:
                    problems.append(
                        f"{table} {key}: строка {len(part)} символов "
                        f"(в игре максимум {max_chars}) — {part[:50]!r}")
        report.append((table, max_lines, max_chars, done))

    print(f"переведено записей: {translated} из "
          f"{sum(len(r) for r in data['tables'].values())}")

    if args.all:
        print(f"\n{'таблица':22} {'строк':>6} {'символов':>9} {'переведено':>11}")
        for table, ml, mc, done in report:
            print(f"{table:22} {ml:6d} {mc:9d} {done:11d}")

    if problems:
        print(f"\nнарушений: {len(problems)}")
        for line in problems[:30]:
            print("  ", line)
        return 1

    print("OK — влезает в окна, кириллица на месте, теги шрифта целы.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
