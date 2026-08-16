"""Не разошлись ли два конвейера: реплики дела переведены, а его подписи нет.

Текст дела живёт в двух хранилищах сразу, и переводятся они по отдельности:
реплики — `work/case{N}.json`, названия улик, профили и карточки логики —
`work/strings.json`. Пока первое уходит вперёд второго, игрок видит русскую
реплику и английскую улику в органайзере **в одном и том же деле**.

Хуже, чем просто «недоделано»: название улики лежит **в двух местах**.
В таблице — то, что видно в органайзере, а в скрипте — уведомление
«Salt Lamp added to the Court Record», обычный сегмент, который переводчик
реплик переводит заодно. Разошлись хранилища — и игра называет одну вещь
двумя именами.

Отсюда правило проекта (пользователь, 17 августа 2026): **подписи дела
переводятся до его реплик** — названия улик, имена и возрасты профилей,
плашка говорящего, ключевые слова логики. Описания, кнопки и врезки можно
по ходу, но до того, как дело объявлено готовым.

Проверка мягкая по построению: она **показывает** разрыв всегда и **валится**
только когда реплики дела переведены целиком, а таблицы — нет. Иначе она
блокировала бы установку у сессии, которая как раз переводит дело в середине.

    python tools/check_pipelines.py

Принадлежность записи делу берётся из ключей `SharedTableData` — см.
`tools/table_keys.py`. Кеш `work/table_keys.json` подхватывается, если он есть;
без него ключи читаются из игры.
"""
from __future__ import annotations

import collections

import re

from common import CASES, COMMON_CASE, WORK, load_entries, load_json

# Что считаем «подписями»: короткие строки, которые дублируются внутри реплик
# и потому обязаны быть переведены раньше их.
LABEL_TABLES = ("gk2_item_name", "gk2_logic_name", "gk2_logic_button")

# Уведомление органайзера — то самое место, где имя улики стоит в реплике
# в рамке: «X data jotted down in my Organizer» -> «Данные «X» записаны
# в органайзер». Кавычки-ёлочки в переводе позволяют сверить имя дословно.
VERB = r"(?:jotted down|recorded|updated|added)"
NOTIFY = re.compile(rf"{VERB}\s+(?:in|to)\s+(?:the\s+|your\s+|my\s+)?(?:Organizer|Court Record)",
                    re.I)
NAME_IN_EN = re.compile(rf"^(.*?)\s+(?:data\s+)?{VERB}\s")
CODE = re.compile(r"\{[0-9A-Fa-f]{4}(?::[0-9A-Fa-f]+)?\}")


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", CODE.sub("", text or "").replace("\n", " ")).strip()


def notify_mismatches(case: int, keys: dict, tables: dict) -> list[str]:
    """Имя улики в уведомлении обязано совпасть с её именем в таблице.

    Именно здесь два хранилища встречаются на одном экране: игра говорит
    «Данные «Рубильники» записаны в органайзер», игрок открывает органайзер —
    а там «Электрощит». Такое расхождение жило в деле 2 в четырёх уликах.
    """
    km = keys.get("gk2_item_name", {})
    items = {(v.get("en") or "").strip(): (v.get("ru") or "").strip()
             for mid, v in tables["gk2_item_name"].items()
             if re.match(rf"^gk2_itm{case-1:02d}_", km.get(int(mid), ""))}
    out = []
    for seg in load_entries(case):
        en = flat(seg["en"])
        if not NOTIFY.search(en) or not seg.get("ru"):
            continue
        m = NAME_IN_EN.match(en)
        name = m.group(1).strip() if m else ""
        table = items.get(name)
        if not table:                       # улика не переведена — это уже видно счётчиком
            continue
        quoted = re.findall(r"«(.+?)»", flat(seg["ru"]))
        if quoted and quoted[0] != table:
            out.append(f"дело {case}: «{name}» — в органайзере «{table}», "
                       f"в реплике «{quoted[0]}» ({seg['file']}|{seg['block']}|{seg['index']})")
    return out


def plural(n: int, one: str, few: str, many: str) -> str:
    """«91 подпись», а не «91 подписей» — счётчик читает человек."""
    if n % 100 // 10 == 1:
        return many
    return {1: one, 2: few, 3: few, 4: few}.get(n % 10, many)


def table_keys() -> dict[str, dict[int, str]]:
    cached = load_json(WORK / "table_keys.json")
    if cached:
        return {t: {int(i): k for i, k in rows.items()} for t, rows in cached.items()}
    import table_keys as TK

    return TK.read_shared()


def main() -> int:
    strings = load_json(WORK / "strings.json")
    if not strings:
        print("нет work/strings.json — сначала tools/extract_strings.py")
        return 1
    tables = strings["tables"]

    try:
        keys = table_keys()
    except Exception as exc:                      # игры может не быть под рукой
        print(f"ключи таблиц недоступны ({exc}) — проверка пропущена")
        return 0

    import table_keys as TK

    # дело -> {"подписи": [всего, переведено], "прочее": [...]}
    per = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    for table, rows in tables.items():
        if not table.startswith("gk2_"):
            continue
        km = keys.get(table, {})
        kind = "подписи" if table in LABEL_TABLES else "прочее"
        for mid, entry in rows.items():
            group = TK.case_of_key(km.get(int(mid), "?"))
            if not group.startswith("дело "):
                continue                          # профили делом не размечены
            cell = per[int(group.split()[1])][kind]
            cell[0] += 1
            cell[1] += 1 if entry.get("ru") else 0

    print(f"{'дело':>5} {'реплики':>16} {'подписи':>14} {'прочие таблицы':>16}")
    broken: list[str] = []
    # Отставание не валит прогон, но обязано быть видно: check_all.py показывает
    # последнюю строку проверки, поэтому она и несёт сводку, а не голое «ОК».
    lagging: list[str] = []
    for case in CASES:
        if case == COMMON_CASE:
            continue                              # у псевдодела 0 записей в таблицах нет
        entries = load_entries(case)
        if not entries:
            continue
        done = sum(1 for e in entries if e.get("ru"))
        lab_n, lab_ru = per[case]["подписи"]
        oth_n, oth_ru = per[case]["прочее"]
        pct = 100 * done / len(entries)
        print(f"{case:>5} {done:>7}/{len(entries):<5} {pct:3.0f}%"
              f" {lab_ru:>6}/{lab_n:<5} {oth_ru:>7}/{oth_n:<5}")

        broken += notify_mismatches(case, keys, tables)

        if done == len(entries) and (lab_ru < lab_n or oth_ru < oth_n):
            broken.append(f"дело {case}: реплики переведены целиком, "
                          f"а таблицы нет — подписи {lab_ru} из {lab_n}, "
                          f"прочее {oth_ru} из {oth_n}")
        elif lab_n and lab_ru < lab_n and done:
            behind = lab_n - lab_ru
            print(f"        ⚠ подписи отстают от реплик: {behind} "
                  f"{plural(behind, 'запись', 'записи', 'записей')} "
                  f"(названия улик и карточки логики) ещё английские")
            lagging.append(f"дело {case} — {behind} "
                           f"{plural(behind, 'подпись', 'подписи', 'подписей')}")

    if broken:
        print()
        for line in broken:
            print("  ", line)
        print("Дело считается готовым, только когда закрыты оба хранилища:")
        print("  tools/table_keys.py --case N --todo покажет, чего не хватает.")
        return 1

    if lagging:
        print(f"OK — законченные дела закрыты в обоих хранилищах; "
              f"подписи отстают: {', '.join(lagging)}.")
    else:
        print("OK — конвейеры не разошлись: там, где реплики закончены, таблицы тоже.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
