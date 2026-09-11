# -*- coding: utf-8 -*-
"""Одна и та же служебная реплика обязана звучать одинаково во всех местах.

Два класса, оба найдены ретро-проходом 11 сентября 2026 — и оба прошлые правки
чинили не до конца, потому что видели две копии из трёх:

* **разговор с напарником.** Файлы `*_partner` — один и тот же разговор,
  доступный из нескольких глав; английский в копиях слово в слово, и русский
  обязан совпадать. В деле 3 разговор Грегори с Баддом стоял в трёх файлах
  и был переведён трижды по-разному — 23 группы, ещё 7 в делах 1–2. Реплики
  Бадда про перчатки и «сгоряча» 9 сентября свели в двух файлах — в третьем
  они прожили старыми ещё два дня;
* **служебные реплики осмотра** («I must scour the scene...», «There's nothing
  of interest here.») — строка интерфейса, одна на всю игру. По делам она
  разошлась на четыре-шесть вариантов.

Короткий отклик сюда не попадает: ему по правилу №9 положено звучать по-разному
в разных сценах — это сторожит check_echo.py.

Что делает: (1) английская реплика не короче MIN_VISIBLE знаков, которая хоть
раз стоит в файле напарника, во всех переведённых местах игры должна иметь
один русский текст — буква в букву, с кодами и переносом; (2) реплики из
SERVICE переведены ровно так, как записано там. Разошлось — **валится**.

Законное расхождение — адрес в EXCEPT с причиной и строка в decisions.md.

    python tools/check_repeats.py          # только нарушения, для check_all
    python tools/check_repeats.py --list   # что сторожится
"""
from __future__ import annotations

import argparse
import collections
import re

from common import CASES, case_json, load_json

MIN_VISIBLE = 25  # короче — почти наверняка отклик, ему разнобой положен

# Служебные реплики осмотра: одна строка на всю игру. Выбор и «почему» —
# docs/decisions.md, запись от 11 сентября 2026.
SERVICE: dict[str, str] = {
    "I must scour the scene and inspect anything that catches my attention.":
        "Нужно прочесать место преступления и осмотреть всё, что привлечёт внимание.",
    "I don't believe there is any more to be found here.":
        "Не думаю, что здесь есть ещё что-то.",
    "There's nothing of interest here.":
        "Здесь нет ничего интересного.",
    "Could this be related to the evidence somehow?":
        "Не связано ли это как-то с уликами?",
    # Служебная пара логики: неудачный нажим и досада на него. Вторая реплика
    # решена в деле 2 («Вот и аукнулось»), первая к 11 сентября 2026 разошлась
    # на пять вариантов в семи копиях дел 1–4.
    "Hmph... Well... No, nothing seems out of place!":
        "Хмф... Так... Нет, всё вроде бы на месте!",
    "Nngh! (Well that blew up in my face...)":
        "Нгх! (Вот и аукнулось...)",
}

# Адрес сегмента → причина, по которой расхождение законно.
EXCEPT: dict[str, str] = {
    "sce0_c0_partner.bytes|00000CE1|2":
        "дело 1 хронологически первое: Эджворт с Гамшу ещё на «вы» (voices.md, "
        "«Кто с кем на «вы» в деле 1»), а в делах 2 и 4 та же мысль — на «ты»",
}

CODE = re.compile(r"\{[^{}]*\}")


def visible(text: str) -> str:
    """Текст без кодов и переносов: служебную реплику сверяем по словам."""
    return re.sub(r"\s+", " ", CODE.sub("", text or "")).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="показать, что сторожится")
    args = ap.parse_args()

    entries = []
    for case in CASES:
        data = load_json(case_json(case))
        if data:
            entries.extend(data["entries"])

    groups: dict[str, list[dict]] = collections.defaultdict(list)
    for it in entries:
        groups[it["en"]].append(it)
    partner = {en: lst for en, lst in groups.items()
               if len(visible(en)) >= MIN_VISIBLE and len(lst) > 1
               and any("_partner" in it["file"] for it in lst)}

    if args.list:
        print(f"реплик напарника с копиями: {len(partner)}, "
              f"служебных реплик осмотра: {len(SERVICE)}")
        for en, ru in SERVICE.items():
            print(f"   {en}\n   → {ru}")
        print()

    bad = 0
    for en, lst in partner.items():
        variants: dict[str, list[str]] = collections.defaultdict(list)
        for it in lst:
            if (it.get("ru") or "").strip() and it["id"] not in EXCEPT:
                variants[it["ru"]].append(it["id"])
        if len(variants) > 1:
            bad += 1
            print(f"   напарник: {visible(en)[:80]}")
            for ru, ids in variants.items():
                print(f"       ×{len(ids)} «{visible(ru)[:80]}»   ({ids[0]})")

    checked = 0
    for it in entries:
        want = SERVICE.get(visible(it["en"]))
        if want is None or not (it.get("ru") or "").strip() or it["id"] in EXCEPT:
            continue
        checked += 1
        if visible(it["ru"]) != visible(want):
            bad += 1
            print(f"   осмотр: {it['id']}\n"
                  f"       стоит «{visible(it['ru'])}», принято «{want}»")

    print(f"   реплик напарника с копиями: {len(partner)}, служебных мест "
          f"сверено: {checked}, исключений {len(EXCEPT)}")
    if not bad:
        print("   OK — разговоры с напарником и служебные реплики звучат одинаково везде.")
        return 0
    print(f"   РАСХОЖДЕНИЙ: {bad} — одна реплика обязана звучать одинаково; "
          f"законное место — в EXCEPT с причиной")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
