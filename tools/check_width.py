"""Проверить, влезает ли перевод таблиц в окно — по ширине букв, а не по их числу.

Символы считать бесполезно там, где окно узкое. Кириллица в этих гарнитурах
**шире латиницы**: у немцев средняя буква в описании улики занимает 0,55
кегельной ширины, у нас 0,59 — то есть при равном числе символов русская строка
на 7% длиннее немецкой. В окне реплики этот перекос съедает запас, в описании
улики запаса нет вовсе.

Так и уехала надпись в деле 2 (нашёл игрок, `gk2_item_text 102998757376`):

    англ.  suspect. He certainly ticks all the right boxes...   50 симв.  24,48 em
    нем.   um 7:00 Uhr, 12:00 Uhr und 21:00 Uhr. Beim           42 симв.  24,55 em
    рус.   Впрочем, я предпочитаю держать его в кармане.        45 симв.  26,45 em

Английский и немецкий независимо упираются в 24,5 em — вот ширина окна. Русская
строка короче английской на пять символов и при этом на два кегля длиннее: она
не помещается. `check_strings.py` этого не видел, потому что мерил символы
и брал максимум сразу по обоим языкам — 50 английских символов разрешали
45 русских.

Что делает. Ширина строки считается по метрикам той гарнитуры, которой игра
рисует текст, с уже наложенной правкой `patch_font_metrics.py`: кириллица там
пропорциональная, ширина места = очертания плюс два боковых отступа. Лимит
**на каждую таблицу свой** и замеряется по ней же — по самой широкой английской
или немецкой строке этой таблицы. Как и в `check_strings.py`: числами лимиты
не зашиты, их знает игра.

Окна реплик проверять этим не надо: там лимит 50/53 символа замерен по игре
и держит с запасом ([`docs/limits.md`](../docs/limits.md)). Прогон по делам 1–3
показал, что ни одна русская реплика не выходит за самую широкую английскую
того же дела. Узкие окна таблиц — другое дело.

    python tools/check_width.py            # только нарушения
    python tools/check_width.py --all      # ещё и замеренные лимиты по таблицам
    python tools/check_width.py --rebuild  # пересчитать work/glyph_widths.json из шрифта
"""
from __future__ import annotations

import argparse
import re
import sys

from common import WORK, load_json, save_json

WIDTHS = WORK / "glyph_widths.json"

# Гарнитура окна описаний. Одна на все таблицы: кегль у окон разный, но лимит
# берётся по самой таблице, а отношение ширин букв от кегля не зависит.
FONT = "FOT-MODEMINALARGEPRO-M"

MARKUP = re.compile(r"<[^<>]+>")

# Адресные исключения: запись, где замеренный лимит заведомо уже настоящего окна.
# Только с причиной и только вместе со строкой в docs/decisions.md.
EXCEPT: dict[str, str] = {}


def visible(text: str) -> str:
    """Текст без разметки TMP — только то, что реально занимает место в окне."""
    return MARKUP.sub("", text or "")


def load_widths() -> tuple[dict[int, int], int]:
    data = load_json(WIDTHS)
    if not data:
        print(f"нет {WIDTHS.name} — сначала tools/check_width.py --rebuild", file=sys.stderr)
        raise SystemExit(2)
    return {int(k): v for k, v in data["widths"].items()}, data["upm"]


def rebuild() -> int:
    """Достать метрики из backup/data.unity3d и сложить в work/glyph_widths.json.

    Отдельным шагом, а не при каждом прогоне: разбор бандла стоит полминуты,
    а таблица меняется только вместе с правкой шрифта.
    """
    from io import BytesIO

    import UnityPy
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.ttLib import TTFont

    from common import BACKUP
    from patch_font_metrics import CYRILLIC, DEFAULT_SIDEBEARING

    source = BACKUP / "data.unity3d"
    if not source.exists():
        print(f"нет {source} — сначала tools/backup.py", file=sys.stderr)
        return 1

    blob = None
    for obj in UnityPy.load(str(source)).objects:
        if obj.type.name != "Font":
            continue
        tree = obj.read_typetree()
        if tree.get("m_Name") == FONT:
            blob = bytes(tree.get("m_FontData") or b"")
            break
    if not blob:
        print(f"гарнитура {FONT} в бандле не найдена", file=sys.stderr)
        return 1

    font = TTFont(BytesIO(blob), fontNumber=0)
    cmap, hmtx = font.getBestCmap(), font["hmtx"]
    upm, glyphs = font["head"].unitsPerEm, font.getGlyphSet()

    # Латиница, знаки препинания, ёлочки, тире, кириллица — всё, из чего состоит
    # и оригинал, и перевод. Иероглифы не нужны: в русском слоте их не бывает.
    wanted = (set(range(0x20, 0x100)) | set(range(0x2010, 0x2040))
              | set(range(0x0400, 0x0460)) | {0x2116, 0x20AC})

    widths: dict[int, int] = {}
    for code in sorted(wanted):
        name = cmap.get(code)
        if name is None:
            continue
        advance = hmtx[name][0]
        # Ровно та же арифметика, что и в patch_font_metrics.py: в игре стоит
        # починенный шрифт, и мерить надо по нему, а не по исходному японскому.
        if code in CYRILLIC and advance == upm:
            pen = BoundsPen(glyphs)
            glyphs[name].draw(pen)
            if pen.bounds is None:
                continue
            x_min, _, x_max, _ = pen.bounds
            advance = round(x_max - x_min) + 2 * DEFAULT_SIDEBEARING
        widths[code] = advance

    save_json(WIDTHS, {"font": FONT, "upm": upm,
                       "sidebearing": DEFAULT_SIDEBEARING,
                       "widths": {str(k): v for k, v in widths.items()}})
    print(f"{WIDTHS.name}: {len(widths)} знаков из {FONT}, кегельная ширина {upm}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="показать замеренные лимиты")
    ap.add_argument("--rebuild", action="store_true", help="пересчитать таблицу метрик")
    args = ap.parse_args()

    if args.rebuild:
        return rebuild()

    widths, upm = load_widths()
    unknown: set[str] = set()

    def width(text: str, *, watch: bool = False) -> int:
        """Ширина строки в единицах шрифта.

        Незнакомый знак считаем полноширинным: в английском и немецком столбцах
        это иероглифы и стрелки интерфейса, для них 1000 единиц как раз верно.
        В русском переводе такого знака быть не должно — там про него говорим
        вслух (`watch`), иначе лимит молча посчитается по выдуманной ширине.
        """
        total = 0
        for ch in text:
            if ord(ch) in widths:
                total += widths[ord(ch)]
            else:
                if watch:
                    unknown.add(ch)
                total += upm
        return total

    data = load_json(WORK / "strings.json")
    if not data:
        print("нет work/strings.json — сначала tools/extract_strings.py")
        return 1

    problems: list[str] = []
    report: list[tuple[str, float, int, int]] = []

    for table, rows in sorted(data["tables"].items()):
        limit = 0
        for entry in rows.values():
            for lang in ("en", "de"):
                for line in visible(entry.get(lang)).split("\n"):
                    limit = max(limit, width(line))
        if not limit:
            continue

        checked = 0
        for key, entry in rows.items():
            ru = entry.get("ru")
            if not ru or f"{table} {key}" in EXCEPT:
                continue
            checked += 1
            for line in visible(ru).split("\n"):
                got = width(line, watch=True)
                if got > limit:
                    problems.append(
                        f"{table} {key}: {got / upm:.2f} em при окне {limit / upm:.2f} "
                        f"({len(line)} симв.) — {line!r}")
        report.append((table, limit / upm, len(rows), checked))

    if args.all:
        print(f"{'таблица':28} {'окно, em':>9} {'записей':>8} {'проверено':>10}")
        for table, limit, total, checked in report:
            print(f"{table:28} {limit:9.2f} {total:8} {checked:10}")
        print()

    if unknown:
        print("знаки без метрик (считаны полноширинными): "
              + " ".join(sorted(unknown)) + "\n", file=sys.stderr)

    for line in problems:
        print(line)
    total_checked = sum(c for _, _, _, c in report)
    print(f"\nстрок таблиц проверено: {total_checked}, шире окна: {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
