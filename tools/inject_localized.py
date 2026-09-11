"""Вставка своих картинок на место немецких — для надписей, которые хочется по-русски.

Парный к `swap_localized.py`. Тот отдаёт немецким адресам английские объекты;
этот кладёт в немецкий объект ваши пиксели и возвращает адрес на него обратно,
так что подмена и перерисовка не мешают друг другу и порядок запуска не важен.

Как пользоваться:

  1. Выгрузить оригиналы в полном разрешении — по ним рисовать:
         tools\\export_localized.py --scope gk2 --langs eng --full
  2. Нарисовать замену и сложить PNG в папку, имя файла — имя ассета без
     языкового хвоста: `cut01_027.png`, `Situation_0.png`, `efc_BigFont00.png`.
     Размер подгонять не нужно, он приводится к оригиналу.
  3. Вставить:
         tools\\inject_localized.py work\\localized_ru
         tools\\inject_localized.py work\\localized_ru --install
         tools\\inject_localized.py --install     # весь work\\graphics_ru, все дела

Без папки берётся весь русский слой `work/graphics_ru/<дело>/` — так его
ставит `make install` вместе с текстом.

`--list` показывает все имена, которые тут принимаются, с размерами оригиналов.

Про формат. Картинка пакуется в тот же формат, что был у оригинала: 402 из 451
немецкой текстуры лежат в BC7, остальные в RGBA32. BC7 умеет `etcpak`, который
и так стоит вместе с UnityPy; на текстуру 1440x1440 уходит около секунды, потери
на глаз незаметны (среднее отличие 0,01 из 255). `--raw` кладёт несжатым — вчетверо
тяжелее, зато мгновенно; годится, когда правок много и их гоняют по кругу.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import UnityPy
from PIL import Image, ImageChops, ImageStat
from UnityPy.enums import TextureFormat

from common import BUNDLES, HOST, WORK, game_is_running, load_json
from swap_localized import BUILD, LANG_KEY, NEVER, register_backup

RAW = int(TextureFormat.RGBA32)


def index() -> dict[str, list[tuple[str, str, str]]]:
    """Имя ассета без языкового хвоста -> [(бандл, адрес _ger, размер)].

    Берётся из переписи `scan_localized.py`, а не обходом бандлов: их 164 на семь
    гигабайт, и ради десятка картинок читать всё — это минуты вместо мгновения.

    Одно имя бывает в нескольких бандлах: FHD и Classic — две разные картинки
    одного и того же места, накрывать надо обе.
    """
    data = load_json(WORK / "localized_assets.json")
    if not data:
        sys.exit("нет work/localized_assets.json — сперва tools/scan_localized.py")

    out: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for fam in data["families"].values():
        if fam["type"] != "Texture2D" or HOST not in fam["variants"]:
            continue
        if any(bad in fam["bundle"] for bad in NEVER):
            continue
        base = LANG_KEY.sub("", fam["base"].split("/")[-1], count=1).rsplit(".", 1)[0]
        ger = fam["variants"][HOST]
        out[base].append((fam["bundle"], ger["path"], f"{ger.get('w')}x{ger.get('h')}"))
    return out


def do_list() -> None:
    idx = index()
    print(f"Принимаются {len(idx)} имён. Файл кладите как <имя>.png\n")
    for base, places in sorted(idx.items()):
        where = "; ".join(f"{b.split('_assets_all_')[0]} {size}" for b, _, size in places)
        print(f"  {base:34} {where}")


def flat(im: Image.Image) -> Image.Image:
    """Серая миниатюра для сравнения: прозрачное — на средний серый, а не в чёрный."""
    im = im.convert("RGBA")
    bg = Image.new("RGB", im.size, (128, 128, 128))
    bg.paste(im, mask=im.split()[3])
    return bg.convert("L").resize((64, 64))


def stored_flipped(env, key: str, src: Image.Image) -> bool:
    """Хранит ли бандл эту текстуру вверх ногами — по английскому соседу.

    Картинки на отдачу лежат лицом вверх, а бандлы хранят по-разному, и правило
    «по имени бандла» не держится: `gk2_idcom` и `gk2_logickeyword` перевёрнуты,
    а их двойники `_trial` (дело 1) — лицом вверх. Замер 12 сентября 2026; до него
    переворота здесь не было вовсе, хотя документы его обещали, и дело 1 уцелело
    только потому, что его бандлы лицом вверх.

    Надёжно одно: русская картинка совпадает с английской везде, кроме надписи,
    значит и класть её надо той стороной, какой она с английской совпадает.
    Английского соседа в бандле нет (плашки локали лежат в чужом) — как есть.
    """
    eng_key = re.sub(r"_ger(?=\.[^./]+$)", "_eng", key)
    if eng_key == key or eng_key not in env.container:
        return False
    eng = flat(env.container[eng_key].read().image)
    mine = flat(src)
    same = ImageStat.Stat(ImageChops.difference(mine, eng)).mean[0]
    flipped = ImageStat.Stat(ImageChops.difference(
        mine, eng.transpose(Image.FLIP_TOP_BOTTOM))).mean[0]
    return flipped < same


def patch(bundle_name: str, jobs: list[tuple[str, Path]], raw: bool) -> tuple[bytes, list[str]]:
    """Вписать картинки в немецкие текстуры бандла и вернуть им адреса."""
    env = UnityPy.load(str(BUNDLES / bundle_name))
    notes = []
    redirect_back: dict[str, int] = {}

    for key, png in jobs:
        obj = env.container[key]
        tex = obj.read()
        src = Image.open(png).convert("RGBA")
        if src.size != (tex.m_Width, tex.m_Height):
            notes.append(f"{png.name}: {src.size[0]}x{src.size[1]} -> {tex.m_Width}x{tex.m_Height}")
            src = src.resize((tex.m_Width, tex.m_Height), Image.LANCZOS)
        if stored_flipped(env, key, src):
            src = src.transpose(Image.FLIP_TOP_BOTTOM)
            notes.append(f"{png.name}: бандл хранит её вверх ногами — перевернул")

        want = RAW if raw else int(tex.m_TextureFormat)
        try:
            tex.set_image(src, target_format=want)
        except Exception as exc:  # noqa: BLE001 — упаковщика может не оказаться, это не повод падать
            notes.append(f"{png.name}: {TextureFormat(want).name} не упаковался ({exc}), кладу RGBA32")
            tex.set_image(src, target_format=RAW)
        tex.save()
        redirect_back[key] = obj.path_id

    # адрес мог быть уведён на английский вариант — вернуть его на свой объект
    ab = next(o for o in env.objects if o.type.name == "AssetBundle")
    tree = ab.read_typetree()
    fixed = 0
    for entry in tree["m_Container"]:
        key, info = entry
        want = redirect_back.get(key)
        if want is not None and info["asset"]["m_PathID"] != want:
            info["asset"]["m_PathID"] = want
            fixed += 1
    if fixed:
        ab.save_typetree(tree)
        notes.append(f"адресов возвращено с английских на свои: {fixed}")
    return env.file.save(packer="lz4"), notes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", nargs="?",
                    help="папка с PNG; по умолчанию work/graphics_ru со всеми делами")
    ap.add_argument("--install", action="store_true", help="поставить собранное в игру")
    ap.add_argument("--list", action="store_true", help="показать принимаемые имена")
    ap.add_argument("--raw", action="store_true",
                    help="класть несжатым (RGBA32): мгновенно, но вчетверо тяжелее")
    args = ap.parse_args()

    if args.list:
        do_list()
        return

    # Без папки — весь русский слой разом, work/graphics_ru/<дело>/*.png. Так его
    # ставит `make install`, и новое дело подхватывается без правки Makefile:
    # требование пользователя от 11 сентября 2026 — русские картинки ставятся
    # той же командой, что и текст, без отдельных флагов.
    folder = Path(args.folder) if args.folder else WORK / "graphics_ru"
    pngs = sorted(folder.rglob("*.png"))
    if not pngs:
        if args.folder:
            sys.exit(f"в {folder} нет PNG")
        # PNG в .gitignore: на свежем клоне их нет, и установка текста
        # не должна из-за этого падать.
        print(f"русских картинок нет ({folder}) — ставить нечего")
        return
    seen: dict[str, Path] = {}
    for png in pngs:
        if png.stem in seen:
            sys.exit(f"одна картинка лежит дважды: {seen[png.stem]} и {png} — "
                     f"какую ставить, не угадать")
        seen[png.stem] = png

    idx = index()
    jobs: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    unknown = []
    for png in pngs:
        places = idx.get(png.stem)
        if not places:
            unknown.append(png.name)
            continue
        for bundle_name, key, _ in places:
            jobs[bundle_name].append((key, png))
    if unknown:
        print(f"Не нашёл таких ассетов ({len(unknown)}): {', '.join(unknown[:8])}")
        print("Список принимаемых имён — с ключом --list\n")
    if not jobs:
        sys.exit("нечего вставлять")

    if args.install and game_is_running():
        sys.exit("GK12.exe запущен — закрой игру, файлы бандлов заблокированы.")

    BUILD.mkdir(parents=True, exist_ok=True)
    for bundle_name, items in sorted(jobs.items()):
        blob, notes = patch(bundle_name, items, args.raw)
        out = BUILD / bundle_name
        out.write_bytes(blob)
        print(f"  {bundle_name.split('_assets_all_')[0]:44} картинок: {len(items)}; {len(blob)/1024/1024:.1f} МБ")
        for note in notes:
            print(f"      {note}")
        if args.install:
            register_backup(bundle_name, BUNDLES / bundle_name)
            shutil.copy2(out, BUNDLES / bundle_name)
            print("      установлен")


if __name__ == "__main__":
    main()
