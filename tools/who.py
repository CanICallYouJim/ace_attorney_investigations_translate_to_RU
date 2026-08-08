"""Показать, кто говорит в каждом сегменте — с текстом и уже сделанным переводом.

speakers.py группирует реплики по персонажу и нужен для составления профилей речи.
Здесь задача обратная и ежедневная: сесть за конкретный файл и видеть подряд, кто
что говорит. Без этого невозможно применить docs/voices.md — регистр речи выбирается
по говорящему, а в самом тексте реплики его имени нет.

Говорящий кодируется параметром кода E101 в преамбуле сегмента; нумерация сегментов
совпадает с extract.py, поэтому идентификаторы те же, что в work/case2.json.

    python tools/who.py sce1_c0_02              # один файл
    python tools/who.py sce1_c0_0 --todo        # все совпадающие, только непереведённое
"""
from __future__ import annotations

import argparse

from common import WORK, in_case_scope, load_json, read_scripts
import segments as S
import tps as T

SPEAKER_OP = 0xE101

# Кто есть кто — из docs/voices.md. Служебные слоты помечены так же, как там.
NAMES = {
    "0000": "Эджворт",
    "0001": "Гамшу",
    "0002": "Кей",
    "0007": "Ланг",
    "0009": "Молотова",
    "000A": "Победин",
    "000B": "Защитин",
    "0015": "Канис",
    "0016": "Святов",
    "0017": "Карчерато",
    "0018": "Лястраж",
    "0019": "Видалл",
    "001A": "циркачка",
    "002A": "охранник",
    "003D": "?сборный",
    "003E": "?сборный",
    "003F": "органайзер",
    "0041": "плашка",
}


def speaker_of(seg: S.Segment) -> str | None:
    """Идентификатор говорящего, если он объявлен в преамбуле сегмента."""
    head, _core, _tail = seg.core()
    for tok in list(seg.prefix) + list(head):
        if isinstance(tok, T.Op) and tok.code == SPEAKER_OP and len(tok.params) == 2:
            return f"{ord(tok.params[1]):04X}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", help="имя файла или его начало, например sce1_c0_02")
    ap.add_argument("--todo", action="store_true", help="только непереведённые сегменты")
    args = ap.parse_args()

    done = {e["id"]: e for e in (load_json(WORK / "case2.json", default={}) or {}).get("entries", [])}
    eng = read_scripts("script_eng")

    # Говорящий объявляется не в каждом сегменте: если код E101 не встретился,
    # реплику продолжает тот же персонаж, что и раньше.
    shown = 0
    for name in sorted(eng):
        if not in_case_scope(name) or not name.startswith(args.file):
            continue
        for block in T.parse(eng[name]).blocks:
            current = None
            for idx, seg in enumerate(S.split(block.text)):
                who = speaker_of(seg)
                if who is not None:
                    current = who
                if not seg.has_text():
                    continue
                key = f"{name}|{block.label_id:08X}|{idx}"
                entry = done.get(key, {})
                if args.todo and entry.get("ru"):
                    continue
                label = NAMES.get(current, current or "—")
                _h, core, _t = seg.core()
                print(f"### {key}  mode={seg.mode}  [{label}]")
                print(T.to_markup(core))
                if entry.get("ru"):
                    print(f"RU: {entry['ru']}")
                print()
                shown += 1

    print(f"показано сегментов: {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
