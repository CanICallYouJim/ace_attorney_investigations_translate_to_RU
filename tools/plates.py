"""Плашки ситуации `Situation_0..6`: набор русских и то, что нужно для их вставки.

Плашка — надпись в левом верхнем углу: «Testimony» на показаниях, «Argument» на версии
противника, ещё пять на реконструкциях. Решение пользователя от 15 сентября 2026:
набирать шрифтом, а не рисовать нейросетью; слова — `work/graphics_ru/ui/plates.json`.

Как плашка лежит в игре (разбор 15 сентября 2026):

  * у каждой своя текстура 695x118 RGBA32 и спрайт на ней; по адресу
    `.../Situation_ger/Situation_N_ger.png` в контейнере **две** записи — текстура и спрайт;
  * видимую часть задаёт сетка спрайта — многоугольник по контуру немецкого слова
    (5–22 вершины) — и `textureRect`. Русское слово шире, поэтому сетка заменяется
    прямоугольником по его рамке (`picture_layer.write_sprite`), иначе буквы
    за контуром немецкого слова не рисуются;
  * `Situation_0` и `Situation_1` игра берёт через таблицу картинок локали
    (`Image Table_de`), остальные пять — прямо по адресу из немецкого бандла.
    `swap_localized.py` уводит строки таблицы на английские спрайты; у русских
    плашек эти строки возвращаются немецкими (`table_rows`).

Набор — по замеру английских плашек этой же игры, а не на глаз: кегль, сжатие по
ширине, базовая линия и левый край подбираются так, чтобы английское слово нашим
набором легло на тело английских букв (медиана по семи плашкам). Гарнитура —
Segoe UI Bold: из шрифтов с кириллицей на машине ближе всех по форме тела букв
(замер 15 сентября 2026, IoU 0,67 при сжатии 0,70; следом Malgun Gothic, Inter,
Arial Narrow). Обводка 7 px тёмно-зелёная; у жёлтых и голубых тёмная кайма 1,5 px
лежит в полосе обводки, а не съедает тело буквы — у оригинала штрих и обводка
цветных плашек той же толщины, что у белых.

    tools\\plates.py            набрать PNG в work/graphics_ru/ui, сверить, лист — work/graphics_masks/checks/plates.png
    tools\\plates.py --check    ничего не писать: набрать заново в памяти и сверить с лежащими PNG
"""
from __future__ import annotations

import argparse
import math
import re
import statistics
import sys
from pathlib import Path

import UnityPy
from PIL import Image, ImageChops, ImageDraw, ImageFont

from common import BACKUP, BUNDLES, WORK, load_json

UI = WORK / "graphics_ru" / "ui"
SPEC = UI / "plates.json"
SHEET = WORK / "graphics_masks" / "checks" / "plates.png"
ENGLISH = "localization-assets-english(en)"
GERMAN = "localization-assets-german(de)"
TABLE = "localization-asset-tables-german(de)"
FONT = Path("C:/Windows/Fonts/segoeuib.ttf")
LABEL_FONT = Path("C:/Windows/Fonts/segoeui.ttf")

W, H = 695, 118
GREEN = (0, 136, 72)
FILLS = {                      # заливка и тёмная кайма — сняты с английских плашек
    "white": ((248, 248, 248), None),
    "yellow": ((248, 208, 72), (160, 120, 0)),
    "blue": ((24, 216, 248), (16, 112, 128)),
}
OUTLINE = 7                    # обводка, px: замер сбоку у всех семи английских
RING = 1.5                     # тёмная кайма у цветных
SS = 2                         # набор в двойном размере, ужатие в конце
PAD = 24                       # поле при раздувании маски: ImageChops.offset заворачивает края
EDGE_ALPHA = 32                # крайняя строка сильнее — обводку срезало краем текстуры
RIGHT_ROOM = 20                # справа от надписи хотя бы столько пустого
TOLERANCE = 1                  # обводка и штрих против английской плашки, px


def untouched(prefix: str) -> Path:
    """Бандл, в который мы не писали: из backup/, если там есть, иначе живой."""
    live = next(BUNDLES.glob(f"{prefix}_assets_all_*.bundle"))
    saved = BACKUP / live.name
    return saved if saved.exists() else live


def load_spec() -> dict[str, dict]:
    spec = load_json(SPEC)
    if not spec:
        sys.exit(f"нет задания плашек: {SPEC}")
    return spec


def english_plates() -> dict[str, Image.Image]:
    """Английские плашки лицом вверх: `Situation_N` -> картинка 695x118."""
    env = UnityPy.load(str(untouched(ENGLISH)))
    out = {}
    for obj in env.objects:
        if obj.type.name == "Texture2D":
            m = re.fullmatch(r"(Situation_\d)_eng", obj.peek_name())
            if m:
                out[m.group(1)] = obj.read().image.convert("RGBA")
    return out


def dist(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def body_mask(im: Image.Image, fill) -> Image.Image:
    """Тело букв: непрозрачное и цвета заливки."""
    m = Image.new("L", im.size, 0)
    px, mp = im.load(), m.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a > 200 and dist((r, g, b), fill) < 110:
                mp[x, y] = 255
    return m


def text_mask(text: str, size: int, sx: float) -> tuple[Image.Image, int]:
    """Маска тела букв в масштабе SS и строка базовой линии в ней.

    Буквы ставятся по одной с кернингом пары: общий трекинг Pillow не умеет,
    а сжатие по ширине применяется ко всей строке сразу.
    """
    if not FONT.exists():
        sys.exit(f"нет гарнитуры {FONT}")
    f = ImageFont.truetype(str(FONT), size)
    asc, desc = f.getmetrics()
    xs, x = [], 0.0
    for i, ch in enumerate(text):
        xs.append(x)
        adv = f.getlength(ch)
        kern = f.getlength(text[i:i + 2]) - adv - f.getlength(text[i + 1]) if i + 1 < len(text) else 0.0
        x += adv + kern
    width = int(x + size)
    m = Image.new("L", (width, asc + desc + 8), 0)
    d = ImageDraw.Draw(m)
    for x0, ch in zip(xs, text):
        d.text((x0, 4), ch, font=f, fill=255)
    m = m.resize((max(1, round(width * sx)), m.height), Image.LANCZOS)
    return m, 4 + asc


def dilate(mask: Image.Image, r: float) -> Image.Image:
    """Раздуть маску кругом радиуса r — максимум по сдвигам внутри круга."""
    big = Image.new("L", (mask.width + 2 * PAD * SS, mask.height + 2 * PAD * SS), 0)
    big.paste(mask, (PAD * SS, PAD * SS))
    out = big.copy()
    ri = int(r)
    for dy in range(-ri, ri + 1):
        for dx in range(-ri, ri + 1):
            if (dx or dy) and dx * dx + dy * dy <= r * r:
                out = ImageChops.lighter(out, ImageChops.offset(big, dx, dy))
    return out.crop((PAD * SS, PAD * SS, PAD * SS + mask.width, PAD * SS + mask.height))


def calibrate(spec: dict, english: dict) -> dict:
    """Кегль, сжатие, базовая линия и левый край — медианой по английским плашкам."""
    sizes, squeezes, rows = [], [], []
    for name, job in spec.items():
        body = body_mask(english[name], FILLS[job["fill"]][0])
        bb = body.getbbox()
        probe, _ = text_mask(job["en"], 100 * SS, 1.0)
        pb = probe.getbbox()
        size = 100 * SS * (bb[3] - bb[1]) * SS / (pb[3] - pb[1])
        m, _ = text_mask(job["en"], round(size), 1.0)
        mb = m.getbbox()
        sizes.append(size)
        squeezes.append((bb[2] - bb[0]) * SS / (mb[2] - mb[0]))
        rows.append((job["en"], bb))
    size = round(statistics.median(sizes))
    sx = statistics.median(squeezes)
    bases, lefts = [], []
    for en, bb in rows:
        m, base = text_mask(en, size, sx)
        mb = m.getbbox()
        bases.append(bb[1] + (base - mb[1]) / SS)
        lefts.append(bb[0])
    return {"size": size, "sx": sx, "baseline": statistics.median(bases), "left": statistics.median(lefts)}


def placed(text: str, cal: dict, shift: float) -> tuple[Image.Image, int, int]:
    """Маска тела и её сдвиг на холсте SS: (маска, x, y)."""
    m, base = text_mask(text, cal["size"], cal["sx"])
    mb = m.getbbox()
    return m, round(cal["left"] * SS) - mb[0], round((cal["baseline"] - shift) * SS) - base


def lift(spec: dict, cal: dict) -> int:
    """На сколько поднять все плашки, чтобы хвосты «у», «р», «ц», «Д» с обводкой влезли.

    Подъём общий: плашки реконструкций переключаются парами, и надпись
    не должна прыгать по высоте.
    """
    need = 0.0
    for job in spec.values():
        m, _, y = placed(job["ru"], cal, 0)
        bottom = (y + m.getbbox()[3]) / SS + OUTLINE + 0.5
        need = max(need, bottom - H)
    return max(0, math.ceil(need))


def compose(text: str, fill_name: str, cal: dict, shift: int) -> Image.Image:
    fill, ring = FILLS[fill_name]
    m, x, y = placed(text, cal, shift)
    body = Image.new("L", (W * SS, H * SS), 0)
    body.paste(m, (x, y))
    img = Image.new("RGBA", body.size, GREEN + (0,))
    img = Image.composite(Image.new("RGBA", body.size, GREEN + (255,)), img, dilate(body, OUTLINE * SS))
    if ring:
        img = Image.composite(Image.new("RGBA", body.size, ring + (255,)), img, dilate(body, RING * SS))
    img = Image.composite(Image.new("RGBA", body.size, fill + (255,)), img, body)
    return img.convert("RGBa").resize((W, H), Image.LANCZOS).convert("RGBA")


def classify(im: Image.Image, fill) -> list[list[int]]:
    """0 — прозрачно, 1 — обводка, 2 — тело, 3 — переход."""
    px = im.load()
    grid = []
    for y in range(im.height):
        row = []
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a < 100:
                row.append(0)
            elif dist((r, g, b), fill) < 110:
                row.append(2)
            elif dist((r, g, b), GREEN) < 60:
                row.append(1)
            else:
                row.append(3)
        grid.append(row)
    return grid


def measure(im: Image.Image, fill, baseline: float) -> tuple[float | None, int | None]:
    """Обводка сбоку (медиана) и ширина вертикального штриха (мода) — в полосе строчных."""
    g = classify(im, fill)
    side, stems = [], []
    for y in range(max(0, int(baseline) - 55), min(im.height, int(baseline) - 12)):
        row = g[y]
        for x in range(1, im.width):
            if row[x - 1] == 0 and row[x] != 0:
                for k in range(x, min(im.width, x + 25)):
                    if row[k] == 2:
                        side.append(k - x)
                        break
        run = 0
        for v in row + [0]:
            if v == 2:
                run += 1
            else:
                if 5 <= run <= 30:
                    stems.append(run)
                run = 0
    return (statistics.median(side) if side else None), (statistics.mode(stems) if stems else None)


def edge_problems(img: Image.Image) -> list[str]:
    """Надпись не упёрлась в края текстуры и оставила место справа."""
    a = img.getchannel("A")
    out = []
    for y, where in ((0, "верхний"), (img.height - 1, "нижний")):
        top = max(a.getpixel((x, y)) for x in range(img.width))
        if top > EDGE_ALPHA:
            out.append(f"обводка упёрлась в {where} край (альфа {top})")
    box = a.getbbox()
    if box is None:
        out.append("картинка пустая")
    elif box[2] > img.width - RIGHT_ROOM:
        out.append(f"надпись до x={box[2]}, справа меньше {RIGHT_ROOM} px")
    return out


def table_rows(table_path: Path, leaves: set[str]) -> dict[int, str]:
    """Строки `Image Table_de`, ведущие на эти немецкие спрайты: `m_Id` -> немецкое значение.

    `leaves` — имена объектов, `Situation_0_ger`. Брать из нетронутой таблицы:
    в подменённой значения уже английские.
    """
    env = UnityPy.load(str(table_path))
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        tree = obj.read_typetree()
        if "m_TableData" not in tree:
            continue
        out = {}
        for row in tree["m_TableData"]:
            m = re.search(r"\[([^\]]+)\]$", row["m_Localized"])
            if m and m.group(1) in leaves:
                out[row["m_Id"]] = row["m_Localized"]
        return out
    return {}


def installed_rows() -> dict[int, str]:
    """Строки таблицы у плашек, которые уже стоят в живом немецком бандле — сверка по пикселям.

    Нужна `swap_localized.py`: подмена таблицы после установки плашек не должна
    уводить их строки обратно на английский, а до установки — оставлять немецкими.
    """
    from picture_layer import leaf, pixels_sha, sprites_by_key, texture_of

    pngs = {p.stem: p for p in UI.glob("Situation_*.png")}
    if not pngs:
        return {}
    env = UnityPy.load(str(next(BUNDLES.glob(f"{GERMAN}_assets_all_*.bundle"))))
    leaves = set()
    for key, sprite in sprites_by_key(env).items():
        name = leaf(key).rsplit("_", 1)[0]
        if name in pngs and pixels_sha(texture_of(env, sprite).read().image) == pixels_sha(Image.open(pngs[name])):
            leaves.add(leaf(key))
    return table_rows(untouched(TABLE), leaves) if leaves else {}


def layer_entry(folder: Path, entry: dict, png: Path, png_sha: str, env, sprite, manifest: dict,
                preview: Path | None) -> list[str]:
    """Плашка в слой патчера: картинка целиком, отпечатки для сверки, строка таблицы локали.

    Слой плашки — наш набор на прозрачном, пикселей Capcom в нём нет, поэтому правило
    `layer_localized.py` «слой не больше четверти картинки» к нему не относится.
    Отпечатков два — немецкой текстуры в оригинале и самой плашки: патчер кладёт
    плашку поверх любой из них, и повторная установка не спотыкается о прежнюю.
    """
    from picture_layer import leaf, pixels_sha, texture_of

    name = entry["name"]
    texture = texture_of(env, sprite).read()
    size = (texture.m_Width, texture.m_Height)
    picture = Image.open(png).convert("RGBA")
    if picture.size != size:
        return [f"{name}: плашка {picture.size[0]}x{picture.size[1]}, текстура {size[0]}x{size[1]} — tools/plates.py"]
    found = edge_problems(picture)
    if found:
        return [f"{name}: {p}" for p in found]
    before = texture.image.convert("RGBA")
    entry.update(kind="plate", size=list(size), png_sha=png_sha, texture_sha=pixels_sha(before),
                 plate_sha=pixels_sha(picture), layer=f"{entry['bundle']}/{name}.png")
    rows = table_rows(untouched(TABLE), {leaf(entry["key"])})
    if rows:
        (m_id, german), = rows.items()
        entry["table"] = {"m_Id": m_id, "german": german}
    target = folder / entry["layer"]
    target.parent.mkdir(parents=True, exist_ok=True)
    picture.save(target)
    manifest["pictures"].append(entry)
    print(f"  {name:18} плашка: набор целиком, {target.stat().st_size / 1024:.0f} КБ; "
          + (f"строка таблицы локали {entry['table']['m_Id']}" if rows
             else "в таблице локали строки нет — игра берёт по адресу"), flush=True)
    if preview is not None:
        sheet([(f"{name}: немецкая в оригинале → русская", [before, picture])], preview / f"{name}.png")
    return []


def on_gray(im: Image.Image) -> Image.Image:
    bg = Image.new("RGBA", im.size, (70, 70, 70, 255))
    bg.alpha_composite(im.convert("RGBA"))
    return bg.convert("RGB")


def sheet(rows: list[tuple[str, list[Image.Image]]], path: Path) -> None:
    fnt = ImageFont.truetype(str(LABEL_FONT), 20)
    cols = max(len(ims) for _, ims in rows)
    out = Image.new("RGB", (cols * (W + 8) + 8, len(rows) * (H + 36) + 8), (28, 28, 28))
    d = ImageDraw.Draw(out)
    for i, (label, ims) in enumerate(rows):
        y = 8 + i * (H + 36)
        d.text((8, y), label, font=fnt, fill=(255, 215, 80))
        for j, im in enumerate(ims):
            out.paste(on_gray(im), (8 + j * (W + 8), y + 28))
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="ничего не писать: набрать в памяти и сверить с лежащими PNG")
    args = ap.parse_args()

    spec = load_spec()
    if args.check and not any((UI / f"{name}.png").exists() for name in spec):
        # PNG в .gitignore: на свежем клоне плашки ещё не набраны, и сверять нечего.
        print(f"плашки не набраны ({UI}) — сверять нечего; набрать: tools/plates.py")
        return 0
    english = english_plates()
    missing = [name for name in spec if name not in english]
    if missing:
        sys.exit(f"в английском бандле нет плашек: {missing}")
    cal = calibrate(spec, english)
    shift = lift(spec, cal)
    print(f"по английским плашкам: кегль {cal['size'] / SS:.1f}, сжатие {cal['sx']:.3f}, "
          f"базовая линия {cal['baseline']:.1f}, левый край {cal['left']}; подъём {shift} px")

    problems, rows = [], []
    for name, job in spec.items():
        fill = FILLS[job["fill"]][0]
        img = compose(job["ru"], job["fill"], cal, shift)
        png = UI / f"{name}.png"
        if args.check:
            if not png.exists():
                problems.append(f"{name}: нет {png} — tools/plates.py")
                continue
            if ImageChops.difference(Image.open(png).convert("RGBA"), img).getbbox():
                problems.append(f"{name}: PNG не совпадает с набором по заданию — tools/plates.py")
        else:
            UI.mkdir(parents=True, exist_ok=True)
            img.save(png)
        found = edge_problems(img)
        en_side, en_stem = measure(english[name], fill, cal["baseline"])
        ru_side, ru_stem = measure(img, fill, cal["baseline"] - shift)
        if None in (en_side, en_stem, ru_side, ru_stem):
            found.append("обводку или штрих не измерить")
        else:
            if abs(ru_side - en_side) > TOLERANCE:
                found.append(f"обводка {ru_side} px против {en_side} у английской")
            if abs(ru_stem - en_stem) > TOLERANCE:
                found.append(f"штрих {ru_stem} px против {en_stem} у английской")
        box = img.getchannel("A").getbbox()
        print(f"  {name}  «{job['ru']}»: x {box[0]}..{box[2]} из {W}, y {box[1]}..{box[3]}; "
              f"обводка {ru_side}/{en_side}, штрих {ru_stem}/{en_stem} (наша/англ.)"
              + "".join(f"; БЕДА: {p}" for p in found))
        problems += [f"{name}: {p}" for p in found]
        rows.append((f"{name}: {job['en']} → «{job['ru']}»", [english[name], img]))

    sheet(rows, SHEET)
    print(f"лист: {SHEET}")
    for p in problems:
        print(f"  БЕДА: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
