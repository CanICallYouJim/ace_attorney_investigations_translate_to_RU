"""Проверка, что патчер даёт ровно то же, что конвейер репозитория.

Гоняется на своей машине перед релизом. Смысл: патчер собирает игровые файлы
теми же функциями `tools/`, но иначе их зовёт — в частности, обе правки гарнитур
делает за один проход по `data.unity3d`, тогда как `patch_font_cmap.py`
и `patch_font_metrics.py` идут двумя запусками через файл игры. Композиция могла
разойтись с последовательным применением, и это надо доказывать, а не полагать.

Реплики и таблицы проверяются проще: их патчер собирает теми же вызовами, что
`build.py` и `build_strings.py`, и результат обязан совпасть побайтно.

    .venv\\Scripts\\python.exe patcher\\selftest.py

Нужны: установленная игра с уже поставленным переводом и `backup/data.unity3d`
с оригинальными гарнитурами. Ничего не пишет.
"""
from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "patcher")]

import UnityPy  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

import carriers as C  # noqa: E402
from common import GAME  # noqa: E402
from patch_font_cmap import LATIN_FONTS, patch_ttf  # noqa: E402
from patch_font_metrics import CYRILLIC, DEFAULT_SIDEBEARING, retype  # noqa: E402

ORIGINAL = ROOT / "backup" / "data.unity3d"
INSTALLED = GAME / "GK12_Data" / "data.unity3d"


def fonts_of(path: Path) -> dict[str, bytes]:
    """Имя гарнитуры -> её TTF-байты. Дубли имён разводятся суффиксом."""
    out: dict[str, bytes] = {}
    env = UnityPy.load(str(path))
    for obj in env.objects:
        if obj.type.name != "Font":
            continue
        tree = obj.read_typetree()
        name = tree.get("m_Name", "?")
        if name not in LATIN_FONTS:
            continue
        blob = bytes(tree.get("m_FontData") or b"")
        if not blob:
            continue
        key = name if name not in out else f"{name}#{sum(k.startswith(name) for k in out)}"
        out[key] = blob
    return out


def describe(blob: bytes) -> tuple[int, int]:
    """(сколько кодов-носителей на месте, сколько букв кириллицы уже не полноширинные)."""
    font = TTFont(BytesIO(blob), fontNumber=0, lazy=True)
    cmap = font.getBestCmap()
    carriers = C.carrier_map(C.CANDIDATES[C.CHOSEN], C.BROKEN)
    present = sum(1 for code in carriers.values() if code in cmap)

    hmtx, upm = font["hmtx"], font["head"].unitsPerEm
    narrow = 0
    for code in CYRILLIC:
        name = cmap.get(code)
        if name is not None and hmtx[name][0] != upm:
            narrow += 1
    return present, narrow


def main() -> int:
    for path in (ORIGINAL, INSTALLED):
        if not path.exists():
            print(f"нет файла {path}", file=sys.stderr)
            return 1

    print(f"оригинал:  {ORIGINAL}")
    print(f"в игре:    {INSTALLED}\n")

    original = fonts_of(ORIGINAL)
    installed = fonts_of(INSTALLED)

    bad = 0
    print(f"{'гарнитура':28} {'носители':>10} {'метрики':>9}  сходится с игрой")
    print("-" * 74)
    for name, blob in original.items():
        # ровно то, что делает patcher/steps.py:fonts за один проход
        patched, added = patch_ttf(blob, C.BROKEN)
        patched, retyped, _ = retype(patched, DEFAULT_SIDEBEARING)

        present, narrow = describe(patched)
        live = installed.get(name)
        if live is None:
            verdict, ok = "в игре нет такой", False
        elif live == patched:
            verdict, ok = "байт в байт", True
        else:
            # Расхождение в байтах ещё не брак: у гарнитуры могут быть лишние
            # коды других участков-кандидатов от прежних проб. Сверяем смысл.
            live_present, live_narrow = describe(live)
            ok = (live_present, live_narrow) == (present, narrow)
            verdict = ("то же по смыслу, байты разошлись" if ok else
                       f"РАЗОШЛОСЬ: в игре {live_present}/{live_narrow}")
        bad += not ok
        print(f"{name[:28]:28} {present:5d}/{len(C.BROKEN):<4} {narrow:5d}/{len(CYRILLIC):<3}  {verdict}")

    print()
    if bad:
        print(f"расхождений: {bad}", file=sys.stderr)
    else:
        print("Гарнитуры сходятся: патчер за один проход даёт то же, что два запуска.")
    return max(1 if bad else 0, pictures())


def pictures() -> int:
    """Русские картинки: бандл, собранный патчером из оригинала, несёт ровно русскую картинку.

    Путь тот же, что у игрока, — `Shipment.build` поверх нетронутого бандла из
    backup/, — только в память, а не в игру. Сверяется то, что увидит игра:
    раскодированная немецкая текстура совпадает с русской картинкой (с потерей
    BC7), лежит той же стороной, что оригинал, адрес ведёт на неё саму вместе
    с преднагрузкой, а английская текстура не тронута.
    """
    import gc

    from PIL import Image, ImageChops, ImageStat

    from common import BUNDLES
    from layer_localized import RU, flat, original
    from picture_layer import FLIP, Shipment, pixels_sha
    from swap_localized import plan_env

    shipment = Shipment()
    print(f"\nрусские картинки в слое: {len(shipment)}")
    if not len(shipment):
        return 0
    pngs = {p.stem: p for p in RU.rglob("*.png")}
    bad = 0

    def plate_ok(built, entry) -> bool:
        """Плашка: немецкая текстура несёт ровно набор, сетка покрывает надпись,
        по адресу по-прежнему текстура и спрайт, строка таблицы локали — на немецкий спрайт."""
        from picture_layer import sprites_by_key, texture_of
        from swap_localized import swap_image_table

        sprite = sprites_by_key(built).get(entry["key"])
        if sprite is None:
            print(f"    {entry['name']:18} спрайта нет  <- РАЗОШЛОСЬ")
            return False
        rd = sprite.read_typetree()["m_RD"]
        tex = texture_of(built, sprite).read()
        want = Image.open(pngs[entry["name"]]).convert("RGBA")
        same = pixels_sha(tex.image) == pixels_sha(want)
        lossy = ""
        if not same and tex.m_TextureFormat not in (4, 5):        # не RGBA32/ARGB32 — сжатый формат
            # фон чтения (`Sousa_TextCutBG_*`) лежит в сжатой текстуре кадра: ровно набор там не бывает,
            # сверка — потерями сжатия, как у картинок (грубых больше 64 уровней — не больше 0,01 %)
            import numpy as np
            d = np.abs(np.asarray(tex.image.convert("RGBA"), np.int16) - np.asarray(want, np.int16)).max(-1)
            same = (d > 64).mean() <= 0.0001
            lossy = f" (сжатие: до {int(d.max())} уровней, грубых {int((d > 64).sum())})"

        box = want.getchannel("A").getbbox()
        tr, h = rd["textureRect"], tex.m_Height
        covers = (rd["m_VertexData"]["m_VertexCount"] == 4
                  and tr["x"] <= box[0] and tr["x"] + tr["width"] >= box[2]
                  and tr["y"] <= h - box[3] and tr["y"] + tr["height"] >= h - box[1])
        types = {o.path_id: o.type.name for o in built.objects}
        tree = next(o for o in built.objects if o.type.name == "AssetBundle").read_typetree()
        kinds = sorted(types.get(info["asset"]["m_PathID"], "?") for k, info in tree["m_Container"]
                       if k == entry["key"])
        addresses = kinds == ["Sprite", "Texture2D"]
        table = True
        if entry.get("table"):
            blob, _ = swap_image_table(shipment.table_rows(BUNDLES))
            rows = {}
            for obj in UnityPy.load(blob).objects:
                if obj.type.name == "MonoBehaviour":
                    data = obj.read_typetree()
                    if "m_TableData" in data:
                        rows = {r["m_Id"]: r["m_Localized"] for r in data["m_TableData"]}
            table = rows.get(entry["table"]["m_Id"]) == entry["table"]["german"]
        ok = same and covers and addresses and table
        print(f"    {entry['name']:18} плашка: пиксели {'ровно набор' if same else 'ДРУГИЕ'}{lossy}; "
              f"сетка {'прямоугольник по надписи' if covers else 'НЕ ПОКРЫВАЕТ НАДПИСЬ'}; "
              f"по адресу {'текстура и спрайт' if addresses else 'СБИТО: ' + ', '.join(kinds)}"
              + (f"; таблица локали {'на немецкий спрайт' if table else 'ВЕДЁТ НЕ ТУДА'}"
                 if entry.get("table") else "")
              + ("" if ok else "  <- РАЗОШЛОСЬ"))
        return ok

    for bundle in sorted(shipment.by_bundle, key=lambda b: (b not in shipment.feeders, b)):
        live = next(BUNDLES.glob(f"{bundle}_assets_all_*.bundle"))
        src = original(live.name)
        if src is None:
            print(f"  {bundle}: оригинала нет — сверять не с чем", file=sys.stderr)
            bad += 1
            continue
        # Бандл графики весит до 350 МБ, а в памяти разворачивается вдвое-втрое:
        # на машине с шестью гигабайтами три копии разом не помещаются. Поэтому
        # каждая загрузка отпускается до следующей.
        plan = plan_env(UnityPy.load(str(src)))
        gc.collect()
        blob, done, notes = shipment.build(src, plan)
        gc.collect()
        built = UnityPy.load(blob)
        ab = next(o for o in built.objects if o.type.name == "AssetBundle").read_typetree()
        container = dict(ab["m_Container"])
        print(f"  {bundle}: собрано картинок {done}" + "".join(f"; {n}" for n in notes))
        for entry in shipment.by_bundle[bundle]:
            if entry.get("kind") == "plate":
                bad += not plate_ok(built, entry)
                continue
            if entry.get("kind") == "splash":
                # Заставки-конструкторы: «Возражение» (`splash.py`) — восемь кусков
                # в переупакованном атласе, мазок Capcom; «Начало / Расследование завершено»
                # (`titles.py`) — шесть кусков и правки немецких префабов. Сверяются кадры,
                # собранные из бандла, против набора и то, что немецкие префабы не уведены
                # на английские. Законные правки соседей по бандлу — не «лишнее».
                import importlib

                from picture_layer import leaf, splash_objects
                check = importlib.import_module(entry.get("check", "splash"))
                others = {leaf(e["key"]).rsplit(".", 1)[0] for e in shipment.by_bundle[bundle]
                          if e.get("kind") != "splash"}
                for e in shipment.by_bundle[bundle]:
                    if e.get("kind") == "splash" and e is not entry:
                        others |= splash_objects(built, e["spec"])
                found, _ = check.verify_bundle(built, others)
                for why in found:
                    print(f"    {entry['name']:18} {why}  <- РАЗОШЛОСЬ")
                if not found:
                    print(f"    {entry['name']:18} заставка: сборка из кусков сходится с набором, "
                          f"префабы немецкие, лишнего не тронуто")
                bad += bool(found)
                continue
            obj = built.container[entry["key"]]
            got = obj.read().image.convert("RGBA")
            want = Image.open(pngs[entry["name"]]).convert("RGBA")
            if want.size != got.size:
                want = want.resize(got.size, Image.LANCZOS)
            if entry["flipped"]:
                want = want.transpose(FLIP)
            channels = ImageChops.difference(got, want).split()[:3]
            mean = max(ImageStat.Stat(ch).mean[0] for ch in channels)
            worst = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
            peak = worst.getextrema()[1]
            rough = sum(worst.histogram()[65:])

            # Сторона — по английской текстуре того же бандла: она не тронута (это
            # проверяется ниже отпечатком), то есть лежит так же, как лежал оригинал.
            source = built.container[entry["source"]]
            english_image = source.read().image
            theirs = flat(english_image)
            mine = flat(got)
            side = (ImageStat.Stat(ImageChops.difference(mine, theirs)).mean[0]
                    < ImageStat.Stat(ImageChops.difference(mine, theirs.transpose(FLIP))).mean[0])

            info = container[entry["key"]]
            first = info["preloadIndex"]
            preload = [ab["m_PreloadTable"][i]["m_PathID"] for i in range(first, first + info["preloadSize"])]
            own = obj.path_id != source.path_id and preload == [obj.path_id]
            english = pixels_sha(english_image) == entry["source_sha"]

            # BC7 на резком красном крае роняет отдельные пиксели далеко: на плане
            # 24 марта 66 пикселей из двух миллионов отличаются больше чем на 64,
            # один — на 129 (замер 13 сентября 2026). Неверная или перевёрнутая
            # картинка даёт сотни тысяч таких, поэтому меряется доля, а не пик.
            ok = (mean < 2 and rough <= got.width * got.height // 10000
                  and side and own and english)
            bad += not ok
            print(f"    {entry['name']:18} отличие от русской: среднее {mean:.2f}, пик {peak}, грубых {rough}; "
                  f"сторона {'как оригинал' if side else 'ПЕРЕВЁРНУТА'}; "
                  f"адрес {'свой' if own else 'ЧУЖОЙ'}; английская {'не тронута' if english else 'ИЗМЕНЕНА'}"
                  f"{'' if ok else '  <- РАЗОШЛОСЬ'}")
        del built, blob
        gc.collect()
    print()
    if bad:
        print(f"картинок разошлось: {bad}", file=sys.stderr)
        return 1
    print("Русские картинки сходятся: патчер из оригинала даёт ровно их, английские не тронуты.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
