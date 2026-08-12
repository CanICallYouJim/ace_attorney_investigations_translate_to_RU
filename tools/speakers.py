"""Сгруппировать реплики дела 2 по говорящему.

Говорящий кодируется параметром кода E101 в преамбуле сегмента: первое слово всегда
FFFF, второе — идентификатор персонажа внутри дела (0000 у Эджворта, 0002 у Кей,
002A у охранника и так далее). Имя из нейм-тега в скрипте не лежит, поэтому кто есть
кто определяется по репликам — зато сама группировка точная.

Нужно для docs/voices.md: чтобы профиль речи каждого персонажа строился на его
настоящих репликах, а не на впечатлении.

    python tools/speakers.py            # сводка: кто сколько говорит
    python tools/speakers.py --id 0002  # реплики одного персонажа
"""
from __future__ import annotations

import argparse
import collections

from common import in_case_scope, read_scripts_all
import segments as S
import tps as T

SPEAKER_OP = 0xE101


def speaker_of(seg: S.Segment) -> str | None:
    head, _core, _tail = seg.core()
    for tok in list(seg.prefix) + list(head):
        if isinstance(tok, T.Op) and tok.code == SPEAKER_OP and len(tok.params) == 2:
            return f"{ord(tok.params[1]):04X}"
    return None


def collect() -> dict[str, list[tuple[str, str]]]:
    """id говорящего -> [(файл, текст реплики)]."""
    eng = read_scripts_all("eng")
    lines: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    for name in sorted(eng):
        if not in_case_scope(name):
            continue
        for block in T.parse(eng[name]).blocks:
            for seg in S.split(block.text):
                if not seg.has_text():
                    continue
                _h, core, _t = seg.core()
                text = "".join(t for t in core if isinstance(t, str)).replace("\n", " ")
                who = speaker_of(seg)
                if who is not None:
                    lines[who].append((name, text.strip()))
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--id", help="показать реплики персонажа с этим идентификатором")
    ap.add_argument("--n", type=int, default=14, help="сколько реплик показать")
    args = ap.parse_args()

    lines = collect()
    if args.id:
        rows = lines.get(args.id.upper(), [])
        print(f"персонаж {args.id.upper()}: {len(rows)} реплик\n")
        step = max(1, len(rows) // args.n)
        for name, text in rows[::step][:args.n]:
            print(f"  [{name}] {text[:110]}")
        return 0

    total = sum(len(v) for v in lines.values())
    print(f"реплик с известным говорящим: {total}")
    print(f"различных персонажей:         {len(lines)}\n")
    print(f"{'id':>6} {'реплик':>7}  первая реплика")
    for who, rows in sorted(lines.items(), key=lambda kv: -len(kv[1])):
        if len(rows) < 15:
            continue
        print(f"  {who:>4} {len(rows):>7}  {rows[0][1][:78]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
