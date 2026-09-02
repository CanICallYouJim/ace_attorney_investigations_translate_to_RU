# -*- coding: utf-8 -*-
"""Сито переводного: места, где реплика верна, но построена по-английски.

Правила 1-9 ловят брак классами, и на них есть проверки. Правило №10
(docs/russian.md) ловит другое — реплику, где всё верно и всё равно слышно
перевод. Проверкой это не сделать: «Это то, что я хотел узнать» не нарушает
ничего, кроме русского языка.

Поэтому здесь не проверка, а **сито**: оно печатает адреса на разбор глазами
и никогда не валится. Классы — те же, что в work/retro.md.

    python tools/find_translationese.py                      # сводка по делам
    python tools/find_translationese.py --class particles --case 1
    python tools/find_translationese.py --class syntax --who 0000 --limit 40
    python tools/find_translationese.py --class stock --case 2 --by-speaker
    python tools/find_translationese.py --class calque --file sce1_c1

Классы:

* **particles** — в английском стоит эмфаза (well, just, really, do have,
  come on), в русском переводе нет ни одной частицы. Самый массовый класс:
  замер 2 сентября 2026 дал 17 % реплик с частицей против 19 % английских
  с маркером, при том что русский обязан нести их больше;
* **syntax** — маркеры письменного и канцелярского строя в живой речи:
  причастный оборот, отглагольное существительное, «является», «данный»,
  «в случае», нанизанные родительные;
* **calque** — конструкция, скопированная с английской: «Что насчёт»,
  «Я не могу поверить», «в порядке?», «Позволь мне», «Это то, что»;
* **stock** — затёртый оборот: у английского на этом месте шесть разных,
  у нас один и тот же в двадцатый раз («полагаю» x127 при «мне кажется» x8).

Говорящий берётся из E101 с переносом, как в reread.py, и кэшируется в
work/.speakers_cache.json — иначе каждый прогон читает бандлы заново.
"""
from __future__ import annotations

import argparse
import collections
import json
import re

from common import WORK, case_of, load_entries
from who import NAMES
import reread

CODES = re.compile(r"\{[^}]*\}")
CACHE = WORK / ".speakers_cache.json"


def w(*words: str) -> re.Pattern:
    """Регулярка «одно из слов целым словом», без учёта регистра."""
    body = "|".join(re.escape(x).replace(r"\ ", r"\s+") for x in words)
    return re.compile("(?<![А-Яа-яЁёA-Za-z-])(?:" + body + ")(?![А-Яа-яЁёA-Za-z-])", re.I)


# --- класс particles ---------------------------------------------------------

# Английская эмфаза: то, что в русском обязано превратиться в частицу.
EMPH_STRONG = [
    (re.compile(r"(?:^|[.!?]\s+|\n)\s*well\b(?![-])", re.I), "well"),
    (w("come on"), "come on"), (w("you know"), "you know"), (w("huh"), "huh"),
    (w("indeed"), "indeed"), (w("after all"), "after all"),
    (w("surely"), "surely"), (w("really"), "really"),
    (re.compile(r"\b(?:I|you|we|they|he|she|it)\s+(?:do|does|did)\s+[a-z]+", re.I),
     "эмфатическое do"),
    (re.compile(r"\bdo\s+(?:seem|have|know|think|look|need|want|believe|remember|realize)\b",
                re.I), "эмфатическое do"),
]

# Слабая эмфаза: у слова есть и обычное значение, ложных срабатываний много.
# Включается флагом --weak.
EMPH_WEAK = [
    (w("just"), "just"), (w("even"), "even"), (w("actually"), "actually"),
    (w("of course"), "of course"), (w("at all"), "at all"),
    (w("anyway", "anyhow"), "anyway"),
]

# Русские частицы — список из lexicon.py плюс то, что там не понадобилось:
# «-то» постфиксом, «ли», «ж», и обороты вроде «да брось».
PARTICLES = w(
    "же", "ж", "ведь", "ну", "вот", "разве", "уж", "неужели", "что ли", "всё-таки",
    "ага", "ой", "эх", "ух", "ох", "эй", "небось", "поди", "знаешь", "знаете",
    "слушай", "слушайте", "мол", "дескать", "право", "чай", "то-то", "да ну",
    "ли", "аж", "прямо", "просто", "именно", "вовсе", "хоть", "пусть",
    "давай", "давайте", "ишь", "ба", "ну-ка", "как же", "да брось",
    "даже", "совсем", "лишь", "только", "всего", "нате", "ей-богу", "ага", "угу",
    # Слова, которые несут ту же интонацию, что частица, и потому закрывают место:
    # «Indeed» -> «И правда», «surely» -> «вы, верно, шутите».
    "правда", "действительно", "верно", "ещё бы", "конечно", "однако", "пожалуй",
    "впрочем", "разумеется", "надо же", "в конце концов", "более чем", "точно",
    "никак", "нате же", "то ли дело", "стало быть", "стал-быть", "выходит",
)
# Частица на конце реплики: «..., а?», «..., да?», «..., нет?» — интонация есть.
TAIL = re.compile(r"[,—-]\s*(?:а|да|нет|ага|угу|правда|верно|точно)\s*[?!]+", re.I)
DASH_TO = re.compile(r"[а-яё]-(?:то|ка|таки)\b", re.I)


def has_particle(ru: str) -> bool:
    return bool(PARTICLES.search(ru) or DASH_TO.search(ru) or TAIL.search(ru))


# --- класс syntax ------------------------------------------------------------

PARTICIPLE = re.compile(
    r"[а-яё]{3,}(?:вший|вшая|вшее|вшие|вшего|вшую|вших|ющий|ющая|ющее|ющие|ющего|ющих|"
    r"ащий|ящий|ащая|ящая|ащие|ящие|ащего|ящего|имый|имая|имые|емый|емая|емые)"
    r"(?![а-яё])", re.I)
# По форме причастия, по существу — существительное и прилагательное. В живой
# речи законны: «стрелявший» это не оборот, а тот, кто стрелял.
NOT_PARTICIPLE = w(
    "стрелявший", "стрелявшего", "стрелявшему", "стрелявшим", "стрелявшем",
    "подозреваемый", "подозреваемого", "подозреваемому", "подозреваемым",
    "обвиняемый", "обвиняемого", "обвиняемому", "обвиняемым",
    "потерпевший", "потерпевшего", "потерпевшему", "пострадавший", "пострадавшего",
    "погибший", "погибшего", "погибшему", "погибшая", "умерший", "умершего",
    "управляющий", "управляющего", "командующий", "нападавший", "нападавшего",
    "звонивший", "звонившего", "присутствующие", "присутствующих", "проходящий",
    "любимый", "любимая", "любимое", "любимые", "любимого", "любимую",
    "необходимый", "необходимая", "необходимое", "необходимые",
    "невозможный", "невозможная", "невозможное", "невыносимый", "невыносимая",
    "видимый", "видимая", "видимые", "мнимый", "мнимая", "неуловимый", "неуловимая",
    "настоящий", "настоящая", "настоящее", "настоящие", "настоящего", "будущий",
    "будущая", "будущее", "текущий", "текущая", "следующий", "следующая",
    "следующее", "следующие", "следующего", "блестящий", "блестящая", "блестящие",
    "подходящий", "подходящая", "подходящее", "выдающийся", "выдающаяся",
    "потрясающий", "потрясающая", "потрясающее", "решающий", "решающая", "решающее",
    "изящный",
)
# Врезка органайзера — служебная формула игры, а не канцелярит переводчика.
ORGANIZER = re.compile(r"Данные\s+[«„\"]", re.I)
GERUND = re.compile(r"[а-яё]{3,}(?:вши|учи|ючи)\b|[а-яё]{4,}(?:ая|яя)сь\b", re.I)
VERBAL_NOUN = w(
    "осуществление", "проведение", "получение", "использование", "применение",
    "обнаружение", "установление", "подтверждение", "предоставление", "совершение",
    "выяснение", "уточнение", "оказание", "принятие", "нахождение", "изучение",
    "рассмотрение", "определение", "выполнение", "исполнение", "составление",
    "осуществления", "проведения", "получения", "использования", "применения",
    "обнаружения", "установления", "подтверждения", "предоставления", "совершения",
    "наличие", "наличия", "отсутствие", "отсутствия",
)
CLERICAL = w(
    "является", "являются", "являлся", "являлась", "являетесь", "данный", "данная",
    "данное", "данные", "данного", "данной", "данным", "в случае", "в связи",
    "в качестве", "при помощи", "в целях", "с целью", "в отношении", "по причине",
    "в результате", "посредством", "относительно", "касательно",
    "ввиду", "вследствие", "поскольку", "имеется", "имеются",
    "осуществлять", "осуществить", "производить",
)
GEN_CHAIN = re.compile(
    r"\b[а-яё]{4,}(?:ния|ости|ства|ения|ания)\s+[а-яё]{4,}(?:ния|ости|ства|ения|ания)\b",
    re.I)

SYNTAX = [(PARTICIPLE, "причастие"), (GERUND, "деепричастие"),
          (VERBAL_NOUN, "отглагольное"), (CLERICAL, "канцелярит"),
          (GEN_CHAIN, "родительные цепочкой")]


# --- класс calque ------------------------------------------------------------

# Конструкция скопирована с английской. Пара (что видно в русском, что стояло
# в английском): оригинал нужен, чтобы отсеять случаи, где оборот пришёл не оттуда.
CALQUE = [
    (re.compile(r"что насчёт", re.I), re.compile(r"\bwhat about\b", re.I), "what about"),
    (re.compile(r"как насчёт того,? чтобы", re.I), None, "how about"),
    (re.compile(r"не мог(?:у|ла|)\s+поверить", re.I),
     re.compile(r"can.?t believe", re.I), "can't believe"),
    (re.compile(r"\b(?:ты|вы|я)\s+в порядке", re.I),
     re.compile(r"\b(?:you|I)\s*(?:are|'re|am|'m)?\s*(?:okay|ok|alright|all right)\b", re.I),
     "are you okay"),
    (re.compile(r"позволь(?:те)? мне", re.I), re.compile(r"\blet me\b", re.I), "let me"),
    (re.compile(r"давай(?:те)? сделаем это", re.I), None, "let's do it"),
    (re.compile(r"это то,? что", re.I),
     re.compile(r"\b(?:that|this) is what\b|that.s what", re.I), "that's what"),
    (re.compile(r"это потому,? что", re.I),
     re.compile(r"\b(?:that|this|it).s because\b", re.I), "that's because"),
    (re.compile(r"не имеет смысла", re.I),
     re.compile(r"(?:doesn.?t|does not) make sense", re.I), "make sense"),
    (re.compile(r"имеет смысл", re.I), re.compile(r"\bmakes sense\b", re.I), "makes sense"),
    (re.compile(r"я (?:так )?(?:не )?думаю", re.I),
     re.compile(r"\bI (?:don.?t )?think so\b", re.I), "I think so"),
    (re.compile(r"я имею в виду", re.I), re.compile(r"\bI mean\b", re.I), "I mean"),
    (re.compile(r"нет (?:никакого )?способа", re.I), re.compile(r"\bno way\b", re.I), "no way"),
    (re.compile(r"хорошая работа", re.I),
     re.compile(r"\b(?:good|nice) (?:job|work)\b", re.I), "good job"),
    (re.compile(r"на самом деле", re.I),
     re.compile(r"\b(?:actually|in fact)\b", re.I), "actually"),
    (re.compile(r"я собираюсь", re.I),
     re.compile(r"\b(?:I.m|I am) going to\b", re.I), "going to"),
    (re.compile(r"\b(?:с)?делать это\b", re.I),
     re.compile(r"\bdo (?:it|this|that)\b", re.I), "do it"),
    (re.compile(r"взгляни(?:те)? на|посмотри(?:те)? на это", re.I),
     re.compile(r"\btake a look\b", re.I), "take a look"),
    (re.compile(r"кажется,? что", re.I),
     re.compile(r"\bit seems (?:that|like)\b", re.I), "it seems that"),
    (re.compile(r"одна из вещей|эти вещи|такие вещи", re.I),
     re.compile(r"\bthings?\b", re.I), "things"),
]


# --- класс stock -------------------------------------------------------------

# Затёртые обороты: их в переводе много, и они вытеснили соседей по смыслу.
STOCK = ["полагаю", "не так ли", "похоже", "судя по всему", "разумеется",
         "в самом деле", "вот именно", "что ж", "постойте", "погодите",
         "как я и думал", "этого не может быть", "не может быть", "понятно"]


def speakers() -> dict[str, tuple]:
    """Карта сегмент -> (дело, слот). Кэш: чтение бандлов стоит 8 секунд на прогон."""
    if CACHE.exists():
        return {k: tuple(v) for k, v in json.loads(CACHE.read_text("utf-8")).items()}
    out = {key: (case_of(name), slot) for key, name, slot, _seg in reread.walk(None)}
    CACHE.write_text(json.dumps({k: list(v) for k, v in out.items()}, ensure_ascii=False),
                     "utf-8")
    return out


def rows(cases, file_prefix, who_id):
    """Переведённые сегменты охвата: (запись, дело, слот, имя, en, ru) без кодов."""
    who = speakers()
    for case in cases:
        for e in load_entries(case):
            if not e["ru"].strip() or not e["en"].strip():
                continue
            if file_prefix and not e["file"].startswith(file_prefix):
                continue
            _case, slot = who.get(e["id"], (None, None))
            if who_id and slot != who_id:
                continue
            name = NAMES.get(case, {}).get(slot or "", "") if slot else ""
            yield e, case, slot, name, CODES.sub("", e["en"]), CODES.sub("", e["ru"])


def scan(cases, file_prefix, who_id, kind, weak=False):
    """Найденные места класса kind: (запись, дело, имя, метка находки)."""
    stock_rx = [(s, w(s)) for s in STOCK]
    for e, case, _slot, name, en, ru in rows(cases, file_prefix, who_id):
        if kind == "particles":
            if has_particle(ru):
                continue
            bag = EMPH_STRONG + EMPH_WEAK if weak else EMPH_STRONG
            hits = [tag for rx, tag in bag if rx.search(en)]
            if hits:
                yield e, case, name, ", ".join(sorted(set(hits)))
        elif kind == "syntax":
            if ORGANIZER.search(ru):
                continue
            hits = []
            for rx, tag in SYNTAX:
                m = rx.search(ru)
                if m and not (tag == "причастие" and NOT_PARTICIPLE.fullmatch(m.group(0))):
                    hits.append(tag + ": " + m.group(0))
            if hits:
                yield e, case, name, "; ".join(hits)
        elif kind == "calque":
            hits = [tag for ru_rx, en_rx, tag in CALQUE
                    if ru_rx.search(ru) and (en_rx is None or en_rx.search(en))]
            if hits:
                yield e, case, name, ", ".join(hits)
        elif kind == "stock":
            hits = [s for s, rx in stock_rx if rx.search(ru)]
            if hits:
                yield e, case, name, ", ".join(hits)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--class", dest="kind",
                    choices=["particles", "syntax", "calque", "stock"],
                    help="класс находок; без него — сводка")
    ap.add_argument("--case", default="1,2,3,4", help="дела через запятую")
    ap.add_argument("--file", default="", help="ограничить участком: sce1_c1")
    ap.add_argument("--who", help="слот говорящего, например 0000")
    ap.add_argument("--limit", type=int, default=60, help="сколько мест печатать")
    ap.add_argument("--by-speaker", action="store_true", help="сводка по говорящим")
    ap.add_argument("--weak", action="store_true",
                    help="частицы: считать и слабую эмфазу (just, even, actually)")
    args = ap.parse_args()

    cases = [int(c) for c in args.case.split(",") if c.strip()]
    kinds = ("particles", "syntax", "calque", "stock")

    if not args.kind:
        total = collections.Counter()
        by = collections.defaultdict(collections.Counter)
        for kind in kinds:
            for _e, _case, name, _tag in scan(cases, args.file, args.who, kind, args.weak):
                total[kind] += 1
                by[kind][name or "—"] += 1
        seen = sum(1 for _ in rows(cases, args.file, args.who))
        print("Переведённых сегментов в охвате: %d\n" % seen)
        print("%-12s %7s  %6s  кто чаще всего" % ("класс", "мест", "доля"))
        for kind in kinds:
            top = ", ".join("%s x%d" % (n, k) for n, k in by[kind].most_common(4))
            print("%-12s %7d  %5.0f%%  %s" % (kind, total[kind],
                                              100.0 * total[kind] / max(seen, 1), top))
        print("\nСписок мест: --class particles [--case 1] [--who 0000] [--limit N]")
        return 0

    found = list(scan(cases, args.file, args.who, args.kind, args.weak))
    if args.by_speaker:
        tally = collections.Counter(name or "—" for _e, _c, name, _t in found)
        print("%s: %d мест\n" % (args.kind, len(found)))
        for name, k in tally.most_common(40):
            print("%6d  %s" % (k, name))
        return 0

    print("%s: %d мест, показаны первые %d\n" % (args.kind, len(found),
                                                 min(args.limit, len(found))))
    for e, case, name, tag in found[:args.limit]:
        print("[%d] %s  %s  <%s>" % (case, e["id"], name or "—", tag))
        print("  EN  " + CODES.sub("", e["en"]).replace("\n", " / "))
        print("  RU  " + CODES.sub("", e["ru"]).replace("\n", " / "))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
