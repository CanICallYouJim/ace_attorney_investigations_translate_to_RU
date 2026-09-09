"""Решение, записанное в decisions.md, должно быть применено **везде**.

Запись в [`docs/decisions.md`](../docs/decisions.md) звучит как «было «X» →
стало «Y»», и легко решить, что на этом дело закрыто. Но одна и та же
английская реплика встречается в разных делах, а правка уходит только в то,
над которым работали.

Так и вышло 3 сентября 2026 с разбором вычурности: `That's quite a talent...`
переведено «Недюжинный талант...», сверено по семи локализациям, решение
записано таблицей — **и применено только к делу 1**. В деле 2 та же реплика
прожила с вычурным вариантом ещё неделю, хотя строка про неё лежала
в `decisions.md` и даже цитировалась в `CLAUDE.md` как образцовый пример
ошибки. Нашлось это сплошным чтением, а не проверкой.

Класс шире одного случая: «Весьма любезно» из того же разбора осталось
в делах 2 и 4.

Что делает: берёт из `decisions.md` пары «отвергнуто → принято» и ищет
отвергнутый вариант в переводе. Нашёл — **валится**: решение уже принято,
спорить не о чем, надо применить.

Откуда берутся пары:

* **таблицы** — строка вида `| «Отвергнутое» | ... | ... → **«Принятое»** |`.
  Форма надёжная, разбирается механически;
* **`EXTRA`** — решения, чей формат машиной не читается. Добавлять сюда
  руками вместе со строкой в `decisions.md`.

Ложное срабатывание (отвергнутый вариант законен в другом месте) заносится
в `EXCEPT` **с причиной** — как в `check_gender.py`.

    python tools/check_decisions.py          # только нарушения, для check_all
    python tools/check_decisions.py --list   # все разобранные пары, глазами
"""
from __future__ import annotations

import argparse
import re

from common import CASES, DOCS, case_json, load_json

QUOTED = r"«([^»]{2,90})»"

# Решения, чья запись в decisions.md машиной не читается. Строка сюда —
# только вместе со строкой в docs/decisions.md, иначе через месяц исключение
# уже не отличить от выдумки.
EXTRA: dict[str, str] = {}

# Отвергнутый вариант, который в конкретном месте законен. Ключ — адрес
# сегмента, значение — причина.
EXCEPT: dict[str, str] = {}


def pairs_from_tables(text: str) -> list[tuple[str, str, int]]:
    """Пары «отвергнуто → принято» из табличных строк decisions.md.

    Надёжный признак: первая ячейка — русская цитата в ёлочках, где-то дальше
    в той же строке — `→ **«принято»**`. Так записан разбор вычурности
    от 3 сентября 2026, и так же стоит записывать дальше.
    """
    out = []
    for num, line in enumerate(text.split("\n"), 1):
        if not line.startswith("|"):
            continue
        accepted = re.search(r"\*\*" + QUOTED + r"\*\*", line)
        if not accepted:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rejected = re.search(QUOTED, cells[0]) if cells else None
        if rejected and rejected.group(1) != accepted.group(1):
            out.append((rejected.group(1), accepted.group(1), num))
    return out


def strip_codes(ru: str) -> str:
    """Текст без управляющих кодов и переносов: сравниваем слова, а не разметку."""
    return re.sub(r"\s+", " ", re.sub(r"\{[^}]*\}", "", ru)).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="показать все разобранные пары")
    args = ap.parse_args()

    text = (DOCS / "decisions.md").read_text(encoding="utf-8")
    pairs = pairs_from_tables(text)
    for rejected, accepted in EXTRA.items():
        pairs.append((rejected, accepted, 0))

    if args.list:
        print(f"пар «отвергнуто → принято»: {len(pairs)}")
        for rejected, accepted, num in pairs:
            where = f"decisions.md:{num}" if num else "EXTRA"
            print(f"   «{rejected}»\n   → «{accepted}»   ({where})")
        print()

    # Ищем отвергнутое во всех делах разом.
    bad: list[tuple[str, str, str, str]] = []
    checked = 0
    for case in CASES:
        data = load_json(case_json(case))
        if not data:
            continue
        for it in data["entries"]:
            ru = strip_codes(it.get("ru") or "")
            if not ru:
                continue
            checked += 1
            for rejected, accepted, _ in pairs:
                if rejected in ru and accepted not in ru:
                    if it["id"] in EXCEPT:
                        continue
                    bad.append((it["id"], rejected, accepted, ru))

    print(f"   решений разобрано: {len(pairs)}, сегментов сверено: {checked}, "
          f"исключений {len(EXCEPT)}")
    if not bad:
        print("   OK — принятые решения применены везде.")
        return 0

    for sid, rejected, accepted, ru in bad:
        print(f"   {sid}")
        print(f"       осталось «{rejected}», решением принято «{accepted}»")
        print(f"       реплика: {ru[:90]}")
    print(f"   РАСХОЖДЕНИЙ: {len(bad)} — решение принято, надо применить; "
          f"место, где старый вариант законен, — в EXCEPT с причиной")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
