"""Английский эталон в `work/graphics_en/` совпадает с нетронутым бандлом.

Правило №13, строка «эталон берётся оттуда, куда мы не пишем». `work/graphics_en/` —
не эталон сам по себе, а **кеш** выгрузки: обычные PNG в рабочей папке, которые
живут между прогонами месяцами. По ним `prints.py` замеряет кегль английской
надписи, `sign.py` считает след логотипа и карту света, `paste_art.py` и
`relabel.py` берут фон. Стоит одному такому PNG разойтись с оригиналом —
и весь набор меряется не по игре, а по нашей же прошлой работе, причём молча:
у замера нет способа заметить, что эталон поддельный.

Разойтись он может тремя путями, и все три уже случались или стояли рядом:

  * выгрузка из **живой** папки игры вместо `backup/` — механизм 13 сентября 2026,
    когда сверка стороны текстуры сравнивала бандл сам с собой. Починено
    в `export_localized.py` 20 сентября, но кеш, снятый до починки, так и лежит;
  * **кадр-двойник, который сам стоит в очереди на перевод.** Для вывески
    `cut02_032` независимым источником служит `cut02_037` — тот самый кадр,
    который переводится следующим. Пока он английский, замер честен; как только
    станет русским, `sign.py` начнёт мерить сам себя. Нашёл агент 20 сентября;
  * правка руками — вырезка, подгонка, «я только посмотрю».

Проверка ничего не чинит: она открывает нетронутый бандл (`layer_localized.original()`,
то есть `backup/`), достаёт оттуда английский вариант картинки и сверяет с PNG
на диске пиксель в пиксель. Бандл читается один раз на все свои картинки.

**Сколько сверено — печатается всегда, и ноль сверенного это провал** (правило №7,
перенесённое на проверки: корзины «мы про неё не знали» не существует). Картинка,
у которой нет PNG в папке, в знаменатель не идёт — её просто ещё не выгружали;
картинка, у которой нет нетронутого бандла, идёт в находки.

    tools\\check_etalon.py                 сверить все дела
    tools\\check_etalon.py --case case3    одно дело
    tools\\check_etalon.py --selftest      проверка самой проверки
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import UnityPy
from PIL import Image, ImageChops

from common import WORK, load_json
from layer_localized import index, original, variants
from picture_layer import FLIP, leaf, short

EN = WORK / "graphics_en"
TOL = 0          # эталон обязан совпасть ровно: это тот же файл, а не пересжатие


def wanted(case: str | None) -> dict[str, list[tuple[str, Path, dict]]]:
    """{бандл: [(имя, путь к PNG, запись манифеста)]} — всё, что есть и на диске, и в манифесте."""
    out: dict[str, list[tuple[str, Path, dict]]] = defaultdict(list)
    for manifest in sorted(EN.glob("*/manifest.json")):
        if case and manifest.parent.name != case:
            continue
        for name, man in (load_json(manifest) or {}).items():
            png = manifest.parent / f"{name}.png"
            if png.exists():
                out[man["bundle"]].append((name, png, man))
    return out


def check(case: str | None = None, damage: dict[str, Image.Image] | None = None):
    """Сверяет кеш с нетронутыми бандлами. Возвращает (сверено, находки)."""
    damage = damage or {}
    seen, problems = 0, []
    for bundle, jobs in sorted(wanted(case).items()):
        # Адрес картинки в бандле лежит в переписи, а сам бандл — в `backup/`.
        # Одно имя бывает в нескольких бандлах (FHD и Classic); берём тот,
        # что назван в манифесте, иначе сверим не ту картинку.
        envs: dict[str, object] = {}
        for name, png, man in jobs:
            hits = [e for e in index().get(name, []) if short(e[0]) == bundle]
            if not hits:
                problems.append(f"{name}: в переписи нет для бандла {bundle} — "
                                f"перечитать tools/scan_localized.py")
                continue
            full, gerkey, _ = hits[0]
            if full not in envs:
                src = original(full)
                if src is None:
                    problems.append(f"{short(full)}: живой бандл уже переписан нами, "
                                    f"а в backup/ его нет — эталон брать неоткуда")
                    envs[full] = None
                else:
                    envs[full] = UnityPy.load(str(src))
            env = envs[full]
            if env is None:
                continue
            keys = {leaf(k).rsplit("_", 1)[-1] if leaf(k) != name else "base": k
                    for k in variants(gerkey, env.container)}
            key = keys.get(man.get("source_lang", "eng"))
            if key is None:
                problems.append(f"{name}: в нетронутом бандле нет варианта "
                                f"«{man.get('source_lang', 'eng')}»")
                continue
            was = env.container[key].read().image.convert("RGB")
            if man.get("flipped"):
                was = was.transpose(FLIP)
            now = damage.get(name) or Image.open(png).convert("RGB")
            seen += 1
            if now.size != was.size:
                problems.append(f"{name}: размер {now.size} против {was.size} в оригинале")
                continue
            diff = ImageChops.difference(now, was).convert("L")
            hist = diff.histogram()
            bad = sum(hist[TOL + 1:])
            if bad:
                peak = max(i for i, c in enumerate(hist) if c)
                problems.append(f"{name}: расходится с нетронутым бандлом — {bad} пикс., "
                                f"пик {peak}; это уже не эталон, перевыгрузить")
    return seen, problems


def selftest() -> int:
    """Посеянная порча обязана свалить проверку, а чистый кеш — пройти."""
    seen, problems = check("case3")
    if problems:
        print("  селфтест: чистый кеш дела 3 уже не проходит —", problems[0], file=sys.stderr)
        return 1
    if not seen:
        print("  селфтест: сверять нечего, проверка бессмысленна", file=sys.stderr)
        return 1
    print(f"  чистый кеш дела 3 проходит, сверено {seen}")

    # Порча сеется **по картинке**, а не по маске набора: один пиксель посреди кадра.
    name = "cut02_037"
    spoiled = Image.open(EN / "case3" / f"{name}.png").convert("RGB")
    x, y = spoiled.size[0] // 2, spoiled.size[1] // 2
    r, g, b = spoiled.getpixel((x, y))
    spoiled.putpixel((x, y), (255 - r, 255 - g, 255 - b))
    _, caught = check("case3", damage={name: spoiled})
    if not any(name in p for p in caught):
        print(f"  селфтест: подменённый пиксель в «{name}» проверка не заметила", file=sys.stderr)
        return 1
    print(f"  один подменённый пиксель в «{name}» проверка ловит")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", help="одно дело: case1 … case4, ui")
    ap.add_argument("--selftest", action="store_true", help="проверка самой проверки")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    seen, problems = check(args.case)
    for p in problems:
        print(f"  БЕДА: {p}", file=sys.stderr)
    print(f"  сверено картинок с нетронутыми бандлами: {seen}")
    if not seen:
        print("  ПУСТО — сверять нечего, а это провал, а не тишина", file=sys.stderr)
        return 2
    if problems:
        return 1
    print("  OK — английский эталон совпадает с оригиналом из backup/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
