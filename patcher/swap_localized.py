"""Подмена локализованной графики, видео и звука: слот-носитель показывает английские варианты.

Зачем. Русский занимает немецкий слот (`common.HOST`), поэтому всё, что запечено
в картинки, префабы, 3D-модели, ролики и звук, игра берёт по адресу `..._ger`
и показывает по-немецки. Английский вариант каждой такой вещи уже лежит в игре
рядом, в том же бандле, по адресу `..._eng`.

Как. Два механизма, оба без перерисовки пикселей:

  1. **Перенаправление контейнера.** У бандла есть таблица «адрес -> объект»
     (`AssetBundle.m_Container`). Записи `..._ger` выдаётся тот же объект, что
     и записи `..._eng`. Работает одинаково для текстур, звука, роликов, префабов
     и атласов — байты ассетов не трогаются вовсе.
  2. **Таблица картинок локали.** Ассеты из `localization-assets-german(de)`
     адресуются не по имени, а по GUID из `Image Table_de`. Там значения
     заменяются английскими из `Image Table_en`. Это ровно то, что Capcom уже
     сделала сама для логотипов: в немецкой таблице они указывают на `_eng`.

Порядок работы:

    .venv\\Scripts\\python.exe tools\\swap_localized.py                  # план, ничего не меняет
    .venv\\Scripts\\python.exe tools\\swap_localized.py --build ui
    .venv\\Scripts\\python.exe tools\\swap_localized.py --build ui --install
    .venv\\Scripts\\python.exe tools\\swap_localized.py --check          # что стоит в игре

Собранные бандлы кладутся в `work/build_assets/`. `--install` копирует их в игру,
предварительно занося оригиналы в `backup/` и в `backup/manifest.json`,
так что `restore.py` откатит их вместе со всем остальным.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import defaultdict

import UnityPy

from common import BACKUP, BUNDLES, HOST, WORK, bundle, game_is_running, load_json, save_json, sha256

SOURCE = "eng"                      # откуда берём вариант
BUILD = WORK / "build_assets"
MANIFEST = BACKUP / "manifest.json"

LANG_KEY = re.compile(r"_(eng|ger|fre|jpn|kor|sim|tra)(?=_|\.|/|$)", re.IGNORECASE)

# Бандлы с переводом трогать нельзя ни при каких условиях.
NEVER = ("scriptmessage", "string-tables")

# Категория -> по каким кускам имени бандла её узнать. Нужна, чтобы пользователь
# мог ставить не всё сразу: звук — это чужие голоса, а classic — режим графики,
# который может быть вообще не включён.
CATEGORIES: dict[str, tuple[str, ...]] = {
    "ui":       ("gk_common_ingameui", "gk2_logicchess", "localization-assets-german(de)",
                 "localization-asset-tables-german(de)"),
    "graphics": ("gk2_upcut", "gk2_cutobj", "gk2_idcom", "gk2_idlocal", "gk2_logickeyword",
                 "gk2_mapbg", "gk2_mapobj", "gk2_bustup", "gk2_opening", "gk2_modelitem",
                 "gk2_cutdata"),
    "movie":    ("gk2_movie",),
    "audio":    ("gk2_se_",),
    "gk1":      ("gk1_",),
}
DEFAULT_CATEGORIES = ("ui", "graphics", "movie")

# Особый бандл: английских двойников внутри нет, подменяется таблица картинок локали.
IMAGE_TABLE_BUNDLE = "localization-asset-tables-german(de)"


# Адреса, где русскому годится не английский вариант, а другой язык: лист базового
# адреса (без языкового хвоста) -> язык. Ролики камеры `mgm_0_00/03`: у французов метка
# времени уже в нашем виде «27/3 6:42:19» — как на принятых кадрах той же записи
# `cut01_03e/03f/040` (решение пользователя 9 октября 2026); вне метки французский ролик
# равен английскому до пикселя (сверка каждого 10-го кадра). Пикселей не везём — только адрес.
OTHER_SOURCE = {"mgm_0_00.mods.bytes": "fre", "mgm_0_03.mods.bytes": "fre"}


def category_of(name: str) -> str | None:
    for cat, marks in CATEGORIES.items():
        if any(m in name for m in marks):
            return cat
    return None


def plan_bundle(path) -> list[tuple[str, str]]:
    """Пары (адрес _ger, адрес-источник) для одного бандла. Пустой список — менять нечего.

    Источник — `..._eng`, а если такого нет, то вариант вообще без языкового хвоста.
    Хвоста нет там, где английскому отдельная картинка не понадобилась: фантик
    `itm01_01e_00_l.png` и так подписан «CANDY», отдельные только `_fre` и `_ger`
    («BONBON»). Английский игрок в таких местах видит именно базовый вариант.
    """
    return plan_env(UnityPy.load(str(path)))


def plan_env(env) -> list[tuple[str, str]]:
    """То же по уже открытому бандлу — чтобы не читать его с диска второй раз."""
    keys = set(env.container)
    pairs = []
    for key in sorted(keys):
        m = LANG_KEY.search(key)
        if not m or m.group(1).lower() != HOST:
            continue
        base = key[: m.start()] + key[m.end():]
        lang = OTHER_SOURCE.get(base.rsplit("/", 1)[-1], SOURCE)
        english = key[: m.start()] + f"_{lang}" + key[m.end():]
        source = english if english in keys else base if base in keys else None
        if source:
            pairs.append((key, source))
    return pairs


def redirect(path, pairs: list[tuple[str, str]]) -> bytes:
    """Переписать m_Container: адресу _ger отдать объект и преднагрузку записи _eng."""
    env = UnityPy.load(str(path))
    ab = next(o for o in env.objects if o.type.name == "AssetBundle")
    tree = ab.read_typetree()
    by_key = {k: v for k, v in tree["m_Container"]}
    wanted = dict(pairs)

    missing = [g for g, e in pairs if g not in by_key or e not in by_key]
    if missing:
        raise KeyError(f"в контейнере нет записей: {missing[:5]}")

    tree["m_Container"] = [
        [k, (dict(by_key[wanted[k]]) if k in wanted else v)] for k, v in tree["m_Container"]
    ]
    ab.save_typetree(tree)
    return env.file.save(packer="lz4")


def swap_image_table(keep: dict[int, str] | None = None) -> tuple[bytes, int]:
    """Значения `Image Table_de` заменить английскими из `Image Table_en`.

    `keep` — строки, которым остаться немецкими (`m_Id` -> немецкое значение): у русских
    плашек `Situation_0/1` пиксели лежат в немецком спрайте, и таблица обязана вести
    на него (`plates.table_rows`, `picture_layer.Shipment.table_rows`).
    """
    keep = keep or {}
    def read_table(logical_bundle: str):
        env = UnityPy.load(str(logical_bundle))
        for obj in env.objects:
            if obj.type.name == "MonoBehaviour":
                tree = obj.read_typetree()
                if "m_TableData" in tree:
                    return env, obj, tree
        raise KeyError(f"нет таблицы в {logical_bundle}")

    en_path = next(BUNDLES.glob("localization-asset-tables-english(en)_assets_all_*.bundle"))
    de_path = next(BUNDLES.glob(f"{IMAGE_TABLE_BUNDLE}_assets_all_*.bundle"))

    _, _, en_tree = read_table(en_path)
    english = {row["m_Id"]: row["m_Localized"] for row in en_tree["m_TableData"]}

    env, obj, de_tree = read_table(de_path)
    changed = 0
    for row in de_tree["m_TableData"]:
        new = keep.get(row["m_Id"]) or english.get(row["m_Id"])
        if new is None:
            raise KeyError(f"в английской таблице нет записи {row['m_Id']}")
        if row["m_Localized"] != new:
            row["m_Localized"] = new
            changed += 1
    obj.save_typetree(de_tree)
    return env.file.save(packer="lz4"), changed


def collect(categories: tuple[str, ...], only: str | None = None) -> dict[str, list[tuple[str, str]]]:
    """{имя бандла: пары адресов} для выбранных категорий."""
    out: dict[str, list[tuple[str, str]]] = {}
    for path in sorted(BUNDLES.glob("*.bundle")):
        if any(bad in path.name for bad in NEVER):
            continue
        cat = category_of(path.name)
        if cat not in categories:
            continue
        if only and only not in path.name:
            continue
        if IMAGE_TABLE_BUNDLE in path.name:
            out[path.name] = []          # особый случай, пары не по контейнеру
            continue
        pairs = plan_bundle(path)
        if pairs:
            out[path.name] = pairs
    return out


def show_plan(work: dict[str, list]) -> None:
    print(f"{'бандл':62} {'кат':9} {'адресов':>8} {'МБ':>8}")
    print("-" * 92)
    total = size = 0
    for name, pairs in sorted(work.items()):
        mb = (BUNDLES / name).stat().st_size / 1024 / 1024
        n = len(pairs) if pairs else 28
        total += n
        size += mb
        print(f"{name.split('_assets_all_')[0][:62]:62} {category_of(name) or '?':9} {n:8} {mb:8.1f}")
    print("-" * 92)
    print(f"{'ИТОГО':62} {'':9} {total:8} {size:8.1f}")


def register_backup(name: str, live) -> None:
    manifest = load_json(MANIFEST, default={}) or {}
    key = f"asset_{name.split('_assets_all_')[0]}"
    dst = BACKUP / live.name
    if key in manifest and dst.exists() and sha256(dst) == manifest[key]["sha256"]:
        return
    BACKUP.mkdir(parents=True, exist_ok=True)
    digest = sha256(live)
    shutil.copy2(live, dst)
    manifest[key] = {"file": live.name, "source": str(live), "sha256": digest}
    save_json(MANIFEST, manifest)
    print(f"    бэкап: {live.name}")


def do_build(work: dict[str, list], install: bool) -> int:
    if install and game_is_running():
        print("GK12.exe запущен — закрой игру, файлы бандлов заблокированы.", file=sys.stderr)
        return 1

    BUILD.mkdir(parents=True, exist_ok=True)
    for name, pairs in sorted(work.items()):
        live = BUNDLES / name
        short = name.split("_assets_all_")[0]
        if IMAGE_TABLE_BUNDLE in name:
            # Русские плашки, уже стоящие в игре, берутся через эту таблицу: их строки
            # остаются немецкими, иначе подмена снова показала бы английские.
            from plates import installed_rows
            keep = installed_rows()
            blob, changed = swap_image_table(keep)
            note = f"таблица картинок, записей заменено: {changed}" + (
                f", немецкими оставлены {len(keep)} — русские плашки" if keep else "")
        else:
            blob = redirect(live, pairs)
            note = f"адресов перенаправлено: {len(pairs)}"
        out = BUILD / name
        out.write_bytes(blob)
        print(f"  {short:56} {note}; {len(blob)/1024/1024:.1f} МБ")

        if install:
            register_backup(name, live)
            shutil.copy2(out, live)
            print(f"    установлен")
    return 0


def do_check(categories: tuple[str, ...], only: str | None = None) -> int:
    """Проверить по живым файлам игры: адрес _ger указывает на тот же объект, что _eng."""
    bad = ok = 0
    for path in sorted(BUNDLES.glob("*.bundle")):
        if any(b in path.name for b in NEVER) or category_of(path.name) not in categories:
            continue
        if only and only not in path.name:
            continue
        if IMAGE_TABLE_BUNDLE in path.name:
            continue
        env = UnityPy.load(str(path))
        ids = {k: v.path_id for k, v in env.container.items()}
        pairs = [(g, e) for g, e in plan_bundle(path)]
        if not pairs:
            continue
        done = sum(1 for g, e in pairs if ids[g] == ids[e])
        ok += done
        bad += len(pairs) - done
        mark = "OK " if done == len(pairs) else "   "
        print(f"  {mark}{path.name.split('_assets_all_')[0]:56} {done}/{len(pairs)}")
    print(f"\nподменено адресов: {ok}, осталось немецких: {bad}")
    return 1 if bad else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", nargs="*", metavar="КАТЕГОРИЯ",
                    help=f"собрать бандлы; категории: {', '.join(CATEGORIES)} (по умолчанию {', '.join(DEFAULT_CATEGORIES)})")
    ap.add_argument("--install", action="store_true", help="поставить собранное в игру")
    ap.add_argument("--check", nargs="*", metavar="КАТЕГОРИЯ",
                    help="проверить, что стоит в игре; без аргументов — все категории")
    ap.add_argument("--bundle", metavar="ПОДСТРОКА", help="ограничиться одним бандлом — для проб")
    args = ap.parse_args()

    if args.check is not None:
        # бандлы читаются целиком, а gk1_ipnce_fhd — полтора гигабайта: гонять
        # проверку по всему сразу и параллельно с другой работой не стоит, ляжет по памяти
        sys.exit(do_check(tuple(args.check) or tuple(CATEGORIES), args.bundle))

    if args.build is None:
        categories = tuple(CATEGORIES)
        print("План. Ничего не меняется. Запуск с --build поставит выбранные категории.\n")
        show_plan(collect(categories, args.bundle))
        return

    categories = tuple(args.build) or DEFAULT_CATEGORIES
    unknown = set(categories) - set(CATEGORIES)
    if unknown:
        sys.exit(f"неизвестные категории: {sorted(unknown)}")
    work = collect(categories, args.bundle)
    show_plan(work)
    print()
    sys.exit(do_build(work, args.install))


if __name__ == "__main__":
    main()
