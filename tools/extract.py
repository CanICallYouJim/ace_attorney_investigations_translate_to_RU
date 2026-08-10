"""Извлечь реплики дела в редактируемый work/case{N}.json.

Единица перевода — сегмент блока (см. tools/segments.py). Адрес сегмента —
файл + идентификатор блока + порядковый номер — не зависит от длины текста,
поэтому перевод переживает любые правки формулировок.

Управляющие коды внутри реплики показаны метками вида {E108:0010}: их нужно
сохранять в переводе как есть, они несут паузы, интонации и выделения.

Скрипт не затирает уже сделанный перевод: если английский оригинал сегмента
не изменился, поле "ru" переносится из прошлого запуска.

    python tools/extract.py            # все дела в работе, каждое в свой файл
    python tools/extract.py --case 3   # только дело 3 -> work/case3.json
"""
from __future__ import annotations

import argparse
import collections

from common import (CASES, case_json, case_prefixes, load_json, read_scripts,
                    save_json)
import segments as S
import tps as T


def extract_case(case: int, eng: dict[str, bytes]) -> int:
    out = case_json(case)
    previous = {e["id"]: e for e in (load_json(out, default={}) or {}).get("entries", [])}
    prefixes = case_prefixes(case)

    entries = []
    skipped = 0
    for name in sorted(eng):
        if not name.lower().startswith(prefixes):
            continue
        # Метка блока в файле не уникальна, и в sce2_opening.bytes все одиннадцать
        # блоков помечены FFFFFFFF: адрес «файл|метка|номер» слипался в один на всех,
        # и патч мог дотянуться только до последнего. Повторы нумеруются с двойки.
        seen: collections.Counter = collections.Counter()
        for block in T.parse(eng[name]).blocks:
            for idx, seg in enumerate(S.split(block.text)):
                if not seg.has_text():
                    skipped += 1
                    continue
                label = f"{block.label_id:08X}"
                seen[(label, idx)] += 1
                nth = seen[(label, idx)]
                key = f"{name}|{label}|{idx}" if nth == 1 else f"{name}|{label}#{nth}|{idx}"
                _head, core, _tail = seg.core()
                english = T.to_markup(core)
                old = previous.get(key)
                keep = bool(old) and old.get("en") == english
                entries.append({
                    "id": key,
                    "file": name,
                    "block": label,
                    "index": idx,
                    "mode": seg.mode,
                    "en": english,
                    "ru": old["ru"] if keep else "",
                    "status": old.get("status", "pending") if keep else "pending",
                })

    save_json(out, {"case": case, "source": "gk2 eng", "entries": entries})

    by_file = collections.Counter(e["file"] for e in entries)
    plain = sum(len(T.detokenize([t for t in T.from_markup(e["en"]) if isinstance(t, str)]))
                for e in entries)
    print(f"=== дело {case} ===")
    print(f"файлов:               {len(by_file)}")
    print(f"сегментов с текстом:  {len(entries)}")
    print(f"сегментов без текста: {skipped} (чистая логика, не переводится)")
    print(f"собственно текста:    {plain:,} символов")
    print(f"уже переведено:       {sum(1 for e in entries if e['ru'])}")
    print(f"-> {out}")
    print("крупнейшие файлы:")
    for name, n in by_file.most_common(8):
        print(f"   {n:4d}  {name}")
    print()
    return len(entries)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", type=int, choices=CASES, help="только это дело")
    args = ap.parse_args()

    eng = read_scripts("script_eng")
    total = sum(extract_case(case, eng) for case in (CASES if args.case is None else (args.case,)))
    print(f"всего сегментов в работе: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
