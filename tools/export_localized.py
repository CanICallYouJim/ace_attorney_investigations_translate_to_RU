"""Выгрузка локализованной графики из бандлов — посмотреть, что вообще написано на картинках.

Работает по переписи `work/localized_assets.json` (её делает `scan_localized.py`).
Кладёт PNG в `work/localized/<бандл>/<имя>_<язык>.png` и, по флагу, собирает
контактные листы — сетку миниатюр с подписями, по одному листу на бандл.

    .venv\\Scripts\\python.exe tools\\export_localized.py --scope gk2
    .venv\\Scripts\\python.exe tools\\export_localized.py --scope gk2 --sheet
    .venv\\Scripts\\python.exe tools\\export_localized.py --bundle upcutlocal --full

По умолчанию картинки ужимаются до 384 px по длинной стороне: их сотни и они
до 3840x2160. `--full` выгружает в оригинальном разрешении — для работы в редакторе.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict

import UnityPy
from PIL import Image, ImageDraw

from common import BUNDLES, WORK, load_json
from layer_localized import original

OUT = WORK / "localized"
THUMB = 384


def pick(fams: dict, scope: str, bundle_filter: str | None, langs: tuple[str, ...]) -> dict[str, list]:
    """Семьи Texture2D, у которых есть хоть один из нужных языков, сгруппированные по бандлу."""
    groups: dict[str, list] = defaultdict(list)
    for fam in fams.values():
        if fam["type"] != "Texture2D":
            continue
        if bundle_filter and bundle_filter not in fam["bundle"]:
            continue
        if scope != "all" and not fam["bundle"].startswith(scope):
            continue
        if not any(lang in fam["variants"] for lang in langs):
            continue
        groups[fam["bundle"]].append(fam)
    return groups


def short(name: str) -> str:
    """Имя бандла без хеша: `gk2_upcutlocal_assets_all_e93c...bundle` -> `gk2_upcutlocal`."""
    return name.split("_assets_all_")[0]


def export(groups: dict[str, list], langs: tuple[str, ...], full: bool) -> dict[str, list]:
    """Выгружает PNG. Возвращает {бандл: [(имя, {язык: путь к png})]}."""
    result: dict[str, list] = {}
    for bundle_name, fams in sorted(groups.items()):
        wanted = {v["path"]: (fam, lang)
                  for fam in fams for lang, v in fam["variants"].items() if lang in langs}
        # Эталон выгружается только из **нетронутого** бандла: живой мы сами
        # переписываем `make install`, и после первой же установки «английская»
        # картинка стала бы нашей русской. Ровно этим механизмом 13 сентября 2026
        # вставка сверяла сторону текстуры сама с собой и сходилась.
        src = original(bundle_name)
        if src is None:
            sys.exit(f"{short(bundle_name)}: живой бандл уже переписан нами, а в backup/ "
                     f"его нет — эталон брать неоткуда. Вернуть оригинал: tools/restore.py")
        env = UnityPy.load(str(src))
        dest = OUT / short(bundle_name)
        dest.mkdir(parents=True, exist_ok=True)

        saved: dict[str, dict[str, str]] = defaultdict(dict)
        for asset_path, obj in env.container.items():
            if asset_path not in wanted:
                continue
            fam, lang = wanted[asset_path]
            img = obj.read().image
            if not full:
                img = img.copy()
                img.thumbnail((THUMB, THUMB))
            base = fam["base"].split("/")[-1].rsplit(".", 1)[0]
            png = dest / f"{base}_{lang}.png"
            img.save(png)
            saved[base][lang] = str(png)
        result[bundle_name] = sorted(saved.items())
        print(f"{short(bundle_name):34} {sum(len(v) for _, v in saved.items()):4} png -> {dest}")
    return result


def sheet(bundle_name: str, rows: list, langs: tuple[str, ...]) -> None:
    """Контактный лист: строка на ассет, колонка на язык, подписи именами файлов."""
    cell, pad, label = THUMB, 8, 22
    cols = len(langs)
    w = pad + cols * (cell + pad)
    h = pad + len(rows) * (cell + label + pad)
    canvas = Image.new("RGB", (w, h), (28, 28, 32))
    draw = ImageDraw.Draw(canvas)

    for r, (base, by_lang) in enumerate(rows):
        y = pad + r * (cell + label + pad)
        draw.text((pad, y + cell + 4), f"{base}   [{', '.join(sorted(by_lang))}]", fill=(210, 210, 215))
        for c, lang in enumerate(langs):
            x = pad + c * (cell + pad)
            path = by_lang.get(lang)
            if not path:
                draw.text((x + 4, y + cell // 2), f"нет {lang}", fill=(120, 120, 125))
                continue
            img = Image.open(path).convert("RGBA")
            img.thumbnail((cell, cell))
            # шахматка под альфой — иначе прозрачные надписи не видно на тёмном фоне
            tile = Image.new("RGBA", img.size, (255, 255, 255, 255))
            for ty in range(0, img.size[1], 16):
                for tx in range(0, img.size[0], 16):
                    if (tx // 16 + ty // 16) % 2:
                        tile.paste((205, 205, 210, 255), (tx, ty, min(tx + 16, img.size[0]), min(ty + 16, img.size[1])))
            tile.alpha_composite(img)
            canvas.paste(tile.convert("RGB"), (x, y + (cell - img.size[1]) // 2))
            draw.text((x + 2, y + 2), lang, fill=(255, 220, 120))

    out = OUT / f"sheet_{short(bundle_name)}.png"
    canvas.save(out)
    print(f"лист: {out}  ({len(rows)} строк)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="gk2", help="префикс бандла: gk2 / gk1 / gk_ / localization / all")
    ap.add_argument("--bundle", help="подстрока имени бандла")
    ap.add_argument("--langs", default="ger,eng")
    ap.add_argument("--full", action="store_true", help="без уменьшения")
    ap.add_argument("--sheet", action="store_true", help="собрать контактные листы")
    args = ap.parse_args()

    data = load_json(WORK / "localized_assets.json")
    if not data:
        sys.exit("нет work/localized_assets.json — сперва tools/scan_localized.py")

    langs = tuple(args.langs.split(","))
    groups = pick(data["families"], args.scope, args.bundle, langs)
    if not groups:
        sys.exit("под фильтр ничего не попало")

    exported = export(groups, langs, args.full)
    if args.sheet:
        for bundle_name, rows in exported.items():
            if rows:
                sheet(bundle_name, rows, langs)


if __name__ == "__main__":
    main()
