"""Найти в оригинале английские идиомы — места, где калька особенно вероятна.

Замечание пользователя 11 августа 2026: часть реплик переведена дословно с
английских устойчивых оборотов. Смысл верен, `check_len.py` зелёный, редких
русских слов нет — и потому прогон на книжную лексику этот класс не видел
вовсе: «Хорошо было, пока длилось» составлено сплошь из обычных слов.

Ловить приходится **с английской стороны**: признак не в русском тексте,
а в том, что в оригинале стоял оборот, не равный сумме частей. Дальше каждое
найденное место смотрится глазами и, если сомнительно, через `polyglot.py` —
идиомы не калькирует ни одна из семи локализаций, и их выбор показывает,
что оборот надо заменить целиком, а не разбирать по словам.

    python tools/find_idioms.py                 # дело 2, все совпадения
    python tools/find_idioms.py --case 3        # другое дело
    python tools/find_idioms.py --case all      # все дела разом
    python tools/find_idioms.py --counts        # только сводка по оборотам
    python tools/find_idioms.py --only "teeth"  # один оборот
    python tools/find_idioms.py --untranslated  # включая ещё не переведённые

Список неполон по устройству — это сито, а не доказательство. Пополнять его
при каждой новой пойманной кальке: правило и разбор класса — в
docs/decisions.md, раздел «Правило, которое из этого следует».

## Вердикт: --calques

Сито само ничего не утверждает — оно показывает места, где надо смотреть глазами.
Отдельный режим `--calques` утверждает: он ищет не английский оборот, а **пару**
«английский оборот рядом с русской дословщиной», и на совпадении **валится**.

    python tools/find_idioms.py --calques --case all   # тест, ненулевой код возврата
    python tools/find_idioms.py --calques --list       # чем список заполнен

Пара срабатывает, только когда сошлись обе стороны, поэтому ложных почти нет:
«контора» сама по себе законное слово, «контора» напротив `firm` — уже брак,
разобранный пользователем. Исключения адресные, по идентификатору сегмента,
и каждое с причиной — см. `ALLOWED` ниже.

**Каждая калька, пойманная вычиткой, обязана стать здесь строкой.** Иначе она
поймана один раз, а не навсегда: разбор в `decisions.md` читает человек, а этот
список читает прогон перед каждой сборкой.
"""
from __future__ import annotations

import argparse
import collections
import re

from common import CASES, load_entries

# Обороты, которые в английском стоят целиком и не значат суммы частей.
# Порядок — по темам, чтобы дописывать было куда.
IDIOMS = [
    # разговорные формулы обращения и реакции
    r"come now", r"there there", r"my my", r"good grief", r"for crying out loud",
    r"you don't say", r"give me a break", r"take it easy", r"suit yourself",
    r"fair enough", r"no dice", r"beats me", r"go figure", r"you bet",
    # время и упущенный момент
    r"while it lasted", r"about time", r"high time", r"in the nick of time",
    r"once and for all", r"sooner or later", r"the eleventh hour",
    r"call it a day", r"time flies",
    # удар, поражение, неприятность
    r"kick(ed|ing)? (\w+ )?in the teeth", r"a slap in the face", r"the last straw",
    r"add insult to injury", r"rub salt", r"face the music", r"throw in the towel",
    r"bite the bullet", r"take the fall", r"hang (\w+ )?out to dry",
    # верность, отказ, предательство
    r"turn(ing|ed)? (my|his|her|your|their|\w+'s) back on", r"stab(bed)? .{0,12}in the back",
    r"stick to (my|his|her|your|their) guns", r"through thick and thin",
    r"leave (\w+ )?in the lurch", r"go out on a limb",
    # знание, догадка, сокрытие
    r"in the dark", r"jump to conclusions", r"read between the lines",
    r"put two and two together", r"the tip of the iceberg", r"spill the beans",
    r"let the cat out of the bag", r"get to the bottom of", r"draw a blank",
    r"hit the nail on the head", r"turn a blind eye", r"take .{0,20}with a grain of salt",
    r"hook, line,? and sinker", r"a shot in the dark", r"wild goose chase",
    r"beat around the bush", r"cut to the chase", r"in a nutshell",
    # согласие, отношения
    r"see eye to eye", r"on the same page", r"rub (\w+ )?the wrong way",
    r"a bone to pick", r"bury the hatchet", r"water under the bridge",
    r"give (\w+ )?the benefit of the doubt", r"hit it off",
    # риск, шанс, положение
    r"on thin ice", r"a long shot", r"a close call", r"cold feet",
    r"a sitting duck", r"back to square one", r"a dead end", r"up in the air",
    r"off the hook", r"in hot water", r"the ball is in", r"play it by ear",
    r"hold (your|his|her|their) horses", r"keep (your|his|her|their) (eyes peeled|cool|chin up)",
    r"drop the ball", r"miss the boat", r"break the ice", r"the whole nine yards",
    # речь о людях
    r"old man", r"a piece of work", r"pull(ing)? (my|his|her|your) leg",
    r"put (\w+ )?foot down", r"point the finger", r"make a scene",
    r"fall on deaf ears", r"wrap (my|his|her|your) head around",
    r"second thoughts", r"have a change of heart",
    # прочее ходовое
    r"piece of cake", r"out of the blue", r"under the weather",
    r"at the end of the day", r"easier said than done", r"no strings attached",
    r"the last thing (\w+ )?need", r"like a broken record", r"same old",
]

# ─────────────────────────────────────────────────────────────────────────────
# Кальки: пара «английский оборот → русская дословщина». Это уже не сито, а тест.
# ─────────────────────────────────────────────────────────────────────────────

Calque = collections.namedtuple("Calque", "en ru instead why")

# Первые семь — не общие соображения, а брак, который **дошёл до текста** и был
# разобран пользователем 11 августа 2026: docs/decisions.md, «Кальки с идиом».
# Остальные — тот же класс, пойманный заранее: английский оборот стоит целиком,
# а русский собран из его частей.
CALQUES = [
    Calque(r"come now", r"\bполнот[еа]\b|\bполно\b",
           "«Да будет вам», «Брось»", "«полноте» вышло из речи в XIX веке"),
    Calque(r"while it lasted", r"пока (это )?дл[ия]л",
           "«Недолго музыка играла»", "дословный оборот по-русски не живёт"),
    Calque(r"\bfirm\b", r"\bконтор[аыуеой]\b",
           "«фирма»", "«контора» тянет за собой «шарашкину»"),
    Calque(r"kick(ed|ing|s)? .{0,15}in the teeth", r"по зубам",
           "«огорошить»", "английское стёрто до незаметности, русское физически грубо"),
    Calque(r"\btaught\b", r"\bвыучил[аи]?\b",
           "«научил»", "«выучить кого-то чему-то» — не та валентность"),
    Calque(r"turn(ing|ed|s)? (my|his|her|your|their) back on",
           r"спиной поворач|поверн\w+ спиной|повернуться спиной",
           "«отвернуться»", "оборот разобран по частям вместо своей идиомы"),
    Calque(r"at the end of the day", r"в конце дня",
           "«в конечном счёте»", "по-русски это про время суток, а не про итог"),
    Calque(r"piece of cake", r"кусок (торта|пирога)",
           "«проще простого»", "русский кусок пирога — про долю, не про лёгкость"),
    Calque(r"the last straw", r"последн\w+ соломин",
           "«последняя капля»", "у русской идиомы другой предмет"),
    Calque(r"hit the nail on the head", r"(попал|ударил)\w* \w* ?гвозд",
           "«в точку»", "гвоздя в русском обороте нет"),
    Calque(r"wild goose chase", r"(погон|охот)\w+ за \w*гус",
           "«мартышкин труд», «гонять пустоту»", "гуся в русском обороте нет"),
    Calque(r"beat around the bush", r"(вокруг|около) куста",
           "«ходить вокруг да около»", "куст в русском обороте не участвует"),
    Calque(r"on the same page", r"на одной страниц",
           "«на одной волне»", "страница по-русски ничего не значит"),
    Calque(r"water under the bridge", r"вода под мостом",
           "«дело прошлое», «быльём поросло»", "мост в русском обороте не участвует"),
    Calque(r"cold feet", r"холодны[ех] ног",
           "«струсил», «пошёл на попятную»", "по-русски это буквально мёрзнут ноги"),
    Calque(r"a long shot", r"длинный выстрел",
           "«призрачный шанс»", "выстрела в русском обороте нет"),
    Calque(r"sitting duck", r"сидяч\w+ утк",
           "«лёгкая добыча»", "утка по-русски не значит беззащитности"),
    Calque(r"back to square one", r"к (первому )?квадрат",
           "«снова с нуля»", "квадрата в русском обороте нет"),
    Calque(r"spill the beans", r"(рассыпа|разлива|разли)\w* бобы",
           "«проболтаться»", "бобов в русском обороте нет"),
    Calque(r"let the cat out of the bag", r"кота из мешка",
           "«выдать себя»", "по-русски из мешка достают кота другого смысла"),
    Calque(r"benefit of the doubt", r"(выгод|польз)\w+ сомнени",
           "«поверить на слово»", "юридическая калька вместо живой речи"),
    Calque(r"give me a break", r"дай(те)? мне (перерыв|передышку)",
           "«да ладно», «хватит уже»", "английское — реакция, а не просьба о паузе"),
    Calque(r"face the music", r"(встрет|посмотр)\w+ \w* ?музык",
           "«держать ответ»", "музыки в русском обороте нет"),
    Calque(r"bite the bullet", r"(прикус|куса)\w* пул",
           "«стиснуть зубы»", "пули в русском обороте нет"),
    Calque(r"my two cents", r"(мои|свои) два цента",
           "«моё мнение», «если спросите меня»", "центы по-русски ничего не весят"),
    Calque(r"a piece of work", r"кусок работы",
           "«тот ещё фрукт»", "английское — о человеке, русское вышло о задании"),
]

# Адресные исключения: где дословный оборот оставлен намеренно, и почему.
# Ключ — идентификатор сегмента, тот же, что в work/case*.json.
ALLOWED = {
    # Решение пользователя 11 августа 2026: у Каниса тот же оборот был браком,
    # а у судьи Молотовой архаизм работает на образ — высокая размеренная речь
    # с религиозным оттенком, docs/voices.md. Править только случайную книжность.
    "sce1_c0_09.bytes|010004B9|0": "судья Молотова: архаизм по образу, не случайный",
    # Решение пользователя 12 августа 2026: «контора» — слово Защитина, его
    # просторечие. У Эджворта на том же `firm` стоит «фирма», и разнобой между
    # ними осмысленный, а не случайный: один говорит «биз», другой — как в суде.
    "sce1_c1_02.bytes|010008AD|33": "Защитин: «контора» — его просторечие, не калька",
    # 17 августа 2026: здесь `on the same page` стоит в прямом значении — речь
    # о листе альбома, на котором нарисованы все лица разом. Соседние сегменты
    # это подтверждают: «сперва я собирался нарисовать зал», «так и черкал их
    # всех подряд». Идиома «быть заодно» тут ни при чём, и «на одной странице» —
    # не калька, а перевод по смыслу.
    "sce2_c6_m0a_npc.bytes|0200245B|4": "прямое значение: лица нарисованы на одном листе альбома",
}


strip = lambda t: re.sub(r"\{[^}]*\}", "", t).replace("\n", " ")


def check_calques(cases: tuple[int, ...]) -> int:
    """Тест: английский оборот рядом с русской дословщиной. Ненулевой код — брак."""
    rx = [(c, re.compile(c.en, re.I), re.compile(c.ru, re.I)) for c in CALQUES]
    found: list[str] = []
    excused: list[str] = []
    checked = 0

    for case in cases:
        for e in load_entries(case):
            ru = e.get("ru")
            if not ru:
                continue
            checked += 1
            en, ru = strip(e["en"]), strip(ru)
            for calque, en_rx, ru_rx in rx:
                if not en_rx.search(en) or not ru_rx.search(ru):
                    continue
                if e["id"] in ALLOWED:
                    excused.append(f"{e['id']}: {ALLOWED[e['id']]}")
                    continue
                found.append(f"{e['id']}\n  EN: {en[:90]}\n  RU: {ru[:90]}\n"
                             f"  → {calque.instead}; {calque.why}")

    print(f"проверено переведённых сегментов: {checked}, пар в словаре: {len(CALQUES)}")
    if excused:
        print(f"\nоставлено намеренно ({len(excused)}):")
        for line in excused:
            print("  ", line)
    if found:
        print(f"\nКАЛЬКИ ({len(found)}) — английский оборот разобран по частям:")
        for line in found:
            print("  ", line)
        print("\nЛибо править перевод, либо — если оборот намеренный — вписать сегмент"
              "\nв ALLOWED в этом файле, вместе с причиной.")
        return 1

    print("\nOK — известных калек в переводе нет.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", default="2", help="дело, по умолчанию 2; all — все")
    ap.add_argument("--counts", action="store_true", help="только сводка по оборотам")
    ap.add_argument("--only", help="подстрока оборота: показать один")
    ap.add_argument("--untranslated", action="store_true",
                    help="показывать и непереведённые сегменты")
    ap.add_argument("--calques", action="store_true",
                    help="тест: русская дословщина напротив английского оборота")
    ap.add_argument("--list", action="store_true", help="показать словарь калек")
    args = ap.parse_args()

    cases = CASES if args.case == "all" else (int(args.case),)

    if args.list:
        print(f"{'английский оборот':38} {'русская калька':34} чем заменить")
        for c in CALQUES:
            print(f"{c.en[:37]:38} {c.ru[:33]:34} {c.instead}")
        print(f"\nвсего пар: {len(CALQUES)}, адресных исключений: {len(ALLOWED)}")
        return 0

    if args.calques:
        return check_calques(cases)

    pats = [p for p in IDIOMS if not args.only or args.only.lower() in p.lower()]
    if not pats:
        print(f"нет оборота по подстроке {args.only!r}")
        return 2
    rx = [(p, re.compile(p, re.I)) for p in pats]

    tally: dict[str, int] = {p: 0 for p in pats}
    hits = 0
    for case in cases:
        for e in load_entries(case):
            ru = e.get("ru") or ""
            if not ru and not args.untranslated:
                continue
            en = strip(e["en"])
            for pat, r in rx:
                if not r.search(en):
                    continue
                tally[pat] += 1
                hits += 1
                if not args.counts:
                    print(f"--- {e['id']}   [{pat}]")
                    print(f"  EN: {en}")
                    print(f"  RU: {strip(ru) if ru else '(не переведено)'}")
                break

    if args.counts:
        for pat, n in sorted(tally.items(), key=lambda kv: -kv[1]):
            if n:
                print(f"{n:>4}  {pat}")
    print(f"\nдело {args.case}: сегментов с оборотами {hits}, "
          f"оборотов сработало {sum(1 for n in tally.values() if n)} из {len(pats)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
