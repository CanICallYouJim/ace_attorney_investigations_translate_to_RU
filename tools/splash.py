"""Заставка «Возражение» (`Rebuttal`): набор русского слова, нарезка и упаковка атласа.

Заставка перед возражением — не картинка, а разрезанное пополам слово: половины
въезжают с краёв экрана, стоят целым словом 1,7 с и разлетаются — верхние куски
влево, нижние вправо (клип `SousaPart_Title_Tuikyuu_In_R`, один на все языки).
У каждого языка своё слово и свой префаб `SousaPart_Title_Tuikyuu_R_<язык>`.

Устройство (разбор 15 сентября 2026):

  * **восемь спрайтов**: половина (`L`, `R`) × часть (`Top`, `Bottom`) × слой
    (малиновые буквы, белая обводка `Outline_`). Рамки `Top` и `Bottom` стоят одна
    над другой — опора `Top` снизу, `Bottom` сверху, между ними линия разреза;
  * все восемь и первый мазок `anim_1_0` лежат в атласе `SousaPart_Title_Tuikyuu_ger2`
    (текстура 1024×1024 BC7), прочие мазки — в соседнем атласе `..._ger`;
  * место куска в атласе задаёт **запись карты атласа** (`m_RenderDataMap`), а не поля
    самого спрайта: `textureRect` — рамка в атласе, `textureRectOffset` — где кусок
    стоит внутри рамки спрайта, считая **от низа**.

Набор — вариант A, выбранный пользователем 16 сентября 2026 (`docs/decisions.md`):
Arial Black с наклоном 0,22 (у Capcom тоже не курсив, а сдвиг), кегль 0,92 от немецкого,
межбуквенное −10 px; сжатие по ширине и базовая линия сняты с немецкого `Widerlegung`
этой же игры, а не на глаз. Разрез слова — «Возра | жение», стык приходится в полосу,
где рамки половин перекрываются.

    tools\\splash.py            набрать, упаковать атлас, сверить, лист — work/graphics_masks/checks/splash.png
    tools\\splash.py --check    ничего не писать: набрать заново в памяти и сверить с лежащим PNG
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import UnityPy
from PIL import Image, ImageChops, ImageDraw, ImageFont

from common import BACKUP, BUNDLES, WORK, save_json
from picture_layer import pixels_sha

UI = WORK / "graphics_ru" / "ui"
ATLAS_PNG = UI / "splash_ger2.png"
SPEC_JSON = UI / "splash.json"
SHEET = WORK / "graphics_masks" / "checks" / "splash.png"
BUNDLE = "gk_common_ingameui_trial"
ATLAS = "SousaPart_Title_Tuikyuu_ger2"
PREFIX = "SousaPart_Title_Tuikyuu"
HOST = "ger"

FONTS = Path("C:/Windows/Fonts")
FONT = "ariblk.ttf"
LABEL_FONT = "segoeuib.ttf"
SHEAR = 0.22
SCALE = 0.92                  # кегль против немецкого
TRACK = -10.0                 # межбуквенное на экране, px
WORD = "Возражение"
SPLIT = 5                     # «Возра» | «жение»
GERMAN_WORD = "Widerlegung"
CRIMSON = (152, 0, 56)
WHITE = (255, 255, 255)
OUTLINE = 22                  # белая обводка, px — замер по немецкой заставке
KEEP = f"{PREFIX}_anim_1_0_R_{HOST}"   # мазок в том же атласе: переезжает как есть

W, H, LINE = 1920, 460, 230   # холст сборки: экран по ширине, линия разреза
PAD = 30                      # запас под обводку при наращивании маски
GAP = 2                       # зазор между кусками в атласе, как у самого Unity

PARTS = [(side, part, outline)
         for side in ("L", "R") for part in ("Top", "Bottom") for outline in (True, False)]


def sprite_name(side: str, part: str, outline: bool, lang: str = HOST) -> str:
    return f"{PREFIX}_{'Outline_' if outline else ''}{side}_{part}_R_{lang}"


def open_bundle():
    """Оригинал бандла из `backup/`, а не живой файл: в живом уже стоит подмена."""
    live = next(BUNDLES.glob(f"{BUNDLE}_assets_all_*.bundle"))
    source = BACKUP / live.name
    return UnityPy.load(str(source if source.exists() else live))


def key_of(k):
    first, second = k
    return (tuple(first.values()) if isinstance(first, dict) else tuple(first), second)


def atlas_map(env) -> dict:
    """Ключ спрайта -> его запись в карте атласа (где кусок лежит на самом деле)."""
    out = {}
    for o in env.objects:
        if o.type.name == "SpriteAtlas" and (o.peek_name() or "").startswith(PREFIX):
            for k, rd in o.read_typetree()["m_RenderDataMap"]:
                out[key_of(k)] = rd
    return out


def sprites_of(env) -> dict:
    return {o.peek_name(): o for o in env.objects if o.type.name == "Sprite" and o.peek_name()}


def atlas_texture(env):
    """Текстура атласа заставки: одна на восемь кусков и первый мазок."""
    found = [o for o in env.objects if o.type.name == "Texture2D"
             and (o.peek_name() or "").endswith(f"{PREFIX}_{HOST}2-00082734")]
    if len(found) != 1:
        found = [o for o in env.objects if o.type.name == "Texture2D"
                 and f"{PREFIX}_{HOST}2" in (o.peek_name() or "")]
    if len(found) != 1:
        raise KeyError(f"текстуру атласа {ATLAS} не найти: нашлось {len(found)}")
    return found[0]


def prefab_key(env, lang: str = HOST) -> str:
    """Адрес немецкого префаба заставки в контейнере бандла."""
    ab = next(o for o in env.objects if o.type.name == "AssetBundle")
    tail = f"{PREFIX}_R_{lang}.prefab"
    found = [key for key, _ in ab.read_typetree()["m_Container"] if key.endswith(tail)]
    if len(found) != 1:
        raise KeyError(f"адрес префаба {tail} не найти: нашлось {len(found)}")
    return found[0]


def rect_tree(env, lang: str) -> dict:
    """Узлы префаба языка: путь от `root` -> RectTransform."""
    objs = {o.path_id: o for o in env.objects}
    root = next(o for o in env.objects if o.type.name == "GameObject"
                and o.peek_name() == f"{PREFIX}_R_{lang}")
    found = {}

    def walk(tr, parts):
        tt = tr.read_typetree()
        go = objs[tt["m_GameObject"]["m_PathID"]].read_typetree()
        full = parts + [go["m_Name"]]
        found["/".join(full[1:])] = tt
        for ch in tt.get("m_Children", []):
            walk(objs[ch["m_PathID"]], full)

    g = root.read_typetree()
    walk(next(objs[c["component"]["m_PathID"]] for c in g["m_Component"]
              if objs[c["component"]["m_PathID"]].type.name == "RectTransform"), [])
    return found


def geometry(env, lang: str) -> dict:
    """Рамки половин на экране: край, ширина и высота куска, как их задаёт префаб.

    Левая половина прижата правым краем, правая — левым; у обводки свой контейнер
    и свой край, поэтому пара (половина, обводка) — свой ключ.
    """
    tree = rect_tree(env, lang)
    geo = {}
    for side in ("L", "R"):
        for outline in (False, True):
            group = f"{side}_Outline" if outline else side
            cont = tree[f"root/Title/{group}"]
            off = tree[f"root/Title/{group}/offset"]
            centre = -cont["m_SizeDelta"]["x"] / 2 if side == "L" else cont["m_SizeDelta"]["x"] / 2
            node = tree[f"root/Title/{group}/offset/{'Char_W_' if outline else 'Char_'}{side}_Top"]
            geo[(side, outline)] = {"edge": centre + off["m_AnchoredPosition"]["x"],
                                    "w": node["m_SizeDelta"]["x"], "h": node["m_SizeDelta"]["y"]}
    return geo


def frame(geo_side: dict, side: str, part: str) -> dict:
    """Рамка куска на холсте сборки: левый верх (от левого края холста), ширина, высота."""
    w, h = geo_side["w"], geo_side["h"]
    x0 = geo_side["edge"] - w if side == "L" else geo_side["edge"]
    return {"x0": W / 2 + x0, "y0": LINE - h if part == "Top" else LINE, "w": w, "h": h}


def piece(env, maps, sprites, name: str):
    """Кусок из атласа: картинка, смещение в рамке спрайта (от низа), рамка спрайта."""
    objs = {o.path_id: o for o in env.objects}
    t = sprites[name].read_typetree()
    rd = maps[key_of(t["m_RenderDataKey"])]
    tex = objs[rd["texture"]["m_PathID"]].read()
    r = rd["textureRect"]
    img = tex.image.crop((round(r["x"]), round(tex.m_Height - r["y"] - r["height"]),
                          round(r["x"] + r["width"]), round(tex.m_Height - r["y"]))).convert("RGBA")
    return img, rd["textureRectOffset"], t["m_Rect"]


def lay(canvas: Image.Image, img: Image.Image, box: dict, offset, rect) -> None:
    """Кусок на холст сборки — так же, как его кладёт игра: рамка половины, сдвиг от низа."""
    sx, sy = box["w"] / rect["width"], box["h"] / rect["height"]
    want = (max(1, round(img.width * sx)), max(1, round(img.height * sy)))
    if want != img.size:
        img = img.resize(want, Image.LANCZOS)
    canvas.alpha_composite(img, (round(box["x0"] + offset["x"] * sx),
                                 round(box["y0"] + box["h"] - offset["y"] * sy - img.height)))


def original_layers(env, lang: str) -> dict:
    """Заставка языка по слоям: `outline` — белая обводка, `letters` — буквы."""
    maps, sprites, geo = atlas_map(env), sprites_of(env), geometry(env, lang)
    out = {}
    for outline in (True, False):
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for side in ("L", "R"):
            for part in ("Top", "Bottom"):
                img, offset, rect = piece(env, maps, sprites, sprite_name(side, part, outline, lang))
                lay(canvas, img, frame(geo[(side, outline)], side, part), offset, rect)
        out["outline" if outline else "letters"] = canvas
    return out


def flatten(layers: dict) -> Image.Image:
    return Image.alpha_composite(layers["outline"], layers["letters"])


def alpha_mask(im: Image.Image, level: int = 128) -> Image.Image:
    return im.getchannel("A").point(lambda v: 255 if v > level else 0)


def render(text: str, size: int, track: float = 0.0):
    """Тело букв: маска, базовая линия в ней и опорные x каждой буквы (по опережению)."""
    f = ImageFont.truetype(str(FONTS / FONT), size)
    asc, desc = f.getmetrics()
    xs, x = [], 0.0
    for i, ch in enumerate(text):
        xs.append(x)
        adv = f.getlength(ch)
        kern = f.getlength(text[i:i + 2]) - adv - f.getlength(text[i + 1]) if i + 1 < len(text) else 0.0
        x += adv + kern + (track if i + 1 < len(text) else 0.0)
    extra = int(SHEAR * (asc + desc)) + 8
    m = Image.new("L", (int(x) + size + extra, asc + desc + 16), 0)
    d = ImageDraw.Draw(m)
    for x0, ch in zip(xs, text):
        d.text((x0 + extra, 8), ch, font=f, fill=255)
    base = 8 + asc
    if SHEAR:
        m = m.transform(m.size, Image.AFFINE, (1, SHEAR, -SHEAR * base, 0, 1, 0), Image.BICUBIC)
    return m, base, [x0 + extra for x0 in xs] + [x + extra]


def calibrate(word_mask: Image.Image, text: str):
    """Кегль, сжатие по ширине и рамки — чтобы набор лёг на тело букв оригинала."""
    bb = word_mask.getbbox()
    ref = word_mask.crop(bb)
    probe, _, _ = render(text, 200)
    pb = probe.getbbox()
    size = 200 * ref.height / (pb[3] - pb[1])
    cand, base, _ = render(text, round(size))
    cb = cand.getbbox()
    return size, ref.width / (cb[2] - cb[0]), cb, base, bb


def dilate(mask: Image.Image, r: int) -> Image.Image:
    """Обводка: тело букв, наращённое на r пикселей по кругу."""
    big = Image.new("L", (mask.width + 2 * PAD, mask.height + 2 * PAD), 0)
    big.paste(mask, (PAD, PAD))
    out = big.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if (dx or dy) and dx * dx + dy * dy <= r * r:
                out = ImageChops.lighter(out, ImageChops.offset(big, dx, dy))
    return out.crop((PAD, PAD, PAD + mask.width, PAD + mask.height))


def typeset(env):
    """Русское слово на холсте сборки: маски по половинам и числа набора.

    Кегль, сжатие и базовая линия — от немецкого слова этой же игры; стык половин
    ставится в середину полосы, где рамки левой и правой половины перекрываются.
    """
    german = original_layers(env, HOST)
    size, sx, cb, base, bb = calibrate(alpha_mask(german["letters"]), GERMAN_WORD)
    baseline = bb[1] + (base - cb[1]) * (bb[3] - bb[1]) / (cb[3] - cb[1])
    scale_y = (bb[3] - bb[1]) / (cb[3] - cb[1])

    m, rbase, xs = render(WORD, round(size * SCALE), TRACK / sx)
    m = m.resize((round(m.width * sx), round(m.height * scale_y)), Image.LANCZOS)
    xs = [x * sx for x in xs]
    rbase *= scale_y

    geo = geometry(env, HOST)
    junction = W / 2 + (geo[("L", False)]["edge"] + geo[("R", False)]["edge"]) / 2
    x_off = round(junction - xs[SPLIT])
    y_off = round(baseline - rbase)
    whole = Image.new("L", (W, H), 0)
    whole.paste(m, (x_off, y_off))
    cut = round(x_off + xs[SPLIT])
    left = whole.copy()
    ImageDraw.Draw(left).rectangle((cut, 0, W, H), fill=0)
    right = ImageChops.subtract(whole, left)
    masks = {"L": {"letters": left, "outline": dilate(left, OUTLINE)},
             "R": {"letters": right, "outline": dilate(right, OUTLINE)}}
    info = {"кегль": round(size * SCALE, 1), "сжатие": round(sx, 3),
            "базовая линия": round(baseline, 1), "стык": round(cut - W / 2, 1),
            "слово": WORD, "шрифт": FONT, "наклон": SHEAR, "межбуквенное": TRACK,
            "обводка": OUTLINE, "разрез": SPLIT}
    return masks, german, info


def cut_pieces(env):
    """Восемь кусков в пространстве своих спрайтов: цвет, альфа, рамка спрайта."""
    masks, german, info = typeset(env)
    geo, sprites = geometry(env, HOST), sprites_of(env)
    pieces, rects, problems = {}, {}, []
    for side, part, outline in PARTS:
        name = sprite_name(side, part, outline)
        box = frame(geo[(side, outline)], side, part)
        mask = masks[side]["outline" if outline else "letters"]
        x0, y0 = round(box["x0"]), round(box["y0"])
        crop = mask.crop((x0, y0, x0 + round(box["w"]), y0 + round(box["h"])))
        img = Image.new("RGBA", crop.size, (WHITE if outline else CRIMSON) + (0,))
        img.putalpha(crop)
        pieces[name] = img
        # Рамка спрайта — сама рамка половины из префаба: тогда кусок и лежит в атласе,
        # и рисуется на экране один к одному. У Capcom рамка на 3 px уже (886,4 против
        # 883), её куски игра растягивает; русские вписывать в чужую рамку незачем.
        rects[name] = {"width": float(box["w"]), "height": float(box["h"])}
        if crop.getbbox() is None:
            problems.append(f"{name}: кусок пустой")
    # Ни одна половина не должна потерять пикселей на краях рамок: Top и Bottom вместе
    # обязаны забрать всю маску своей половины.
    for side in ("L", "R"):
        for layer, outline in (("letters", False), ("outline", True)):
            mask = masks[side][layer]
            whole = sum(mask.point(lambda v: v).getdata())
            taken = 0
            for part in ("Top", "Bottom"):
                box = frame(geo[(side, outline)], side, part)
                taken += sum(mask.crop((round(box["x0"]), round(box["y0"]),
                                        round(box["x0"] + box["w"]),
                                        round(box["y0"] + box["h"]))).getdata())
            if taken < whole:
                problems.append(f"{side} {layer}: рамки половины режут надпись — "
                                f"{(whole - taken) / max(whole, 1):.2%} тела букв за краем")
    return pieces, rects, masks, german, info, problems


def shelf_pack(items: list[tuple[str, tuple[int, int]]], size: int = 1024):
    """Полосами, как у самого Unity: куски по убыванию высоты, каждая полоса — своя высота.

    Возвращает {имя: (x, y сверху)} или None, если в квадрат не влезло.
    """
    place, x, y, row_h = {}, 0, 0, 0
    for name, (w, h) in sorted(items, key=lambda it: -it[1][1]):
        if x and x + w > size:
            x, y, row_h = 0, y + row_h + GAP, 0
        if y + h > size:
            return None
        place[name] = (x, y)
        x += w + GAP
        row_h = max(row_h, h)
    return place


def build_atlas(env):
    """Русский атлас 1024×1024 и новые поля кусков; мазок `anim_1_0` переезжает как есть.

    Возвращает атлас целиком, наш слой (тот же атлас без мазка — только наши пиксели,
    их и раздаём игрокам) и задание. Пикселей Capcom в слое нет: мазок патчер
    вырезает из текстуры самого игрока и кладёт на новое место.
    """
    pieces, rects, masks, german, info, problems = cut_pieces(env)
    maps, sprites = atlas_map(env), sprites_of(env)
    texture = atlas_texture(env).read()
    side = texture.m_Width
    if texture.m_Width != texture.m_Height:
        raise ValueError(f"атлас {texture.m_Width}x{texture.m_Height}, ожидался квадрат")

    keep_img, keep_off, keep_rect = piece(env, maps, sprites, KEEP)
    boxes, cuts = {}, {}
    for name, img in pieces.items():
        bb = img.getchannel("A").getbbox()
        if bb is None:
            problems.append(f"{name}: пустой кусок")
            continue
        cuts[name] = img.crop(bb)
        boxes[name] = {"bb": bb, "rect": rects[name]}
    cuts[KEEP] = keep_img

    spots = shelf_pack([(n, im.size) for n, im in cuts.items()], side)
    if spots is None:
        raise SystemExit("русские куски не влезли в атлас 1024×1024 — нужна другая раскладка")

    atlas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    spec = {}
    keep_box = None
    for name, (x, y) in spots.items():
        img = cuts[name]
        atlas.paste(img, (x, y))
        if name == KEEP:
            offset, rect = keep_off, keep_rect
            bb = (0, 0, img.width, img.height)
        else:
            bb, rect = boxes[name]["bb"], boxes[name]["rect"]
            offset = {"x": float(bb[0]), "y": float(round(rect["height"]) - bb[3])}

        spec[name] = {
            "textureRect": {"x": float(x), "y": float(side - y - img.height),
                            "width": float(img.width), "height": float(img.height)},
            "textureRectOffset": {"x": float(offset["x"]), "y": float(offset["y"])},
            "rect": {"width": float(rect["width"]), "height": float(rect["height"])},
        }
        if name == KEEP:
            # Мазок только переезжает: рамка и тугая сетка у него свои и верные,
            # трогать их незачем — в атласе меняется лишь место. Его пиксели — Capcom,
            # в наш слой они не идут: патчер вырежет их у игрока.
            keep_rd = maps[key_of(sprites[KEEP].read_typetree()["m_RenderDataKey"])]
            spec[name]["как есть"] = True
            spec[name]["было"] = {k: float(v) for k, v in keep_rd["textureRect"].items()}
            keep_box = (x, y, img.width, img.height)
    layer = atlas.copy()
    if keep_box is not None:
        x, y, w, h = keep_box
        layer.paste(Image.new("RGBA", (w, h), (0, 0, 0, 0)), (x, y))
    return atlas, layer, spec, masks, german, info, problems


def assemble(atlas: Image.Image, spec: dict, geo: dict) -> Image.Image:
    """Заставка, собранная из записанных кусков — то же, что сделает игра."""
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    side = atlas.width
    for outline in (True, False):
        for s in ("L", "R"):
            for part in ("Top", "Bottom"):
                name = sprite_name(s, part, outline)
                item = spec[name]
                r = item["textureRect"]
                img = atlas.crop((round(r["x"]), round(side - r["y"] - r["height"]),
                                  round(r["x"] + r["width"]), round(side - r["y"])))
                lay(canvas, img, frame(geo[(s, outline)], s, part),
                    item["textureRectOffset"], item["rect"])
    return canvas


def expected(masks: dict) -> Image.Image:
    """Как русская заставка задумана набором: обводка под буквами, без атласа.

    Слои кладутся тем же порядком, что и куски в игре, и цвет у прозрачных пикселей
    остаётся своим: иначе полупрозрачный край буквы умножился бы на альфу дважды.
    """
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for colour, layer in ((WHITE, "outline"), (CRIMSON, "letters")):
        for s in ("L", "R"):
            im = Image.new("RGBA", (W, H), colour + (0,))
            im.putalpha(masks[s][layer])
            canvas.alpha_composite(im)
    return canvas


def on_dark(im: Image.Image, shade=(40, 40, 48)) -> Image.Image:
    bg = Image.new("RGBA", im.size, shade + (255,))
    bg.alpha_composite(im.convert("RGBA"))
    return bg.convert("RGB")


def sheet(rows: list[tuple[str, Image.Image]], path: Path) -> None:
    fnt = ImageFont.truetype(str(FONTS / LABEL_FONT), 26)
    width = max(im.width for _, im in rows)
    height = sum(im.height + 44 for _, im in rows) + 8
    out = Image.new("RGB", (width, height), (28, 28, 28))
    d = ImageDraw.Draw(out)
    y = 8
    for label, im in rows:
        d.text((10, y), label, font=fnt, fill=(255, 215, 80))
        out.paste(im, (0, y + 36))
        y += im.height + 44
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="ничего не писать: набрать заново в памяти и сверить с лежащим PNG")
    ap.add_argument("--built", nargs="?", const="", metavar="БАНДЛ",
                    help="сверить собранный бандл с оригиналом и собрать лист из него; "
                         "по умолчанию берётся work/build_assets")
    args = ap.parse_args()

    env = open_bundle()
    if args.check and not ATLAS_PNG.exists():
        print(f"заставка не набрана ({ATLAS_PNG}) — сверять нечего; набрать: tools/splash.py")
        return 2 if args.check else 0

    atlas, layer, spec, masks, german, info, problems = build_atlas(env)
    geo = geometry(env, HOST)
    print("набор: " + ", ".join(f"{k} {v}" for k, v in info.items()))

    # Сверка: собранное из кусков против задуманного набором — так, как это увидит
    # игрок, то есть уже на фоне: у прозрачных пикселей цвет свой у каждого куска
    # и на экране его никто не увидит.
    want, got = expected(masks), assemble(atlas, spec, geo)
    diff = ImageChops.difference(on_dark(want), on_dark(got)).getbbox()
    if diff or ImageChops.difference(want.getchannel("A"), got.getchannel("A")).getbbox():
        stat = ImageChops.difference(on_dark(want), on_dark(got))
        worst = max(band[1] for band in stat.getextrema())
        problems.append(f"сборка из кусков расходится с набором: рамка {diff}, до {worst} уровней")

    # Мазок `anim_1_0` обязан переехать нетронутым.
    maps, sprites = atlas_map(env), sprites_of(env)
    keep_img, _, _ = piece(env, maps, sprites, KEEP)
    r = spec[KEEP]["textureRect"]
    moved = atlas.crop((round(r["x"]), round(atlas.height - r["y"] - r["height"]),
                        round(r["x"] + r["width"]), round(atlas.height - r["y"])))
    if ImageChops.difference(moved, keep_img).getbbox():
        problems.append("мазок anim_1_0 при переупаковке изменился")

    # Надпись не должна вылезать за рамки половин — их края режут буквы.
    for side, part, outline in PARTS:
        name = sprite_name(side, part, outline)
        r = spec[name]["textureRect"]
        off = spec[name]["textureRectOffset"]
        rect = spec[name]["rect"]
        if off["x"] < 0 or off["y"] < 0 or off["x"] + r["width"] > rect["width"] + 1 \
                or off["y"] + r["height"] > rect["height"] + 1:
            problems.append(f"{name}: кусок {r['width']:.0f}x{r['height']:.0f} не влезает "
                            f"в рамку спрайта {rect['width']:.0f}x{rect['height']:.0f}")

    used = sum(round(spec[n]["textureRect"]["width"]) * round(spec[n]["textureRect"]["height"])
               for n in spec)
    print(f"атлас {atlas.width}×{atlas.height}: занято {used / atlas.width / atlas.height:.0%}, "
          f"кусков {len(spec)}")
    for side, part, outline in PARTS:
        name = sprite_name(side, part, outline)
        r, off = spec[name]["textureRect"], spec[name]["textureRectOffset"]
        print(f"  {name[len(PREFIX) + 1:]:24} {r['width']:5.0f}x{r['height']:5.0f} "
              f"в атласе x {r['x']:4.0f} y {r['y']:4.0f}, в рамке ({off['x']:5.0f},{off['y']:5.0f})")

    if args.built is not None:
        live = next(BUNDLES.glob(f"{BUNDLE}_assets_all_*.bundle"))
        path = Path(args.built) if args.built else WORK / "build_assets" / live.name
        if not path.exists():
            sys.exit(f"{path} не собран — сначала tools/inject_localized.py")
        found, shot = verify_built(path)
        problems += found
        sheet([("Оригинал: немецкая заставка, собранная из кусков её атласа", on_dark(flatten(german))),
               ("Результат: русская заставка, собранная из того, что легло в бандл", on_dark(shot)),
               ("Где менялись пиксели: атлас заставки — оригинал | русский",
                on_dark(atlas_pair(env, atlas)))], SHEET)
        print(f"лист: {SHEET}")
        for p in problems:
            print(f"  БЕДА: {p}", file=sys.stderr)
        return 1 if problems else 0

    if args.check:
        if ImageChops.difference(Image.open(ATLAS_PNG).convert("RGBA"), layer).getbbox():
            problems.append(f"{ATLAS_PNG.name} не совпадает с набором по заданию — tools/splash.py")
    else:
        UI.mkdir(parents=True, exist_ok=True)
        layer.save(ATLAS_PNG)
        save_json(SPEC_JSON, {"вариант": "A", "набор": info, "атлас": ATLAS, "бандл": BUNDLE,
                              "префаб": prefab_key(env), "мазок": KEEP,
                              "размер": [atlas.width, atlas.height],
                              "текстура_sha": pixels_sha(atlas_texture(env).read().image),
                              "куски": spec})
        sheet([("Немецкая заставка, собранная из кусков оригинала", on_dark(flatten(german))),
               ("Русская заставка, собранная из записанных кусков", on_dark(got)),
               ("Атлас: оригинал | русский", on_dark(atlas_pair(env, atlas)))], SHEET)
        print(f"атлас: {ATLAS_PNG}\nзадание: {SPEC_JSON}\nлист: {SHEET}")

    for p in problems:
        print(f"  БЕДА: {p}", file=sys.stderr)
    return 1 if problems else 0


def from_bundle(env) -> Image.Image:
    """Заставка, собранная из того, что лежит в бандле, — по карте атласа и префабу."""
    maps, sprites, geo = atlas_map(env), sprites_of(env), geometry(env, HOST)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for outline in (True, False):
        for side in ("L", "R"):
            for part in ("Top", "Bottom"):
                img, offset, rect = piece(env, maps, sprites, sprite_name(side, part, outline))
                lay(canvas, img, frame(geo[(side, outline)], side, part), offset, rect)
    return canvas


def verify_built(path: Path) -> tuple[list[str], Image.Image]:
    """То же, что `verify_bundle`, но для бандла, лежащего файлом. Законные правки других
    наших картинок того же бандла (фон чтения, заставки расследования) — не «лишнее»."""
    from layer_localized import bundle_neighbours

    return verify_bundle(UnityPy.load(str(path)), bundle_neighbours(BUNDLE, "splash"))


def verify_bundle(built, others: set[str] = frozenset()) -> tuple[list[str], Image.Image]:
    """Сверка собранного бандла с нетронутым оригиналом и с набором.

    Правило №13: картинка готова, только когда машина сверила её с оригиналом
    из `backup/`, а не с живым бандлом. Сверяются четыре вещи: заставка из бандла
    против набора, мазок против оригинала, адрес немецкого префаба и то, что в бандле
    не тронулось ничего лишнего. Допуск — на потери BC7: грубых пикселей (расхождение
    больше 64 уровней) не больше 0,01 %, как в `selftest.py`.

    `others` — имена объектов других наших картинок в том же бандле (фон чтения
    `Sousa_TextCutBG_R_05_ger`, 10 октября 2026) и path_id безымянных (префабы заставок
    расследования, `titles.py`, 12 октября 2026): их правка законна, свою сверку
    они проходят сами.
    """
    orig = open_bundle()
    problems: list[str] = []

    masks, _, _ = typeset(orig)
    want, got = on_dark(expected(masks)), on_dark(from_bundle(built))
    diff = ImageChops.difference(want, got)
    rough = sum(1 for v in diff.convert("L").getdata() if v > 64)
    worst = max(band[1] for band in diff.getextrema())
    share = rough / (W * H)
    print(f"заставка из бандла против набора: грубых пикселей {rough} ({share:.4%}), "
          f"максимум {worst} уровней")
    if share > 0.0001:
        problems.append(f"заставка из бандла расходится с набором: {share:.3%} грубых пикселей")

    keep_before, _, _ = piece(orig, atlas_map(orig), sprites_of(orig), KEEP)
    keep_after, _, _ = piece(built, atlas_map(built), sprites_of(built), KEEP)
    if keep_before.size != keep_after.size:
        problems.append("мазок anim_1_0 сменил размер")
    else:
        d = max(band[1] for band in ImageChops.difference(keep_before, keep_after).getextrema())
        print(f"мазок anim_1_0: {keep_before.size[0]}x{keep_before.size[1]}, расхождение до {d} уровней")
        if d > 64:
            problems.append(f"мазок anim_1_0 изменился на {d} уровней")

    def container(env):
        ab = next(o for o in env.objects if o.type.name == "AssetBundle")
        return {k: v["asset"]["m_PathID"] for k, v in ab.read_typetree()["m_Container"]}

    key = prefab_key(orig)
    if container(built).get(key) != container(orig).get(key):
        problems.append("адрес немецкого префаба уведён — на экране встанет английская заставка")

    def stamps(env):
        out = {}
        for o in env.objects:
            try:
                name = o.peek_name() or ""
            except Exception:  # noqa: BLE001 — у части объектов имени нет вовсе
                name = ""
            out[o.path_id] = (o.type.name, name, hash(o.get_raw_data()))
        return out

    before, after = stamps(orig), stamps(built)
    changed = [(k, *before[k]) for k in before if k in after and before[k][2] != after[k][2]]
    allowed = {sprite_name(side, part, outline) for side, part, outline in PARTS}
    stray = [f"{kind} {name or pid}" for pid, kind, name, _ in changed
             if name not in allowed and name not in others and pid not in others
             and kind not in ("AssetBundle", "SpriteAtlas")
             and not (kind == "Texture2D" and ATLAS in name)]
    print(f"в бандле изменилось объектов: {len(changed)} из {len(before)}"
          + (f"; лишние: {', '.join(stray)}" if stray else "; лишнего не тронуто"))
    if stray:
        problems.append(f"в бандле тронуто лишнее: {', '.join(stray[:5])}")
    return problems, from_bundle(built)


def atlas_pair(env, atlas: Image.Image) -> Image.Image:
    """Две текстуры атласа рядом: что было и что стало."""
    before = atlas_texture(env).read().image.convert("RGBA")
    pair = Image.new("RGBA", (before.width + atlas.width + 8, max(before.height, atlas.height)),
                     (0, 0, 0, 0))
    pair.paste(before, (0, 0))
    pair.paste(atlas, (before.width + 8, 0))
    return pair


if __name__ == "__main__":
    raise SystemExit(main())
