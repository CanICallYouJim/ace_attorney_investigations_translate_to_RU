"""Короткий отклик — проверить по предыдущей реплике, а не по себе самому.

Английский переспрашивает служебным глаголом: `You do?`, `There is?`, `It does?`,
`I am.` Смысла в них нет вовсе — он весь в предыдущей строке, и русский обязан
достать оттуда настоящий глагол:

    ...I have a recipe for a cure back at my mansion.  →  ...есть рецепт средства.
    You do?                                           →  Есть?

Ошибка выходит тихая: `check_len.py` зелёный, калькой это не считается, а сам
сегмент выглядит безупречно — до тех пор, пока не прочитать его вместе с соседом.

**Откуда берётся.** Из приёма «взять готовым»: непереведённые сегменты гоняются
против уже переведённых, и совпавшие слово в слово берутся даром
(`work/patch_prefill_case3.json`, 149 сегментов за раз). Для обычной реплики это
честно, для отклика — нет: английское `You do?` в двух сценах одинаковое, а русское
разное. Так «Есть?» из сцены про рецепт уехало в сцену про чайники, а «Объясним...?»
из разговора о настрое Победина — в разговор про лицо Эджворта. Обе нашёл игрок.

Что делает:

* **валит**, если один и тот же английский отклик переведён **одинаково в разных
  сценах**. Отклик повторяет глагол соседа, а соседи разные — совпадение почти
  всегда значит, что перевод скопирован. Отклики, годные после любой реплики
  («Да?», «Правда?», «Разве?»), перечислены в `FREE` — это и есть разрешённое
  совпадение;
* **показывает** по `--list` каждый отклик вместе с предыдущей репликой — так его
  и надо переводить. `--todo` берёт ещё не переведённые: для дел 4 и 5.

    python tools/check_echo.py                 # только нарушения, для check_all
    python tools/check_echo.py --list          # все отклики с соседом, глазами
    python tools/check_echo.py --todo --case 4 # что предстоит перевести
"""
from __future__ import annotations

import argparse
import collections
import re

from common import case_of, load_entries

SUBJECT = r"(?:I|you|he|she|it|we|they|there|that|this)"
AUX = (r"(?:do|does|did|is|are|was|were|am|have|has|had|will|would|can|could|"
       r"should|might|must|isn't|aren't|wasn't|weren't|don't|doesn't|didn't|"
       r"haven't|hasn't|hadn't|won't|can't|couldn't|shouldn't)")
ECHO = re.compile(rf"^(?:{SUBJECT}\s+{AUX}|{AUX}\s+{SUBJECT})\s*[.?!…]*$", re.I)

CODES = re.compile(r"\{[^}]*\}")

# Отклики, которые не повторяют ничего конкретного и потому законно совпадают
# в разных сценах. Пополнять только тем, что верно после **любой** реплики.
FREE = {
    "да?", "да...", "да.", "правда?", "разве?", "неужели?", "серьёзно?",
    "вот как?", "вот как...", "именно так.", "непременно.", "ага.", "ага?",
    "точно?", "верно?", "что?", "как?", "а?",
}


def plain(text: str) -> str:
    """Видимый текст: без управляющих кодов и без переносов внутри реплики."""
    return re.sub(r"\s+", " ", CODES.sub("", text or "")).strip()


def scan(case) -> list[tuple[str, str, str, str, str]]:
    """(дело, id, английский, русский, предыдущая русская) по всем откликам."""
    out = []
    for entry, previous in with_previous(case):
        english = plain(entry["en"])
        if ECHO.match(english):
            out.append((str(case_of(entry["id"])), entry["id"], english,
                        plain(entry.get("ru")), plain(previous.get("ru") if previous else "")))
    return out


def with_previous(case):
    """Сегменты подряд, каждый вместе с предыдущим сегментом того же блока.

    Отклик читается по соседу сверху, а соседство — внутри блока: между блоками
    ветвление, и предыдущий по файлу сегмент игроку мог не показываться вовсе.
    """
    by_block: dict[tuple[str, str], list] = collections.defaultdict(list)
    for entry in load_entries(case):
        by_block[(entry["file"], entry["block"])].append(entry)
    for block in by_block.values():
        block.sort(key=lambda e: e["index"])
        previous = None
        for entry in block:
            yield entry, previous
            previous = entry


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", default="all", help="номер дела или all")
    ap.add_argument("--list", action="store_true", help="показать отклики с соседом")
    ap.add_argument("--todo", action="store_true", help="ещё не переведённые")
    args = ap.parse_args()

    found = scan(None if args.case == "all" else int(args.case))
    done = [row for row in found if row[3]]
    todo = [row for row in found if not row[3]]

    if args.todo:
        for case, ident, english, _, previous_ru in todo:
            print(f"дело {case}  {ident}\n   ← {previous_ru[:70]}\n   = {english}")
        print(f"\nоткликов без перевода: {len(todo)}")
        return 0

    if args.list:
        for case, ident, english, russian, previous_ru in done:
            print(f"дело {case}  {ident}\n   ← {previous_ru[:70]}"
                  f"\n   = {english}  →  {russian}")
        print()

    # Совпал перевод в разных сценах — почти наверняка скопирован.
    by_pair: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    for _, ident, english, russian, _ in done:
        if russian.lower() not in FREE:
            by_pair[(english.lower(), russian)].append(ident)

    problems = []
    for (english, russian), ids in sorted(by_pair.items()):
        blocks = {ident.rsplit("|", 1)[0] for ident in ids}
        if len(blocks) > 1:
            problems.append(f"{english!r} → {russian!r} в разных сценах: "
                            + ", ".join(sorted(ids)))

    for line in problems:
        print(line)
    print(f"\nоткликов переведено: {len(done)}, скопированных на чужую реплику: "
          f"{len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
