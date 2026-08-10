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
    python tools/find_idioms.py --counts        # только сводка по оборотам
    python tools/find_idioms.py --only "teeth"  # один оборот
    python tools/find_idioms.py --untranslated  # включая ещё не переведённые

Список неполон по устройству — это сито, а не доказательство. Пополнять его
при каждой новой пойманной кальке: правило и разбор класса — в
docs/decisions.md, раздел «Правило, которое из этого следует».
"""
from __future__ import annotations

import argparse
import re

from common import load_entries

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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", type=int, default=2, help="дело, по умолчанию 2")
    ap.add_argument("--counts", action="store_true", help="только сводка по оборотам")
    ap.add_argument("--only", help="подстрока оборота: показать один")
    ap.add_argument("--untranslated", action="store_true",
                    help="показывать и непереведённые сегменты")
    args = ap.parse_args()

    pats = [p for p in IDIOMS if not args.only or args.only.lower() in p.lower()]
    if not pats:
        print(f"нет оборота по подстроке {args.only!r}")
        return 2
    rx = [(p, re.compile(p, re.I)) for p in pats]
    strip = lambda t: re.sub(r"\{[^}]*\}", "", t).replace("\n", " ")

    tally: dict[str, int] = {p: 0 for p in pats}
    hits = 0
    for e in load_entries(args.case):
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
