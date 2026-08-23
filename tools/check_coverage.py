"""Ни одна запись не остаётся английской молча.

Проверка отвечает на вопрос, на который до 18 августа 2026 не отвечал никто:
**сколько всего текста в игре и куда делся каждый непереведённый кусок.**

Почему она понадобилась. Счётчики проекта считали то, что мы сумели разметить:
`table_keys.py --case N` фильтрует записи по номеру дела в ключе, а у профилей
персонажей (`gk2_castNNN_MM`) номера дела в ключе нет — `case_of_key()` кладёт их
в отдельную корзину «профиль». Обе стороны конвейера спрашивали одну и ту же
функцию, и обе на профилях молчали: `--case 3 --todo` их не показывал,
`check_pipelines.py` пропускал строкой `if not group.startswith("дело "): continue`.
Отчёт «прочие таблицы дела 3 — 139 из 139» был честен относительно своего
знаменателя и при этом скрывал 103 английские записи: имена, возрасты и описания
профилей. Игрок увидел их первым.

Отсюда устройство этой проверки. **Знаменатель — все записи всех таблиц**, и
каждая обязана попасть ровно в одну корзину:

* **переведено** — есть `ru`;
* **исключение** (`ALLOWED`) — переводить нечего или нельзя: имя гарнитуры,
  число, «©CAPCOM», название языка на своём языке. У каждого — причина;
* **отложено** (`DEFERRED`) — решение принято и записано: дела 4 и 5 не начаты,
  по галерее пользователь не выбирал. У каждого — причина и когда закроется;
* **долг** — всё остальное. На долге проверка **валится**.

Третьей корзины «не разметили» не существует: незнакомая запись падает в долг.
Именно это и есть требование пользователя от 18 августа 2026 — английским
в игре остаётся только то, что кто-то сознательно решил оставить английским.

    python tools/check_coverage.py            # сводка и долг
    python tools/check_coverage.py --list     # весь долг поимённо
    python tools/check_coverage.py --deferred # что отложено и почему

Реплики считает `check_pipelines.py`, графику — `swap_localized.py --check`;
здесь — строковые таблицы, тот самый пласт, где дыра и жила.
"""
from __future__ import annotations

import argparse
import collections
import fnmatch

from common import WORK, load_json

# --- Корзина «переводить нечего или нельзя» -------------------------------
# Ключ — шаблон `таблица|человеческий ключ` (fnmatch). Человеческий ключ берётся
# из SharedTableData и, в отличие от m_Id, читается глазами и переживает патчи.
ALLOWED: dict[str, str] = {
    "FontTable|*":
        "имена гарнитур TMP — движок ищет их по имени, перевод сломает шрифт",
    "gk_common_option|optionvalue_0*":
        "цифры и разрешения экрана: «0», «7», «1920 x 1080»",
    "gk_common_option|optionvalue_lang_text_*":
        "названия языков на своём языке — так они и должны выглядеть в меню",
    "gk_common_saveload|nowloading_msg_*":
        "точки анимации загрузки: «.», «..», «...»",
    "gk_common_saveload|saveload_gk*":
        "названия самих игр серии, они и на витрине латиницей",
    "gk_common_gallery|gallery_ui1*":
        "то же название игры в шапке галереи",
    "gk_common_gallery|gallery_ui0[89]":
        "шаблоны подстановки без слов: «{0}%» и «{0}/{1}»",
    "gk_common_title|title_copyright*":
        "«©CAPCOM» — правовая надпись, не переводится",
    "gk_common_title|epselect_dialogue_007":
        "«HD» — пометка издания",
    "gk_common_title|secselect_gk1_ep3_sec2":
        "запись пуста в оригинале, переводить нечего",
    "gk_common_dialog|dialog_021":
        "«...» — многоточие",
    "gk2_common_nametag|gk2_cast21f_02_nt":
        "плашка пуста в оригинале: персонаж в этой версии профиля без имени",
}

# --- Корзина «решено отложить» --------------------------------------------
# Отличие от ALLOWED: это долг, у которого назначен срок. Пока дело не начато,
# английский в его таблицах — не брак, а отставание, и оно видно счётчиком.
DEFERRED: dict[str, str] = {
    "дело 5":
        "дело 5 не начато — закроется вместе с ним, правило №6 (подписи до реплик)",
    "*|gallery_music*":
        "названия музыкальных треков галереи (147) — пользователь не решал, "
        "переводить ли их вообще; вопрос открыт с 18 августа 2026",
    "*|gallery_chara*":
        "имена в галерее персонажей (112) — больше половины из GK1, а GK1 вне "
        "объёма проекта; вопрос открыт с 18 августа 2026",
    "*|gk2_cast20C_00":
        "профиль ждёт названий «Global Studios» и имени Penny Nichols — "
        "материал дела 5, имена выбирает пользователь (правило №4)",
    "*|gk2_cast219_00":
        "профиль ждёт названий «Global Studios» и «Taurusaurus» — "
        "материал дела 5, имена выбирает пользователь (правило №4)",
}


def match(patterns: dict[str, str], table: str, key: str, group: str) -> str | None:
    """Причина, по которой запись законно английская, — или None."""
    for pattern, reason in patterns.items():
        if pattern == group:
            return reason
        if fnmatch.fnmatch(f"{table}|{key}", pattern):
            return reason
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="весь долг поимённо")
    ap.add_argument("--deferred", action="store_true", help="что отложено и почему")
    args = ap.parse_args()

    strings = load_json(WORK / "strings.json")
    if not strings:
        print("нет work/strings.json — сначала tools/extract_strings.py")
        return 1
    tables = strings["tables"]

    keys = load_json(WORK / "table_keys.json")
    if not keys:
        try:
            import table_keys as TK

            keys = {t: {str(i): k for i, k in rows.items()}
                    for t, rows in TK.read_shared().items()}
        except Exception as exc:                  # игры может не быть под рукой
            print(f"ключи таблиц недоступны ({exc}) — проверка пропущена")
            return 0

    import table_keys as TK

    total = ru = 0
    allowed: collections.Counter[str] = collections.Counter()
    deferred: collections.Counter[str] = collections.Counter()
    debt: list[tuple[str, str, str]] = []
    for table, rows in tables.items():
        km = keys.get(table, {})
        for mid, entry in rows.items():
            total += 1
            key = km.get(str(mid), "?")
            if entry.get("ru"):
                ru += 1
                continue
            group = TK.case_of_key(key)
            reason = match(ALLOWED, table, key, group)
            if reason:
                allowed[reason] += 1
                continue
            reason = match(DEFERRED, table, key, group)
            if reason:
                deferred[reason] += 1
                continue
            debt.append((table, key, (entry.get("en") or "").replace("\n", " ")[:48]))

    print(f"записей в таблицах: {total}")
    print(f"  переведено:  {ru}")
    print(f"  исключения:  {sum(allowed.values())}  (переводить нечего или нельзя)")
    print(f"  отложено:    {sum(deferred.values())}  (решение записано, срок назначен)")
    print(f"  ДОЛГ:        {len(debt)}")

    if args.deferred:
        print()
        for reason, n in deferred.most_common():
            print(f"  {n:5d}  {reason}")
        for reason, n in allowed.most_common():
            print(f"  {n:5d}  [исключение] {reason}")

    if debt:
        print()
        shown = debt if args.list else debt[:20]
        for table, key, en in shown:
            print(f"   {table:22s} {key:28s} {en!r}")
        if len(shown) < len(debt):
            print(f"   ... ещё {len(debt) - len(shown)} — с ключом --list")
        print()
        print("Каждая из этих записей уйдёт в игру по-английски, и никто об этом")
        print("не узнает, кроме игрока. Либо перевести, либо вписать в ALLOWED")
        print("или DEFERRED этого файла — с причиной. Третьего не дано.")
        return 1

    print(f"OK — английского по недосмотру нет: {ru} переведено, "
          f"{sum(allowed.values())} исключений, {sum(deferred.values())} отложено "
          f"по записанному решению.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
