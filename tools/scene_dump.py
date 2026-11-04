"""Сцена целиком для сплошной вычитки: кто говорит, английский, немецкий/французский, русский.

Порция редактора в проходе ноября 2026 — одна сцена (файл скрипта). Ему нужно видеть
её подряд, как в игре, с говорящим у каждой реплики, — иначе не выбрать ни ты/вы,
ни регистр. Говорящие и чужие языки берутся из `work/review/` (выгружает
`tools/export_review_pack.py` на машине с игрой); если пакета нет, колонка
говорящего пустая и это честно написано в шапке.

    python tools/scene_dump.py sce3_c0_01                 # одна сцена, en+ru
    python tools/scene_dump.py sce3_c0_01 --langs ger,fre # плюс немецкий и французский
    python tools/scene_dump.py sce3_c0_01 --ru-only       # только русский, как слышит игрок
    python tools/scene_dump.py sce3_c0_01 --cast          # кто говорит и сколько
    python tools/scene_dump.py --list 4                   # сцены дела 4 по порядку, с числом реплик
"""
from __future__ import annotations

import argparse
import collections
import re

from common import WORK, case_of, load_entries, load_json
from who import NAMES

PACK = WORK / "review"
CODES = re.compile(r"\{(?!\{)[^}]*\}")


def plain(text: str) -> str:
    return CODES.sub("", text or "").replace("\n", " / ")


def load_pack(langs: list[str]):
    speakers = load_json(PACK / "speakers.json", default=None)
    locales = {lang: load_json(PACK / "locales" / f"{lang}.json", default={}) or {}
               for lang in langs}
    return speakers, locales


def name_of(case: int | None, slot: str | None) -> str:
    if slot is None:
        return "?"
    return NAMES.get(case, {}).get(slot, slot)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="имя файла или его начало, например sce3_c0_01")
    ap.add_argument("--langs", default="", help="чужие языки через запятую: ger,fre,...")
    ap.add_argument("--ru-only", action="store_true", help="только русский")
    ap.add_argument("--codes", action="store_true", help="не вырезать управляющие коды")
    ap.add_argument("--cast", action="store_true", help="кто говорит в сцене и сколько реплик")
    ap.add_argument("--list", type=int, metavar="N", help="список сцен дела N")
    args = ap.parse_args()

    entries = load_entries()
    if args.list is not None:
        counts = collections.Counter(e["file"] for e in entries if case_of(e["file"]) == args.list)
        for name, n in counts.items():
            print(f"{name}\t{n}")
        return 0
    if not args.file:
        ap.error("нужно имя файла или --list N")

    langs = [x for x in args.langs.split(",") if x]
    speakers, locales = load_pack(langs)
    if speakers is None:
        print("! нет work/review/speakers.json — говорящие неизвестны (make review-pack на машине с игрой)")

    if args.cast:
        cast = collections.Counter(
            name_of(case_of(e["file"]), (speakers or {}).get(e["id"]))
            for e in entries if e["file"].startswith(args.file))
        for who, n in cast.most_common():
            print(f"{who}\t{n}")
        return 0

    show = (lambda t: t) if args.codes else plain
    last_file = None
    for e in entries:
        if not e["file"].startswith(args.file):
            continue
        if e["file"] != last_file:
            print(f"\n=== {e['file']} ===")
            last_file = e["file"]
        who = name_of(case_of(e["file"]), (speakers or {}).get(e["id"]))
        if args.ru_only:
            print(f"[{e['block']}|{e['index']}] {who}: {show(e['ru'])}")
            continue
        print(f"\n#{e['id']}  — {who}")
        print(f"  EN: {show(e['en'])}")
        for lang in langs:
            other = locales.get(lang, {}).get(e["id"])
            if other:
                print(f"  {lang.upper()}: {show(other)}")
        print(f"  RU: {show(e['ru'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
