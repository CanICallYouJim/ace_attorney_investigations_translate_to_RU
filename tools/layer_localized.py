"""Слой русских надписей для патчера: снять, сверить и показать.

Картинку из `work/graphics_ru` игроку не отдать — она на девять десятых рисунок
Capcom. Отдаётся слой: пиксели, которыми русская картинка отличается от
английской, и рецепт уменьшения для мелких копий. Склеивает у игрока
`picture_layer.py`; этот скрипт снимает слой на своей машине и доказывает,
что склейка даст ровно русскую картинку.

    tools\\layer_localized.py            снять слой в work/graphics_layers, листы — в preview/
    tools\\layer_localized.py --all      то же, но с нуля, не опираясь на прошлый манифест
    tools\\layer_localized.py --check    ничего не писать: собрать во временной папке и сверить

Сборка инкрементальная (10 октября 2026): картинка, у которой не изменились ни русская PNG
(`png_sha`), ни английская текстура оригинала (`source_sha`), ни рецепт уменьшения, берётся
из прошлого манифеста вместе со слоем и листом — склейка детерминирована, и пересобирать её
незачем. До этого каждый запуск сносил слой и пересобирал все 110 картинок (2–3 минуты на одну
изменённую). `--check` по-прежнему собирает всё с нуля — это независимое доказательство.

Правило №13 (пользователь, 13 сентября 2026): картинку показывать только после
машинной сверки. Сверяется всё с **нетронутым оригиналом** из `backup/`, а не
с живым бандлом, куда мы сами пишем:

  1. склейка «английская текстура + слой» совпадает с русской картинкой — RGB
     пиксель в пиксель, альфа с точностью до единицы (`relabel.py` до 13 сентября
     терял родную альфу 254, а разницу 254 и 255 глазом не увидеть);
  2. сторона — так, как лежат оригиналы: голосуют все языковые варианты картинки;
  3. правка не выходит за рамки надписей из `labels.json` и `art.json` — такие
     пиксели на листе жёлтые, и их число печатается;
  4. слой — надпись, а не рисунок: больше четверти картинки игроку не везём;
  5. правка не испортила рисунок **внутри** рамок: снятие повторяется на оригинале
     теми же параметрами и ищутся недоснятые хвосты старых букв и стёртые линии.
     Рамка — не гарантия: 13 сентября на плане дела 1 «0 пикселей за рамками»
     соседствовали с хвостом английской `R` и затёртой стеной. Эти места не валят
     сборку, а печатаются и красятся на листе — решает пользователь.

Лист на картинку — `preview/<имя>.png`: оригинал, склейка, где менялись пиксели,
правка крупно и, если нашлось, подозрительные места крупно. Листы — кадры игры,
в репозиторий они не идут.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import re
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

import UnityPy
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageStat

from common import BACKUP, BUNDLES, HOST, WORK, load_json, save_json
from picture_layer import FLIP, FOLDER, compose, leaf, pixels_sha, short, texture_of
from relabel import remap, strip_text
from swap_localized import LANG_KEY, NEVER, plan_env

RU = WORK / "graphics_ru"
PREVIEW = FOLDER / "preview"
MAX_SHARE = 0.25          # слой больше четверти картинки — это уже рисунок
# Адресные исключения из MAX_SHARE — только решением пользователя, с причиной.
# cut02_037: экран заставки целиком перерисован нейросетью по рисунку пользователя
# (вся зона — плашка, фон под логотипом не показывает ни один язык); в слое нет
# пикселей Capcom, есть их перерисовка. Разрешено пользователем 23 сентября 2026.
# efc_BigFont00/01/02/04: самостоятельные крупные графические выкрики.
# Замена английских и русских контуров занимает31.51–35.86% даже после возврата
# малых RGB-отличий≤4; уменьшение до25% требует вернуть сильные отличия122–128,
# то есть повредить сами буквы. Четыре показанных PNG заморожены.
# Пользователь явно разрешил только эти пределы24октября2026; общий25% прежний.
SHARE_ALLOWED = {
    "cut02_037": 0.55,
    "efc_BigFont00": 0.32,
    "efc_BigFont01": 0.35,
    "efc_BigFont02": 0.36,
    "efc_BigFont04": 0.36,
}
MARGIN = 12               # запас вокруг рамки: снятие расширяет маску и затягивает края
NOTE_ZONE = 40            # запас вокруг рамки рукописной пометки: дальше него набор
                          # (`notes.py`, он берёт эту же величину) строку не поставит
RING = 30                 # полоса за рамкой снятия, где ищутся недоснятые хвосты букв
TAIL_MAX = 600            # хвост — обрывок; связный кусок крупнее — край листа или рамка
DARK = 110                # «линия рисунка» — пиксель оригинала темнее этого
ERASED = 60               # снятие высветлило его больше чем на столько
EDGE = 40                 # «деталь рисунка» — резкая граница в оригинале
LANGS = ("eng", "ger", "fre", "jpn", "kor", "sim", "tra")
FONT = Path("C:/Windows/Fonts/segoeui.ttf")

# Заставки-конструкторы: куски в атласе по заданию, а не картинка на текстуру. Каждая —
# свой инструмент набора и сверки (модуль), задание и наш атлас в work/graphics_ru/ui.
# В общий разбор картинок по именам их PNG не попадают; в слой и в бандл они идут
# своим шагом (`splash_layer`, `inject_localized.load_splashes`, `picture_layer.write_splash`).
SPLASHES = (
    ("splash", "splash.json", "splash_ger2.png"),       # «Возражение», tools/splash.py
    ("titles", "titles.json", "titles_StEd_ger.png"),   # «Начало / Расследование завершено», tools/titles.py
    ("titles_chess", "titles_chess.json", "titles_chess_ger.png"),  # «Ментальные шахматы», tools/titles_chess.py
)
SPLASH_PNGS = {png for _, _, png in SPLASHES}


def splash_jobs() -> list[tuple[str, dict, Path]]:
    """Набранные заставки: (модуль сверки, задание, PNG атласа). Не набранная — пропускается."""
    out = []
    for module, spec_name, png_name in SPLASHES:
        spec_path, png = RU / "ui" / spec_name, RU / "ui" / png_name
        if spec_path.exists() and png.exists():
            out.append((module, load_json(spec_path), png))
    return out


def bundle_neighbours(bundle_short: str, me: str) -> set:
    """Что в бандле вправе менять наши картинки, кроме заставки `me`: имена объектов
    картинок и плашек, а у других заставок — их спрайты, атлас и объекты с правками.
    Нужно сверке одной заставки по собранному бандлу: чужая законная правка — не «лишнее»."""
    from picture_layer import splash_objects

    out: set = set()
    for module, spec, _ in splash_jobs():
        if module != me and spec["бандл"] == bundle_short:
            live = next(BUNDLES.glob(f"{bundle_short}_assets_all_*.bundle"), None)
            src = original(live.name) if live else None
            if src is not None:
                out |= splash_objects(UnityPy.load(str(src)), spec)
    ours = {png.stem for png in RU.rglob("*.png")}
    for name, places in index().items():
        for bundle_name, key, _ in places:
            if short(bundle_name) == bundle_short and name in ours:
                out.add(leaf(key))
    return out


def index() -> dict[str, list[tuple[str, str, str]]]:
    """Имя ассета без языкового хвоста -> [(бандл, адрес _ger, размер)].

    Берётся из переписи `scan_localized.py`, а не обходом бандлов: их 164 на семь
    гигабайт, и ради десятка картинок читать всё — это минуты вместо мгновения.

    Одно имя бывает в нескольких бандлах: FHD и Classic — две разные картинки
    одного и того же места, накрывать надо обе.
    У GK2 без немецкого варианта возвращается будущий адрес: отдельный объект
    для него создаёт write_bundle, не изменяя английскую текстуру.
    """
    data = load_json(WORK / "localized_assets.json")
    if not data:
        sys.exit("нет work/localized_assets.json — сперва tools/scan_localized.py")

    out: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for fam in data["families"].values():
        if fam["type"] != "Texture2D":
            continue
        if any(bad in fam["bundle"] for bad in NEVER):
            continue
        base = LANG_KEY.sub("", fam["base"].split("/")[-1], count=1).rsplit(".", 1)[0]
        ger = fam["variants"].get(HOST)
        if ger is None:
            if not fam["bundle"].startswith("gk2_"):
                continue
            # Только семейства из переписи языковых текстур. Объект и адрес
            # создаются при записи, оригинальные языки остаются нетронутыми.
            source = fam["variants"].get("eng") or next(iter(fam["variants"].values()))
            stem, ext = fam["base"].rsplit(".", 1)
            ger = {**source, "path": f"{stem}_{HOST}.{ext}"}
        out[base].append((fam["bundle"], ger["path"], f"{ger.get('w')}x{ger.get('h')}"))
    return out


def original(bundle_name: str) -> Path | None:
    """Нетронутый бандл: из backup/, а если бэкапа нет — живой, но только нетронутый.

    Снимать слой и сверять сторону можно лишь с тем, чего мы никогда не писали.
    Живой бандл, записанный в манифест бэкапа, уже менялся, а оригинала у него
    нет — тогда None.
    """
    saved = BACKUP / bundle_name
    if saved.exists():
        return saved
    manifest = load_json(BACKUP / "manifest.json", default={}) or {}
    if f"asset_{short(bundle_name)}" in manifest:
        return None
    return BUNDLES / bundle_name


def flat(im: Image.Image) -> Image.Image:
    """Серая миниатюра для сравнения: прозрачное — на средний серый, а не в чёрный."""
    im = im.convert("RGBA")
    bg = Image.new("RGB", im.size, (128, 128, 128))
    bg.paste(im, mask=im.split()[3])
    return bg.convert("L").resize((64, 64))


def variants(key: str, container) -> list[str]:
    """Языковые варианты той же картинки в бандле, включая японский без хвоста."""
    found = [re.sub(r"_ger(?=\.[^./]+$)", f"_{lang}", key) for lang in LANGS]
    found.append(re.sub(r"_ger(?=\.[^./]+$)", "", key))
    return [k for k in found if k in container]


def stored_flipped(env, key: str, face_up: Image.Image) -> bool:
    """Хранит ли бандл эту картинку вверх ногами — голосуют нетронутые варианты.

    `env` — оригинал (`original()`). Рисунок у языковых вариантов общий, отличается
    надпись, так что сторона видна однозначно. До 13 сентября 2026 голосовал один
    английский сосед в живом бандле — тот, куда вставка сама писала русское:
    сверка сходилась сама с собой, и три картинки дела 1 встали вверх ногами.
    Ничья — ошибка, а не повод угадывать.
    """
    mine = flat(face_up)
    same = turned = 0.0
    for other in variants(key, env.container):
        theirs = flat(env.container[other].read().image)
        same += ImageStat.Stat(ImageChops.difference(mine, theirs)).mean[0]
        turned += ImageStat.Stat(ImageChops.difference(mine, theirs.transpose(FLIP))).mean[0]
    if max(same, turned) == 0 or min(same, turned) > 0.8 * max(same, turned):
        raise ValueError(f"{leaf(key)}: сторону не определить — {same:.1f} против {turned:.1f}")
    return turned < same


def recipes(case_dir: Path) -> dict[str, list[dict]]:
    """Задания набора и вклейки по картинкам дела: рамки надписей и рецепты уменьшения."""
    out: dict[str, list[dict]] = defaultdict(list)
    for fname in ("labels.json", "art.json", "notes.json", "sign.json", "plate.json"):
        spec = load_json(case_dir / fname, default={}) or {}
        for name, job in spec.items():
            if not isinstance(job, dict):
                continue            # «_» в задании — пояснение для человека, а не картинка
            if "как" in job:
                own = {k: v for k, v in job.items() if k not in ("как", "якорь_там", "якорь_тут")}
                job = {**remap(spec[job["как"]], job["якорь_там"], job["якорь_тут"]), **own}
            out[name].append(job)
    return out


def allowed(size: tuple[int, int], jobs: list[dict]) -> Image.Image | None:
    """Где правке можно быть: рамки надписей с запасом. None — рамок нет, смотреть глазами."""
    if not jobs:
        return None
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)

    def rect(box, grow: int) -> None:
        draw.rectangle((box[0] - grow, box[1] - grow, box[2] + grow, box[3] + grow), fill=255)

    for job in jobs:
        for cut in job.get("снять", []):
            rect(cut["box"], MARGIN + cut.get("pad", 6))
        for glue in job.get("вклеить", []):
            rect(glue["box"], MARGIN)
        # «вернуть» у вклейки — [{"box"}]; у `prints.py` (с 1 октября 2026) «вернуть»,
        # «стереть» и «залатать» — области рамкой [x0, y0, x1, y1] или многоугольником
        # [[x, y], …]: это законные места правки, а не «за рамками надписей»
        areas = list(job.get("вернуть", []))
        areas += [part["где"] for part in job.get("стереть", []) + job.get("залатать", [])]
        for area in areas:
            if isinstance(area, dict):
                area = area["box"]
            if area and isinstance(area[0], (list, tuple)):
                xs, ys = [p[0] for p in area], [p[1] for p in area]
                area = (min(xs), min(ys), max(xs), max(ys))
            rect(area, MARGIN)
        for label in job.get("labels", []):
            # набранная строка центрируется по рамке и может быть шире её — до max_width
            x0, y0, x1, y1 = label["box"]
            half = max(x1 - x0, label.get("max_width", 0)) // 2
            cx = (x0 + x1) // 2
            rect((cx - half, y0, cx + half, y1), MARGIN + 6 + job.get("stroke_width", 3))
        for note in job.get("пометки", []):
            # рукописная пометка: русская живёт в рамках английской с тем же запасом,
            # какой держит сам набор (notes.ZONE) — больше него он строку не поставит.
            # У мелкой копии рамки пересчитаны, и запас едет вместе с ними
            for box in note["рамки"]:
                rect(box, MARGIN + round(NOTE_ZONE * job.get("масштаб", 1.0)))
        for box in job.get("надпись", []):
            # вывеска: рамка снята с самого набора — след английской надписи
            # вместе с нашими буквами (tools/sign.py). Без неё слой вывески
            # числился «правкой за рамками надписей» целиком, 106 089 пикселей.
            rect(box, MARGIN)
        if "уменьшить" in job:
            rect(job["уменьшить"]["якорь_тут"], 2)
    return mask


def rgb_delta(a: Image.Image, b: Image.Image) -> Image.Image:
    r, g, bl, _ = ImageChops.difference(a, b).split()
    return ImageChops.lighter(ImageChops.lighter(r, g), bl)


def changed(result: Image.Image, base: Image.Image) -> Image.Image:
    """Какие пиксели отличаются: RGB хоть на единицу, альфа — больше чем на единицу."""
    rgb = rgb_delta(result, base).point(lambda v: 255 if v else 0)
    alpha = ImageChops.difference(result.getchannel("A"), base.getchannel("A")).point(
        lambda v: 255 if v > 1 else 0)
    return ImageChops.lighter(rgb, alpha)


def count(mask: Image.Image) -> int:
    return mask.histogram()[255]


def rgb_max_delta(a: Image.Image, b: Image.Image) -> Image.Image:
    r, g, bl = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).split()
    return ImageChops.lighter(ImageChops.lighter(r, g), bl)


def near_colour(im: Image.Image, colour, tol: int) -> Image.Image:
    """Пиксели, у которых каждый канал в пределах tol от цвета, — как `relabel.near`."""
    return rgb_max_delta(im, Image.new("RGB", im.size, tuple(colour))).point(lambda v: 255 if v <= tol else 0)


def strips(jobs: list[dict]) -> list[dict]:
    """Снятия старых надписей с цветами и допусками — ровно как их зовут relabel.py и paste_art.py.

    Картинку с `по_оригиналу` подсказка пропускает: там английское снято **подложкой**
    (`prints.py`, `notes.py`), а не маской по цвету, и повтор старого снятия на оригинале
    объявлял «испорченным рисунком» ровно то, что мы восстановили точнее его (20 сентября 2026).
    За такие картинки отвечает `check_pictures.py`, у него эталон — подложка и оригинал.
    """
    out = []
    for job in jobs:
        if job.get("по_оригиналу") or job.get("пометки"):
            continue
        for label in job.get("labels", []):
            out.append({"box": label["box"], "pad": 6, "fill": job["fill"], "stroke": job["stroke"],
                        "tol_fill": job.get("допуск", 45), "tol_stroke": job.get("допуск_обводки", 25)})
        for cut in job.get("снять", []):
            out.append({"box": cut["box"], "pad": cut.get("pad", 6), "fill": cut["fill"],
                        "stroke": cut["stroke"],
                        "tol_fill": cut.get("допуск", job.get("допуск", 45)),
                        "tol_stroke": cut.get("допуск_обводки", job.get("допуск_обводки", 25))})
    return out


def small_parts(mask: Image.Image, limit: int) -> Image.Image:
    """Оставить в маске только связные куски не больше `limit` пикселей."""
    keep = Image.new("L", mask.size, 0)
    box = mask.getbbox()
    if not box:
        return keep
    x0, y0, x1, y1 = box
    src, dst = mask.load(), keep.load()
    seen: set[tuple[int, int]] = set()
    for y in range(y0, y1):
        for x in range(x0, x1):
            if not src[x, y] or (x, y) in seen:
                continue
            stack, part = [(x, y)], []
            seen.add((x, y))
            while stack:
                cx, cy = stack.pop()
                part.append((cx, cy))
                for nx in (cx - 1, cx, cx + 1):
                    for ny in (cy - 1, cy, cy + 1):
                        if (x0 <= nx < x1 and y0 <= ny < y1 and src[nx, ny]
                                and (nx, ny) not in seen):
                            seen.add((nx, ny))
                            stack.append((nx, ny))
            if len(part) <= limit:
                for point in part:
                    dst[point] = 255
    return keep


def damage(face: Image.Image, result: Image.Image,
           jobs: list[dict]) -> tuple[Image.Image, Image.Image] | None:
    """Где правка испортила рисунок в рамках: хвосты старых букв и испорченный рисунок.

    Снятие повторяется на оригинале теми же параметрами, и сверяются:

      * хвосты — пиксели цвета старых букв в полосе за рамкой снятия, не тронутые
        правкой и сросшиеся с буквами, которые снятие убрало. Так ловится хвост
        английской `R`, вылезший за рамку на плане дела 1. Стрелка, возвращённая
        «вернуть», не ловится: её пиксели в склейке совпадают с оригиналом.
        Крупный связный кусок — не хвост, а край листа или рамка того же цвета;
      * испорченный рисунок — тёмные линии, которые снятие высветлило (затёртая
        стена), и резкие границы, которые оно замазало в гладь (фигурка коня того
        же красного, что чернила, ушла в кляксу), — там, где новая надпись
        так и не легла.

    Это подсказки для глаз, а не приговор: цвет букв бывает и у рисунка.
    None — снятий в задании нет, проверять нечего.
    """
    cuts = strips(jobs)
    if not cuts:
        return None
    size = face.size
    original = face.convert("RGB")
    stripped = original.copy()
    inner = Image.new("L", size, 0)
    ring = Image.new("L", size, 0)
    letters = Image.new("L", size, 0)
    draw_inner, draw_ring = ImageDraw.Draw(inner), ImageDraw.Draw(ring)
    for cut in cuts:
        strip_text(stripped, cut["box"], tuple(cut["fill"]), tuple(cut["stroke"]), cut["pad"],
                   tol_fill=cut["tol_fill"], tol_stroke=cut["tol_stroke"])
        x0, y0, x1, y1 = cut["box"]
        pad = cut["pad"]
        draw_inner.rectangle((x0 - pad, y0 - pad, x1 + pad - 1, y1 + pad - 1), fill=255)
        draw_ring.rectangle((x0 - pad - RING, y0 - pad - RING, x1 + pad + RING, y1 + pad + RING), fill=255)
        letters = ImageChops.lighter(letters, ImageChops.lighter(
            near_colour(original, cut["fill"], cut["tol_fill"]),
            near_colour(original, cut["stroke"], cut["tol_stroke"])))
    ring = ImageChops.subtract(ring, inner)

    moved = rgb_max_delta(result, original).point(lambda v: 255 if v > 8 else 0)
    removed = ImageChops.multiply(ImageChops.multiply(letters, inner), moved)
    candidates = ImageChops.multiply(ImageChops.multiply(letters, ring), ImageChops.invert(moved))
    tails = ImageChops.multiply(removed.filter(ImageFilter.MaxFilter(5)), candidates)
    for _ in range(RING):
        grown = ImageChops.multiply(tails.filter(ImageFilter.MaxFilter(3)), candidates)
        if count(grown) == count(tails):
            break
        tails = grown
    tails = small_parts(tails, TAIL_MAX)

    def both(*masks: Image.Image) -> Image.Image:
        out = masks[0]
        for mask in masks[1:]:
            out = ImageChops.multiply(out, mask)
        return out

    grey = original.convert("L")
    uncovered = rgb_max_delta(result, stripped).point(lambda v: 255 if v <= 12 else 0)
    dark = both(grey.point(lambda v: 255 if v < DARK else 0), ImageChops.invert(letters))
    lighter = ImageChops.subtract(stripped.convert("L"), grey).point(lambda v: 255 if v > ERASED else 0)
    erased = both(dark, inner, lighter, uncovered)

    sharp_before = grey.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > EDGE else 0)
    sharp_after = stripped.convert("L").filter(ImageFilter.FIND_EDGES).point(
        lambda v: 255 if v > EDGE // 3 else 0)
    away = ImageChops.invert(letters.filter(ImageFilter.MaxFilter(7)))
    smeared = both(sharp_before, ImageChops.invert(sharp_after), inner, uncovered, away)
    return tails, ImageChops.lighter(erased, smeared)


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_layer(folder: Path, entry: dict, picture: Image.Image, mask: Image.Image) -> int:
    """Записать слой: пиксели правки и маску, обрезанные по её рамке. Возвращает байты."""
    box = mask.getbbox()
    if not box:
        return 0
    crop_mask = mask.crop(box)
    layer = Image.new("RGBA", crop_mask.size, (0, 0, 0, 0))
    layer.paste(picture.crop(box), (0, 0), crop_mask)
    rel_layer = f"{entry['bundle']}/{entry['name']}.png"
    rel_mask = f"{entry['bundle']}/{entry['name']}_mask.png"
    (folder / entry["bundle"]).mkdir(parents=True, exist_ok=True)
    layer.save(folder / rel_layer, optimize=True)
    crop_mask.convert("1", dither=Image.Dither.NONE).save(folder / rel_mask, optimize=True)
    entry.update(box=list(box), layer=rel_layer, mask=rel_mask)
    return (folder / rel_layer).stat().st_size + (folder / rel_mask).stat().st_size


def drop_layer(folder: Path, entry: dict) -> None:
    for rel in (entry.pop("layer", None), entry.pop("mask", None)):
        if rel:
            (folder / rel).unlink(missing_ok=True)
    entry.pop("box", None)


def fonts():
    try:
        return ImageFont.truetype(str(FONT), 26), ImageFont.truetype(str(FONT), 19)
    except OSError:
        return ImageFont.load_default(), ImageFont.load_default()


def fit(im: Image.Image, width: int = 960, height: int = 720) -> Image.Image:
    """В ячейку листа: мелкое — целым множителем без размытия, крупное — уменьшением."""
    im = im.convert("RGB")
    k = min(width / im.width, height / im.height)
    if k >= 1:
        n = int(k)
        return im.resize((im.width * n, im.height * n), Image.NEAREST)
    return im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)


def preview(entry: dict, face: Image.Image, result: Image.Image, full: Image.Image,
            room: Image.Image | None, harm: tuple[Image.Image, Image.Image] | None,
            note: str, path: Path) -> None:
    """Лист для показа пользователю: оригинал, склейка, где менялись пиксели, правка крупно.

    На карте правки красное — изменено в рамках надписей, жёлтое — за рамками,
    голубое — недоснятые хвосты старых букв, лиловое — стёртые линии рисунка.
    Нашлись хвосты или стёртое — ниже ещё пара ячеек: эти места крупно, в склейке
    и в оригинале.
    """
    w, h = result.size
    marks = Image.blend(face.convert("RGB"), Image.new("RGB", (w, h)), 0.6)
    marks.paste(Image.new("RGB", (w, h), (255, 45, 45)), (0, 0), full)
    if room is not None:
        marks.paste(Image.new("RGB", (w, h), (255, 215, 0)), (0, 0), ImageChops.subtract(full, room))
    suspect = None
    if harm is not None:
        thick = ImageFilter.MaxFilter(5)
        marks.paste(Image.new("RGB", (w, h), (60, 170, 255)), (0, 0), harm[0].filter(thick))
        marks.paste(Image.new("RGB", (w, h), (230, 0, 230)), (0, 0), harm[1].filter(thick))
        suspect = ImageChops.lighter(*harm).getbbox()
    x0, y0, x1, y1 = full.getbbox() or (0, 0, w, h)
    pad = max(8, (x1 - x0) // 20)
    zoom = result.crop((max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad)))
    cells = [("Оригинал — английская текстура игры", fit(face)),
             ("У игрока — склейка из его текстуры и слоя", fit(result)),
             ("Карта: красное — правка, жёлтое — за рамками, голубое — хвосты букв, лиловое — испорчен рисунок",
              fit(marks)),
             ("Правка крупно", fit(zoom))]
    if suspect:
        x0, y0, x1, y1 = suspect
        crop = (max(0, x0 - 40), max(0, y0 - 40), min(w, x1 + 40), min(h, y1 + 40))
        cells += [("Подозрительные места крупно — склейка", fit(result.crop(crop))),
                  ("Те же места в оригинале", fit(face.crop(crop)))]
    big, small = fonts()
    # столбец не уже подписи: иначе у мелких текстур подписи наезжают друг на друга
    cw = max(960, *(c.width for _, c in cells))
    ch = max(c.height for _, c in cells)
    head, cap, gap = 110, 30, 16
    rows = (len(cells) + 1) // 2
    sheet = Image.new("RGB", (2 * cw + 3 * gap, head + rows * (cap + ch + gap) + gap), (36, 36, 40))
    draw = ImageDraw.Draw(sheet)
    draw.text((gap, 10), f"{entry['name']} · {entry['bundle']}", font=big, fill=(255, 255, 255))
    parts = note.split("; ")
    half = (len(parts) + 1) // 2
    draw.text((gap, 46), "; ".join(parts[:half]), font=small, fill=(205, 205, 205))
    draw.text((gap, 74), "; ".join(parts[half:]), font=small, fill=(205, 205, 205))
    for i, (caption, cell) in enumerate(cells):
        x = gap + (i % 2) * (cw + gap)
        y = head + (i // 2) * (cap + ch + gap)
        draw.text((x, y), caption, font=small, fill=(225, 225, 225))
        sheet.paste(cell, (x, y + cap))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, optimize=True)


def build(folder: Path, show: bool, prev: dict | None = None) -> tuple[dict, list[str]]:
    """Снять слой со всех картинок work/graphics_ru в `folder`. Возвращает манифест и беды.

    `prev` — прошлый манифест той же папки: картинки, у которых совпали `png_sha`, `source_sha`
    (для плашек — `texture_sha`), адрес и рецепт уменьшения, а слой и маска лежат на месте,
    в манифест переносятся как есть, без склейки, сверки и листа."""
    # `<имя>_ink.png` и `<имя>_print_ink.png` — маски набранных букв для проверки,
    # а не картинки игры: в слой они не идут и в «не везём» им делать нечего
    pngs = [png for png in sorted(RU.rglob("*.png"))
            if png.name not in SPLASH_PNGS and not png.stem.endswith("_ink")]
    manifest: dict = {"pictures": [], "skipped": [], "aliases": []}
    problems: list[str] = []
    seen: dict[str, Path] = {}
    for png in pngs:
        if png.stem in seen:
            problems.append(f"одна картинка лежит дважды: {seen[png.stem]} и {png}")
        seen[png.stem] = png
    if problems:
        return manifest, problems

    idx = index()
    jobs = {case: recipes(case) for case in {p.parent for p in pngs}}
    derive_of = {name: {"из": job["уменьшить"]["из"], "там": job["уменьшить"]["якорь_там"],
                        "тут": job["уменьшить"]["якорь_тут"]}
                 for spec in jobs.values() for name, js in spec.items()
                 for job in js if "уменьшить" in job}
    feeding = {d["из"] for d in derive_of.values()}
    known = {e["name"]: e for e in (prev or {}).get("pictures", []) if e.get("kind") != "splash"}

    def intact(old: dict) -> bool:
        return all((folder / old[k]).exists() for k in ("layer", "mask") if k in old)

    places: dict[str, list[tuple[Path, str]]] = defaultdict(list)
    for png in pngs:
        where = idx.get(png.stem)
        if not where:
            manifest["skipped"].append({"name": png.stem, "why": "у картинки нет немецкого варианта: "
                                        "в слоте русского игра её не показывает, класть некуда"})
            continue
        for bundle_name, key, _ in where:
            places[bundle_name].append((png, key))

    # Осознанно оставленный English без GER — отдельный адрес, а не перевод
    # и не пиксельный слой. Такие исключения берутся только из coverage policy.
    aliases: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    policy = load_json(RU / "coverage.json", default={}) or {}
    for fam in load_json(WORK / "localized_assets.json")["families"].values():
        name = fam["base"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if (fam["type"] != "Texture2D" or HOST in fam["variants"]
                or not fam["bundle"].startswith("gk2_") or "eng" not in fam["variants"]
                or policy.get("excluded", {}).get(name, {}).get("kind") != "original"
                or not policy.get("excluded", {}).get(name, {}).get("english_alias")):
            continue
        stem, ext = fam["base"].rsplit(".", 1)
        aliases[fam["bundle"]].append((name, f"{stem}_{HOST}.{ext}", fam["variants"]["eng"]["path"]))
    composites: dict[str, Image.Image] = {}
    order = sorted(set(places) | set(aliases),
                   key=lambda b: (not any(p.stem in feeding for p, _ in places.get(b, [])), b))
    for bundle_name in order:
        src = original(bundle_name)
        if src is None:
            problems.append(f"{short(bundle_name)}: бандл менялся, а оригинала в backup/ нет")
            continue
        print(f"\n{short(bundle_name)} — {'оригинал из backup/' if src.parent == BACKUP else 'живой, нетронутый'}",
              flush=True)
        env = UnityPy.load(str(src))
        for name, key, source in aliases.get(bundle_name, []):
            if source not in env.container:
                problems.append(f"{name}: нет английского источника для оставленного оригинала")
                continue
            manifest["aliases"].append({"name": name, "bundle": short(bundle_name), "key": key,
                                        "source": source, "source_sha": pixels_sha(env.container[source].read().image)})
        pairs = dict(plan_env(env, [key for _, key in places.get(bundle_name, [])]))
        from picture_layer import sprites_by_key
        from plates import layer_entry
        sprites = sprites_by_key(env)
        for png, key in sorted(places.get(bundle_name, []), key=lambda it: (it[0].stem in derive_of, it[0].stem)):
            name = png.stem
            entry: dict = {"name": name, "bundle": short(bundle_name), "key": key}
            png_sha = file_sha(png)
            old = known.get(name)
            if key in sprites:
                # Плашка ситуации: наш набор целиком, склеивать не с чем (plates.py).
                if (old is not None and old.get("kind") == "plate" and old.get("png_sha") == png_sha
                        and old.get("key") == key and old.get("bundle") == entry["bundle"] and intact(old)
                        and old.get("texture_sha") == pixels_sha(texture_of(env, sprites[key]).read().image)):
                    manifest["pictures"].append(dict(old))
                    print(f"  {name:18} плашка без изменений — слой с прошлой сборки", flush=True)
                    continue
                problems += layer_entry(folder, entry, png, png_sha, env, sprites[key], manifest,
                                        PREVIEW if show else None)
                continue
            source_key = pairs.get(key)
            if source_key is None:
                manifest["skipped"].append({**entry, "why": "нет ни английского, ни базового варианта"})
                continue
            create = key not in env.container
            german = env.container[source_key if create else key].read()
            size = (german.m_Width, german.m_Height)
            picture = Image.open(png).convert("RGBA")
            if picture.size != size:
                picture = picture.resize(size, Image.LANCZOS)
            source = env.container[source_key].read().image.convert("RGBA")
            if source.size != size:
                manifest["skipped"].append({**entry, "why": f"английская текстура {source.size}, немецкая {size}"})
                continue
            source_sha = pixels_sha(source)
            if name in derive_of and derive_of[name]["из"] not in composites:
                problems.append(f"{name}: уменьшается из «{derive_of[name]['из']}», а та не собралась")
                continue
            if (old is not None and "kind" not in old and old.get("png_sha") == png_sha
                    and old.get("source_sha") == source_sha and old.get("key") == key
                    and old.get("bundle") == entry["bundle"] and old.get("source") == source_key
                    and old.get("derive") == derive_of.get(name) and intact(old)):
                # ни картинка, ни оригинал, ни рецепт не менялись — склейка дала бы то же самое
                entry = dict(old)
                manifest["pictures"].append(entry)
                if name in feeding:
                    composites[name] = compose(entry, source, composites, folder)
                print(f"  {name:18} без изменений — слой с прошлой сборки", flush=True)
                continue
            try:
                flipped = stored_flipped(env, key, picture)
            except ValueError as exc:
                problems.append(str(exc))
                continue
            entry.update(source=source_key, size=list(size), flipped=flipped,
                         source_sha=source_sha, png_sha=png_sha)
            if create:
                entry["create"] = True
            if name in derive_of:
                entry["derive"] = derive_of[name]

            base = compose(entry, source, composites, folder)
            mask = changed(picture, base)
            weight = save_layer(folder, entry, picture, mask)
            result = compose(entry, source, composites, folder)

            face = source.transpose(FLIP) if flipped else source
            full = changed(result, face)
            share = count(mask) / (size[0] * size[1])
            recipe = jobs[png.parent].get(name, [])
            room = allowed(size, recipe)
            outside = count(ImageChops.subtract(full, room)) if room is not None else None
            harm = damage(face, result, recipe)
            rgb_off = count(rgb_delta(result, picture).point(lambda v: 255 if v else 0))
            alpha_off = count(ImageChops.difference(result.getchannel("A"), picture.getchannel("A"))
                              .point(lambda v: 255 if v > 1 else 0))
            side = "бандл хранит вверх ногами" if flipped else "бандл хранит лицом вверх"
            where_txt = ("рамок в заданиях нет — смотреть глазами" if outside is None
                         else f"за рамками надписей {outside} пикс.")
            harm_txt = ("" if harm is None else
                        f"; хвосты старых букв {count(harm[0])} пикс.; испорчено рисунка {count(harm[1])} пикс.")
            derived = f"уменьшение из {entry['derive']['из']} + " if entry.get("derive") else ""
            note = (f"{side}; {derived}слой {share:.1%} картинки, {weight / 1024:.0f} КБ; {where_txt}{harm_txt}; "
                    f"склейка против русской PNG: RGB {rgb_off}, альфа {alpha_off}")
            print(f"  {name:18} {note}", flush=True)

            if rgb_off or alpha_off:
                problems.append(f"{name}: склейка не сходится с русской картинкой (RGB {rgb_off}, альфа {alpha_off})")
                drop_layer(folder, entry)
                continue
            if share > SHARE_ALLOWED.get(name, MAX_SHARE):
                manifest["skipped"].append({**entry, "why": f"слой — {share:.0%} картинки: это рисунок, а не надпись"})
                drop_layer(folder, entry)
                continue
            entry.update(changed=count(mask), outside=outside,
                         tails=None if harm is None else count(harm[0]),
                         erased=None if harm is None else count(harm[1]))
            manifest["pictures"].append(entry)
            composites[name] = result
            if show:
                preview(entry, face, result, full, room, harm, note, PREVIEW / f"{name}.png")
        del env
        gc.collect()
    problems += splash_layer(folder, manifest)
    return manifest, problems


def splash_layer(folder: Path, manifest: dict) -> list[str]:
    """Заставки-конструкторы в слой: наши куски атласа и задание для их рамок.

    Картинкой это не снять: куски лежат в общем атласе, и переезд каждого меняет
    не пиксели, а поля спрайта, а у заставок расследования — ещё и поля немецких
    префабов. Поэтому слой заставки — наш атлас без единого пикселя Capcom (мазок
    `anim_1_0` «Возражения» патчер вырежет у игрока) плюс задание `tools/splash.py`
    или `tools/titles.py`, по которому переписываются рамки и префабы.
    """
    problems: list[str] = []
    for module, spec, png in splash_jobs():
        live = next(BUNDLES.glob(f"{spec['бандл']}_assets_all_*.bundle"), None)
        if live is None:
            problems.append(f"заставка {png.stem}: в игре нет бандла {spec['бандл']}")
            continue
        if original(live.name) is None:
            problems.append(f"заставка {png.stem}: {spec['бандл']} менялся, а оригинала в backup/ нет")
            continue
        layer = Image.open(png).convert("RGBA")
        entry = {"name": png.stem, "bundle": spec["бандл"], "kind": "splash",
                 "key": spec.get("префаб") or spec["префабы"][0], "size": list(spec["размер"]), "spec": spec,
                 "png_sha": file_sha(png), "layer": f"{spec['бандл']}/{png.name}"}
        if module != "splash":
            entry["check"] = module          # чем сверять в selftest; у «Возражения» — splash.py
        target = folder / entry["layer"]
        target.parent.mkdir(parents=True, exist_ok=True)
        layer.save(target)
        manifest["pictures"].append(entry)
        pieces = len(spec["куски"]) - (1 if spec.get("мазок") else 0)
        edits = len(spec.get("правки", []))
        print("\n" + f"{spec['бандл']} — заставка «{spec['набор']['слово']}»: "
              f"{pieces} кусков" + (f", правок префабов {edits}" if edits else "")
              + f", слой {target.stat().st_size / 1024:.0f} КБ, пикселей Capcom нет", flush=True)
    return problems


def sweep(folder: Path, manifest: dict) -> None:
    """Инкрементальная сборка слой не сносит — убрать слои, маски и листы картинок, которых в манифесте нет."""
    keep = {(folder / e[k]).resolve() for e in manifest["pictures"] for k in ("layer", "mask") if k in e}
    names = {e["name"] for e in manifest["pictures"]}
    for path in folder.rglob("*"):
        if not path.is_file() or path.name == "manifest.json":
            continue
        if path.parent.name == "preview":
            if path.stem not in names:
                path.unlink()
        elif path.resolve() not in keep:
            path.unlink()


def stale() -> list[str]:
    """Что в собранном слое разошлось с work/graphics_ru — перед выпуском."""
    data = load_json(FOLDER / "manifest.json", default=None)
    pngs = {p.stem: p for p in RU.rglob("*.png") if not p.stem.endswith("_ink")}
    if data is None:
        return ["слой не собран — make layers"] if pngs else []
    out = []
    known = {e["name"]: e for e in data["pictures"]}
    skipped = {s["name"] for s in data.get("skipped", [])}
    for name, png in sorted(pngs.items()):
        entry = known.get(name)
        if entry is None and name not in skipped:
            out.append(f"{name}: картинки нет в слое — make layers")
        elif entry is not None and entry["png_sha"] != file_sha(png):
            out.append(f"{name}: картинка поменялась после сборки слоя — make layers")
    out += [f"{name}: в слое есть, а картинки уже нет — make layers" for name in known if name not in pngs]
    return out


def report(manifest: dict, problems: list[str], wrote: bool) -> None:
    print(f"\nв слое картинок: {len(manifest['pictures'])}")
    for item in manifest["skipped"]:
        print(f"  не везём: {item['name']} — {item['why']}")
    for item in manifest["pictures"]:
        if item.get("tails") or item.get("erased"):
            print(f"  смотреть глазами: {item['name']} — хвосты старых букв {item['tails']} пикс., "
                  f"испорчено рисунка {item['erased']} пикс.")
    if wrote and manifest["pictures"]:
        print(f"листы для показа: {PREVIEW}")
    for problem in problems:
        print(f"  БЕДА: {problem}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="ничего не писать: собрать во временной папке, сверить и сказать, не устарел ли слой")
    ap.add_argument("--all", action="store_true",
                    help="собрать слой с нуля, не опираясь на прошлый манифест")
    args = ap.parse_args()

    if args.check:
        with tempfile.TemporaryDirectory(prefix="aai2_layers_") as tmp:
            manifest, problems = build(Path(tmp), show=False)
        problems += stale()
    else:
        prev = None if args.all else load_json(FOLDER / "manifest.json", default=None)
        if prev is None:
            shutil.rmtree(FOLDER, ignore_errors=True)
            FOLDER.mkdir(parents=True)
        manifest, problems = build(FOLDER, show=True, prev=prev)
        if prev is not None:
            sweep(FOLDER, manifest)
            reused = sum(1 for e in manifest["pictures"] if e in prev["pictures"])
            print(f"\nбез изменений с прошлой сборки: {reused} из {len(manifest['pictures'])}")
        manifest["built"] = time.strftime("%Y-%m-%d %H:%M")
        save_json(FOLDER / "manifest.json", manifest)
    report(manifest, problems, wrote=not args.check)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
