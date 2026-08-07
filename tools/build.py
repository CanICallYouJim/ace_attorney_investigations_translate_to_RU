"""Собрать русский слот: подставить перевод из work/case2.json в бандл-носитель.

Английский бандл берётся как источник содержимого, переведённые сегменты подменяются,
результат пишется поверх слота-носителя (см. common.HOST — сейчас немецкий) — так
русский становится обычным пунктом в игровом меню языков.

**Всё непереведённое остаётся английским, а не немецким.** В слот-носитель
переписываются все 399 ассетов бандла, включая другие дела GK2 и файлы вне объёма
перевода: игроку-русскому немецкий текст бесполезен, английский хотя бы читается.
Файлы без единого перевода копируются из английского байт-в-байт, даже не разбираясь
парсером — так их нельзя случайно испортить (в бандле есть чисто бинарные, см.
common.BINARY_ONLY_FILES).

Собирать можно на любой стадии перевода и сразу смотреть результат в игре.

При сборке 16 букв переписываются кодами-носителями (tools/carriers.py): на их
родных кодах сидит письменность вымышленной Борджинии, и отобрать эти коды у неё
нельзя — проверено, см. docs/font-atlas.md. В work/case2.json текст остаётся
обычным русским, подмена живёт только внутри собранного бандла.

    python tools/build.py            # собрать в work/build/, игру не трогать
    python tools/build.py --install  # собрать и установить в игру (игра должна быть закрыта)
"""
from __future__ import annotations

import argparse
import shutil
import sys

from bundle_io import asset_paths, write_text_assets
import carriers as C
from common import (HOST_SCRIPT, WORK, bundle, game_is_running,
                    in_case_scope, load_json, read_scripts, sha256)
import segments as S
import tps as T

STAGE = WORK / "build"


def build_assets(entries: list[dict]) -> tuple[dict[str, bytes], int, int, list[str]]:
    """Собрать содержимое слота-носителя целиком.

    Возвращает (ассеты, сколько сегментов заменено, в скольких файлах есть русский, ошибки).
    В ассетах — все файлы бандла: с переводом собранные заново, остальные английские как есть.
    """
    # Разметка кодов ({E108:0008}) под подмену не попадает: в таблице только кириллица.
    carriers = C.chosen_map()

    by_file: dict[str, dict[tuple[str, int], str]] = {}
    for entry in entries:
        if entry.get("ru"):
            by_file.setdefault(entry["file"], {})[(entry["block"], entry["index"])] = \
                C.encode(entry["ru"], carriers)

    eng = read_scripts("script_eng")
    # Путь внутри бандла-носителя берём из него самого: регистр в именах не всегда
    # нижний (sce1_LateDebug.bytes), а при записи он должен совпасть в точности.
    host_path = asset_paths(bundle(HOST_SCRIPT))
    assets: dict[str, bytes] = {}
    replaced = 0
    russian_files = 0
    problems: list[str] = []

    for name, raw in eng.items():
        wanted = by_file.get(name, {}) if in_case_scope(name) else {}
        if not wanted:
            # Ни одного перевода — английский оригинал уезжает в слот нетронутым.
            # Не разбираем парсером сознательно: портить тут нечего, а в бандле
            # есть файлы из чистых бинарных данных.
            assets[host_path[name]] = raw
            continue

        parsed = T.parse(raw)
        touched = False
        for block in parsed.blocks:
            segs = S.split(block.text)
            for idx, seg in enumerate(segs):
                key = (f"{block.label_id:08X}", idx)
                if key not in wanted:
                    continue
                try:
                    head, _core, tail = seg.core()
                    seg.body = head + T.from_markup(wanted[key]) + tail
                except Exception as exc:
                    problems.append(f"{name} {key}: разметка не разобралась — {exc}")
                    continue
                replaced += 1
                touched = True
            if touched:
                block.text = S.join(segs)

        assets[host_path[name]] = T.build(parsed) if touched else raw
        russian_files += 1 if touched else 0

    return assets, replaced, russian_files, problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--install", action="store_true", help="установить собранный бандл в игру")
    args = ap.parse_args()

    data = load_json(WORK / "case2.json")
    if not data:
        print("нет work/case2.json — сначала tools/extract.py", file=sys.stderr)
        return 1

    entries = data["entries"]
    assets, replaced, russian_files, problems = build_assets(entries)
    if problems:
        print(f"ошибки разметки ({len(problems)}):", file=sys.stderr)
        for line in problems[:10]:
            print("  ", line, file=sys.stderr)
        return 1

    total = len(entries)
    print(f"переведено сегментов: {replaced} из {total} ({100*replaced/total:.1f}%)")
    print(f"файлов с русским:     {russian_files}")
    print(f"английским в слот:    {len(assets) - russian_files} (всё непереведённое)")
    print(f"коды-носители:        {C.CHOSEN} U+{C.CANDIDATES[C.CHOSEN]:04X}+ "
          f"для {len(C.BROKEN)} букв ({C.BROKEN})")
    if not assets:
        print("нечего собирать — заполни поля \"ru\" в work/case2.json")
        return 0

    src = bundle(HOST_SCRIPT)
    out = STAGE / src.name
    done, size = write_text_assets(src, assets, out)
    print(f"бандл собран:         {done} ассетов, {size:,} байт")
    print(f"-> {out}")

    if not args.install:
        print("\n(это черновая сборка; для установки в игру запусти с --install)")
        return 0

    if game_is_running():
        print("\nGK12.exe запущен — закрой игру, файлы бандла заблокированы.", file=sys.stderr)
        return 1

    shutil.copy2(out, src)
    print(f"\nустановлено в игру: {src}")
    print(f"SHA-256: {sha256(src)[:16]}...")
    print("В игре: Options -> Language -> Deutsch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
