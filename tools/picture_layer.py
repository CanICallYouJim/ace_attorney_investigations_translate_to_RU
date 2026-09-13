"""Русская картинка у игрока: его английская текстура плюс наш слой.

Готовую русскую картинку раздавать нельзя: она на девять десятых рисунок Capcom,
а витрина обещает «ни одного файла игры». Раздаётся **слой** — только пиксели,
которыми русская картинка отличается от английской, и рецепт для мелких копий,
собранных уменьшением большой. Склеивается картинка на машине игрока, из его
собственной текстуры. Решение пользователя от 13 сентября 2026, вариант (а).

Здесь то, что нужно патчеру: склейка и запись в бандл. Снимает слой и сверяет
его с оригиналом `layer_localized.py`. Запись в бандл общая с `inject_localized.py`,
так что `make install` и игрок получают бандл, собранный одним кодом.

Слой лежит в `graphics_layers/` рядом с данными перевода:

    manifest.json               что склеивать, из какой текстуры и какой стороной
    <бандл>/<имя>.png           изменённые пиксели, обрезанные по рамке правки
    <бандл>/<имя>_mask.png      какие пиксели из них брать
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import UnityPy
from PIL import Image
from UnityPy.enums import TextureFormat

from common import WORK, load_json

FOLDER = WORK / "graphics_layers"
RAW = int(TextureFormat.RGBA32)
FLIP = Image.Transpose.FLIP_TOP_BOTTOM


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
    """
    ab = next(o for o in env.objects if o.type.name == "AssetBundle")
    tree = ab.read_typetree()
    entries = {k: v for k, v in tree["m_Container"]}
    missing = [g for g, e in pairs if g not in entries or e not in entries]
    missing += [k for k in pictures if k not in entries]
    if missing:
        raise KeyError(f"в контейнере нет записей: {missing[:5]}")

    sources = dict(pairs)
    notes: list[str] = []
    own: dict[str, int] = {}
    for key, img in pictures.items():
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

    def build(self, path: Path, pairs: list[tuple[str, str]]) -> tuple[bytes, int, list[str]]:
        """Бандл с подменой и русскими картинками. Возвращает байты, сколько картинок, заметки.

        Картинка склеивается только поверх той английской текстуры, по которой снят
        слой: отпечаток пикселей сверяется. Не совпал (другая версия игры) — эта
        картинка остаётся английской, а не ложится криво.
        """
        env = UnityPy.load(str(path))
        pictures: dict[str, Image.Image] = {}
        notes: list[str] = []
        for entry in self.by_bundle.get(short(path.name), []):
            name = entry["name"]
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
        return blob, len(pictures), notes + more
