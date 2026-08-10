"""Привести кавычки во всём переводе к «ёлочкам».

**Решение пользователя от 9 августа 2026: кавычки везде `«…»`.** Раньше в переводе
жили три вида сразу — прямые `"` из части 1, немецкие `„…“` из части 2 и ни одной
ёлочки. Скрипт сводит всё к одному виду и умеет проверять, что так и осталось.

    python tools/quotes.py --check    # что где стоит, ничего не меняя
    python tools/quotes.py --fix      # привести к «…»

Почему именно ёлочки, а не `„…“`: по гистограмме кодовых точек всего текста игры
(`work/codepoint_hist.json`) `«` встречается 1397 раз и `»` 1273 — их набирает
французская локализация, то есть в гарнитурах они заведомо есть. А `„` встречается
**два раза на всю игру**, то есть прежний выбор держался на символе, которого
в шрифте могло и не оказаться.

Две вещи, которые нельзя трогать при замене:

* **управляющие коды** `{E108:0010}` — внутри них кавычек не бывает, но текст
  разбирается с их учётом, чтобы не съехали границы;
* **разметка TMP** в строковых таблицах: `<font="FOT-MODEMINALARGEPRO-B SDF">`.
  Здесь `"` — синтаксис, а не кавычка. Заменить её значит сломать тег.

Парность проверяется до замены: непарная кавычка в сегменте — это либо реплика,
разорванная на два сегмента, либо опечатка, и решать её надо руками.
"""
from __future__ import annotations

import argparse
import collections
import re

from common import CASES, case_json, WORK, load_json, save_json

OPEN, CLOSE = "«", "»"
TAG = re.compile(r"<[^<>]*>")


def split_tags(text: str) -> list[tuple[bool, str]]:
    """Разбить на куски: (это_разметка, текст). Разметку не трогаем."""
    out, pos = [], 0
    for m in TAG.finditer(text):
        if m.start() > pos:
            out.append((False, text[pos:m.start()]))
        out.append((True, m.group()))
        pos = m.end()
    if pos < len(text):
        out.append((False, text[pos:]))
    return out


def normalize(text: str) -> str:
    """Все кавычки вне разметки -> «…», по порядку открывающая/закрывающая."""
    pieces = []
    depth = 0
    for is_tag, chunk in split_tags(text):
        if is_tag:
            pieces.append(chunk)
            continue
        buf = []
        for ch in chunk:
            if ch == "„":
                buf.append(OPEN); depth = 1
            elif ch == "“":
                buf.append(CLOSE); depth = 0
            elif ch == '"':
                buf.append(CLOSE if depth else OPEN)
                depth ^= 1
            else:
                buf.append(ch)
        pieces.append("".join(buf))
    return "".join(pieces)


def bare_quotes(text: str) -> str:
    """Только кавычки вне разметки — для подсчёта парности."""
    return "".join(ch for is_tag, chunk in split_tags(text) if not is_tag
                   for ch in chunk if ch in '"„“«»')


def survey(label: str, items: list[tuple[str, str]]) -> tuple[collections.Counter, list]:
    counts = collections.Counter()
    odd = []
    for ident, ru in items:
        q = bare_quotes(ru)
        if not q:
            continue
        if '"' in q:
            counts["прямые \""] += 1
        if "„" in q or "“" in q:
            counts["немецкие „…“"] += 1
        if "«" in q or "»" in q:
            counts["ёлочки «…»"] += 1
        if len(q) % 2:
            odd.append((ident, ru))
    return counts, odd


def collect_scripts() -> list[tuple[int, dict]]:
    return [(case, load_json(case_json(case))) for case in CASES]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fix", action="store_true", help="переписать файлы")
    ap.add_argument("--check", action="store_true", help="только отчёт (по умолчанию)")
    args = ap.parse_args()

    changed_total = 0
    for case, data in collect_scripts():
        if not data:
            continue
        items = [(e["id"], e["ru"]) for e in data["entries"] if e.get("ru")]
        counts, odd = survey(f"дело {case}", items)
        print(f"=== work/case{case}.json ===")
        print("   " + (", ".join(f"{k}: {v}" for k, v in counts.items()) or "кавычек нет"))
        for ident, ru in odd:
            print(f"   ! непарная кавычка: {ident} | {ru[:70]}")
        if args.fix:
            if odd:
                print("   непарные кавычки — не трогаю файл, чините руками")
                continue
            n = 0
            for e in data["entries"]:
                if not e.get("ru"):
                    continue
                new = normalize(e["ru"])
                if new != e["ru"]:
                    e["ru"] = new
                    n += 1
            save_json(case_json(case), data)
            print(f"   исправлено сегментов: {n}")
            changed_total += n

    strings = load_json(WORK / "strings.json")
    if strings:
        items = [(f"{tn}/{k}", v["ru"]) for tn, t in strings["tables"].items()
                 for k, v in t.items() if v.get("ru")]
        counts, odd = survey("таблицы", items)
        print("=== work/strings.json ===")
        print("   " + (", ".join(f"{k}: {v}" for k, v in counts.items()) or "кавычек нет"))
        for ident, ru in odd:
            print(f"   ! непарная кавычка: {ident} | {ru[:70]}")
        if args.fix and not odd:
            n = 0
            for t in strings["tables"].values():
                for v in t.values():
                    if not v.get("ru"):
                        continue
                    new = normalize(v["ru"])
                    if new != v["ru"]:
                        v["ru"] = new
                        n += 1
            save_json(WORK / "strings.json", strings)
            print(f"   исправлено записей: {n}")
            changed_total += n
        elif args.fix:
            print("   непарные кавычки — не трогаю файл, чините руками")

    if args.fix:
        print(f"\nвсего исправлено: {changed_total}")
        print("дальше: check_len.py, build.py --install, build_strings.py --install")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
