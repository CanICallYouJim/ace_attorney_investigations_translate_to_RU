"""Проверить переводы в work/case2.json: длина строк, число строк и сохранность кодов.

Гоняется на каждой итерации перевода — до сборки, чтобы не ловить проблемы уже в игре.
Числа лимитов взяты из замеров, см. docs/limits.md.

    python tools/check_len.py           # только нарушения
    python tools/check_len.py --all     # ещё и сводка по длинам
"""
from __future__ import annotations

import argparse
import collections

from common import load_entries
import tps as T

LINE_SOFT = 50   # рабочий лимит: столько выдержали французы и немцы
LINE_HARD = 53   # жёсткий предел, дальше строка рискует не поместиться
MAX_LINES = 2    # в окне реплики ровно две строки, третьей нет
NARROW_MODE = 7  # узкий режим окна
NARROW_LIMIT = 24

# Один сегмент — не обязательно одно окно: E104 и E106 закрывают окно и открывают
# следующее, после чего счёт строк начинается заново. Ограничение в две строки
# действует на окно, а не на сегмент.
#
# Пара выведена не из общих соображений, а проверена на всех 7402 английских
# сегментах дела: с обоими кодами окон длиннее двух строк ноль, с любым одним
# из них остаются (9 при только E106, 26 при только E104).
WINDOW_BREAKS = {0xE104, 0xE106}


DEMO_PLACEHOLDER = "DEMO TEXT"


def is_demo_placeholder(entry) -> bool:
    """Заглушка сборки, которую западные локализации не переводили.

    В деле 1 семьдесят один сегмент содержит ровно ``DEMO TEXT``. Это не
    недосмотр переводчиков: у японцев, корейцев и китайцев там настоящая
    реплика, а **английская, французская и немецкая** версии все три
    оставили заглушку — проверено ``tools/polyglot.py``. Русский занимает
    немецкий слот, то есть игрок увидит ровно то же, что видят игроки
    остальных западных версий.

    Поэтому такие сегменты — записанное решение «оставить как есть»
    (правило №7 в CLAUDE.md), а не долг. Исключение адресное: оно
    срабатывает, только когда и оригинал, и перевод — в точности эта
    строка. Разбор — docs/decisions.md, раздел про DEMO TEXT.
    """
    return (plain_text(entry["en"]).strip() == DEMO_PLACEHOLDER
            and plain_text(entry["ru"]).strip() == DEMO_PLACEHOLDER)


def plain_text(markup: str) -> str:
    """Только видимый текст: коды и их параметры выбрасываются."""
    return "".join(t for t in T.from_markup(markup) if isinstance(t, str))


MODE_OP = 0xE107  # смена режима окна прямо посреди реплики


def windows(markup: str, start_mode: int | None) -> list[list[tuple[str, int | None]]]:
    """Окна реплики; каждое — список строк вместе с режимом, в котором строка рисуется.

    Режим меняется кодом E107 по ходу реплики, и это не мелочь: узкое окно (режим 7)
    почти всегда переключается на обычное сразу после многоточия, так что узкий лимит
    действует лишь на само многоточие, а не на всю реплику.
    """
    mode = start_mode
    line = ""
    wins: list[list[tuple[str, int | None]]] = [[]]
    for tok in T.from_markup(markup):
        if isinstance(tok, T.Op):
            if tok.code == MODE_OP and len(tok.params) == 1:
                mode = ord(tok.params[0])
            elif tok.code in WINDOW_BREAKS:
                wins[-1].append((line, mode))
                line = ""
                wins.append([])
        else:
            for ch in tok:
                if ch == "\n":
                    wins[-1].append((line, mode))
                    line = ""
                else:
                    line += ch
    wins[-1].append((line, mode))
    return wins


def opcodes_of(markup: str) -> collections.Counter:
    return collections.Counter(
        (t.code, t.params) for t in T.from_markup(markup) if isinstance(t, T.Op))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="показать сводку по длинам")
    args = ap.parse_args()

    entries = load_entries()
    if not entries:
        print("нет work/case*.json — сначала tools/extract.py")
        return 1

    translated = [e for e in entries if e.get("ru")]
    if not translated:
        print("переводов пока нет")
        return 0

    problems: list[str] = []
    lengths: list[int] = []

    for entry in translated:
        try:
            ru_tokens = T.from_markup(entry["ru"])
        except Exception as exc:
            problems.append(f"{entry['id']}: разметка не разобралась — {exc}")
            continue

        # 1. управляющие коды должны сохраниться (порядок может меняться, набор — нет)
        lost = opcodes_of(entry["en"]) - opcodes_of(entry["ru"])
        added = opcodes_of(entry["ru"]) - opcodes_of(entry["en"])
        if lost:
            codes = ", ".join(f"{c:04X}" for c, _p in list(lost)[:4])
            problems.append(f"{entry['id']}: потеряны коды {codes}")
        if added:
            codes = ", ".join(f"{c:04X}" for c, _p in list(added)[:4])
            problems.append(f"{entry['id']}: появились лишние коды {codes}")

        # 2. текст должен быть русским, а не забытым английским
        text = plain_text(entry["ru"])
        if text.strip() and not any("а" <= c.lower() <= "я" or c == "ё" for c in text):
            if not is_demo_placeholder(entry):
                problems.append(f"{entry['id']}: в переводе нет кириллицы — {text[:50]!r}")

        # 3. геометрия — считаем по каждому окну и с учётом смены режима по ходу реплики
        for win_no, window in enumerate(windows(entry["ru"], entry.get("mode")), 1):
            if len(window) > MAX_LINES:
                where = f" (окно {win_no})" if win_no > 1 else ""
                problems.append(
                    f"{entry['id']}: {len(window)} строк{where}, в окно влезает {MAX_LINES}")
            for line, mode in window:
                limit = NARROW_LIMIT if mode == NARROW_MODE else LINE_HARD
                lengths.append(len(line))
                if len(line) > limit:
                    problems.append(
                        f"{entry['id']}: строка {len(line)} символов (предел {limit}"
                        f"{', узкое окно' if mode == NARROW_MODE else ''}) — {line[:60]!r}")

    print(f"переведено сегментов: {len(translated)} из {len(entries)}")
    if args.all and lengths:
        over_soft = sum(1 for n in lengths if n > LINE_SOFT)
        lengths.sort()
        print(f"строк: {len(lengths)}  медиана={lengths[len(lengths)//2]}  "
              f"max={lengths[-1]}  длиннее {LINE_SOFT}: {over_soft}")

    if problems:
        print(f"\nнарушений: {len(problems)}")
        for line in problems[:30]:
            print("  ", line)
        return 1

    print("OK — коды сохранены, кириллица на месте, в окно всё влезает.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
