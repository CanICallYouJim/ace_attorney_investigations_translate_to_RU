"""Выложить переведённые реплики одного персонажа подряд — для редакторской вычитки.

who.py показывает файл целиком, всех говорящих вперемешку: так переводят. Здесь
задача обратная — увидеть одного персонажа сквозь всё дело, вне сцен. Регистр речи
съезжает незаметно: внутри своей сцены каждая реплика выглядит уместной, и только
полсотни реплик подряд показывают, что книжная речь Эджворта к третьей части стала
разговорной, а Кей растеряла восклицания. Это то, что не ловится в момент перевода.

Говорящий берётся из кода E101, как в who.py, **с переносом на следующие сегменты**:
код объявляется не в каждом, и без переноса теряется большая часть реплик персонажа
(speakers.py считает только явные — потому его числа меньше).

    python tools/reread.py                          # кто сколько переведён
    python tools/reread.py --id 0000                # Эджворт целиком, EN и RU
    python tools/reread.py --id 0002 --ru-only      # только русский: слышно язык, не точность
    python tools/reread.py --id 0000 --file sce1_c1 # один участок
    python tools/reread.py --id 0000 --grep "\\bты\\b"  # где он на «ты»

Идентификаторы персонажей — docs/voices.md, профили речи там же.
"""
from __future__ import annotations

import argparse
import collections
import re

from common import case_of, in_case_scope, load_entries, read_scripts
import segments as S
import tps as T
from who import NAMES, speaker_of


def walk(case: int | None, file_prefix: str = ""):
    """Пройти сегменты в порядке прохождения, отдавая (ключ, файл, говорящий, сегмент)."""
    eng = read_scripts("script_eng")
    for name in sorted(eng):
        if not in_case_scope(name) or not name.startswith(file_prefix):
            continue
        if case is not None and case_of(name) != case:
            continue
        for block in T.parse(eng[name]).blocks:
            current = None
            for idx, seg in enumerate(S.split(block.text)):
                who = speaker_of(seg)
                if who is not None:
                    current = who
                if seg.has_text():
                    yield f"{name}|{block.label_id:08X}|{idx}", name, current, seg


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", help="идентификатор персонажа, например 0000")
    ap.add_argument("--case", type=int, default=2, help="дело, по умолчанию 2")
    ap.add_argument("--file", default="", help="ограничить участком: sce1_c1")
    ap.add_argument("--grep", help="показать только реплики, где перевод совпал с этим regex")
    ap.add_argument("--ru-only", action="store_true", help="без английского")
    ap.add_argument("--codes", action="store_true", help="не прятать управляющие коды")
    args = ap.parse_args()

    entries = {e["id"]: e for e in load_entries(args.case)}
    names = NAMES.get(args.case, {})
    hide = (lambda t: t) if args.codes else (lambda t: re.sub(r"\{[^}]*\}", "", t))
    pattern = re.compile(args.grep) if args.grep else None

    if not args.id:
        # Сводка: сколько у кого переведено. Вычитывать имеет смысл готовое.
        tally: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
        for key, _name, who, _seg in walk(args.case, args.file):
            row = tally[who or "—"]
            row[0] += 1
            if entries.get(key, {}).get("ru"):
                row[1] += 1
        print(f"{'id':>6} {'персонаж':<14} {'реплик':>7} {'переведено':>11}")
        for who, (total, done) in sorted(tally.items(), key=lambda kv: -kv[1][1]):
            if done == 0:
                continue
            print(f"  {who:>4} {names.get(who, ''):<14} {total:>7} {done:>11}")
        print("\nВычитывать: tools/reread.py --id <id>")
        return 0

    want = args.id.upper()
    shown = 0
    for key, _name, who, seg in walk(args.case, args.file):
        if who != want:
            continue
        ru = entries.get(key, {}).get("ru")
        if not ru:
            continue
        if pattern and not pattern.search(ru):
            continue
        print(f"--- {key}  mode={seg.mode}")
        if not args.ru_only:
            _h, core, _t = seg.core()
            print(hide(T.to_markup(core)))
        print(hide(ru))
        print()
        shown += 1

    label = names.get(want, want)
    print(f"{label}: показано переведённых реплик {shown}")
    if pattern:
        print(f"(фильтр по переводу: {args.grep})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
