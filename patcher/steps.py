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
    staged: Path      # где лежит собранная замена
    note: str         # строка для человека


# Категории графики, которые ставятся. Ровно те, что стоят и проверены в игре
# на своей машине (268 адресов из 268): интерфейс, картинки, ролики и выкрики.
# «gk1» намеренно снаружи — первая игра не в объёме перевода, а «classic»
# сидит внутри graphics, потому что режим ретро-графики включается в настройках
# и надписи там свои.
CATEGORIES = ("ui", "graphics", "movie", "audio")


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

def graphics(stage: Path, with_gk1: bool = False, only: tuple[str, ...] = ()) -> Iterator[Change]:
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

    `with_gk1` добавляет графику первой игры: ещё 213 адресов и 2,3 ГБ
    перезаписи. По умолчанию выключено — GK1 вне объёма перевода, её текст
    наш патч и так делает английским, а ради надписей на картинках удваивать
    время установки незачем. Решение пользователя от 12 августа 2026.

    `only` — куски имён бандлов: собрать только их. Для проверки, не для игрока.
    """
    from common import BUNDLES
    from picture_layer import Shipment, short
    from swap_localized import IMAGE_TABLE_BUNDLE, collect, redirect, swap_image_table

    wanted = CATEGORIES + ("gk1",) if with_gk1 else CATEGORIES
    plan: dict[str, list] = {}
    for part in only or (None,):
        plan.update(collect(wanted, part))
    russian = Shipment()
    # Бандл, где подменять адреса нечего, а русское лежит, — немецкие плашки ситуации:
    # английских двойников в нём нет, и collect() его не берёт.
    have = {short(n) for n in plan}
    for bundle in russian.by_bundle:
        live = next(BUNDLES.glob(f"{bundle}_assets_all_*.bundle"), None)
        if live is not None and bundle not in have and (not only or any(p in live.name for p in only)):
            plan[live.name] = []
    # Строки таблицы локали у плашек, которые лягут: игра берёт Situation_0/1 через таблицу.
    keep = russian.table_rows(BUNDLES)
    for name, pairs in sorted(plan.items(), key=lambda kv: (not russian.feeds(kv[0]), kv[0])):
        live = BUNDLES / name
        if IMAGE_TABLE_BUNDLE in name:
            # Особый бандл: английских двойников внутри нет, подменяются
            # значения в таблице картинок локали; строки русских плашек — немецкие.
            blob, changed = swap_image_table(keep)
            note = f"таблица картинок локали, записей {changed}" + (
                f", немецкими оставлены {len(keep)} — русские плашки" if keep else "")
        elif russian.has(name):
            blob, done, notes = russian.build(live, pairs)
            note = "; ".join([f"адресов {len(pairs)}, из них с русской картинкой {done}", *notes])
        else:
            blob = redirect(live, pairs)
            note = f"адресов {len(pairs)}"
        staged = stage / name
        staged.write_bytes(blob)
        yield Change(f"asset_{name.split('_assets_all_')[0]}", live, staged, note)
