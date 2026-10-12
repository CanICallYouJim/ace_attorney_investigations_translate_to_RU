"""Буквенные заставки «Начало расследования» / «Расследование завершено» (`SousaPart_Title_Start/End_R`).

Заставка — не картинка, а конструктор: надпись разрезана на куски, каждый кусок —
два спрайта (белая обводка `Char_NN_W` и малиновые буквы `Char_NN` её потомком),
куски лежат в атласе `SousaPart_Title_StEd_ger` (текстура 1024×2048 BC7), а где
кусок стоит на экране, задаёт `RectTransform` его слота в немецком префабе.
Анимация общая для всех языков: клип включает слоты по номеру через 0,267 с
(`Char_00_W` сразу, `Char_01_W` на 0,267, `Char_02_W` на 0,533, `Char_03_W` на 0,8),
буквы проявляются альфой следом. Позиции кусков клип не трогает — их задаёт префаб.
Разбор — `docs/localized-assets.md`, «Буквенные заставки — разбор 12 октября 2026».

Решения пользователя 12 октября 2026 (`docs/decisions.md`): «Начало расследования»
и «Расследование завершено» в две строки, Segoe UI Black прямым начертанием
с наклоном 0,16 (курсивные гарнитуры пишут кириллицу курсивными формами), кегль
и сжатие — по немецкому «Ermittlung» этой же игры, штрих утончён на 2,5 px до
немецкого, малиновый (152, 0, 56), белая обводка 17 px; строки по центру, как у немцев.

Раскладка. У немцев шесть уникальных кусков на две заставки (общая первая строка
«Ermitt|lung» + «star|ten» / «abgesch|lossen»), и спрайтов в атласе ровно шесть пар.
У нас первые строки разные, поэтому кусков тоже шесть, но иначе: «Начало» одним
куском, «рассле|дования»; «Рассле|дование», «завершено» одним куском. Лишний слот
в каждой заставке сжат в точку (`m_LocalScale` 0): у «Начала» — первый (`L/Char_00`),
тогда три куска встают на 0,267 / 0,533 / 0,8 с, ровным шагом и кончают вместе
с немецкими; у «завершено» — последний (`R/Char_03`), и куски встают на 0 / 0,267 /
0,533. Спрайты из-за этого переставлены минимально: у Start ни одной ссылки не
тронуто, у End — одна пара (`L/Char_01` и его буквы смотрят на `End_03` вместо
общего `Start_01`). Имена спрайтов после этого не говорят, что в них лежит, —
таблица `PIECES` ниже.

Рамка слота (`m_SizeDelta`) — рамка куска с обводкой и запасом, высота 280 и центр
по высоте — как у немецкого слота той же строки; `m_AnchoredPosition` ставит кусок
ровно туда, где его задумал набор. Рамка спрайта равна рамке слота, так что кусок
рисуется один к одному, без растяжения.

    tools\\titles.py              набрать, упаковать атлас, сверить, лист — work/graphics_masks/checks/titles.png
    tools\\titles.py --check      ничего не писать: набрать заново в памяти и сверить с лежащим PNG и заданием
    tools\\titles.py --built [Б]  сверить собранный бандл (по умолчанию work/build_assets) с оригиналом
                                 и с набором; лист — кадры, собранные из бандла
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import UnityPy
from PIL import Image, ImageChops, ImageDraw, ImageFont
from scipy import ndimage

from common import BACKUP, BUNDLES, WORK, save_json, load_json
from picture_layer import pixels_sha

UI = WORK / "graphics_ru" / "ui"
ATLAS_PNG = UI / "titles_StEd_ger.png"
SPEC_JSON = UI / "titles.json"
SHEET = WORK / "graphics_masks" / "checks" / "titles.png"
BUNDLE = "gk_common_ingameui_trial"
ATLAS = "SousaPart_Title_StEd_ger"
HOST = "ger"

FONTS = Path("C:/Windows/Fonts")
FONT = "seguibl.ttf"          # Segoe UI Black, прямое начертание
LABEL_FONT = "segoeuib.ttf"
SHEAR = 0.16                  # наклон, как у немецких кусков (≈9°)
THIN = -2.5                   # штрих: утончить на столько px с каждой стороны — до немецкого
CRIMSON = (152, 0, 56)
WHITE = (255, 255, 255)
OUTLINE = 17                  # белая обводка, px — замер по немецкой заставке
GERMAN_LINE1 = "Ermittlung"   # по нему кегль и сжатие
MARGIN = 2                    # запас рамки слота вокруг обводки, px
GAP = 2                       # зазор между кусками в атласе

W, H = 1920, 1080             # экран, в котором префаб раскладывает куски

# Заставка -> её немецкий префаб и русские строки (L — первая, R — вторая).
PREFABS = {"Start": f"SousaPart_Title_Start_R_{HOST}", "End": f"SousaPart_Title_End_R_{HOST}"}
LINES = {"Start": ("Начало", "расследования"), "End": ("Расследование", "завершено")}

# Кусок: заставка, слот в префабе, спрайт (основа имени), буквы. Куски строки идут
# слева направо и вместе дают строку целиком.
PIECES = [
    ("Start", "L/Char_01", "Start_01", "Начало"),
    ("Start", "R/Char_02", "Start_02", "рассле"),
    ("Start", "R/Char_03", "Start_03", "дования"),
    ("End", "L/Char_00", "Start_00", "Рассле"),
    ("End", "L/Char_01", "End_03", "дование"),
    ("End", "R/Char_02", "End_02", "завершено"),
]
# Слоты, которым куска нет: сжать в точку. Клип их всё равно включит — рисовать нечего.
HIDE = [("Start", "L/Char_00"), ("End", "R/Char_03")]


def sprite_name(base: str, outline: bool) -> str:
    return f"SousaPart_Title_{base}_{'W_' if outline else ''}R_{HOST}"


def slot_path(slot: str, outline: bool) -> str:
    """`L/Char_01` -> путь узла от корня префаба: обводка — слот, буквы — его потомок."""
    group, char = slot.split("/")
    node = f"root/Title/{group}/{char}_W"
    return node if outline else f"{node}/{char}"


# --- бандл --------------------------------------------------------------------

def open_bundle():
    """Оригинал бандла из `backup/`, а не живой файл: в живом уже стоит подмена."""
    live = next(BUNDLES.glob(f"{BUNDLE}_assets_all_*.bundle"))
    source = BACKUP / live.name
    return UnityPy.load(str(source if source.exists() else live))


def key_of(k):
    first, second = k
    return (tuple(first.values()) if isinstance(first, dict) else tuple(first), second)


def atlas_object(env):
    found = [o for o in env.objects if o.type.name == "SpriteAtlas" and o.peek_name() == ATLAS]
    if len(found) != 1:
        raise KeyError(f"атлас {ATLAS} не найти: нашлось {len(found)}")
    return found[0]


def atlas_map(env) -> dict:
    """Ключ спрайта -> его запись в карте атласа (где кусок лежит на самом деле)."""
    return {key_of(k): rd for k, rd in atlas_object(env).read_typetree()["m_RenderDataMap"]}


def atlas_texture(env):
    """Текстура атласа: одна на все двенадцать спрайтов заставок."""
    objs = {o.path_id: o for o in env.objects}
    found = {rd["texture"]["m_PathID"] for _, rd in atlas_object(env).read_typetree()["m_RenderDataMap"]}
    if len(found) != 1:
        raise KeyError(f"у атласа {ATLAS} текстур {len(found)}, ожидалась одна")
    return objs[found.pop()]


def sprites_of(env) -> dict:
    return {o.peek_name(): o for o in env.objects if o.type.name == "Sprite" and o.peek_name()}


def container(env) -> dict:
    ab = next(o for o in env.objects if o.type.name == "AssetBundle")
    return {k: v["asset"]["m_PathID"] for k, v in ab.read_typetree()["m_Container"]}


def prefab_keys(env) -> dict[str, str]:
    """Заставка -> адрес её немецкого префаба в контейнере бандла."""
    out = {}
    keys = list(container(env))
    for title, prefab in PREFABS.items():
        found = [k for k in keys if k.endswith(f"/{prefab}.prefab")]
        if len(found) != 1:
            raise KeyError(f"адрес префаба {prefab} не найти: нашлось {len(found)}")
        out[title] = found[0]
    return out


def nodes(env, prefab: str) -> dict[str, dict]:
    """Узлы префаба: путь от корня -> {RectTransform, его path_id, Image и его path_id}."""
    objs = {o.path_id: o for o in env.objects}
    roots = [o for o in env.objects if o.type.name == "GameObject" and o.peek_name() == prefab]
    if len(roots) != 1:
        raise KeyError(f"префаб {prefab} не найти: нашлось {len(roots)}")
    found: dict[str, dict] = {}

    def walk(tr_obj, parts):
        tt = tr_obj.read_typetree()
        go = objs[tt["m_GameObject"]["m_PathID"]].read_typetree()
        path = "/".join(parts[1:] + [go["m_Name"]]) if parts else ""
        item = {"rt": tt, "rt_id": tr_obj.path_id, "active": go["m_IsActive"], "image": None, "image_id": None}
        for c in go["m_Component"]:
            obj = objs.get(c["component"]["m_PathID"])
            if obj is not None and obj.type.name == "MonoBehaviour":
                mb = obj.read_typetree()
                if "m_Sprite" in mb:
                    item["image"], item["image_id"] = mb, obj.path_id
        found[path] = item
        for ch in tt.get("m_Children", []):
            walk(objs[ch["m_PathID"]], parts + [go["m_Name"]])

    g = roots[0].read_typetree()
    rt = next(objs[c["component"]["m_PathID"]] for c in g["m_Component"]
              if objs[c["component"]["m_PathID"]].type.name == "RectTransform")
    walk(rt, [])
    return found


# --- сборка кадра из префаба и атласа ------------------------------------------

def piece_image(env, maps, sprite_obj):
    """Кусок спрайта из атласа: картинка, смещение в рамке спрайта (от низа), рамка спрайта."""
    objs = {o.path_id: o for o in env.objects}
    t = sprite_obj.read_typetree()
    rd = maps[key_of(t["m_RenderDataKey"])]
    tex = objs[rd["texture"]["m_PathID"]].read()
    r = rd["textureRect"]
    img = tex.image.crop((round(r["x"]), round(tex.m_Height - r["y"] - r["height"]),
                          round(r["x"] + r["width"]), round(tex.m_Height - r["y"]))).convert("RGBA")
    return img, rd["textureRectOffset"], t["m_Rect"]


def frame_layers(env, prefab: str, step: int | None = None) -> tuple[Image.Image, list[dict]]:
    """Кадр заставки так, как его рисует игра в конце появления: все слоты включены,
    буквы непрозрачны. Порядок — порядок иерархии (обводка слота, его буквы, следующий слот).

    `step` — кадр на включении слота с этим номером (клип `SousaPart_Title_In_R`):
    включены слоты с номером не больше него, буквы проявились у слотов до него.

    Рамка узла считается по правилам `RectTransform`: якоря в рамке родителя, опора,
    `m_AnchoredPosition` от опорной точки якорей, `m_SizeDelta` к размеру якорей.
    Узел с нулевым масштабом не рисуется вместе с потомками. Экран 1920×1080, y вниз.
    """
    maps = atlas_map(env)
    objs = {o.path_id: o for o in env.objects}
    tree = nodes(env, prefab)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    placed: list[dict] = []
    boxes: dict[str, tuple[float, float, float, float]] = {}      # путь -> x0, y0 (низ), ш, в

    for path in tree:                                             # порядок обхода = порядок иерархии
        rt = tree[path]["rt"]
        if path == "":
            parent = (0.0, 0.0, float(W), float(H))
        else:
            parent = boxes.get(path.rsplit("/", 1)[0] if "/" in path else "")
        if parent is None:                                        # предок сжат в точку
            boxes[path] = None
            continue
        px, py, pw, ph = parent
        a0, a1, pv = rt["m_AnchorMin"], rt["m_AnchorMax"], rt["m_Pivot"]
        ax0, ay0 = px + a0["x"] * pw, py + a0["y"] * ph
        ax1, ay1 = px + a1["x"] * pw, py + a1["y"] * ph
        sw = ax1 - ax0 + rt["m_SizeDelta"]["x"]
        sh = ay1 - ay0 + rt["m_SizeDelta"]["y"]
        refx = ax0 + (ax1 - ax0) * pv["x"] + rt["m_AnchoredPosition"]["x"]
        refy = ay0 + (ay1 - ay0) * pv["y"] + rt["m_AnchoredPosition"]["y"]
        box = (refx - sw * pv["x"], refy - sh * pv["y"], sw, sh)
        sc = rt["m_LocalScale"]
        if sc["x"] == 0 or sc["y"] == 0:
            boxes[path] = None
            continue
        if (sc["x"], sc["y"]) != (1, 1):
            raise ValueError(f"{prefab}/{path}: масштаб {sc} — сборка кадра его не умеет")
        boxes[path] = box
        img_tree = tree[path]["image"]
        if img_tree is None or not img_tree["m_Sprite"]["m_PathID"]:
            continue
        if step is not None and "Char_" in path:
            number = int(path.split("Char_")[1][:2])
            if number > step or (number == step and not path.endswith("_W")):
                continue
        sprite = objs[img_tree["m_Sprite"]["m_PathID"]]
        img, off, rect = piece_image(env, maps, sprite)
        sx, sy = box[2] / rect["width"], box[3] / rect["height"]
        want = (max(1, round(img.width * sx)), max(1, round(img.height * sy)))
        if want != img.size:
            img = img.resize(want, Image.LANCZOS)
        x = round(box[0] + off["x"] * sx)
        y = round(H - (box[1] + off["y"] * sy) - img.height)
        canvas.alpha_composite(img, (x, y))
        placed.append({"path": path, "sprite": sprite.peek_name(),
                       "box": [round(v, 1) for v in box], "at": (x, y, img.width, img.height)})
    return canvas, placed


def on_dark(im: Image.Image, shade=(40, 40, 48)) -> Image.Image:
    bg = Image.new("RGBA", im.size, shade + (255,))
    bg.alpha_composite(im.convert("RGBA"))
    return bg.convert("RGB")


# --- набор ----------------------------------------------------------------------

def render_parts(text: str, size: int, cuts: list[int]) -> tuple[list[Image.Image], int]:
    """Строка гарнитурой с наклоном: по маске на каждый кусок, все на одном холсте.

    Буквы ставятся по опережению с кернингом пары, как их поставил бы набор целой
    строкой; кусок — это просто те же буквы, нарисованные на своём слое. Так разрез
    проходит между буквами, а не по ним, и кусок, проявившийся раньше соседа, не
    показывает полбуквы. Наклон — сдвигом вокруг базовой линии. Возвращает маски
    и строку базовой линии в них.
    """
    f = ImageFont.truetype(str(FONTS / FONT), size)
    asc, desc = f.getmetrics()
    xs, x = [], 0.0
    for i, ch in enumerate(text):
        xs.append(x)
        adv = f.getlength(ch)
        kern = f.getlength(text[i:i + 2]) - adv - f.getlength(text[i + 1]) if i + 1 < len(text) else 0.0
        x += adv + kern
    extra = int(SHEAR * (asc + desc)) + 40
    width, height = int(x) + size + 2 * extra, asc + desc + 80
    base = 40 + asc
    bounds = [0] + cuts + [len(text)]
    masks = []
    for a, b in zip(bounds, bounds[1:]):
        m = Image.new("L", (width, height), 0)
        d = ImageDraw.Draw(m)
        for i in range(a, b):
            d.text((xs[i] + extra, 40), text[i], font=f, fill=255)
        m = m.transform(m.size, Image.AFFINE, (1, SHEAR, -SHEAR * base, 0, 1, 0), Image.BICUBIC)
        masks.append(m)
    return masks, base


def weight(mask: Image.Image, delta: float) -> Image.Image:
    """Утолщить (delta > 0) или утончить (delta < 0) штрих на delta px с каждой стороны."""
    if not delta:
        return mask
    a = np.asarray(mask) > 127
    if delta > 0:
        d = ndimage.distance_transform_edt(~a)
        r = np.clip(delta + 0.5 - d, 0, 1)
    else:
        d = ndimage.distance_transform_edt(a)
        r = np.clip(d - (-delta) - 0.5, 0, 1)
    return Image.fromarray((r * 255).astype(np.uint8))


def outline(mask: Image.Image, r: int = OUTLINE) -> Image.Image:
    """Белая обводка: тело букв, наращённое на r px по кругу, край сглажен на пиксель."""
    a = np.asarray(mask) > 127
    d = ndimage.distance_transform_edt(~a)
    return Image.fromarray((np.clip(r + 0.5 - d, 0, 1) * 255).astype(np.uint8))


def stroke(mask: Image.Image) -> float:
    """Толщина штриха: медиана горизонтальных отрезков тела букв длиннее 4 px."""
    a = np.asarray(mask) > 128
    runs = []
    for row in a[::2]:
        r = np.diff(np.concatenate([[0], row.astype(int), [0]]))
        runs += list(np.nonzero(r == -1)[0] - np.nonzero(r == 1)[0])
    runs = np.array(runs)
    return float(np.median(runs[runs > 4])) if len(runs) else 0.0


def baseline(mask: Image.Image) -> float:
    """Базовая линия по самой картинке: медиана низов по столбцам с краской.

    Одинаковая мера у немецкой строки и у русской: выносные (g, р, д) — меньшинство
    столбцов и в медиану не попадают.
    """
    a = np.asarray(mask) > 128
    cols = [np.nonzero(a[:, x])[0].max() for x in range(a.shape[1]) if a[:, x].any()]
    return float(np.median(cols))


def centre_x(mask: Image.Image) -> float:
    bb = mask.point(lambda v: 255 if v > 128 else 0).getbbox()
    return (bb[0] + bb[2]) / 2


def german_lines(env) -> dict:
    """Немецкие строки «Ermittlung / starten»: маска букв каждой строки на экране, база, центр."""
    _, placed = frame_layers(env, PREFABS["Start"])
    maps, sprites = atlas_map(env), sprites_of(env)
    out = {}
    for group, line in (("L", 0), ("R", 1)):
        m = Image.new("L", (W, H), 0)
        for p in placed:
            if p["path"].startswith(f"root/Title/{group}/") and not p["path"].endswith("_W"):
                img, _, _ = piece_image(env, maps, sprites[p["sprite"]])
                x, y, w, h = p["at"]
                one = Image.new("L", (W, H), 0)
                one.paste(img.getchannel("A").resize((w, h), Image.LANCZOS) if (w, h) != img.size
                          else img.getchannel("A"), (x, y))
                m = ImageChops.lighter(m, one)
        out[line] = {"mask": m, "base": baseline(m), "centre": centre_x(m)}
    return out


def calibrate(ref: Image.Image) -> tuple[int, float]:
    """Кегль по высоте немецкого «Ermittlung», сжатие по ширине — тем же набором."""
    bb = ref.point(lambda v: 255 if v > 128 else 0).getbbox()
    probe, _ = render_parts(GERMAN_LINE1, 200, [])
    pb = probe[0].point(lambda v: 255 if v > 128 else 0).getbbox()
    size = round(200 * (bb[3] - bb[1]) / (pb[3] - pb[1]))
    cand, _ = render_parts(GERMAN_LINE1, size, [])
    cb = cand[0].point(lambda v: 255 if v > 128 else 0).getbbox()
    return size, (bb[2] - bb[0]) / (cb[2] - cb[0])


def line_pieces(title: str, line: int) -> list[tuple]:
    group = "L" if line == 0 else "R"
    return [p for p in PIECES if p[0] == title and p[1].startswith(group + "/")]


def typeset(env) -> tuple[dict, dict]:
    """Русские строки на экране: маска букв каждого куска (1920×1080) и числа набора.

    Кегль и сжатие — от немецкого «Ermittlung»; базовая линия каждой строки — немецкая
    той же строки (одна мера, `baseline`); центр строки по рамке букв — на центре
    немецкой строки, то есть экрана.
    """
    german = german_lines(env)
    size, sx = calibrate(german[0]["mask"])
    masks: dict[str, Image.Image] = {}
    lines_info = {}
    for title, texts in LINES.items():
        for line, text in enumerate(texts):
            parts = line_pieces(title, line)
            if "".join(p[3] for p in parts) != text:
                raise ValueError(f"{title}: куски {[p[3] for p in parts]} не складываются в «{text}»")
            cuts, at = [], 0
            for p in parts[:-1]:
                at += len(p[3])
                cuts.append(at)
            raw, base = render_parts(text, size, cuts)
            thin = [weight(m, THIN) for m in raw]
            wide = [m.resize((round(m.width * sx), m.height), Image.LANCZOS) for m in thin]
            whole = wide[0]
            for m in wide[1:]:
                whole = ImageChops.lighter(whole, m)
            dx = round(german[line]["centre"] - centre_x(whole))
            dy = round(german[line]["base"] - baseline(whole))
            placed_whole = Image.new("L", (W, H), 0)
            placed_whole.paste(whole, (dx, dy))
            for p, m in zip(parts, wide):
                screen = Image.new("L", (W, H), 0)
                screen.paste(m, (dx, dy))
                masks[p[2]] = screen
            lines_info[f"{title} {line + 1}"] = {
                "текст": text, "куски": [p[3] for p in parts],
                "база": round(baseline(placed_whole), 1), "немецкая база": round(german[line]["base"], 1),
                "центр": round(centre_x(placed_whole), 1), "ширина": placed_whole.getbbox()[2] - placed_whole.getbbox()[0],
                "штрих": round(stroke(placed_whole), 1)}
    info = {"шрифт": FONT, "кегль": size, "сжатие": round(sx, 3), "наклон": SHEAR, "утончение": THIN,
            "обводка": OUTLINE, "цвет": list(CRIMSON),
            "немецкий штрих": round(stroke(german[0]["mask"]), 1), "строки": lines_info}
    return masks, info


# --- куски, атлас, правки -------------------------------------------------------

def coloured(alpha: Image.Image, colour: tuple) -> Image.Image:
    img = Image.new("RGBA", alpha.size, colour + (0,))
    img.putalpha(alpha)
    return img


def cut_pieces(env, masks: dict) -> tuple[dict, dict, list[str]]:
    """Шесть кусков: картинки обводки и букв в рамке слота и сама рамка на экране.

    Рамка — обводка куска с запасом `MARGIN` по ширине; по высоте — немецкий слот той же
    строки (280 px, центр как у немцев), если кусок в него влезает. Возвращает
    {спрайт: картинка в рамке}, {основа спрайта: рамка (x0, y0 сверху, ш, в)} и беды.
    """
    problems: list[str] = []
    images: dict[str, Image.Image] = {}
    frames: dict[str, tuple[int, int, int, int]] = {}
    for title, slot, base, text in PIECES:
        german = nodes(env, PREFABS[title])[slot_path(slot, True)]["rt"]
        gh = round(german["m_SizeDelta"]["y"])
        gtop = round(H / 2 - german["m_AnchoredPosition"]["y"] - gh / 2)
        letters = masks[base]
        ring = outline(letters)
        bb = ring.getbbox()
        x0, x1 = bb[0] - MARGIN, bb[2] + MARGIN
        y0, y1 = gtop, gtop + gh
        if bb[1] < y0 or bb[3] > y1:
            problems.append(f"«{text}»: обводка {bb[1]}–{bb[3]} не влезает в немецкую высоту слота "
                            f"{y0}–{y1} — рамка расширена")
            y0, y1 = min(y0, bb[1] - MARGIN), max(y1, bb[3] + MARGIN)
        if x0 < 0 or x1 > W:
            problems.append(f"«{text}»: кусок выходит за экран ({x0}–{x1})")
        box = (x0, y0, x1, y1)
        images[sprite_name(base, True)] = coloured(ring.crop(box), WHITE)
        images[sprite_name(base, False)] = coloured(letters.crop(box), CRIMSON)
        frames[base] = (x0, y0, x1 - x0, y1 - y0)
    # Обводка слота, включившегося позже, рисуется поверх букв прежних: залезет на них —
    # на экране в букве будет белая выемка. У немцев зазор на разрезе шире обводки. Мера —
    # сам кадр: порядок иерархии против «все обводки, потом все буквы»; бледная кайма
    # сглаживания, которую обводка задевает, а буквы тут же перекрывают, бедой не считается.
    for title in PREFABS:
        layered = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        mine = [p for p in PIECES if p[0] == title]
        for p in mine:
            layered.alpha_composite(coloured(outline(masks[p[2]]), WHITE))
        for p in mine:
            layered.alpha_composite(coloured(masks[p[2]], CRIMSON))
        d = np.abs(np.asarray(on_dark(expected(masks, title)), np.int16)
                   - np.asarray(on_dark(layered), np.int16)).max(-1)
        if (d > 8).any():
            problems.append(f"{title}: обводка позднего куска ложится на буквы прежнего — "
                            f"{int((d > 8).sum())} пикс., до {int(d.max())} уровней")
    return images, frames, problems


def shelf_pack(items: list[tuple[str, tuple[int, int]]], width: int, height: int):
    """Полосами, как у самого Unity: куски по убыванию высоты, каждая полоса — своя высота.

    Возвращает {имя: (x, y сверху)} или None, если не влезло."""
    place, x, y, row_h = {}, 0, 0, 0
    for name, (w, h) in sorted(items, key=lambda it: (-it[1][1], -it[1][0], it[0])):
        if w > width:
            return None
        if x and x + w > width:
            x, y, row_h = 0, y + row_h + GAP, 0
        if y + h > height:
            return None
        place[name] = (x, y)
        x += w + GAP
        row_h = max(row_h, h)
    return place


def build_atlas(env, images: dict, frames: dict) -> tuple[Image.Image, dict]:
    """Русский атлас и поля кусков. Чужих кусков в этом атласе нет — он целиком наш."""
    texture = atlas_texture(env).read()
    width, height = texture.m_Width, texture.m_Height
    cuts, boxes = {}, {}
    for name, img in images.items():
        bb = img.getchannel("A").getbbox()
        if bb is None:
            raise SystemExit(f"{name}: пустой кусок")
        cuts[name], boxes[name] = img.crop(bb), bb
    spots = shelf_pack([(n, im.size) for n, im in cuts.items()], width, height)
    if spots is None:
        raise SystemExit(f"русские куски не влезли в атлас {width}×{height} — нужна другая раскладка")
    atlas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    spec = {}
    base_of = {sprite_name(b, o): b for _, _, b, _ in PIECES for o in (True, False)}
    for name, (x, y) in sorted(spots.items()):
        img, bb = cuts[name], boxes[name]
        atlas.paste(img, (x, y))
        _, _, fw, fh = frames[base_of[name]]
        spec[name] = {
            "textureRect": {"x": float(x), "y": float(height - y - img.height),
                            "width": float(img.width), "height": float(img.height)},
            "textureRectOffset": {"x": float(bb[0]), "y": float(fh - bb[3])},
            "rect": {"width": float(fw), "height": float(fh)},
        }
    return atlas, spec


def plan_edits(env, frames: dict) -> list[dict]:
    """Правки немецких префабов: рамки слотов, ссылки на спрайты, скрытые слоты.

    «было» — поля немецкого оригинала (по ним патчер узнаёт, что пишет в ту самую игру),
    «стало» — наши. Правка, где «было» уже равно «стало», не пишется вовсе.
    """
    sprites = sprites_of(env)
    edits: list[dict] = []

    def add(title, path, node, kind, field, value):
        obj_id = node["rt_id"] if kind == "RectTransform" else node["image_id"]
        before = node["rt"][field] if kind == "RectTransform" else node["image"][field]
        if before == value:
            return
        for e in edits:
            if e["объект"] == obj_id:
                e["было"][field], e["стало"][field] = before, value
                return
        edits.append({"префаб": PREFABS[title], "узел": path, "тип": kind, "объект": obj_id,
                      "было": {field: before}, "стало": {field: value}})

    for title, slot, base, _ in PIECES:
        tree = nodes(env, PREFABS[title])
        x0, y0, w, h = frames[base]
        path = slot_path(slot, True)
        add(title, path, tree[path], "RectTransform", "m_AnchoredPosition",
            {"x": float(x0 + w / 2 - W / 2), "y": float(H / 2 - (y0 + h / 2))})
        add(title, path, tree[path], "RectTransform", "m_SizeDelta", {"x": float(w), "y": float(h)})
        for outline_ in (True, False):
            p = slot_path(slot, outline_)
            want = {"m_FileID": 0, "m_PathID": sprites[sprite_name(base, outline_)].path_id}
            add(title, p, tree[p], "MonoBehaviour", "m_Sprite", want)
    for title, slot in HIDE:
        tree = nodes(env, PREFABS[title])
        path = slot_path(slot, True)
        scale = dict(tree[path]["rt"]["m_LocalScale"])
        add(title, path, tree[path], "RectTransform", "m_LocalScale", {**scale, "x": 0.0, "y": 0.0})
    return edits


def expected(masks: dict, title: str, step: int | None = None) -> Image.Image:
    """Кадр заставки так, как его задумал набор: слоты в порядке иерархии, обводка, потом буквы."""
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for _, slot, base, _ in sorted((p for p in PIECES if p[0] == title), key=lambda p: p[1].split("/")[1]):
        number = int(slot.split("Char_")[1])
        if step is not None and number > step:
            continue
        canvas.alpha_composite(coloured(outline(masks[base]), WHITE))
        if step is None or number < step:
            canvas.alpha_composite(coloured(masks[base], CRIMSON))
    return canvas


def compare(want: Image.Image, got: Image.Image) -> tuple[int, int]:
    """Грубых пикселей (больше 64 уровней по худшему каналу, на тёмном фоне) и максимум."""
    a = np.asarray(on_dark(want), np.int16)
    b = np.asarray(on_dark(got), np.int16)
    d = np.abs(a - b).max(-1)
    return int((d > 64).sum()), int(d.max())


def build(env) -> dict:
    """Всё задание в памяти: набор, куски, атлас, правки; проверка сборкой в копии бандла."""
    masks, info = typeset(env)
    images, frames, problems = cut_pieces(env, masks)
    atlas, pieces = build_atlas(env, images, frames)
    edits = plan_edits(env, frames)
    keys = prefab_keys(env)
    info["слово"] = " / ".join(" ".join(LINES[t]) for t in PREFABS)
    info["раскладка"] = {f"{t} {slot}": f"{text} — спрайт {base}" for t, slot, base, text in PIECES}
    info["скрыты"] = [f"{t} {slot}" for t, slot in HIDE]
    spec = {"набор": info, "атлас": ATLAS, "бандл": BUNDLE,
            "префабы": [keys[t] for t in PREFABS],
            "размер": [atlas.width, atlas.height],
            "текстура_sha": pixels_sha(atlas_texture(env).read().image),
            "куски": pieces, "правки": edits}
    return {"masks": masks, "info": info, "atlas": atlas, "spec": spec, "problems": problems}


def simulate(spec: dict, atlas: Image.Image) -> tuple[object, list[str]]:
    """Записать задание в свежую копию оригинала тем же кодом, что у патчера, сохранить
    бандл в память и открыть заново — то, что получит игра."""
    from picture_layer import write_splash

    env = open_bundle()
    notes = write_splash(env, spec, atlas)
    # Записанное видно только в сохранённом бандле: UnityPy читает объекты из исходных байт.
    return UnityPy.load(env.file.save(packer="lz4")), notes


def check_frames(env, masks: dict, label: str) -> list[str]:
    """Кадры из бандла (префаб + атлас) против набора — в конце появления и на каждом шаге."""
    problems = []
    for title, prefab in PREFABS.items():
        for step in (None, 0, 1, 2, 3):
            got, _ = frame_layers(env, prefab, step)
            rough, worst = compare(expected(masks, title, step), got)
            share = rough / (W * H)
            if step is None:
                print(f"{label} {title}: кадр из бандла против набора — грубых пикселей {rough} "
                      f"({share:.4%}), максимум {worst} уровней")
            if share > 0.0001:
                problems.append(f"{title}{'' if step is None else f' (шаг {step})'}: кадр из бандла "
                                f"расходится с набором — {share:.3%} грубых пикселей")
    return problems


def atlas_pair(before: Image.Image, after: Image.Image) -> Image.Image:
    pair = Image.new("RGBA", (before.width + after.width + 8, max(before.height, after.height)), (0, 0, 0, 0))
    pair.paste(before, (0, 0))
    pair.paste(after, (before.width + 8, 0))
    return pair


def make_sheet(orig, built, info: dict, path: Path, title_line: str) -> None:
    """Лист: немецкий кадр | русский кадр (оба собраны из бандла, экран 1920×1080 в половину),
    порядок появления по шагам клипа и атлас «оригинал | русский»."""
    fnt = ImageFont.truetype(str(FONTS / LABEL_FONT), 24)
    rows: list[tuple[str, Image.Image]] = []
    for title, prefab in PREFABS.items():
        de, _ = frame_layers(orig, prefab)
        ru, _ = frame_layers(built, prefab)
        pair = Image.new("RGB", (W, H // 2), (28, 28, 28))
        pair.paste(on_dark(de).resize((W // 2, H // 2), Image.LANCZOS), (0, 0))
        pair.paste(on_dark(ru).resize((W // 2, H // 2), Image.LANCZOS), (W // 2, 0))
        rows.append((f"{title}: немецкий оригинал | русский — оба собраны из бандла (префаб + атлас)", pair))
        steps = Image.new("RGB", (W, H // 4 * 2 + 4), (28, 28, 28))
        for i, step in enumerate((0, 1, 2, 3)):
            for j, env in enumerate((orig, built)):
                im, _ = frame_layers(env, prefab, step)
                steps.paste(on_dark(im).resize((W // 4, H // 4), Image.LANCZOS), (i * W // 4, j * (H // 4 + 4)))
        rows.append((f"{title}: появление по клипу — слоты 0 / 0,267 / 0,533 / 0,8 с; сверху немецкий, снизу русский",
                     steps))
    before = atlas_texture(orig).read().image.convert("RGBA")
    after = atlas_texture(built).read().image.convert("RGBA")
    pair = on_dark(atlas_pair(before, after))
    pair = pair.resize((pair.width // 2, pair.height // 2), Image.LANCZOS)
    rows.append(("Атлас SousaPart_Title_StEd_ger: оригинал | русский (половина размера)", pair))
    lines = info["строки"]
    notes = [title_line,
             f"{info['шрифт']}, кегль {info['кегль']}, сжатие {info['сжатие']}, наклон {info['наклон']}, "
             f"штрих {info['утончение']} px -> {lines['Start 1']['штрих']} (нем. {info['немецкий штрих']}), "
             f"обводка {info['обводка']} px, цвет {tuple(info['цвет'])}",
             *(f"{k}: «{v['текст']}» = {' | '.join(v['куски'])}; база {v['база']} (нем. {v['немецкая база']}), "
               f"центр букв {v['центр']} (экран 960), ширина {v['ширина']}, штрих {v['штрих']}"
               for k, v in lines.items()),
             "скрыты (масштаб 0): " + ", ".join(info["скрыты"])]
    width = max(im.width for _, im in rows)
    height = 20 + 34 * len(notes) + sum(im.height + 44 for _, im in rows)
    out = Image.new("RGB", (width, height), (28, 28, 28))
    d = ImageDraw.Draw(out)
    y = 10
    for line in notes:
        d.text((10, y), line, font=fnt, fill=(255, 215, 80))
        y += 34
    for label, im in rows:
        d.text((10, y), label, font=fnt, fill=(255, 215, 80))
        out.paste(im, (0, y + 36))
        y += im.height + 44
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(path)


# --- сверка собранного бандла ---------------------------------------------------

def neighbours() -> set:
    """Что в этом бандле вправе менять другие наши картинки: их сверка — своя."""
    from layer_localized import bundle_neighbours

    return bundle_neighbours(BUNDLE, "titles")


def verify_bundle(built, others: set = frozenset(), spec: dict | None = None) -> tuple[list[str], dict]:
    """Сверка собранного бандла с нетронутым оригиналом из `backup/` и с набором.

    Правило №13: машина сверяет механику с оригиналом, а не с живым бандлом. Сверяется:
    кадры обеих заставок, собранные из бандла (префаб + атлас), против набора — в конце
    появления и на каждом шаге клипа (потери BC7: грубых пикселей не больше 0,01 %);
    правки префабов стоят («стало»); адреса немецких префабов не уведены на английские;
    в бандле не тронуто ничего, кроме кусков, атласа, объектов с правками и `others` —
    имён и path_id других наших картинок того же бандла.
    """
    from picture_layer import edits_state

    spec = spec or load_json(SPEC_JSON)
    orig = open_bundle()
    masks, _ = typeset(orig)
    problems = check_frames(built, masks, "сверка бандла:")

    state = edits_state(built, spec["правки"])
    print(f"правки префабов: {len(spec['правки'])}, в бандле — «{state}»")
    if state != "стало":
        problems.append(f"правки префабов в бандле не стоят: {state}")

    before, after = container(orig), container(built)
    for key in spec["префабы"]:
        if after.get(key) != before.get(key):
            problems.append(f"адрес {key.rsplit('/', 1)[-1]} уведён — на экране встанет английская заставка")

    def stamps(env):
        out = {}
        for o in env.objects:
            try:
                name = o.peek_name() or ""
            except Exception:  # noqa: BLE001 — у части объектов имени нет вовсе
                name = ""
            out[o.path_id] = (o.type.name, name, hash(o.get_raw_data()))
        return out

    a, b = stamps(orig), stamps(built)
    changed = [(pid, a[pid]) for pid in a if pid in b and a[pid][2] != b[pid][2]]
    mine = set(spec["куски"]) | {e["объект"] for e in spec["правки"]} | {atlas_texture(orig).path_id}
    stray = [f"{kind} {name or pid}" for pid, (kind, name, _) in changed
             if kind != "AssetBundle" and not (kind == "SpriteAtlas" and (name == ATLAS or name in others))
             and name not in mine and pid not in mine and name not in others and pid not in others]
    print(f"в бандле изменилось объектов: {len(changed)} из {len(a)}"
          + (f"; лишние: {', '.join(stray)}" if stray else "; лишнего не тронуто"))
    if stray:
        problems.append(f"в бандле тронуто лишнее: {', '.join(stray[:5])}")
    return problems, {"orig": orig, "masks": masks}


# --- запуск ---------------------------------------------------------------------

def report(spec: dict, atlas: Image.Image) -> None:
    info = spec["набор"]
    print(f"набор: {info['шрифт']}, кегль {info['кегль']}, сжатие {info['сжатие']}, наклон {info['наклон']}, "
          f"утончение {info['утончение']}, обводка {info['обводка']}; немецкий штрих {info['немецкий штрих']}")
    for k, v in info["строки"].items():
        print(f"  {k:8} «{v['текст']}» = {' | '.join(v['куски'])}: база {v['база']} (нем. {v['немецкая база']}), "
              f"центр {v['центр']}, ширина {v['ширина']}, штрих {v['штрих']}")
    used = sum(round(p["textureRect"]["width"]) * round(p["textureRect"]["height"]) for p in spec["куски"].values())
    print(f"атлас {atlas.width}×{atlas.height}: занято {used / atlas.width / atlas.height:.0%}, кусков {len(spec['куски'])}")
    for e in spec["правки"]:
        print(f"  правка {e['префаб'][16:]:14} {e['узел'][11:]:22} {e['тип']:14} "
              + ", ".join(f"{f}: {e['было'][f]} -> {e['стало'][f]}" for f in e["стало"]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="ничего не писать: набрать заново в памяти и сверить с лежащим PNG и заданием")
    ap.add_argument("--built", nargs="?", const="", metavar="БАНДЛ",
                    help="сверить собранный бандл с оригиналом и с набором, лист — из него; "
                         "по умолчанию work/build_assets")
    args = ap.parse_args()

    if args.check and not (ATLAS_PNG.exists() and SPEC_JSON.exists()):
        print(f"заставки не набраны ({ATLAS_PNG.name}, {SPEC_JSON.name}) — сверять нечего; набрать: tools/titles.py")
        return 2

    if args.built is not None:
        live = next(BUNDLES.glob(f"{BUNDLE}_assets_all_*.bundle"))
        path = Path(args.built) if args.built else WORK / "build_assets" / live.name
        if not path.exists():
            sys.exit(f"{path} не собран — сначала tools/inject_localized.py")
        spec = load_json(SPEC_JSON)
        built = UnityPy.load(str(path))
        problems, ctx = verify_bundle(built, neighbours(), spec)
        make_sheet(ctx["orig"], built, spec["набор"], SHEET,
                   f"Собранный бандл: {path.name} — кадры собраны из него, немецкие — из backup/")
        print(f"лист: {SHEET}")
        for p in problems:
            print(f"  БЕДА: {p}", file=sys.stderr)
        return 1 if problems else 0

    orig = open_bundle()
    job = build(orig)
    spec, atlas, problems = job["spec"], job["atlas"], list(job["problems"])
    report(spec, atlas)

    # Сборка тем же кодом, что у патчера, в копии оригинала — и кадры из неё против набора.
    env, notes = simulate(spec, atlas)
    print("запись в копию бандла: " + "; ".join(notes))
    if any("оставлена как есть" in n for n in notes):
        problems.append("запись в бандл отказала: " + "; ".join(notes))
    else:
        problems += check_frames(env, job["masks"], "в памяти:")

    if args.check:
        if ImageChops.difference(Image.open(ATLAS_PNG).convert("RGBA"), atlas).getbbox():
            problems.append(f"{ATLAS_PNG.name} не совпадает с набором по заданию — tools/titles.py")
        if load_json(SPEC_JSON) != json_roundtrip(spec):
            problems.append(f"{SPEC_JSON.name} не совпадает с заданием, собранным заново — tools/titles.py")
    else:
        UI.mkdir(parents=True, exist_ok=True)
        atlas.save(ATLAS_PNG)
        save_json(SPEC_JSON, spec)
        make_sheet(orig, env, spec["набор"], SHEET,
                   "Проба в памяти: задание записано в копию оригинала кодом патчера; кадры собраны из неё")
        print(f"атлас: {ATLAS_PNG}\nзадание: {SPEC_JSON}\nлист: {SHEET}")

    for p in problems:
        print(f"  БЕДА: {p}", file=sys.stderr)
    if not problems:
        print("заставки сходятся: кадры из бандла равны набору, задание и атлас на месте")
    return 1 if problems else 0


def json_roundtrip(data):
    import json

    return json.loads(json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
