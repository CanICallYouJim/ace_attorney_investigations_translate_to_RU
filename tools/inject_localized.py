"""Вставка своих картинок на место немецких — для надписей, которые хочется по-русски.

Парный к `swap_localized.py`. Тот отдаёт немецким адресам английские объекты.
Этот собирает бандл с русскими картинками заново **из нетронутого оригинала**
(`backup/`): немецким адресам — английские объекты, как у `swap_localized.py`,
а где есть своя картинка — её пиксели в **немецкий** объект, и адрес остаётся ему.
Запись в бандл общая с патчером игрока (`picture_layer.write_bundle`), так что
`make install` и игрок получают бандл, собранный одним кодом.

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

Про сторону. Картинки на отдачу лежат лицом вверх, а бандлы хранят по-разному.
Сторону решает `layer_localized.stored_flipped` — по языковым вариантам той же
картинки в оригинале. До 13 сентября 2026 её решал английский сосед в живом
бандле, а сама вставка брала объект по адресу `_ger`, который после подмены вёл
на тот же английский: русское писалось в английские текстуры и сверялось само
с собой. Три картинки дела 1 так и встали в игру вверх ногами.

Про плашки ситуации (`Situation_0..6`, набирает `plates.py`). Это спрайты: пиксели
идут в их текстуру, сетка спрайта становится прямоугольником по русской надписи
(`picture_layer.write_sprite`). Сторона не голосуется — языковых вариантов в немецком
бандле нет, а плашка набрана лицом вверх по английской, раскодированной тем же
UnityPy. `Situation_0` и `Situation_1` игра берёт через таблицу картинок локали,
поэтому вместе с плашками собирается и таблица: их строки — на немецкие спрайты.

Про формат. Картинка пакуется в тот же формат, что был у оригинала: 402 из 451
немецкой текстуры лежат в BC7, остальные в RGBA32. BC7 умеет `etcpak`, который
и так стоит вместе с UnityPy; на текстуру 1440x1440 уходит около секунды, потери
на глаз незаметны (среднее отличие 0,01 из 255). `--raw` кладёт несжатым — вчетверо
тяжелее, зато мгновенно; годится, когда правок много и их гоняют по кругу.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import UnityPy
from PIL import Image

from common import BACKUP, BUNDLES, WORK, game_is_running
from layer_localized import index, original, stored_flipped
from picture_layer import FLIP, leaf, sprites_by_key, texture_of, write_bundle, write_splash
from plates import table_rows
from swap_localized import BUILD, IMAGE_TABLE_BUNDLE, plan_env, register_backup, swap_image_table


def do_list() -> None:
    idx = index()
    print(f"Принимаются {len(idx)} имён. Файл кладите как <имя>.png\n")
    for base, places in sorted(idx.items()):
        where = "; ".join(f"{b.split('_assets_all_')[0]} {size}" for b, _, size in places)
        print(f"  {base:34} {where}")


def load_splash() -> tuple[dict, Image.Image] | None:
    """Задание заставки «Возражение», если она набрана: куски и русский атлас."""
    spec_path = WORK / "graphics_ru" / "ui" / "splash.json"
    atlas_path = WORK / "graphics_ru" / "ui" / "splash_ger2.png"
    if not (spec_path.exists() and atlas_path.exists()):
        return None
    return json.loads(spec_path.read_text(encoding="utf-8")), Image.open(atlas_path).convert("RGBA")


def patch(bundle_name: str, jobs: list[tuple[str, Path]], raw: bool,
          splash: tuple[dict, Image.Image] | None = None) -> tuple[bytes, list[str], list[str]]:
    """Собрать бандл с картинками из нетронутого оригинала. Возвращает байты, заметки и плашки.

    Из оригинала, а не из живого файла: повторная установка не наслаивается
    на прежнюю и заодно лечит её — до 13 сентября 2026 в живых бандлах лежали
    русские пиксели на месте английских.
    """
    src = original(bundle_name)
    if src is None:
        sys.exit(f"{bundle_name}: бандл уже менялся, а оригинала в backup/ нет — собирать не из чего.\n"
                 f"Вернуть оригинал: Steam -> свойства игры -> Проверить целостность файлов.")
    env = UnityPy.load(str(src))
    notes = [] if src.parent == BACKUP else ["бэкапа нет, но бандл не менялся — собираю из живого"]
    sprites = sprites_by_key(env)
    pictures: dict[str, Image.Image] = {}
    plates: list[str] = []
    for key, png in jobs:
        img = Image.open(png).convert("RGBA")
        if key in sprites:
            tex = texture_of(env, sprites[key]).read()
            if img.size != (tex.m_Width, tex.m_Height):
                sys.exit(f"{png.name}: {img.size[0]}x{img.size[1]}, а текстура плашки "
                         f"{tex.m_Width}x{tex.m_Height} — набрать заново: tools/plates.py")
            pictures[key] = img
            plates.append(leaf(key))
            continue
        tex = env.container[key].read()
        if img.size != (tex.m_Width, tex.m_Height):
            notes.append(f"{png.name}: {img.size[0]}x{img.size[1]} -> {tex.m_Width}x{tex.m_Height}")
            img = img.resize((tex.m_Width, tex.m_Height), Image.LANCZOS)
        if stored_flipped(env, key, img):
            img = img.transpose(FLIP)
            notes.append(f"{png.name}: бандл хранит её вверх ногами — перевернул")
        pictures[key] = img
    pairs = plan_env(env)
    if splash is not None:
        spec, atlas = splash
        # Заставку игра берёт из немецкого префаба, и его адрес подмене не отдаётся:
        # уведи его на английский — на экране снова встанет `Rebuttal`.
        pairs = [(german, english) for german, english in pairs if german != spec["префаб"]]
        notes += write_splash(env, spec, atlas, raw)
    blob, more = write_bundle(env, pairs, pictures, raw)
    return blob, notes + more, plates


def plate_table(plates: list[str], install: bool) -> None:
    """Таблица картинок локали: строки русских плашек — на немецкие спрайты, остальное английское.

    `Situation_0` и `Situation_1` игра берёт через таблицу, а `swap_localized.py` увёл
    её строки на английские спрайты: без этого шага русские «Показания» и «Доводы»
    лежали бы в бандле, а на экране горели бы английские.
    """
    live = next(BUNDLES.glob(f"{IMAGE_TABLE_BUNDLE}_assets_all_*.bundle"))
    src = original(live.name)
    if src is None:
        sys.exit(f"{IMAGE_TABLE_BUNDLE}: таблица менялась, а оригинала в backup/ нет — немецких строк не взять")
    keep = table_rows(src, set(plates))
    blob, changed = swap_image_table(keep)
    out = BUILD / live.name
    out.write_bytes(blob)
    names = ", ".join(sorted(value.rsplit("[", 1)[-1].rstrip("]") for value in keep.values())) or "нет"
    print(f"  {IMAGE_TABLE_BUNDLE:44} таблица картинок: немецкими оставлены {len(keep)} ({names}), "
          f"изменено строк против живой: {changed}")
    if install:
        register_backup(live.name, live)
        shutil.copy2(out, live)
        print("      установлен")


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
    # Атлас заставки — не картинка на текстуру, а куски с рамками: он идёт своим
    # шагом, по заданию tools/splash.py, и в общий разбор по именам не попадает.
    splash = load_splash()
    pngs = [png for png in sorted(folder.rglob("*.png")) if png.name != "splash_ger2.png"]
    if not pngs and splash is None:
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
    splash_bundle = None
    if splash is not None:
        live = next(BUNDLES.glob(f"{splash[0]['бандл']}_assets_all_*.bundle"), None)
        if live is None:
            print(f"заставка набрана, а бандла {splash[0]['бандл']} в игре нет — пропускаю")
            splash = None
        else:
            splash_bundle = live.name
            jobs[splash_bundle]
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
    jobs = {name: items for name, items in jobs.items() if items or name == splash_bundle}

    if args.install and game_is_running():
        sys.exit("GK12.exe запущен — закрой игру, файлы бандлов заблокированы.")

    BUILD.mkdir(parents=True, exist_ok=True)
    plates: list[str] = []
    for bundle_name, items in sorted(jobs.items()):
        here = splash if bundle_name == splash_bundle else None
        blob, notes, done = patch(bundle_name, items, args.raw, here)
        plates += done
        out = BUILD / bundle_name
        out.write_bytes(blob)
        print(f"  {bundle_name.split('_assets_all_')[0]:44} картинок: {len(items)}"
              + ("; заставка «Возражение»" if here else "")
              + f"; {len(blob)/1024/1024:.1f} МБ")
        for note in notes:
            print(f"      {note}")
        if args.install:
            register_backup(bundle_name, BUNDLES / bundle_name)
            shutil.copy2(out, BUNDLES / bundle_name)
            print("      установлен")
    if plates:
        plate_table(plates, args.install)


if __name__ == "__main__":
    main()
