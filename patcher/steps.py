"""Шаги патча: что именно меняется в игре и чем это собирается.

Здесь нет ни одного собственного алгоритма — только склейка. Разбор формата,
сборка бандлов, правка гарнитур и подмена графики живут в `tools/` и там же
проверяются тестами; патчер вызывает те же функции, просто нацелив их
на чужую игру через переменные окружения (см. `common.py`).

Каждый шаг складывает готовый файл во временную папку и отдаёт `Change`.
Пишет в игру не он, а `aai2ru.py`: так шаг может упасть, не оставив игру
в наполовину пропатченном виде, а память и диск не держат больше одного
бандла разом — важно для графики, там 2,9 ГБ на 34 файла.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class Change:
    """Один файл игры, который надо заменить."""
    key: str          # логическое имя: script_ger, font_data.unity3d, asset_gk2_movie
    target: Path      # где он лежит в игре
    staged: Path | None   # где лежит собранная замена; None — бандл уже стоит, не собирался
    note: str         # строка для человека
    recipe: str = ""  # отпечаток того, из чего собран (у графики) — см. `graphics_recipe`


# Категории графики, которые ставятся. Ровно те, что стоят и проверены в игре
# на своей машине (268 адресов из 268): интерфейс, картинки, ролики и выкрики.
# «gk1» намеренно снаружи — первая игра не в объёме перевода, а «classic»
# сидит внутри graphics, потому что режим ретро-графики включается в настройках
# и надписи там свои.
CATEGORIES = ("ui", "graphics", "movie", "audio")

# Версия сборки графики. Поднять, когда код меняет то, что ложится в бандл
# (подмена адресов, склейка, упаковка): у игроков, поставивших прежний патч,
# каждый бандл тогда соберётся заново, а не будет пропущен как «уже стоит».
GRAPHICS_VERSION = "2026-10-02"


def stamp(path: Path) -> list[int]:
    """Отметка файла игры: размер и время записи. Steam, обновивший или вернувший
    бандл, меняет обе; читать 2,9 ГБ ради хэша на каждом запуске незачем."""
    st = path.stat()
    return [st.st_size, st.st_mtime_ns]


def graphics_recipe(bundle_short: str, russian, keep: dict) -> str:
    """Отпечаток того, из чего собирается бандл: версия кода, его русские картинки
    (с хэшами слоя и английской основы) и картинки, из которых его уменьшаются.

    Пары подмены адресов в отпечаток не входят — они берутся из самой игры,
    и её перемену ловит `stamp`."""
    import hashlib
    import json

    from swap_localized import IMAGE_TABLE_BUNDLE, OTHER_SOURCE

    own = sorted(russian.by_bundle.get(bundle_short, []), key=lambda e: e["name"])
    names = {e["derive"]["из"] for e in own if e.get("derive")}
    sources = sorted((e for e in russian.pictures if e["name"] in names), key=lambda e: e["name"])
    data = {"v": GRAPHICS_VERSION, "own": own, "sources": sources}
    if IMAGE_TABLE_BUNDLE in bundle_short:
        data["table"] = sorted(keep.items())
    if "gk2_movie" in bundle_short:
        # ролики берут французский вариант (OTHER_SOURCE) — его смена пересобирает
        # только этот бандл, а не всю графику, как подъём GRAPHICS_VERSION
        data["other_source"] = sorted(OTHER_SOURCE.items())
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


# --- реплики ------------------------------------------------------------------

def scripts(stage: Path) -> list[Change]:
    """Два скриптовых бандла: английское содержимое, поверх — наш перевод.

    Бандла именно два: основной и `_trial`, во втором дело 1 и общая механика
    (логические шахматы, экран проигрыша, реакции «Логики»). Собираются оба,
    иначе часть текста доходит до игрока по-немецки.
    """
    from build import build_assets
    from bundle_io import write_text_assets
    from common import SCRIPT_PAIR, bundle, load_entries

    entries = load_entries()
    if not entries:
        raise RuntimeError("рядом с патчером нет данных перевода (case*.json)")

    out: list[Change] = []
    for host_key, eng_key in SCRIPT_PAIR:
        assets, replaced, russian_files, problems = build_assets(entries, host_key, eng_key)
        if problems:
            raise RuntimeError(f"{host_key}: разметка не разобралась — {problems[0]}")
        src = bundle(host_key)
        staged = stage / src.name
        done, size = write_text_assets(src, assets, staged)
        out.append(Change(host_key, src, staged,
                          f"{done} ассетов, файлов с русским {russian_files}, "
                          f"сегментов переведено {replaced}"))
    return out


def gk1_scripts(stage: Path) -> list[Change]:
    """Реплики первой игры: немецкие ассеты заменяются английскими.

    GK1 не в объёме перевода — у неё другой формат скриптов, и её целиком
    покрывает известный фанатский русификатор. Но игрок, выбравший в меню
    «Русский», садясь за первую игру, получал бы немецкий текст. Английский
    он хотя бы прочитает, поэтому содержимое немецкого бандла берётся
    из английского.

    Разбирать формат не нужно и не хочется: ассеты копируются сырыми байтами.
    Набор имён в бандлах не совпадает (273 против 271), поэтому переписывается
    пересечение, а лишнее немецкое остаётся как есть — английского для него
    в игре просто нет.
    """
    from bundle_io import asset_paths, write_text_assets
    from common import bundle, read_scripts

    out: list[Change] = []
    for host_key, eng_key in (("gk1_script_ger", "gk1_script_eng"),
                              ("gk1_script_ger_trial", "gk1_script_eng_trial")):
        try:
            src = bundle(host_key)
            host_path = asset_paths(src)
            english = read_scripts(eng_key)
        except (FileNotFoundError, KeyError):
            continue                      # у этой сборки игры такого бандла нет

        replacements = {host_path[name]: raw for name, raw in english.items()
                        if name in host_path}
        if not replacements:
            continue
        staged = stage / src.name
        done, size = write_text_assets(src, replacements, staged)
        left = len(host_path) - done
        note = f"{done} ассетов по-английски" + (f", {left} без пары оставлены" if left else "")
        out.append(Change(host_key, src, staged, note))
    return out


# --- строковые таблицы --------------------------------------------------------

def strings(stage: Path) -> list[Change]:
    """Имена в плашке, названия и описания улик, профили, кнопки логики, интерфейс."""
    from build_strings import plan, verify
    from bundle_io import write_string_tables
    from common import WORK, bundle, load_json

    data = load_json(WORK / "strings.json")
    if not data:
        raise RuntimeError("рядом с патчером нет данных таблиц (strings.json)")
    translations = data["tables"]

    out: list[Change] = []
    for host_key, per_table in plan(translations).items():
        src = bundle(host_key)
        staged = stage / src.name
        tables, rows, size = write_string_tables(src, per_table, staged)
        problems = verify(staged, host_key, translations, per_table)
        if problems:
            raise RuntimeError(f"{host_key}: {problems[0]}")
        out.append(Change(host_key, src, staged, f"таблиц {tables}, строк {rows}"))
    return out


# --- гарнитуры ----------------------------------------------------------------

def fonts(stage: Path) -> list[Change]:
    """Две правки шрифтов в `GK12_Data/data.unity3d` — без них кириллица не рисуется.

    Первая: коды-носители. На родных кодах 16 букв сидит письменность вымышленной
    Борджинии, отобрать их у неё нельзя (проверено, буквы пропадают совсем),
    поэтому буквы уводятся на свободные коды, а в cmap добавляется запись
    «код-носителя -> тот же глиф».

    Вторая: метрики. Кириллица в этих гарнитурах полноширинная, как иероглиф,
    и текст без правки идёт вразрядку.

    Обе делаются за один проход по файлу: он весит 113 МБ, и разбирать его
    дважды незачем. Правки идемпотентны — на уже пропатченной игре обе функции
    возвращают шрифт как есть, и шаг честно скажет «менять нечего».
    """
    import UnityPy

    import carriers as C
    from patch_font_cmap import LATIN_FONTS, patch_ttf
    from patch_font_metrics import DEFAULT_SIDEBEARING, retype
    from common import GAME

    target = GAME / "GK12_Data" / "data.unity3d"
    if not target.exists():
        raise RuntimeError(f"в игре нет {target.name} — это точно папка игры?")

    env = UnityPy.load(str(target))
    touched: list[str] = []
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

        blob, added = patch_ttf(blob, C.BROKEN)
        blob, retyped, _ = retype(blob, DEFAULT_SIDEBEARING)
        if not added and not retyped:
            continue
        tree["m_FontData"] = list(blob)
        obj.save_typetree(tree)
        touched.append(f"{name} (+{added} кодов, {retyped} букв)")

    if not touched:
        return []

    staged = stage / target.name
    staged.write_bytes(env.file.save(packer="lz4"))
    return [Change("font_data.unity3d", target, staged,
                   f"гарнитур {len(touched)}: " + ", ".join(touched))]


# --- графика, ролики и звук ---------------------------------------------------

def graphics(stage: Path, with_gk1: bool = False, only: tuple[str, ...] = (),
             done: dict | None = None) -> Iterator[Change]:
    """Немецким адресам отдаются английские объекты: надписи, ролики, выкрики.

    Байты картинок и звука не трогаются вовсе — правится таблица «адрес -> объект»
    внутри бандла. Перерисовывать ничего не нужно: английский вариант каждой
    надписи уже лежит в игре рядом с немецким.

    Исключение — надписи, у которых есть русский слой (`graphics_layers/`, снимает
    его `layer_localized.py`). Такая картинка склеивается тут же, из английской
    текстуры этой игры и слоя, и ложится в немецкий объект; адрес остаётся ему,
    английская текстура не трогается. Английская картинка в игре не та, по которой
    снят слой, — надпись остаётся английской. Решение пользователя от 13 сентября
    2026. Бандлы, из картинок которых уменьшаются другие, идут первыми.

    Генератор, а не список: бандлов 33 и весят они 2,9 ГБ, держать их разом
    негде. Каждый отдаётся сразу после сборки, ставится и стирается.

    `done` — записи прошлых установок из манифеста бэкапа: имя бандла ->
    {"recipe", "stamp"}. Бандл, у которого отпечаток рецепта (`graphics_recipe`)
    и отметка файла (`stamp`) те же, что после прошлой записи, не читается
    и не собирается: отдаётся `Change` с `staged=None`. Так повторная установка
    (новая версия перевода с парой новых картинок) переписывает только бандлы,
    где что-то поменялось, а не все 2,9 ГБ — просьба пользователя от 2 октября
    2026. Бандл, которому менять нечего, записывается в `done` сам, с `empty`.
    `done=None` — собрать всё заново, как до 2 октября (`aai2ru.exe --full`).

    `with_gk1` добавляет графику первой игры: ещё 213 адресов и 2,3 ГБ
    перезаписи. По умолчанию выключено — GK1 вне объёма перевода, её текст
    наш патч и так делает английским, а ради надписей на картинках удваивать
    время установки незачем. Решение пользователя от 12 августа 2026.

    `only` — куски имён бандлов: собрать только их. Для проверки, не для игрока.
    """
    from common import BUNDLES
    from picture_layer import Shipment, short
    from swap_localized import (IMAGE_TABLE_BUNDLE, NEVER, category_of, plan_bundle,
                                redirect, swap_image_table)

    wanted = CATEGORIES + ("gk1",) if with_gk1 else CATEGORIES
    russian = Shipment()
    # Строки таблицы локали у плашек, которые лягут: игра берёт Situation_0/1 через таблицу.
    keep = russian.table_rows(BUNDLES)
    # Те же бандлы, что брал `collect()`, но пока без чтения: категория по имени файла.
    # Плюс бандлы с русским, где подменять адреса нечего (немецкие плашки ситуации).
    names = []
    for path in sorted(BUNDLES.glob("*.bundle")):
        if any(bad in path.name for bad in NEVER):
            continue
        if only and not any(p in path.name for p in only):
            continue
        if category_of(path.name) in wanted or russian.has(path.name):
            names.append(path.name)
    recipes = {name: graphics_recipe(short(name), russian, keep) for name in names}

    skip: set[str] = set()
    if done is not None:
        for name in names:
            rec = done.get(name)
            if rec and rec.get("recipe") == recipes[name] and rec.get("stamp") == stamp(BUNDLES / name):
                skip.add(name)
        # Пересобираемому бандлу нужны картинки, из которых уменьшаются его мелкие
        # копии: их бандл собирается тоже, иначе копия осталась бы английской.
        home = {e["name"]: e["bundle"] for e in russian.pictures}
        changed = True
        while changed:
            changed = False
            for name in names:
                if name in skip:
                    continue
                for entry in russian.by_bundle.get(short(name), []):
                    src = (entry.get("derive") or {}).get("из")
                    for other in [n for n in skip if short(n) == home.get(src)]:
                        skip.discard(other)
                        changed = True

    for name in sorted(names, key=lambda n: (not russian.feeds(n), n)):
        live = BUNDLES / name
        key = f"asset_{name.split('_assets_all_')[0]}"
        if name in skip:
            if not done[name].get("empty"):
                yield Change(key, live, None, "уже стоит, не менялся", recipes[name])
            continue
        if IMAGE_TABLE_BUNDLE in name:
            # Особый бандл: английских двойников внутри нет, подменяются
            # значения в таблице картинок локали; строки русских плашек — немецкие.
            blob, changed = swap_image_table(keep)
            note = f"таблица картинок локали, записей {changed}" + (
                f", немецкими оставлены {len(keep)} — русские плашки" if keep else "")
        else:
            pairs = plan_bundle(live)
            if not pairs and not russian.has(name):
                if done is not None:
                    done[name] = {"recipe": recipes[name], "stamp": stamp(live), "empty": True}
                continue
            if russian.has(name):
                blob, count, notes = russian.build(live, pairs)
                note = "; ".join([f"адресов {len(pairs)}, из них с русской картинкой {count}", *notes])
            else:
                blob = redirect(live, pairs)
                note = f"адресов {len(pairs)}"
        staged = stage / name
        staged.write_bytes(blob)
        yield Change(key, live, staged, note, recipes[name])
