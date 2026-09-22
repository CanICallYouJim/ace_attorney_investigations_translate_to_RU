# -*- coding: utf-8 -*-
"""Реплика зовёт вещь и человека так же, как таблица, и одинаково во всей игре.

Правило №6 требует, чтобы улика не получила два имени: одно в органайзере
(строковая таблица), другое в реплике («Salt Lamp added to the Court Record»).
`check_pipelines.py` сторожит **объём** — что таблицы дела не отстают от реплик;
совпадение самих **слов** до 22 сентября 2026 не сторожил никто, и находились
расхождения случайно, глазами игрока или переводчика:

* `chisel` — в таблице «Стамеска», а в четырёх репликах дела 5 стояло «зубило»;
* `Mr. Saint` — 59 раз «мистер Святов» и 4 раза «господин Святов» в одном файле;
* уведомление органайзера звало улику «Дело IS-7» при таблице «Дело о
  происшествии IS-7» и «Донесение о Коневе» при таблице «Рапорт о Коневе».

Класс у всех один: **эталон лежит в таблице, а реплику с ним никто не сверял.**
Отсюда устройство проверки — эталон берётся оттуда, куда этот конвейер не пишет
(`work/strings.json`), а судится текст реплик (`work/caseN.json`).

Что делает:

* **валит**, если уведомление органайзера (`X data jotted down/updated in my
  Organizer`) называет улику не тем именем, что стоит в `gk2_item_name`. Место
  сомнений не оставляет: английское имя в уведомлении — это буквально ключ
  таблицы, и русское обязано быть её значением;
* **валит**, если сама таблица разошлась с собой: одна английская улика с двумя
  разными русскими именами. Так жило `IS-7 Incident Case File` — «Дело IS-7»
  в строке дела 3 и «Дело о происшествии IS-7» в строке дела 5; у каждого дела
  своя строка на одну и ту же вещь, и правка одной второй не касается. Пока
  эталон противоречив, сверять реплику с ним бессмысленно, поэтому это первое,
  что проверяется;
* **валит**, если один английский «титул + фамилия» (`Mr. Saint`, `Judge Gavèlle`)
  переведён в игре двумя разными русскими титулами. Падежи сводятся к лемме, так
  что «мистера» и «мистеру» разнобоем не считаются, а «мистер» против «господин» —
  считается. Законные исключения — в `EXCEPT`, **каждое со своей причиной**;
* **показывает** по `--mentions` реплики, где английское имя улики есть, а русского
  слова из таблицы нет. Это **список для глаз, а не приговор**: по-русски вещь
  сплошь и рядом называется местоимением («её унести», «та, которую мы приняли»),
  и машина отличить это от подмены слова не может. Ничего не валит.

Чего проверка **не** судит, чтобы «ноль находок» не путали с «ничего не смотрели»:

* имя улики, которое во **всех** репликах переведено не по таблице — это уже
  не дрейф, а решение; его ловят глоссарий и `check_coverage.py`;
* имена без титула («Святов» просто по фамилии) — там выбора нет и дрейфовать
  нечему;
* клички и прозвища — у них свой сторож, `check_decisions.py`.

    python tools/check_terms.py              # только нарушения, для check_all
    python tools/check_terms.py --mentions   # список для глаз: имя улики в репликах
    python tools/check_terms.py --selftest   # проверка умеет краснеть
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys

from common import WORK, load_entries

CODES = re.compile(r"\{[^}]*\}")

EN_TITLE = (r"(Mr|Ms|Mrs|Miss|Judge|Detective|Prosecutor|Warden|Chairman|Agent|"
            r"President|Chief)")

# Падежные формы русских титулов. Список закрытый нарочно: незнакомое слово
# лучше пропустить, чем принять за титул случайное существительное перед фамилией.
RU_TITLE_FORMS = [
    "мистер", "мистера", "мистеру", "мистером", "мистере",
    "господин", "господина", "господину", "господином", "господине",
    "госпожа", "госпожи", "госпоже", "госпожой", "госпожу",
    "мисс", "миссис",
    "судья", "судьи", "судье", "судьёй", "судью",
    "детектив", "детектива", "детективу", "детективом", "детективе",
    "прокурор", "прокурора", "прокурору", "прокурором", "прокуроре",
    "инспектор", "инспектора", "инспектору", "инспектором",
    "начальник", "начальника", "начальнику", "начальником",
    "начальница", "начальницы", "начальнице", "начальницу", "начальницей",
    "председатель", "председателя", "председателю", "председателем",
    "агент", "агента", "агенту", "агентом",
    "президент", "президента", "президенту", "президентом",
]
RU_TITLE = "(" + "|".join(sorted(RU_TITLE_FORMS, key=len, reverse=True)) + ")"

# Приведение падежа к лемме: «мистера» и «мистеру» — одно слово, «господин» — другое.
LEMMA_PREFIX = [
    ("начальниц", "начальница"), ("начальник", "начальник"),
    ("председател", "председатель"), ("госпож", "госпожа"),
    ("миссис", "миссис"), ("мисс", "мисс"), ("судь", "судья"),
    ("мистер", "мистер"), ("господин", "господин"), ("детектив", "детектив"),
    ("прокурор", "прокурор"), ("инспектор", "инспектор"), ("агент", "агент"),
    ("президент", "президент"),
]

# Законный разнобой. Ключ — (английский титул, английская фамилия, русская лемма);
# значение — причина. Без причины строки здесь быть не должно: исключение без
# записанного «почему» через полгода нарушат, не зная, что оно было осознанным.
EXCEPT: dict[tuple[str, str, str], str] = {}

# Уведомления органайзера, где английское имя улики не совпадает с ключом таблицы
# по вине самой игры (опечатка разработчиков, склейка двух уведомлений в сегменте).
EXCEPT_NOTE: dict[str, str] = {}

VOWEL = "аяоеыиуюэёьй"


def plain(text: str) -> str:
    return CODES.sub("", text or "")


def lemma(word: str) -> str:
    low = word.lower()
    for prefix, base in LEMMA_PREFIX:
        if low.startswith(prefix):
            return base
    return low


def stem(word: str) -> str:
    """Грубая основа русского слова: срезать до двух конечных гласных."""
    out = word.lower()
    for _ in range(2):
        if len(out) > 4 and out[-1] in VOWEL:
            out = out[:-1]
    return out


def tables() -> dict:
    data = json.loads((WORK / "strings.json").read_text(encoding="utf-8"))
    return data["tables"]


def item_names() -> dict[str, str]:
    """Английское имя улики → русское, из `gk2_item_name`."""
    out = {}
    for row in tables()["gk2_item_name"].values():
        english = (row.get("en") or "").strip()
        russian = (row.get("ru") or "").strip()
        if english and russian:
            out[english] = russian
    return out


def table_conflicts() -> list[str]:
    """Одна английская улика с двумя русскими именами — эталон противоречив.

    У каждого дела своя строка таблицы на ту же вещь (улики повторяются между
    делами), и правка одной строки вторую не задевает. Пока строки расходятся,
    сверка реплики с таблицей ничего не значит: какое из двух имён «верное»,
    проверка решить не может и решать не должна.
    """
    variants: dict[str, dict[str, list[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    for mid, row in tables()["gk2_item_name"].items():
        english = (row.get("en") or "").strip()
        russian = (row.get("ru") or "").strip()
        if english and russian:
            variants[english][russian].append(str(mid))
    out = []
    for english, by_russian in sorted(variants.items()):
        if len(by_russian) < 2:
            continue
        lines = [f"таблица спорит сама с собой: {english!r} — {len(by_russian)} имени"]
        for russian, ids in sorted(by_russian.items()):
            lines.append(f"   {russian!r}  строки {', '.join(ids)}")
        out.append("\n".join(lines))
    return out


def person_names() -> dict[str, str]:
    """Английская фамилия → русская, из `gk2_common_nametag`."""
    out = {}
    for row in tables()["gk2_common_nametag"].values():
        english = (row.get("en") or "").strip()
        russian = (row.get("ru") or "").strip()
        if english and russian and english[0].isupper() and re.search(r"[А-ЯЁ]", russian):
            out[english] = russian
    return out


def translated(entries=None) -> list[dict]:
    return [e for e in (entries if entries is not None else load_entries(None)) if e.get("ru")]


# --- правило 1: уведомление органайзера -------------------------------------

def note_pattern(items: dict[str, str]) -> re.Pattern:
    """`<имя улики> data jotted down / updated in my Organizer`.

    Имя берётся не «сколько-нибудь слов перед data», а перебором ключей таблицы:
    иначе в сегменте с двумя уведомлениями подряд в имя утаскивается хвост
    предыдущего предложения, и проверка находит несуществующее.
    """
    alternatives = "|".join(re.escape(name) for name in
                            sorted(items, key=len, reverse=True))
    return re.compile(rf"({alternatives})\s*\n?\s*data\s+"
                      rf"(?:jotted\s*\n?\s*down|updated)\s*\n?\s*in my Organizer",
                      re.I)


def check_notes(entries, items) -> tuple[int, list[str]]:
    pattern = note_pattern(items)
    by_lower = {name.lower(): russian for name, russian in items.items()}
    seen, problems = 0, []
    for entry in entries:
        english, russian = plain(entry["en"]), plain(entry["ru"])
        for match in pattern.finditer(english):
            name = re.sub(r"\s+", " ", match.group(1)).strip()
            seen += 1
            expected = by_lower[name.lower()]
            if expected.lower() in russian.lower():
                continue
            if entry["id"] in EXCEPT_NOTE:
                continue
            problems.append(
                f"органайзер: {entry['id']}\n"
                f"   улика {name!r} — в таблице {expected!r}, а в реплике его нет\n"
                f"   RU: {russian.replace(chr(10), ' / ')[:110]}")
    return seen, problems


# --- правило 2: титул при фамилии -------------------------------------------

def collect_titles(entries, people) -> tuple[int, dict]:
    pairs: dict[tuple[str, str], dict[str, list[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    seen = 0
    for entry in entries:
        english, russian = plain(entry["en"]), plain(entry["ru"])
        for en_name, ru_name in people.items():
            for match in re.finditer(rf"\b{EN_TITLE}\.?\s+{re.escape(en_name)}\b", english):
                seen += 1
                root = ru_name[:-1] if len(ru_name) > 5 else ru_name
                found = re.search(rf"{RU_TITLE}\s+{re.escape(root)}", russian, re.I)
                if found:
                    pairs[(match.group(1).lower(), en_name)][lemma(found.group(1))].append(
                        entry["id"])
    return seen, pairs


def check_titles(pairs) -> list[str]:
    problems = []
    for (title, name), variants in sorted(pairs.items()):
        live = {ru: ids for ru, ids in variants.items()
                if (title, name, ru) not in EXCEPT}
        if len(live) < 2:
            continue
        order = sorted(live.items(), key=lambda kv: -len(kv[1]))
        total = sum(len(ids) for ids in live.values())
        lines = [f"титул: {title.capitalize()}. {name} — {len(order)} разных слова "
                 f"на {total} мест"]
        for ru_title, ids in order:
            lines.append(f"   {ru_title:14} x{len(ids):3}  {', '.join(sorted(ids)[:4])}")
        problems.append("\n".join(lines))
    return problems


# --- список для глаз: имя улики в реплике ------------------------------------

def mentions(entries, items) -> tuple[list[str], tuple[int, int, int]]:
    rows, clean, judged, unjudged = [], 0, 0, 0
    for english_name, russian_name in sorted(items.items()):
        if len(english_name) < 4:
            unjudged += 1
            continue
        words = re.findall(r"[А-Яа-яЁё\-]{3,}", russian_name)
        if not words:
            unjudged += 1
            continue
        root = stem(max(words, key=len))
        pattern = re.compile(r"(?<![A-Za-z])" + re.escape(english_name) + r"(?![A-Za-z])", re.I)
        hits = [e for e in entries if pattern.search(plain(e["en"]))]
        if not hits:
            continue
        ok = [e for e in hits if root in plain(e["ru"]).lower()]
        missing = [e for e in hits if root not in plain(e["ru"]).lower()]
        if len(ok) < 2:
            unjudged += 1
            continue
        judged += 1
        if not missing:
            clean += 1
            continue
        rows.append(f"--- {english_name!r} → {russian_name!r} (корень {root!r}): "
                    f"со словом {len(ok)}, без слова {len(missing)}")
        for entry in missing:
            rows.append(f"    {entry['id']}")
            rows.append(f"      EN: {plain(entry['en']).replace(chr(10), ' / ')[:88]}")
            rows.append(f"      RU: {plain(entry['ru']).replace(chr(10), ' / ')[:88]}")
    return rows, (judged, clean, unjudged)


# --- сторож самой проверки ---------------------------------------------------

def selftest() -> int:
    """Посеять порчу обоих классов и убедиться, что проверка её валит.

    Правило №13: зелёное число засчитывается, только если проверка показала, что
    умеет краснеть. Порча сеется **по тексту реплик**, а не по внутренним спискам
    проверки, иначе сторож меряет сам себя.
    """
    items, people = item_names(), person_names()
    entries = translated()

    seen_notes, problems = check_notes(entries, items)
    seen_titles, pairs = collect_titles(entries, people)
    if problems or check_titles(pairs) or table_conflicts():
        print("чистый прогон уже красный — сперва почини находки")
        return 1
    if not seen_notes or not seen_titles:
        print(f"сверять нечего: уведомлений {seen_notes}, титулов {seen_titles}")
        return 1

    ok = True

    # порча 1: уведомление органайзера зовёт улику синонимом
    victim = None
    pattern = note_pattern(items)
    for entry in entries:
        match = pattern.search(plain(entry["en"]))
        if match:
            victim = (entry, items[
                next(n for n in items if n.lower() == match.group(1).lower())])
            break
    spoiled = dict(victim[0])
    spoiled["ru"] = victim[0]["ru"].replace(victim[1], "Некая вещица")
    if spoiled["ru"] == victim[0]["ru"]:
        print("порчу 1 посеять не вышло: имя улики в реплике не нашлось")
        return 1
    rest = [e for e in entries if e["id"] != spoiled["id"]] + [spoiled]
    _, caught = check_notes(rest, items)
    if not caught:
        print("ПРОВАЛ: подменённое имя улики в органайзере проверка не заметила")
        ok = False

    # порча 2: один титул из многих заменён другим
    target = None
    for entry in entries:
        found = re.search(rf"\b(Mr)\.?\s+(\w+)\b", plain(entry["en"]))
        if found and found.group(2) in people:
            ru_name = people[found.group(2)]
            root = ru_name[:-1] if len(ru_name) > 5 else ru_name
            if re.search(rf"мистер\w*\s+{re.escape(root)}", plain(entry["ru"]), re.I):
                target = entry
                break
    if target is None:
        print("порчу 2 посеять не вышло: «мистер + фамилия» в репликах не нашлось")
        return 1
    spoiled2 = dict(target)
    spoiled2["ru"] = re.sub(r"[Мм]истер(\w*)", r"господин\1", target["ru"], count=1)
    rest2 = [e for e in entries if e["id"] != spoiled2["id"]] + [spoiled2]
    _, pairs2 = collect_titles(rest2, people)
    if not check_titles(pairs2):
        print("ПРОВАЛ: подменённый титул проверка не заметила")
        ok = False

    if ok:
        print(f"сторож на месте: обе порчи поймал, чистый текст прошёл "
              f"(сверено уведомлений {seen_notes}, титулов {seen_titles})")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mentions", action="store_true",
                        help="список для глаз: имя улики есть, слова из таблицы нет")
    parser.add_argument("--selftest", action="store_true",
                        help="посеять порчу и убедиться, что проверка её валит")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    items, people = item_names(), person_names()
    entries = translated()

    if args.mentions:
        rows, (judged, clean, unjudged) = mentions(entries, items)
        print("\n".join(rows))
        print(f"\nимён улик судимо: {judged} (без находок {clean}, "
              f"с находками {judged - clean}); не судили {unjudged} — "
              f"у них меньше двух реплик со словом из таблицы")
        print("Это список для глаз: местоимение вместо названия — не ошибка.")
        return 0

    problems = table_conflicts()
    seen_notes, notes = check_notes(entries, items)
    seen_titles, pairs = collect_titles(entries, people)
    problems += notes + check_titles(pairs)

    # «Сверять нечего» — провал, а не тишина (правило №13).
    if not seen_notes or not seen_titles:
        print(f"ПРОВАЛ: сверять нечего — уведомлений {seen_notes}, "
              f"титулов {seen_titles}. Проверка ничего не смотрела.")
        return 1

    for line in problems:
        print(line)
    print(f"\nсверено: имён улик в таблице {len(items)}, уведомлений органайзера "
          f"{seen_notes}, мест «титул + фамилия» {seen_titles} в {len(pairs)} парах; "
          f"расхождений {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
