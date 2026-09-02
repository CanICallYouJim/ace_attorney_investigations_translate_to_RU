# -*- coding: utf-8 -*-
"""Словарь речи персонажа из нашего же перевода: что он на самом деле говорит.

voices.md описывает регистр словами («подросток, восклицания, простые
конструкции»). Описание задаёт направление, но не даёт переводчику **слов**,
и потому не мешает написать «Восполню пробелы» подростку: правило в профиле
стояло верное, а слово всё равно вышло не из того рта. Список мешает.

Здесь список собирается не из головы, а из **готового перевода**: 24 260 реплик
дел 0–4 — это корпус, где персонаж уже звучит по-русски и уже принят игроком.

    python tools/lexicon.py                     # сводка: доля частиц у всех
    python tools/lexicon.py Эджворт Кей         # словарь названных
    python tools/lexicon.py --case 5            # весь состав дела и их словари
    python tools/lexicon.py --corpus 0,1,2,3,4  # из каких дел брать корпус

Три числа на выходе и что с ними делать:

* **доля частиц** — сколько процентов реплик несут хоть одно слово вроде
  «же, ведь, ну, вот, разве, уж». По корпусу среднее 17 %, разброс 8 %–43 %.
  Низкая доля не ошибка, а запас: реплика без интонации звучит протоколом,
  разбор — docs/russian.md;
* **характерные слова** — те, что у этого персонажа встречаются заметно чаще,
  чем у остальных. Это его метки, из них берут;
* **книжный пласт** — помеченные слова, которые у него уже стоят. Одному
  персонажу они характер (Молотова, де Киллер), другому брак (Кей, Гамшу):
  сверять с профилем в voices.md, а не считать находкой саму по себе.

Готовые списки по составу дела 5 лежат в docs/voices.md, раздел
«Словари речи». Инструмент нужен, чтобы их пересобрать после новых файлов
и чтобы завести список новому персонажу.
"""
from __future__ import annotations

import argparse
import collections
import re

from common import case_of, load_entries
from who import NAMES
import reread

CODES = re.compile(r"\{[^}]*\}")
WORD = re.compile(r"[а-яё][а-яё-]+", re.I)

# Слот сквозной по игре, но занят в каждом деле своим персонажем; там, где имя
# у одного и того же героя разное, сводим к одному — иначе корпус делится надвое.
ALIAS = {"Победин": "Юстас", "циркачка": "Реджина"}

PARTICLES = ["же", "ведь", "ну", "вот", "разве", "уж", "неужели", "что ли", "всё-таки",
             "ага", "ой", "эх", "ух", "ох", "эй", "небось", "поди", "знаешь", "знаете",
             "слушай", "слушайте", "мол", "дескать", "право", "чай", "то-то", "да ну"]
ADDRESS = ["сестрёнка", "дружище", "милочка", "дорогуша", "малец", "мелкая", "малявка",
           "братец", "подруга", "голубушка", "голубчик", "душенька", "лапушка",
           "дамочка", "барышня", "сынок", "дочка", "приятель", "парень", "шеф",
           "начальник", "сэр", "мистер", "господин", "госпожа", "ваша честь",
           "детектив", "прокурор", "напарница", "малышка", "милая", "милый"]
BOOKISH = ["ибо", "полноте", "отнюдь", "извольте", "изволь", "надлежит", "надобно",
           "весьма", "столь", "дабы", "сие", "нежели", "коли", "покамест", "вышколить",
           "восполнить", "обратилась", "выписала", "занедужу", "откланяться", "искомое",
           "извне", "некое", "полагаю", "намерен", "не так ли", "соблаговолите",
           "позвольте", "благоволите", "нынче", "давеча", "оный"]


def bag_hits(lines: list[str], bag: list[str], top: int = 14) -> str:
    """Сколько реплик несут каждое слово из набора. Считаем реплики, а не слова:
    «ну-ну-ну» в одной реплике — одна интонация, а не три."""
    out = []
    for w in bag:
        rx = re.compile(r"(?<![А-Яа-яЁё-])" + re.escape(w) + r"(?![А-Яа-яЁё])", re.I)
        k = sum(1 for line in lines if rx.search(line))
        if k:
            out.append((k, w))
    out.sort(reverse=True)
    return ", ".join(f"{w}×{k}" for k, w in out[:top])


def collect(corpus: set[int]) -> dict[str, list[str]]:
    """Реплики по персонажу. Говорящий — код E101 с переносом, как в reread.py."""
    who = {key: (case_of(name), slot) for key, name, slot, _seg in reread.walk(None)}
    lines: dict[str, list[str]] = collections.defaultdict(list)
    for entry in load_entries():
        if not entry["ru"].strip():
            continue
        case, slot = who.get(entry["id"], (None, None))
        if case is None or slot is None or case not in corpus:
            continue
        name = NAMES.get(case, {}).get(slot)
        if not name or name.startswith("?"):
            continue
        lines[ALIAS.get(name, name)].append(CODES.sub("", entry["ru"]))
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="персонажи; без них — сводка по всем")
    ap.add_argument("--case", type=int, help="взять состав этого дела")
    ap.add_argument("--corpus", default="0,1,2,3,4", help="из каких дел брать реплики")
    ap.add_argument("--min", type=int, default=90, help="порог реплик для сводки")
    args = ap.parse_args()

    corpus = {int(c) for c in args.corpus.split(",") if c.strip()}
    lines = collect(corpus)

    freq = {name: collections.Counter(w.lower() for line in ls for w in WORD.findall(line))
            for name, ls in lines.items()}
    total = collections.Counter()
    for counter in freq.values():
        total.update(counter)
    grand = sum(total.values())
    part_rx = re.compile("|".join(r"(?<![А-Яа-яЁё-])" + re.escape(w) + r"(?![А-Яа-яЁё])"
                                 for w in PARTICLES), re.I)

    want = list(args.names)
    if args.case:
        want = [ALIAS.get(n, n) for n in NAMES.get(args.case, {}).values()
                if not n.startswith("?")]
        want = sorted(set(want), key=lambda n: -len(lines.get(n, [])))

    if not want:
        print(f"корпус: дела {sorted(corpus)}, персонажей {len(lines)}")
        print("доля реплик с частицей — чем ниже, тем суше речь\n")
        rows = sorted(((sum(1 for l in ls if part_rx.search(l)) * 100 // len(ls), len(ls), n)
                       for n, ls in lines.items() if len(ls) >= args.min))
        for share, n_lines, name in rows:
            print(f"{share:3}%  {name:16} {n_lines} реплик")
        return 0

    for name in want:
        ls = lines.get(name)
        if not ls:
            print(f"\n### {name}: в корпусе реплик нет — профиль строить до сцен")
            continue
        counter = freq[name]
        n_words = sum(counter.values())
        share = sum(1 for l in ls if part_rx.search(l)) * 100 // len(ls)
        print(f"\n### {name} — {len(ls)} реплик, {n_words} слов, частица в {share}%")
        marks = []
        for word, k in counter.items():
            if k < 3 or len(word) < 3:
                continue
            mine = k / n_words
            rest = (total[word] - k) / max(grand - n_words, 1)
            marks.append((mine / (rest + 1e-6), k, word))
        marks.sort(reverse=True)
        print("   характерные:", ", ".join(f"{w}×{k}" for _s, k, w in marks[:22]))
        print("   частицы:  ", bag_hits(ls, PARTICLES) or "—")
        print("   обращения:", bag_hits(ls, ADDRESS) or "—")
        print("   книжное:  ", bag_hits(ls, BOOKISH) or "—")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
