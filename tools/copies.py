"""Найти копии реплики: те же английские слова в других местах игры.

Разговор с напарником, служебные реплики, флешбэк, повторённый в другом деле, —
игра хранит их копиями, и по-русски копии обязаны совпадать (`check_repeats.py`),
кроме законной разницы: другой адресат, другая сторона границы «ты/вы».
Редактор, правящий одну сцену, видит только свою копию; этот инструмент
показывает все — с говорящим и нынешним русским, чтобы сразу было видно,
разошлись ли они уже.

    python tools/copies.py "sce3_c0_01.bytes|03000080|26"
    python tools/copies.py "sce3_c0_01.bytes|03000080|26" --json   # для скриптов
"""
from __future__ import annotations

import argparse
import json
import re

from common import case_of, load_entries, load_json
from scene_dump import PACK, name_of

CODES = re.compile(r"\{(?!\{)[^}]*\}")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", CODES.sub("", text)).strip()


def copies_of(key: str, entries: list[dict]) -> list[dict]:
    by_id = {e["id"]: e for e in entries}
    me = by_id[key]
    target = norm(me["en"])
    return [e for e in entries if e["id"] != key and norm(e["en"]) == target]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    entries = load_entries()
    if args.id not in {e["id"] for e in entries}:
        print(f"нет id {args.id} (ключ полный, с .bytes)")
        return 1
    speakers = load_json(PACK / "speakers.json", default={}) or {}
    me = next(e for e in entries if e["id"] == args.id)
    found = copies_of(args.id, entries)
    rows = [{"id": e["id"], "who": name_of(case_of(e["file"]), speakers.get(e["id"])),
             "ru": e["ru"], "same_ru": norm(e["ru"]) == norm(me["ru"])} for e in found]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0
    print(f"EN: {norm(me['en'])}\nRU: {norm(me['ru'])}\nкопий: {len(rows)}")
    for r in rows:
        mark = "=" if r["same_ru"] else "≠"
        print(f"  {mark} {r['id']} — {r['who']}: {norm(r['ru'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
