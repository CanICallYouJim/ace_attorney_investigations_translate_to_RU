"""Извлечь реплики дела 2 в редактируемый work/case2.json.

Единица перевода — сегмент блока (см. tools/segments.py). Адрес сегмента —
файл + идентификатор блока + порядковый номер — не зависит от длины текста,
поэтому перевод переживает любые правки формулировок.

Управляющие коды внутри реплики показаны метками вида {E108:0010}: их нужно
сохранять в переводе как есть, они несут паузы, интонации и выделения.

Скрипт не затирает уже сделанный перевод: если английский оригинал сегмента
не изменился, поле "ru" переносится из прошлого запуска.

    python tools/extract.py
"""
from __future__ import annotations

import collections

from common import WORK, in_case_scope, load_json, read_scripts, save_json
import segments as S
import tps as T

OUT = WORK / "case2.json"


def main() -> int:
    eng = read_scripts("script_eng")
    previous = {e["id"]: e for e in (load_json(OUT, default={}) or {}).get("entries", [])}

    entries = []
    skipped = 0
    for name in sorted(eng):
        if not in_case_scope(name):
            continue
        for block in T.parse(eng[name]).blocks:
            for idx, seg in enumerate(S.split(block.text)):
                if not seg.has_text():
                    skipped += 1
                    continue
                key = f"{name}|{block.label_id:08X}|{idx}"
                _head, core, _tail = seg.core()
                english = T.to_markup(core)
                old = previous.get(key)
                keep = bool(old) and old.get("en") == english
                entries.append({
                    "id": key,
                    "file": name,
                    "block": f"{block.label_id:08X}",
                    "index": idx,
                    "mode": seg.mode,
                    "en": english,
                    "ru": old["ru"] if keep else "",
                    "status": old.get("status", "pending") if keep else "pending",
                })

    save_json(OUT, {"case": 2, "source": "gk2 eng", "entries": entries})

    by_file = collections.Counter(e["file"] for e in entries)
    plain = sum(len(T.detokenize([t for t in T.from_markup(e["en"]) if isinstance(t, str)]))
                for e in entries)
    print(f"файлов дела 2:        {len(by_file)}")
    print(f"сегментов с текстом:  {len(entries)}")
    print(f"сегментов без текста: {skipped} (чистая логика, не переводится)")
    print(f"собственно текста:    {plain:,} символов")
    print(f"уже переведено:       {sum(1 for e in entries if e['ru'])}")
    print(f"\n-> {OUT}")
    print("\nкрупнейшие файлы:")
    for name, n in by_file.most_common(8):
        print(f"   {n:4d}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
