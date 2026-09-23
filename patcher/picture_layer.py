"""Русская картинка у игрока: его английская текстура плюс наш слой.

Готовую русскую картинку раздавать нельзя: она на девять десятых рисунок Capcom,
а витрина обещает «ни одного файла игры». Раздаётся **слой** — только пиксели,
которыми русская картинка отличается от английской, и рецепт для мелких копий,
собранных уменьшением большой. Склеивается картинка на машине игрока, из его
собственной текстуры. Решение пользователя от 13 сентября 2026, вариант (а).

Плашки ситуации (`plates.py`) — исключение: их надпись наша целиком, набранная
шрифтом на прозрачном, склеивать не с чем. Плашка едет готовой картинкой
и ложится в немецкий спрайт вместе с новой сеткой (`write_sprite`).

Здесь то, что нужно патчеру: склейка и запись в бандл. Снимает слой и сверяет
его с оригиналом `layer_localized.py`. Запись в бандл общая с `inject_localized.py`,
так что `make install` и игрок получают бандл, собранный одним кодом.

Слой лежит в `graphics_layers/` рядом с данными перевода:

    manifest.json               что склеивать, из какой текстуры и какой стороной
    <бандл>/<имя>.png           изменённые пиксели, обрезанные по рамке правки; у плашки — она целиком
    <бандл>/<имя>_mask.png      какие пиксели из них брать
"""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import UnityPy
from PIL import Image
from UnityPy.enums import TextureFormat

from common import WORK, load_json

FOLDER = WORK / "graphics_layers"
RAW = int(TextureFormat.RGBA32)
FLIP = Image.Transpose.FLIP_TOP_BOTTOM
MESH_PAD = 2              # запас сетки вокруг надписи — как у тугой сетки самого Unity


def short(bundle_name: str) -> str:
    """Имя бандла без хеша сборки — по нему слой находит бандл на чужой машине."""
    return bundle_name.split("_assets_all_")[0]


def leaf(key: str) -> str:
    """Адрес в контейнере -> имя объекта: `.../cut00_007_ger.png` -> `cut00_007_ger`."""
    return key.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def pixels_sha(img: Image.Image) -> str:
    """Отпечаток по пикселям, а не по байтам сжатой текстуры."""
    return hashlib.sha256(img.convert("RGBA").tobytes()).hexdigest()


def shrink(img: Image.Image, box, size: tuple[int, int]) -> Image.Image:
    """Кусок картинки, ужатый в рамку: цвет и прозрачность — порознь.

    Pillow ужимает RGBA через премультипликацию, и у кадра с альфой 254 цвет
    уезжает на единицу в половине пикселей: карточка логики, ужатая из русского
    PNG (альфа 255) и из склейки (родные 254), расходилась на 31 % площади.
    Кадры тут непрозрачные, считать цвет через альфу незачем — а раздельный
    расчёт даёт одно и то же у `paste_art.py` и у патчера игрока.
    """
    part = img.crop(tuple(box))
    colour = part.convert("RGB").resize(size, Image.LANCZOS)
    colour.putalpha(part.getchannel("A").resize(size, Image.LANCZOS))
    return colour


def compose(entry: dict, source: Image.Image, composites: dict[str, Image.Image],
            folder: Path = FOLDER) -> Image.Image:
    """Склеить картинку игрока лицом вверх: текстура, уменьшенная копия, слой.

    `source` — текстура так, как её отдаёт бандл (`Texture2D.image`);
    `composites` — уже склеенные картинки лицом вверх, из них берутся уменьшения.
    """
    face = source.convert("RGBA")
    if entry["flipped"]:
        face = face.transpose(FLIP)
    derive = entry.get("derive")
    if derive:
        # Мелкая копия большой картинки (карточка логики 158x158 с листа 1920x1080):
        # набирать там нечего, и готовая большая ужимается в рамку ориентира — так же,
        # как это делает paste_art.py. Пикселей уменьшения игроку не везём: они
        # получаются у него из его же склейки.
        there, here = derive["там"], derive["тут"]
        patch = shrink(composites[derive["из"]], there, (here[2] - here[0], here[3] - here[1]))
        face.paste(patch, (here[0], here[1]))
    if entry.get("box"):
        layer = Image.open(folder / entry["layer"]).convert("RGBA")
        mask = Image.open(folder / entry["mask"]).convert("L")
        face.paste(layer, (entry["box"][0], entry["box"][1]), mask)
    return face


def german_object(env, entries: dict, key: str, source_key: str | None):
    """Немецкий объект картинки: по адресу, если тот не уведён на английский, иначе по имени."""
    pid = entries[key]["asset"]["m_PathID"]
    if source_key is None or pid != entries[source_key]["asset"]["m_PathID"]:
        for obj in env.objects:
            if obj.path_id == pid:
                return obj
    name = leaf(key)
    found = [o for o in env.objects if o.type.name == "Texture2D" and o.peek_name() == name]
    if len(found) != 1:
        raise KeyError(f"{name}: немецкий объект не найти — по имени их {len(found)}")
    return found[0]


def sprites_by_key(env) -> dict[str, object]:
    """Адрес контейнера -> спрайт.

    У картинки-спрайта по одному адресу **две** записи — текстура и спрайт, —
    и словарь `env.container` оставляет от них последнюю, какая попадётся.
    """
    ab = next(o for o in env.objects if o.type.name == "AssetBundle")
    sprites = {o.path_id: o for o in env.objects if o.type.name == "Sprite"}
    return {key: sprites[info["asset"]["m_PathID"]]
            for key, info in ab.read_typetree()["m_Container"]
            if info["asset"]["m_PathID"] in sprites}


def texture_of(env, sprite):
    """Объект текстуры, на которой лежит спрайт.

    У спрайтов из атласа (даты ситуации) текстура в другом файле — такие сюда
    не ходят; плашки лежат на своих текстурах в том же бандле.
    """
    ptr = sprite.read_typetree()["m_RD"]["texture"]
    found = next((o for o in env.objects if o.path_id == ptr["m_PathID"]), None) if ptr["m_FileID"] == 0 else None
    if found is None:
        raise KeyError(f"{sprite.peek_name()}: текстура спрайта не в этом бандле (m_FileID {ptr['m_FileID']})")
    return found


def write_sprite(env, sprite, img: Image.Image) -> str:
    """Плашка: пиксели — в текстуру спрайта, сетка — прямоугольник по рамке надписи.

    Сетка спрайта у Unity — многоугольник по контуру немецкого слова, и русское
    слово шире рисовалось бы обрезанным по нему. Прямоугольник покрывает рамку
    надписи с запасом `MESH_PAD`; `textureRect` — та же рамка. UV в сетке у Unity
    нулевые — он считает их сам из позиций и `uvTransform`, — так что пишутся
    только позиции. Треугольники по часовой, как у оригинала.
    """
    tree = sprite.read_typetree()
    rd = tree["m_RD"]
    tex_obj = texture_of(env, sprite)
    tex = tex_obj.read()
    w, h = tex.m_Width, tex.m_Height
    if img.size != (w, h):
        raise ValueError(f"{tree['m_Name']}: картинка {img.size[0]}x{img.size[1]}, текстура {w}x{h}")
    box = img.getchannel("A").getbbox()
    if box is None:
        raise ValueError(f"{tree['m_Name']}: картинка пустая")
    tex.set_image(img, target_format=int(tex.m_TextureFormat))
    tex.save()

    x0, x1 = max(0, box[0] - MESH_PAD), min(w, box[2] + MESH_PAD)
    top, bottom = max(0, box[1] - MESH_PAD), min(h, box[3] + MESH_PAD)
    y0, y1 = h - bottom, h - top                  # у Unity y растёт снизу
    ppu = tree["m_PixelsToUnits"]
    px = tree["m_Pivot"]["x"] * tree["m_Rect"]["width"]
    py = tree["m_Pivot"]["y"] * tree["m_Rect"]["height"]
    corners = [(x0, y1), (x1, y1), (x1, y0), (x0, y0)]
    positions = b"".join(struct.pack("<3f", (x - px) / ppu, (y - py) / ppu, 0.0) for x, y in corners)
    uv_at = -(-len(positions) // 16) * 16         # поток UV выровнен на 16 байт
    vd = rd["m_VertexData"]
    old = vd["m_VertexCount"]
    vd["m_VertexCount"] = len(corners)
    vd["m_DataSize"] = positions + bytes(uv_at - len(positions) + 8 * len(corners))
    indices = struct.pack("<6H", 0, 1, 2, 2, 3, 0)
    rd["m_IndexBuffer"] = indices if isinstance(rd["m_IndexBuffer"], (bytes, bytearray)) else list(indices)
    rd["m_SubMeshes"] = rd["m_SubMeshes"][:1]
    rd["m_SubMeshes"][0].update(firstByte=0, indexCount=6, baseVertex=0, firstVertex=0, vertexCount=4)
    rd["textureRect"] = {"x": float(x0), "y": float(y0), "width": float(x1 - x0), "height": float(y1 - y0)}
    rd["textureRectOffset"] = {"x": float(x0), "y": float(y0)}
    tree["m_PhysicsShape"] = [[{"x": (x - px) / ppu, "y": (y - py) / ppu} for x, y in corners]]
    sprite.save_typetree(tree)
    return f"{tree['m_Name']}: сетка {old} вершин -> 4, рамка x {x0}..{x1}, y {y0}..{y1} (снизу)"


def atlas_key(key) -> tuple:
    """Ключ записи карты атласа — в вид, по которому её найти у спрайта."""
    first, second = key
    return (tuple(first.values()) if isinstance(first, dict) else tuple(first), second)


def rect_mesh(tree: dict, rect: dict, box: dict) -> None:
    """Сетку спрайта — прямоугольником по куску: четыре вершины, два треугольника.

    Тугая сетка оригинала обходила контур немецкого слова, и русские буквы за ним
    не рисовались бы. UV в потоке у Unity нулевые — он считает их сам из позиций
    и `uvTransform`, так что пишутся только позиции. Треугольники по часовой,
    как у оригинала.
    """
    rd = tree["m_RD"]
    ppu = tree["m_PixelsToUnits"]
    px, py = tree["m_Pivot"]["x"] * rect["width"], tree["m_Pivot"]["y"] * rect["height"]
    x0, y0 = box["x"], box["y"]
    x1, y1 = x0 + box["width"], y0 + box["height"]
    corners = [(x0, y1), (x1, y1), (x1, y0), (x0, y0)]
    positions = b"".join(struct.pack("<3f", (x - px) / ppu, (y - py) / ppu, 0.0) for x, y in corners)
    uv_at = -(-len(positions) // 16) * 16         # поток UV выровнен на 16 байт
    vd = rd["m_VertexData"]
    vd["m_VertexCount"] = len(corners)
    vd["m_DataSize"] = positions + bytes(uv_at - len(positions) + 8 * len(corners))
    indices = struct.pack("<6H", 0, 1, 2, 2, 3, 0)
    rd["m_IndexBuffer"] = indices if isinstance(rd["m_IndexBuffer"], (bytes, bytearray)) else list(indices)
    rd["m_SubMeshes"] = rd["m_SubMeshes"][:1]
    rd["m_SubMeshes"][0].update(firstByte=0, indexCount=6, baseVertex=0, firstVertex=0, vertexCount=4)
    tree["m_PhysicsShape"] = [[{"x": (x - px) / ppu, "y": (y - py) / ppu} for x, y in corners]]


def splash_atlas(env, spec: dict, layer: Image.Image, texture) -> Image.Image | None:
    """Полный атлас заставки: наши куски плюс мазок, вырезанный из текстуры этой игры.

    Пикселей Capcom мы не раздаём (правило витрины «ни одного файла игры»), поэтому
    единственный чужой кусок в атласе — белый мазок `anim_1_0` — берётся у игрока
    из его же немецкой текстуры и переезжает на новое место. Не та версия игры —
    отпечаток не сойдётся, и заставка останется как была.
    """
    before = texture.read().image.convert("RGBA")
    if pixels_sha(before) != spec["текстура_sha"]:
        return None
    keep = spec["куски"][spec["мазок"]]
    was, now = keep["было"], keep["textureRect"]
    piece = before.crop((round(was["x"]), round(before.height - was["y"] - was["height"]),
                         round(was["x"] + was["width"]), round(before.height - was["y"])))
    atlas = layer.copy()
    atlas.paste(piece, (round(now["x"]), round(atlas.height - now["y"] - now["height"])))
    return atlas


def write_splash(env, spec: dict, layer: Image.Image, raw: bool = False) -> list[str]:
    """Заставка «Возражение»: русские куски в атлас, новые рамки восьми спрайтам.

    Куски заставки лежат не на своих текстурах, а в общем атласе, и где именно —
    сказано в **карте атласа** (`SpriteAtlas.m_RenderDataMap`), а не в самом спрайте:
    у спрайта та же запись хранится «как было до упаковки». Русское слово крупнее
    немецкого, поэтому атлас переупакован целиком (`tools/splash.py`), и обе записи
    переписываются вместе — иначе игра возьмёт кусок по старой рамке.

    Рамка спрайта (`m_Rect`) становится рамкой половины из префаба: у Capcom она
    на 3 px уже, и её кусок игра растягивает, а русский ложится один к одному.
    """
    name = spec["атлас"]
    obj = next((o for o in env.objects if o.type.name == "SpriteAtlas" and o.peek_name() == name), None)
    if obj is None:
        raise KeyError(f"в бандле нет атласа {name}")
    tree = obj.read_typetree()
    objs = {o.path_id: o for o in env.objects}
    sprites = {o.peek_name(): o for o in env.objects if o.type.name == "Sprite" and o.peek_name()}
    pieces = spec["куски"]

    texture = None
    for _, rd in tree["m_RenderDataMap"]:
        texture = objs.get(rd["texture"]["m_PathID"], texture)
    if texture is None:
        raise KeyError(f"{name}: в карте атласа нет текстуры")
    tex = texture.read()
    if layer.size != (tex.m_Width, tex.m_Height):
        raise ValueError(f"{name}: слой {layer.size[0]}x{layer.size[1]}, "
                         f"текстура {tex.m_Width}x{tex.m_Height} — набрать заново: tools/splash.py")
    atlas = splash_atlas(env, spec, layer, texture)
    if atlas is None:
        return [f"{name}: немецкая заставка в этой игре другая — оставлена как есть"]
    notes: list[str] = []
    want = RAW if raw else int(tex.m_TextureFormat)
    try:
        tex.set_image(atlas, target_format=want)
    except Exception as exc:  # noqa: BLE001 — упаковщика может не оказаться, это не повод падать
        notes.append(f"{name}: {TextureFormat(want).name} не упаковался ({exc}), кладу RGBA32")
        tex.set_image(atlas, target_format=RAW)
    tex.save()

    by_key = {}
    for sprite_name in pieces:
        if sprite_name not in sprites:
            raise KeyError(f"в бандле нет спрайта заставки {sprite_name}")
        by_key[atlas_key(sprites[sprite_name].read_typetree()["m_RenderDataKey"])] = sprite_name

    rows, done = [], 0
    for key, rd in tree["m_RenderDataMap"]:
        sprite_name = by_key.get(atlas_key(key))
        item = pieces.get(sprite_name) if sprite_name else None
        if item is None:
            rows.append([key, rd])
            continue
        r, off, rect = item["textureRect"], item["textureRectOffset"], item["rect"]
        sprite = sprites[sprite_name]
        tr = sprite.read_typetree()
        ppu = tr["m_PixelsToUnits"]
        rd = dict(rd)
        rd["textureRect"] = dict(r)
        rd["textureRectOffset"] = dict(off)
        rd["atlasRectOffset"] = {"x": -off["x"], "y": r["y"] - off["y"]}
        rd["uvTransform"] = {"x": ppu, "y": r["x"] - off["x"] + rect["width"] / 2,
                             "z": ppu, "w": r["y"] - off["y"] + rect["height"] / 2}
        rows.append([key, rd])
        done += 1
        if item.get("как есть"):
            # Кусок только переехал в атласе: рамка спрайта и его тугая сетка верны.
            continue

        # Та же запись у самого спрайта — «как было бы на своей текстуре»: кусок
        # стоит в рамке там же, где в атласе, и рамка спрайта равна рамке половины.
        tr["m_Rect"] = {"x": 0.0, "y": 0.0, "width": rect["width"], "height": rect["height"]}
        tr["m_RD"]["textureRect"] = {"x": off["x"], "y": off["y"],
                                     "width": r["width"], "height": r["height"]}
        tr["m_RD"]["textureRectOffset"] = dict(off)
        tr["m_RD"]["uvTransform"] = {"x": ppu, "y": rect["width"] / 2,
                                     "z": ppu, "w": rect["height"] / 2}
        rect_mesh(tr, rect, {"x": off["x"], "y": off["y"], "width": r["width"], "height": r["height"]})
        sprite.save_typetree(tr)

    if done != len(pieces):
        raise KeyError(f"{name}: в карте атласа нашлось {done} кусков из {len(pieces)}")
    tree["m_RenderDataMap"] = rows
    obj.save_typetree(tree)
    notes.append(f"{name}: русский атлас и {done} кусков заставки")
    return notes


def write_bundle(env, pairs: list[tuple[str, str]], pictures: dict[str, Image.Image],
                 raw: bool = False) -> tuple[bytes, list[str]]:
    """Бандл целиком: немецким адресам — английские объекты, кроме адресов со своей картинкой.

    `pairs` — пары (адрес немецкого, адрес английского или базового), как их даёт
    `swap_localized.plan_env`. `pictures` — адрес немецкого -> картинка **в том виде,
    как её хранит бандл** (уже перевёрнутая, где надо).

    Пиксели ложатся в **немецкий** объект, и адрес остаётся ему — вместе с его
    собственным диапазоном преднагрузки. До 13 сентября 2026 вставка брала объект
    по адресу `_ger`, а в подменённом бандле тот вёл на английский: русское
    писалось в английские текстуры, и в английской версии игры восемь картинок
    стали русскими.

    Адрес спрайта (плашки) не трогается: у него две записи, текстура и спрайт,
    и обе и так ведут на немецкие объекты — английских двойников в бандле нет.
    """
    ab = next(o for o in env.objects if o.type.name == "AssetBundle")
    tree = ab.read_typetree()
    entries = {k: v for k, v in tree["m_Container"]}
    missing = [g for g, e in pairs if g not in entries or e not in entries]
    missing += [k for k in pictures if k not in entries]
    if missing:
        raise KeyError(f"в контейнере нет записей: {missing[:5]}")

    sources = dict(pairs)
    sprites = sprites_by_key(env)
    notes: list[str] = []
    own: dict[str, int] = {}
    for key, img in pictures.items():
        if key in sprites:
            notes.append(write_sprite(env, sprites[key], img))
            continue
        obj = german_object(env, entries, key, sources.get(key))
        tex = obj.read()
        if img.size != (tex.m_Width, tex.m_Height):
            raise ValueError(f"{leaf(key)}: картинка {img.size[0]}x{img.size[1]}, "
                             f"текстура {tex.m_Width}x{tex.m_Height}")
        want = RAW if raw else int(tex.m_TextureFormat)
        try:
            tex.set_image(img, target_format=want)
        except Exception as exc:  # noqa: BLE001 — упаковщика может не оказаться, это не повод падать
            notes.append(f"{leaf(key)}: {TextureFormat(want).name} не упаковался ({exc}), кладу RGBA32")
            tex.set_image(img, target_format=RAW)
        tex.save()
        own[key] = obj.path_id

    preload: dict[int, int] = {}
    for i, ptr in enumerate(tree["m_PreloadTable"]):
        if ptr["m_FileID"] == 0:
            preload.setdefault(ptr["m_PathID"], i)

    container = []
    for key, info in tree["m_Container"]:
        if key in own:
            if info["asset"]["m_PathID"] != own[key]:
                # адрес уведён на английский прежней подменой — вернуть его целиком
                info = {**info, "asset": {**info["asset"], "m_PathID": own[key]}}
                if own[key] in preload:
                    info["preloadIndex"], info["preloadSize"] = preload[own[key]], 1
                else:
                    notes.append(f"{leaf(key)}: объекта нет в таблице преднагрузки, диапазон прежний")
        elif key in sources:
            src = entries[sources[key]]
            info = {**src, "asset": dict(src["asset"])}
        container.append([key, info])
    tree["m_Container"] = container
    ab.save_typetree(tree)
    return env.file.save(packer="lz4"), notes


class Shipment:
    """Слой, приехавший с патчером: что в какой бандл склеивать."""

    def __init__(self, folder: Path = FOLDER):
        self.folder = folder
        data = load_json(folder / "manifest.json", default={}) or {}
        self.pictures: list[dict] = data.get("pictures", [])
        self.by_bundle: dict[str, list[dict]] = {}
        for entry in self.pictures:
            self.by_bundle.setdefault(entry["bundle"], []).append(entry)
        home = {e["name"]: e["bundle"] for e in self.pictures}
        self.needed = {e["derive"]["из"] for e in self.pictures if e.get("derive")}
        self.feeders = {home[name] for name in self.needed if name in home}
        self.composites: dict[str, Image.Image] = {}

    def __len__(self) -> int:
        return len(self.pictures)

    def has(self, bundle_name: str) -> bool:
        return short(bundle_name) in self.by_bundle

    def feeds(self, bundle_name: str) -> bool:
        """Из картинок этого бандла уменьшаются другие — собирать его раньше."""
        return short(bundle_name) in self.feeders

    @staticmethod
    def plate_fits(env, sprites: dict, entry: dict) -> str | None:
        """Ляжет ли плашка в этот бандл. None — ляжет, иначе — почему нет."""
        sprite = sprites.get(entry["key"])
        if sprite is None:
            return "в бандле нет её спрайта"
        found = pixels_sha(texture_of(env, sprite).read().image)
        if found not in (entry["texture_sha"], entry["plate_sha"]):
            return "немецкая плашка в этой игре другая"
        return None

    def table_rows(self, bundles: Path) -> dict[int, str]:
        """Строки таблицы картинок локали, которым остаться немецкими: `m_Id` -> значение.

        Только у плашек, которые лягут в живой бандл игрока: иначе таблица повела бы
        на немецкий спрайт с немецкой надписью. Сверка — та же, что при сборке.
        """
        rows: dict[int, str] = {}
        plates: dict[str, list[dict]] = {}
        for entry in self.pictures:
            if entry.get("kind") == "plate" and entry.get("table"):
                plates.setdefault(entry["bundle"], []).append(entry)
        for bundle, entries in plates.items():
            live = next(bundles.glob(f"{bundle}_assets_all_*.bundle"), None)
            if live is None:
                continue
            env = UnityPy.load(str(live))
            sprites = sprites_by_key(env)
            for entry in entries:
                if self.plate_fits(env, sprites, entry) is None:
                    rows[entry["table"]["m_Id"]] = entry["table"]["german"]
        return rows

    def build(self, path: Path, pairs: list[tuple[str, str]]) -> tuple[bytes, int, list[str]]:
        """Бандл с подменой и русскими картинками. Возвращает байты, сколько картинок, заметки.

        Картинка склеивается только поверх той английской текстуры, по которой снят
        слой: отпечаток пикселей сверяется. Не совпал (другая версия игры) — эта
        картинка остаётся английской, а не ложится криво.
        """
        env = UnityPy.load(str(path))
        pictures: dict[str, Image.Image] = {}
        notes: list[str] = []
        sprites: dict | None = None
        extra = 0
        for entry in self.by_bundle.get(short(path.name), []):
            name = entry["name"]
            if entry.get("kind") == "splash":
                spec = entry["spec"]
                found = write_splash(env, spec, Image.open(self.folder / entry["layer"]).convert("RGBA"))
                notes += found
                if not any("оставлена как есть" in note for note in found):
                    # Заставку игра берёт из немецкого префаба — его адрес подмене не отдаём.
                    pairs = [(german, english) for german, english in pairs
                             if german != spec["префаб"]]
                    extra += 1
                continue
            if entry.get("kind") == "plate":
                sprites = sprites if sprites is not None else sprites_by_key(env)
                why = self.plate_fits(env, sprites, entry)
                if why:
                    notes.append(f"{name}: {why} — оставлена как есть")
                    continue
                pictures[entry["key"]] = Image.open(self.folder / entry["layer"]).convert("RGBA")
                continue
            if entry["key"] not in env.container or entry["source"] not in env.container:
                notes.append(f"{name}: в бандле нет её адреса — оставлена английской")
                continue
            source = env.container[entry["source"]].read().image
            if pixels_sha(source) != entry["source_sha"]:
                notes.append(f"{name}: английская картинка в этой игре другая — оставлена английской")
                continue
            derive = entry.get("derive")
            if derive and derive["из"] not in self.composites:
                notes.append(f"{name}: не собралась «{derive['из']}», из которой она уменьшается, "
                             f"— оставлена английской")
                continue
            face = compose(entry, source, self.composites, self.folder)
            if name in self.needed:
                self.composites[name] = face
            pictures[entry["key"]] = face.transpose(FLIP) if entry["flipped"] else face
        blob, more = write_bundle(env, pairs, pictures)
        return blob, len(pictures) + extra, notes + more
