"""Заставки ментальных шахмат по-русски: «Ментальные шахматы» + «Начали!» / «Шах и мат».

Три немецких префаба в бандле `gk2_logicchess_trial`: `LogicChess_Title_Start_R_ger`
(начало, у немцев «Mentalschach / Start»), `LogicChess_Title_Success_R_ger` (победа,
«Mentalschach / Schach matt») и `LogicChess_Title_ger` (та же раскладка без аниматора).
Все куски — в атласе `LogicChess_Title_ger` (текстура 1024×2048 BC7).

Устройство (разбор 12 октября 2026, `docs/localized-assets.md`):

  * верхнее слово — двенадцать слотов `Char_*` двумя гребёнками: чётные (`pos_0`)
    и нечётные (`pos_1`) въезжают навстречу друг другу, каждый слот ещё «выпрыгивает»
    масштабом. У слота два спрайта: `_W` — бледно-голубой ореол, без `_W` — синие буквы
    с белой каймой. Спрайты букв `R_00..R_11` общие у всех трёх префабов;
  * нижнее слово — два куска `Char_d0`/`Char_d1` (`R_12/13` у начала и у `Title`, `R_14/15`
    у победы), появляются альфой;
  * клипы (`LogicChess_Title_R_In`, `_Start_R`, `_Success_R`) ведут масштаб слотов,
    позиции и альфу групп — но не позиции самих слотов: их задаёт префаб. Скрипт
    `LogicChessBigFontDemo` на корне — только аниматор, кадры звука, вспышки и тряски;
    букв он не двигает.

Решения пользователя 12 октября 2026: «Ментальные шахматы» в одну строку уменьшенным
кеглем (≈0,83 немецкого), «Начали!», «Шах и мат»; Segoe UI Black прямым начертанием
с наклоном по замеру немецкого; цвет, кайма, ореол и штрих — замером по немецким кускам.

Раскладка верхней строки — двенадцать кусков на 17 букв: одиночные и пары через одну,
граница слов — между кусками (`TOP`). Слоты остаются в своих гребёнках, меняются только
рамки слотов (`m_AnchoredPosition`, `m_SizeDelta`) во всех трёх префабах; ссылки на
спрайты не трогаются.

    tools\\titles_chess.py              набрать, упаковать атлас, сверить пробой в памяти, лист
    tools\\titles_chess.py --check      ничего не писать: набрать заново и сверить с PNG и заданием
    tools\\titles_chess.py --built [Б]  сверить собранный бандл с оригиналом и с набором
"""
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

import numpy as np
import UnityPy
from PIL import Image, ImageChops, ImageDraw, ImageFont
from scipy import ndimage

from common import BACKUP, BUNDLES, WORK, load_json, save_json
from picture_layer import pixels_sha
import titles as T

UI = WORK / "graphics_ru" / "ui"
ATLAS_PNG = UI / "titles_chess_ger.png"
SPEC_JSON = UI / "titles_chess.json"
SHEET = WORK / "graphics_masks" / "checks" / "titles_chess.png"
BUNDLE = "gk2_logicchess_trial"
ATLAS = "LogicChess_Title_ger"
HOST = "ger"

FONTS = Path("C:/Windows/Fonts")
FONT = "seguibl.ttf"
LABEL_FONT = "segoeuib.ttf"
W, H = 1920, 1080

PREFABS = {"Start": f"LogicChess_Title_Start_R_{HOST}", "Success": f"LogicChess_Title_Success_R_{HOST}",
           "Title": f"LogicChess_Title_{HOST}"}
# Клип, который играет заставка после въезда (`LogicChess_Title_R_In`): в нём нижнее слово.
CLIPS = {"Start": "LogicChess_Title_Start_R", "Success": "LogicChess_Title_Success_R"}
IN_CLIP = "LogicChess_Title_R_In"

GERMAN_TOP = "Mentalschach"
# Слоты верхнего слова слева направо (по месту у немцев) и наши куски в них.
SLOTS = ["st0", "st1", "02", "03", "04", "05", "06", "07", "08", "09", "ed0", "ed1"]
TOP = "Ментальные шахматы"
TOP_PIECES = ["М", "ен", "т", "ал", "ь", "ны", "е", "ш", "ах", "м", "ат", "ы"]
BOTTOM = {"Start": ("Нача", "ли!"), "Success": ("Шах и", "мат")}
GERMAN_BOTTOM = {"Start": ("St", "art"), "Success": ("Schach", "matt")}
TOP_SCALE = 0.83              # кегль верхней строки против немецкого — решение пользователя
EDGE = 20                     # от края экрана до ореола верхней строки, не меньше, px


# --- бандл и префабы --------------------------------------------------------------

def open_bundle():
    """Оригинал бандла из `backup/`, а не живой файл: в живом уже стоит подмена."""
    live = next(BUNDLES.glob(f"{BUNDLE}_assets_all_*.bundle"))
    source = BACKUP / live.name
    return UnityPy.load(str(source if source.exists() else live))


def atlas_maps(env) -> dict:
    """Ключ спрайта -> запись карты атласа, по всем атласам бандла."""
    out = {}
    for o in env.objects:
        if o.type.name == "SpriteAtlas":
            for k, rd in o.read_typetree()["m_RenderDataMap"]:
                out[T.key_of(k)] = rd
    return out


def atlas_object(env):
    found = [o for o in env.objects if o.type.name == "SpriteAtlas" and o.peek_name() == ATLAS]
    if len(found) != 1:
        raise KeyError(f"атлас {ATLAS} не найти: нашлось {len(found)}")
    return found[0]


def atlas_texture(env):
    objs = {o.path_id: o for o in env.objects}
    found = {rd["texture"]["m_PathID"] for _, rd in atlas_object(env).read_typetree()["m_RenderDataMap"]}
    if len(found) != 1:
        raise KeyError(f"у атласа {ATLAS} текстур {len(found)}, ожидалась одна")
    return objs[found.pop()]


def tree_of(env, prefab: str) -> dict[str, dict]:
    """Узлы префаба по порядку иерархии: путь -> RectTransform, активность, Image, CanvasGroup."""
    objs = {o.path_id: o for o in env.objects}
    roots = [o for o in env.objects if o.type.name == "GameObject" and o.peek_name() == prefab]
    if len(roots) != 1:
        raise KeyError(f"префаб {prefab} не найти: нашлось {len(roots)}")
    found: dict[str, dict] = {}

    def walk(tr_obj, parts):
        tt = tr_obj.read_typetree()
        go = objs[tt["m_GameObject"]["m_PathID"]].read_typetree()
        path = "/".join(parts[1:] + [go["m_Name"]]) if parts else ""
        item = {"rt": tt, "rt_id": tr_obj.path_id, "active": bool(go["m_IsActive"]), "image": None,
                "image_id": None, "group": None, "sorting": None, "name": go["m_Name"]}
        for c in go["m_Component"]:
            obj = objs.get(c["component"]["m_PathID"])
            if obj is None:
                continue
            if obj.type.name == "MonoBehaviour":
                mb = obj.read_typetree()
                if "m_Sprite" in mb:
                    item["image"], item["image_id"] = mb, obj.path_id
            elif obj.type.name == "CanvasGroup":
                item["group"] = obj.read_typetree()["m_Alpha"]
            elif obj.type.name == "Canvas":
                cv = obj.read_typetree()
                if cv["m_OverrideSorting"]:
                    item["sorting"] = cv["m_SortingOrder"]
        found[path] = item
        for ch in tt.get("m_Children", []):
            walk(objs[ch["m_PathID"]], parts + [go["m_Name"]])

    g = roots[0].read_typetree()
    walk(next(objs[c["component"]["m_PathID"]] for c in g["m_Component"]
              if objs[c["component"]["m_PathID"]].type.name == "RectTransform"), [])
    return found


def animator_base(tree: dict) -> str | None:
    """Путь узла с аниматором: клипы адресуют узлы от него. У `LogicChess_Title_ger` его нет."""
    return "root" if "root" in tree else None


# --- клипы: значения кривых в момент t -----------------------------------------------

ATTR = {zlib.crc32(n.encode()): n for n in ("m_AnchoredPosition.x", "m_AnchoredPosition.y", "m_IsActive",
                                             "m_Color.a", "m_Alpha", "m_SizeDelta.x", "m_SizeDelta.y")}


def clip_sampler(env, clip_name: str, tree: dict):
    """Значения анимируемых свойств узлов префаба в момент t: путь -> {свойство: значение}.

    Кривые клипа — `m_StreamedClip` (кусочно-кубические, ключ хранит коэффициенты
    сегмента), `m_DenseClip` (здесь пуст) и `m_ConstantClip`; привязки идут по порядку
    кривых, у масштаба и позиции `Transform` их по три. Пути привязок — CRC32 пути
    от узла с аниматором.
    """
    clip = next(o for o in env.objects if o.type.name == "AnimationClip" and o.peek_name() == clip_name)
    ct = clip.read_typetree()
    mc = ct["m_MuscleClip"]["m_Clip"]["data"]
    sc, dc, cc = mc["m_StreamedClip"], mc["m_DenseClip"], mc["m_ConstantClip"]
    if dc["m_CurveCount"]:
        raise ValueError(f"{clip_name}: плотные кривые не поддержаны")
    base = animator_base(tree)
    by_crc = {}
    for path in tree:
        if base and path.startswith(base + "/"):
            by_crc[zlib.crc32(path[len(base) + 1:].encode())] = path
    owners = []
    for b in ct["m_ClipBindingConstant"]["genericBindings"]:
        path = by_crc.get(b["path"])
        if b["typeID"] == 4:
            prop = {1: "pos", 2: "rot", 3: "scale", 4: "euler"}[b["attribute"]]
            for k in range(4 if prop == "rot" else 3):
                owners.append((path, f"{prop}.{'xyzw'[k]}"))
        else:
            owners.append((path, ATTR.get(b["attribute"], str(b["attribute"]))))
    data = struct.pack(f"<{len(sc['data'])}I", *sc["data"])
    keys: dict[int, list] = {}
    pos = 0
    while pos < len(data):
        t, n = struct.unpack_from("<fI", data, pos)
        pos += 8
        for _ in range(n):
            idx, a, b, c, d = struct.unpack_from("<I4f", data, pos)
            pos += 20
            keys.setdefault(idx, []).append((t, a, b, c, d))
    constants = list(cc["data"])
    stop = ct["m_MuscleClip"]["m_StopTime"]

    def at(t: float) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for idx, (path, prop) in enumerate(owners):
            if path is None:
                continue
            if idx < sc["curveCount"]:
                ks = [k for k in keys.get(idx, []) if k[0] <= t + 1e-6] or keys.get(idx, [])[:1]
                if not ks:
                    continue
                k0, a, b, c, d = ks[-1]
                dt = max(0.0, t - k0) if abs(k0) < 1e6 else 0.0
                value = ((a * dt + b) * dt + c) * dt + d
            else:
                value = constants[idx - sc["curveCount"]]
            out.setdefault(path, {})[prop] = value
        return out

    return at, stop


# --- сборка кадра -------------------------------------------------------------------

def layout(tree: dict, anim: dict | None = None) -> dict[str, tuple | None]:
    """Место каждого узла в мире: путь -> (опора x, y — экран, y вверх; масштаб x, y;
    размер w, h; опора узла; альфа; слой сортировки). Выключенный узел — None.

    Опора узла — опора родителя плюс масштаб родителя, умноженный на место узла
    в рамке родителя; масштаб и альфа `CanvasGroup` копятся по цепочке. Вложенный
    `Canvas` с `m_OverrideSorting` даёт свой слой: у шахмат буквы (`offset`, слой 1)
    рисуются поверх всех ореолов (`offset_W`, слой 0).
    """
    anim = anim or {}
    state: dict[str, tuple | None] = {}
    for path, node in tree.items():
        over = anim.get(path, {})
        active = over.get("m_IsActive", 1.0 if node["active"] else 0.0) > 0.5
        if path == "":
            parent = (W / 2, H / 2, 1.0, 1.0, W, H, (0.5, 0.5), 1.0, 0)
        else:
            parent = state.get(path.rsplit("/", 1)[0] if "/" in path else "")
        if parent is None or not active:
            state[path] = None
            continue
        ppx, ppy, psx, psy, pw, ph, ppv, palpha, order = parent
        rt = node["rt"]
        a0, a1, pv = rt["m_AnchorMin"], rt["m_AnchorMax"], rt["m_Pivot"]
        w = (a1["x"] - a0["x"]) * pw + over.get("m_SizeDelta.x", rt["m_SizeDelta"]["x"])
        h = (a1["y"] - a0["y"]) * ph + over.get("m_SizeDelta.y", rt["m_SizeDelta"]["y"])
        # опорная точка якорей в локальных координатах родителя (от его опоры)
        ax = -ppv[0] * pw + (a0["x"] + (a1["x"] - a0["x"]) * pv["x"]) * pw
        ay = -ppv[1] * ph + (a0["y"] + (a1["y"] - a0["y"]) * pv["y"]) * ph
        lx = ax + over.get("m_AnchoredPosition.x", rt["m_AnchoredPosition"]["x"])
        ly = ay + over.get("m_AnchoredPosition.y", rt["m_AnchoredPosition"]["y"])
        sc = rt["m_LocalScale"]
        sx = over.get("scale.x", sc["x"]) * psx
        sy = over.get("scale.y", sc["y"]) * psy
        alpha = palpha * (over.get("m_Alpha", node["group"]) if node["group"] is not None else 1.0)
        order = node["sorting"] if node["sorting"] is not None else order
        state[path] = (ppx + psx * lx, ppy + psy * ly, sx, sy, w, h, (pv["x"], pv["y"]), alpha, order)
    return state


def draw_items(env, prefab: str, anim: dict | None = None, tree: dict | None = None) -> list[dict]:
    """Что игра нарисует в кадре: кусок спрайта, место на экране, слой сортировки."""
    anim = anim or {}
    tree = tree or tree_of(env, prefab)
    maps = atlas_maps(env)
    objs = {o.path_id: o for o in env.objects}
    cache: dict[int, tuple] = {}
    items: list[dict] = []
    for path, st in layout(tree, anim).items():
        img_tree = tree[path]["image"]
        if st is None or img_tree is None or not img_tree["m_Sprite"]["m_PathID"]:
            continue
        px, py, sx, sy, w, h, pv, alpha, order = st
        a = alpha * anim.get(path, {}).get("m_Color.a", img_tree["m_Color"]["a"])
        if a <= 0.0 or abs(sx) < 1e-4 or abs(sy) < 1e-4:
            continue
        sid = img_tree["m_Sprite"]["m_PathID"]
        if sid not in cache:
            cache[sid] = T.piece_image(env, maps, objs[sid])
        img, off, rect = cache[sid]
        x0 = px - pv[0] * w * sx                       # левый нижний угол рамки в мире, y вверх
        y0 = py - pv[1] * h * sy
        kx, ky = w * sx / rect["width"], h * sy / rect["height"]
        want = (max(1, round(img.width * kx)), max(1, round(img.height * ky)))
        piece = img.resize(want, Image.LANCZOS) if want != img.size else img
        if a < 1.0:
            piece = piece.copy()
            piece.putalpha(piece.getchannel("A").point(lambda v, a=a: round(v * a)))
        items.append({"path": path, "order": order, "image": piece, "halo": path.endswith("_W"),
                      "at": (round(x0 + off["x"] * kx), round(H - (y0 + off["y"] * ky) - piece.height))})
    items.sort(key=lambda it: it["order"])           # сортировка устойчивая: внутри слоя — иерархия
    return items


def render(env, prefab: str, anim: dict | None = None, tree: dict | None = None,
           only: str | None = None) -> Image.Image:
    """Кадр префаба на экране 1920×1080 (`draw_items`). `only` — «W» или «C»: только ореолы
    или только буквы (для замеров)."""
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for it in draw_items(env, prefab, anim, tree):
        if only and it["halo"] != (only == "W"):
            continue
        x, y = it["at"]
        piece = it["image"]
        if 0 <= x and 0 <= y and x + piece.width <= W and y + piece.height <= H:
            canvas.alpha_composite(piece, (x, y))
        else:
            paste_clipped(canvas, piece, x, y)
    return canvas


def paste_clipped(canvas: Image.Image, piece: Image.Image, x: int, y: int) -> None:
    """Кусок, вышедший за экран: кладётся видимая часть, как обрежет её игра."""
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(piece, (x, y))
    canvas.alpha_composite(layer)


# --- замеры немецкого ----------------------------------------------------------------

BODY_THRESHOLD = 120          # синее тело: синий канал выше красного на столько


def line_masks(env, prefab: str, tree: dict | None = None) -> dict[str, Image.Image]:
    """Немецкие тела букв на экране: «top» — верхнее слово, «bottom» — нижнее, «all» — силуэт всего."""
    tree = tree or tree_of(env, prefab)
    out = {k: np.zeros((H, W), float) for k in ("top", "bottom", "all")}
    for it in draw_items(env, prefab, tree=tree):
        if it["halo"]:
            continue
        a = np.asarray(it["image"]).astype(float)
        body = a[..., 3] / 255 * np.clip((a[..., 2] - a[..., 0]) / 221.0, 0, 1)
        whole = a[..., 3] / 255
        x, y = it["at"]
        for key, v in (("bottom" if "/Char_d" in it["path"] else "top", body), ("all", whole)):
            sub = out[key][y:y + v.shape[0], x:x + v.shape[1]]
            np.maximum(sub, v[:sub.shape[0], :sub.shape[1]], out=sub)
    return {k: Image.fromarray((v * 255).astype(np.uint8)) for k, v in out.items()}


def slant(mask: Image.Image) -> float:
    """Наклон тела букв: сдвиг, после которого проекция на ось x резче всего."""
    m = mask.crop(mask.getbbox())
    best = None
    for s in np.arange(0.0, 0.40, 0.005):
        u = m.transform(m.size, Image.AFFINE, (1, -s, s * m.height / 2, 0, 1, 0), Image.BILINEAR)
        prof = np.asarray(u, dtype=float).sum(axis=0)
        score = (np.diff(prof) ** 2).sum()
        if best is None or score > best[0]:
            best = (score, s)
    return round(float(best[1]), 3)


def german_halo(env, prefab: str) -> dict:
    """Ореол `_W` по замеру: альфа по расстоянию от силуэта (кайма с буквами), цвет, кайма."""
    tree = tree_of(env, prefab)
    masks = line_masks(env, prefab, tree)
    halo = np.asarray(render(env, prefab, tree=tree, only="W")).astype(float)
    sil = np.asarray(masks["all"]) > 128
    d = ndimage.distance_transform_edt(~sil)
    table = []
    for k in np.arange(1.0, 12.5, 0.5):
        m = (d > k - 0.25) & (d <= k + 0.25)
        if m.sum():
            table.append([float(k), float(np.median(halo[..., 3][m]))])
    glow = (d > 2) & (d < 7) & (halo[..., 3] > 20)
    body = np.asarray(masks["top"]) > 128
    rim = ndimage.distance_transform_edt(~body)[sil & ~ndimage.binary_erosion(sil)]
    colour = np.asarray(render(env, prefab, tree=tree, only="C")).astype(int)
    blue = (colour[..., 3] > 250) & (colour[..., 2] - colour[..., 0] > BODY_THRESHOLD)
    return {"ореол": table, "цвет ореола": [int(v) for v in np.median(halo[glow][:, :3], 0)],
            "кайма": round(float(np.median(rim)), 1),
            "синий": [int(v) for v in np.median(colour[blue][:, :3], 0)]}


# --- набор ----------------------------------------------------------------------------

def render_parts(text: str, size: int, parts: list[str], shear: float) -> tuple[list[Image.Image], int]:
    """Строка гарнитурой с наклоном, по маске на кусок на общем холсте (как `titles.render_parts`)."""
    assert "".join(parts).replace(" ", "") == text.replace(" ", ""), (parts, text)
    f = ImageFont.truetype(str(FONTS / FONT), size)
    asc, desc = f.getmetrics()
    xs, x = [], 0.0
    for i, ch in enumerate(text):
        xs.append(x)
        adv = f.getlength(ch)
        kern = f.getlength(text[i:i + 2]) - adv - f.getlength(text[i + 1]) if i + 1 < len(text) else 0.0
        x += adv + kern
    extra = int(shear * (asc + desc)) + 40
    width, height = int(x) + size + 2 * extra, asc + desc + 80
    base = 40 + asc
    owner, i = [], 0
    for k, part in enumerate(parts):          # буква строки -> её кусок (пробел — ничей)
        for ch in part.replace(" ", ""):
            while text[i] == " ":
                owner.append(None)
                i += 1
            owner.append(k)
            i += 1
    masks = []
    for k in range(len(parts)):
        m = Image.new("L", (width, height), 0)
        d = ImageDraw.Draw(m)
        for j, ch in enumerate(text):
            if j < len(owner) and owner[j] == k:
                d.text((xs[j] + extra, 40), ch, font=f, fill=255)
        masks.append(m.transform(m.size, Image.AFFINE, (1, shear, -shear * base, 0, 1, 0), Image.BICUBIC))
    return masks, base


def calibrate(ref: Image.Image, shear: float) -> tuple[int, float]:
    """Кегль по высоте немецкого «Mentalschach», сжатие по ширине."""
    bb = ref.point(lambda v: 255 if v > 128 else 0).getbbox()
    probe, _ = render_parts(GERMAN_TOP, 200, [GERMAN_TOP], shear)
    pb = probe[0].point(lambda v: 255 if v > 128 else 0).getbbox()
    size = round(200 * (bb[3] - bb[1]) / (pb[3] - pb[1]))
    cand, _ = render_parts(GERMAN_TOP, size, [GERMAN_TOP], shear)
    cb = cand[0].point(lambda v: 255 if v > 128 else 0).getbbox()
    return size, (bb[2] - bb[0]) / (cb[2] - cb[0])


def set_line(text: str, parts: list[str], size: int, sx: float, thin: float, shear: float,
             base: float, centre: float) -> list[Image.Image]:
    """Тела кусков строки на экране: набор, утончение, сжатие; база и центр — немецкие."""
    raw, _ = render_parts(text, size, parts, shear)
    wide = [T.weight(m, thin).resize((round(m.width * sx), m.height), Image.LANCZOS) for m in raw]
    whole = wide[0]
    for m in wide[1:]:
        whole = ImageChops.lighter(whole, m)
    dx = round(centre - T.centre_x(whole))
    dy = round(base - T.baseline(whole))
    out = []
    for m in wide:
        screen = Image.new("L", (W, H), 0)
        screen.paste(m, (dx, dy))
        out.append(screen)
    return out


def dress(bodies: list[Image.Image], look: dict) -> tuple[list[Image.Image], list[Image.Image]]:
    """Строка в цвете: синее тело, белая кайма, бледно-голубой ореол — и разрез на куски.

    Кайма и ореол строятся по силуэту всей строки, как у немцев: где буквы близко, каймы
    сливаются, а не ложатся одна на другую. На куски строка делится по ближайшему телу
    буквы: каждый пиксель каймы и ореола — тому куску, чьё тело ближе. Куски не
    перекрываются, и кадр из них равен строке целиком в любом порядке рисования.
    Возвращает (буквы с каймой, ореолы) по кускам.
    """
    union = np.zeros((H, W), float)
    for b in bodies:
        union = np.maximum(union, np.asarray(b) / 255)
    body_img = Image.fromarray((union * 255).astype(np.uint8))
    sil = np.asarray(T.outline(body_img, round(look["кайма"]))).astype(float) / 255
    dist = ndimage.distance_transform_edt(~(sil > 0.5))
    table = np.array(look["ореол"], float)
    glow = np.interp(dist, np.concatenate([[0.0], table[:, 0]]), np.concatenate([[table[0, 1]], table[:, 1]])) / 255
    glow[dist == 0] = 0

    blue = np.array(look["синий"], float) / 255
    halo_rgb = np.array(look["цвет ореола"], float) / 255
    # буквы: белая кайма, сверху синее тело
    c_a = sil + union * (1 - sil)
    c_rgb = (np.ones(3) * (sil * (1 - union))[..., None] + blue * union[..., None]) / np.maximum(c_a, 1e-6)[..., None]
    # ореол: голубое свечение, сверху белый силуэт
    w_a = sil + glow * (1 - sil)
    w_rgb = (np.ones(3) * sil[..., None] + halo_rgb * (glow * (1 - sil))[..., None]) / np.maximum(w_a, 1e-6)[..., None]

    dists = np.stack([ndimage.distance_transform_edt(~(np.asarray(b) > 127)) for b in bodies])
    label = dists.argmin(0)
    letters, halos = [], []
    for k in range(len(bodies)):
        own = label == k
        for rgb, a, out in ((c_rgb, c_a, letters), (w_rgb, w_a, halos)):
            im = np.zeros((H, W, 4), np.uint8)
            im[..., :3] = np.clip(rgb * 255 + 0.5, 0, 255).astype(np.uint8)
            im[..., 3] = np.clip(a * own * 255 + 0.5, 0, 255).astype(np.uint8)
            out.append(Image.fromarray(im, "RGBA"))
    return letters, halos


def typeset(env) -> tuple[dict, dict]:
    """Все куски на экране: {(заставка, слот): (буквы, ореол)} и числа набора."""
    start = tree_of(env, PREFABS["Start"])
    masks = {t: line_masks(env, PREFABS[t]) for t in ("Start", "Success")}
    top_ref = masks["Start"]["top"]
    shear = slant(top_ref.point(lambda v: 255 if v > 128 else 0))
    size, sx = calibrate(top_ref, shear)
    german_stroke = T.stroke(top_ref)
    thin = 0.0
    best = None
    for delta in np.arange(0.0, -6.01, -0.5):          # утончение до немецкого штриха
        probe = set_line(GERMAN_TOP, [GERMAN_TOP], size, sx, float(delta), shear,
                         T.baseline(top_ref), T.centre_x(top_ref))[0]
        diff = abs(T.stroke(probe) - german_stroke)
        if best is None or diff < best[0]:
            best, thin = (diff, T.stroke(probe)), float(delta)
    look = german_halo(env, PREFABS["Success"])
    top_size = round(size * TOP_SCALE)
    lines = {}
    pieces: dict[tuple, tuple] = {}
    top_bodies = set_line(TOP, TOP_PIECES, top_size, sx, thin * TOP_SCALE, shear,
                          T.baseline(top_ref), T.centre_x(top_ref))
    letters, halos = dress(top_bodies, look)
    for slot, body, c, w in zip(SLOTS, top_bodies, letters, halos):
        pieces[("top", slot)] = (c, w, body)
    lines["верх"] = top_bodies
    for title in ("Start", "Success"):
        ref = masks[title]["bottom"]
        bodies = set_line(BOTTOM_TEXT[title], list(BOTTOM[title]), size, sx, thin, shear,
                          T.baseline(ref), T.centre_x(ref))
        letters, halos = dress(bodies, look)
        for slot, body, c, w in zip(("d0", "d1"), bodies, letters, halos):
            pieces[(title, slot)] = (c, w, body)
        lines[title] = bodies
    info = {"шрифт": FONT, "кегль": size, "кегль верха": top_size, "сжатие": round(sx, 3), "наклон": shear,
            "утончение": thin, "немецкий штрих": german_stroke, **look, "строки": {}}
    refs = {"верх": top_ref, "Start": masks["Start"]["bottom"], "Success": masks["Success"]["bottom"]}
    texts = {"верх": TOP, **BOTTOM_TEXT}
    for key, bodies in lines.items():
        whole = bodies[0]
        for b in bodies[1:]:
            whole = ImageChops.lighter(whole, b)
        bb = whole.point(lambda v: 255 if v > 128 else 0).getbbox()
        sil = T.outline(whole, round(look["кайма"]))
        sb = sil.getbbox()
        info["строки"][key] = {"текст": texts[key], "база": T.baseline(whole), "немецкая база": T.baseline(refs[key]),
                               "центр": T.centre_x(whole), "немецкий центр": T.centre_x(refs[key]),
                               "ширина": bb[2] - bb[0], "с каймой и ореолом": [sb[0] - 11, sb[2] + 11],
                               "штрих": T.stroke(whole)}
    return pieces, info


BOTTOM_TEXT = {"Start": "Начали!", "Success": "Шах и мат"}


# --- куски, атлас, правки -------------------------------------------------------------

MARGIN = 2                    # запас рамки слота вокруг куска, px


def node_path(tree: dict, name: str) -> str:
    found = [p for p, n in tree.items() if n["name"] == name]
    if len(found) != 1:
        raise KeyError(f"узел {name}: нашлось {len(found)}")
    return found[0]


def slot_nodes(title: str, slot: str) -> tuple[str, str]:
    """Имена узлов слота: ореол и буквы. Верхнее слово — `Char_<слот>`, нижнее — `Char_d0/d1`."""
    return f"Char_{slot}_W", f"Char_{slot}"


def pieces_of(title: str) -> list[tuple[str, str]]:
    """Куски, которые показывает префаб: (ключ набора, слот). У `Title` нижнее слово — как у начала."""
    bottom = "Start" if title == "Title" else title
    return [("top", s) for s in SLOTS] + [(bottom, "d0"), (bottom, "d1")]


def cut(env, pieces: dict) -> tuple[dict, dict, dict]:
    """Картинки спрайтов в рамках слотов и сами рамки на экране.

    Рамка — всё, что есть у куска (буквы с каймой и ореол), с запасом `MARGIN`; спрайт
    ореола и спрайт букв слота получают одну рамку, как у немцев. Возвращает
    {спрайт: картинка в рамке}, {ключ куска: рамка (x0, y0 сверху, ш, в)}, {ключ: (спрайт ореола, спрайт букв)}.
    """
    images, frames, names = {}, {}, {}
    objs = {o.path_id: o for o in env.objects}
    trees = {t: tree_of(env, PREFABS[t]) for t in PREFABS}
    for title in PREFABS:
        tree = trees[title]
        for key in pieces_of(title):
            halo_node, letters_node = slot_nodes(title, key[1])
            sprite_names = tuple(objs[tree[node_path(tree, n)]["image"]["m_Sprite"]["m_PathID"]].peek_name()
                                 for n in (halo_node, letters_node))
            if key in names and names[key] != sprite_names:
                raise ValueError(f"{key}: префабы смотрят на разные спрайты {names[key]} и {sprite_names}")
            names[key] = sprite_names
    for key, (letters, halo, _) in pieces.items():
        bb_c, bb_w = letters.getchannel("A").getbbox(), halo.getchannel("A").getbbox()
        x0, y0 = min(bb_c[0], bb_w[0]) - MARGIN, min(bb_c[1], bb_w[1]) - MARGIN
        x1, y1 = max(bb_c[2], bb_w[2]) + MARGIN, max(bb_c[3], bb_w[3]) + MARGIN
        box = (x0, y0, x1, y1)
        frames[key] = (x0, y0, x1 - x0, y1 - y0)
        images[names[key][0]] = halo.crop(box)
        images[names[key][1]] = letters.crop(box)
    return images, frames, names


def build_atlas(env, images: dict, frames: dict, names: dict) -> tuple[Image.Image, dict]:
    """Русский атлас и поля кусков. Атлас `LogicChess_Title_ger` целиком заставочный — чужих кусков нет."""
    texture = atlas_texture(env).read()
    width, height = texture.m_Width, texture.m_Height
    known = {n for pair in names.values() for n in pair}
    in_atlas = {T.key_of(k) for k, _ in atlas_object(env).read_typetree()["m_RenderDataMap"]}
    sprites = {o.peek_name(): o for o in env.objects if o.type.name == "Sprite" and o.peek_name()}
    rest = [n for n, o in sprites.items() if T.key_of(o.read_typetree()["m_RenderDataKey"]) in in_atlas
            and n not in known]
    if rest:
        raise SystemExit(f"в атласе {ATLAS} есть куски вне заставок: {rest[:5]} — переупаковка их потеряет")
    cuts, boxes = {}, {}
    for name, img in images.items():
        bb = img.getchannel("A").getbbox()
        cuts[name], boxes[name] = img.crop(bb), bb
    spots = T.shelf_pack([(n, im.size) for n, im in cuts.items()], width, height)
    if spots is None:
        raise SystemExit(f"русские куски не влезли в атлас {width}×{height}")
    frame_of = {n: frames[k] for k, pair in names.items() for n in pair}
    atlas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    spec = {}
    for name, (x, y) in sorted(spots.items()):
        img, bb = cuts[name], boxes[name]
        atlas.paste(img, (x, y))
        _, _, fw, fh = frame_of[name]
        spec[name] = {"textureRect": {"x": float(x), "y": float(height - y - img.height),
                                      "width": float(img.width), "height": float(img.height)},
                      "textureRectOffset": {"x": float(bb[0]), "y": float(fh - bb[3])},
                      "rect": {"width": float(fw), "height": float(fh)}}
    return atlas, spec


def plan_edits(env, frames: dict) -> list[dict]:
    """Рамки слотов в трёх немецких префабах: `m_AnchoredPosition` и `m_SizeDelta` у ореола
    и у букв каждого слота. «было» — оригинал (отпечаток для патчера), «стало» — наше."""
    edits = []
    for title, prefab in PREFABS.items():
        tree = tree_of(env, prefab)
        state = layout(tree)
        for key in pieces_of(title):
            x0, y0, w, h = frames[key]
            cx, cy = x0 + w / 2, H - (y0 + h / 2)            # центр рамки в мире, y вверх
            for name in slot_nodes(title, key[1]):
                path = node_path(tree, name)
                rt = tree[path]["rt"]
                parent = state[path.rsplit("/", 1)[0]]
                ppx, ppy, psx, psy, pw, ph, ppv, _, _ = parent
                a0, a1, pv = rt["m_AnchorMin"], rt["m_AnchorMax"], rt["m_Pivot"]
                if (a0["x"], a0["y"], a1["x"], a1["y"], pv["x"], pv["y"]) != (0.5, 0.5, 0.5, 0.5, 0.5, 0.5):
                    raise ValueError(f"{prefab}/{path}: якоря или опора не по центру — рамку не пересчитать")
                if (psx, psy) != (1.0, 1.0):
                    raise ValueError(f"{prefab}/{path}: масштаб предков {psx, psy}")
                ax, ay = -ppv[0] * pw + 0.5 * pw, -ppv[1] * ph + 0.5 * ph
                new = {"m_AnchoredPosition": {"x": float(cx - ppx - ax), "y": float(cy - ppy - ay)},
                       "m_SizeDelta": {"x": float(w), "y": float(h)}}
                before = {f: rt[f] for f in new}
                if before != new:
                    edits.append({"префаб": prefab, "узел": path, "тип": "RectTransform",
                                  "объект": tree[path]["rt_id"], "было": before, "стало": new})
    return edits


def prefab_keys(env) -> list[str]:
    keys = list(T.container(env))
    out = []
    for prefab in PREFABS.values():
        found = [k for k in keys if k.endswith(f"/{prefab}.prefab")]
        if len(found) != 1:
            raise KeyError(f"адрес префаба {prefab} не найти: нашлось {len(found)}")
        out.append(found[0])
    return out


def expected(pieces: dict, title: str) -> Image.Image:
    """Кадр так, как задуман набором: ореолы всех кусков префаба, сверху буквы."""
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    keys = pieces_of(title)
    for k in keys:
        canvas.alpha_composite(pieces[k][1])
    for k in keys:
        canvas.alpha_composite(pieces[k][0])
    return canvas


def build(env) -> dict:
    pieces, info = typeset(env)
    images, frames, names = cut(env, pieces)
    atlas, spec_pieces = build_atlas(env, images, frames, names)
    edits = plan_edits(env, frames)
    info["слово"] = f"{TOP} / {BOTTOM_TEXT['Start']} / {BOTTOM_TEXT['Success']}"
    info["раскладка"] = {f"{k[0]} {k[1]}": f"{piece} — спрайты {names[k][1]}, {names[k][0]}"
                         for k, piece in [(("top", s), p) for s, p in zip(SLOTS, TOP_PIECES)]
                         + [((t, d), p) for t in ("Start", "Success") for d, p in zip(("d0", "d1"), BOTTOM[t])]}
    spec = {"набор": info, "атлас": ATLAS, "бандл": BUNDLE, "префабы": prefab_keys(env),
            "размер": [atlas.width, atlas.height],
            "текстура_sha": pixels_sha(atlas_texture(env).read().image),
            "куски": spec_pieces, "правки": edits}
    return {"pieces": pieces, "info": info, "atlas": atlas, "spec": spec}


def simulate(spec: dict, atlas: Image.Image):
    """Записать задание кодом патчера в свежую копию оригинала, сохранить и открыть заново."""
    from picture_layer import write_splash

    env = open_bundle()
    notes = write_splash(env, spec, atlas)
    return UnityPy.load(env.file.save(packer="lz4")), notes


def check_frames(env, pieces: dict, label: str) -> list[str]:
    """Кадры трёх префабов из бандла (статика префаба) против набора."""
    problems = []
    for title, prefab in PREFABS.items():
        got = render(env, prefab)
        rough, worst = T.compare(expected(pieces, title), got)
        share = rough / (W * H)
        print(f"{label} {title}: кадр из бандла против набора — грубых пикселей {rough} ({share:.4%}), "
              f"максимум {worst} уровней")
        if share > 0.0001:
            problems.append(f"{title}: кадр из бандла расходится с набором — {share:.3%} грубых пикселей")
    return problems


STEPS = [(IN_CLIP, 0.84), (IN_CLIP, 0.98), (IN_CLIP, 1.233), (None, 0.6), (None, 1.1), (None, 1.6)]


def frame_at(env, title: str, clip: str | None, t: float, tree: dict) -> Image.Image:
    sampler, _ = clip_sampler(env, clip or CLIPS[title], tree)
    return render(env, PREFABS[title], sampler(t), tree)


def make_sheet(orig, built, info: dict, path: Path, head: str) -> None:
    """Лист: немецкий | русский кадр трёх префабов (из бандла, 1920×1080 в половину),
    шаги клипов у начала и победы и атлас «оригинал | русский»."""
    fnt = ImageFont.truetype(str(FONTS / LABEL_FONT), 24)
    rows = []
    for title, prefab in PREFABS.items():
        pair = Image.new("RGB", (W, H // 2), (28, 28, 28))
        pair.paste(T.on_dark(render(orig, prefab)).resize((W // 2, H // 2), Image.LANCZOS), (0, 0))
        pair.paste(T.on_dark(render(built, prefab)).resize((W // 2, H // 2), Image.LANCZOS), (W // 2, 0))
        rows.append((f"{prefab}: немецкий | русский — оба собраны из бандла (префаб + атлас)", pair))
        if title not in CLIPS:
            continue
        cw, ch = W // len(STEPS), H // len(STEPS)
        strip = Image.new("RGB", (W, 2 * ch + 4), (28, 28, 28))
        for j, env in enumerate((orig, built)):
            tree = tree_of(env, prefab)
            for i, (clip, t) in enumerate(STEPS):
                im = frame_at(env, title, clip, t, tree)
                strip.paste(T.on_dark(im).resize((cw, ch), Image.LANCZOS), (i * cw, j * (ch + 4)))
        names = ", ".join(f"{'въезд' if c else 'нижнее слово'} {t} с" for c, t in STEPS)
        rows.append((f"{title}: шаги клипов ({names}); сверху немецкий, снизу русский", strip))
    before = atlas_texture(orig).read().image.convert("RGBA")
    after = atlas_texture(built).read().image.convert("RGBA")
    pair = T.on_dark(T.atlas_pair(before, after))
    rows.append((f"Атлас {ATLAS}: оригинал | русский (половина размера)",
                 pair.resize((pair.width // 2, pair.height // 2), Image.LANCZOS)))
    lines = info["строки"]
    notes = [head,
             f"{info['шрифт']}, кегль {info['кегль']} (верх {info['кегль верха']}), сжатие {info['сжатие']}, "
             f"наклон {info['наклон']}, утончение {info['утончение']} px; синий {tuple(info['синий'])}, кайма "
             f"{info['кайма']} px, ореол {tuple(info['цвет ореола'])} до 11 px; немецкий штрих {info['немецкий штрих']}",
             *(f"{k}: «{v['текст']}» база {v['база']} (нем. {v['немецкая база']}), центр {v['центр']} "
               f"(нем. {v['немецкий центр']}), ширина {v['ширина']}, с каймой и ореолом x {v['с каймой и ореолом']}, "
               f"штрих {v['штрих']}" for k, v in lines.items()),
             "верх: " + " | ".join(TOP_PIECES) + " — чётные слоты въезжают одной гребёнкой, нечётные другой"]
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


# --- сверка собранного бандла ------------------------------------------------------------

def verify_bundle(built, others: set = frozenset(), spec: dict | None = None) -> tuple[list[str], dict]:
    """Собранный бандл против оригинала из `backup/` и набора (правило №13): кадры трёх префабов
    из бандла равны набору (потери BC7 — грубых не больше 0,01 %), правки «стало», адреса
    немецких префабов не уведены, лишнего не тронуто (`others` — законные правки соседей)."""
    from picture_layer import edits_state

    spec = spec or load_json(SPEC_JSON)
    orig = open_bundle()
    pieces, _ = typeset(orig)
    problems = check_frames(built, pieces, "сверка бандла:")
    state = edits_state(built, spec["правки"])
    print(f"правки префабов: {len(spec['правки'])}, в бандле — «{state}»")
    if state != "стало":
        problems.append(f"правки префабов в бандле не стоят: {state}")
    before, after = T.container(orig), T.container(built)
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
    mine = set(spec["куски"]) | {e["объект"] for e in spec["правки"]} | {atlas_texture(orig).path_id, ATLAS}
    stray = [f"{kind} {name or pid}" for pid, (kind, name, _) in changed
             if kind != "AssetBundle" and name not in mine and pid not in mine
             and name not in others and pid not in others]
    print(f"в бандле изменилось объектов: {len(changed)} из {len(a)}"
          + (f"; лишние: {', '.join(stray)}" if stray else "; лишнего не тронуто"))
    if stray:
        problems.append(f"в бандле тронуто лишнее: {', '.join(stray[:5])}")
    return problems, {"orig": orig}


# --- запуск -------------------------------------------------------------------------------

def report(spec: dict, atlas: Image.Image) -> None:
    info = spec["набор"]
    print(f"набор: {info['шрифт']}, кегль {info['кегль']} (верх {info['кегль верха']}), сжатие {info['сжатие']}, "
          f"наклон {info['наклон']}, утончение {info['утончение']}; синий {info['синий']}, кайма {info['кайма']}, "
          f"ореол {info['цвет ореола']}; немецкий штрих {info['немецкий штрих']}")
    for k, v in info["строки"].items():
        print(f"  {k:8} «{v['текст']}»: база {v['база']} (нем. {v['немецкая база']}), центр {v['центр']} "
              f"(нем. {v['немецкий центр']}), ширина {v['ширина']}, x с каймой и ореолом {v['с каймой и ореолом']}, "
              f"штрих {v['штрих']}")
    used = sum(round(p["textureRect"]["width"]) * round(p["textureRect"]["height"]) for p in spec["куски"].values())
    print(f"атлас {atlas.width}×{atlas.height}: занято {used / atlas.width / atlas.height:.0%}, "
          f"кусков {len(spec['куски'])}; правок префабов {len(spec['правки'])}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="ничего не писать: набрать заново в памяти и сверить с лежащим PNG и заданием")
    ap.add_argument("--built", nargs="?", const="", metavar="БАНДЛ",
                    help="сверить собранный бандл с оригиналом и с набором; по умолчанию work/build_assets")
    args = ap.parse_args()

    if args.check and not (ATLAS_PNG.exists() and SPEC_JSON.exists()):
        print(f"заставки не набраны ({ATLAS_PNG.name}, {SPEC_JSON.name}) — сверять нечего; "
              f"набрать: tools/titles_chess.py")
        return 2

    if args.built is not None:
        live = next(BUNDLES.glob(f"{BUNDLE}_assets_all_*.bundle"))
        path = Path(args.built) if args.built else WORK / "build_assets" / live.name
        if not path.exists():
            sys.exit(f"{path} не собран — сначала tools/inject_localized.py")
        spec = load_json(SPEC_JSON)
        from layer_localized import bundle_neighbours

        built = UnityPy.load(str(path))
        problems, ctx = verify_bundle(built, bundle_neighbours(BUNDLE, "titles_chess"), spec)
        make_sheet(ctx["orig"], built, spec["набор"], SHEET,
                   f"Собранный бандл: {path.name} — кадры собраны из него, немецкие — из backup/")
        print(f"лист: {SHEET}")
        for p in problems:
            print(f"  БЕДА: {p}", file=sys.stderr)
        return 1 if problems else 0

    orig = open_bundle()
    job = build(orig)
    spec, atlas = job["spec"], job["atlas"]
    problems: list[str] = []
    report(spec, atlas)
    for k, v in job["info"]["строки"].items():
        x0, x1 = v["с каймой и ореолом"]
        if x0 < EDGE or x1 > W - EDGE:
            problems.append(f"{k}: строка с каймой и ореолом {x0}–{x1} выходит за край экрана (запас {EDGE} px)")

    env, notes = simulate(spec, atlas)
    print("запись в копию бандла: " + "; ".join(notes))
    if any("оставлена как есть" in n for n in notes):
        problems.append("запись в бандл отказала: " + "; ".join(notes))
    else:
        problems += check_frames(env, job["pieces"], "в памяти:")

    if args.check:
        if ImageChops.difference(Image.open(ATLAS_PNG).convert("RGBA"), atlas).getbbox():
            problems.append(f"{ATLAS_PNG.name} не совпадает с набором по заданию — tools/titles_chess.py")
        if load_json(SPEC_JSON) != T.json_roundtrip(spec):
            problems.append(f"{SPEC_JSON.name} не совпадает с заданием, собранным заново — tools/titles_chess.py")
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
        print("заставки шахмат сходятся: кадры из бандла равны набору, задание и атлас на месте")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
