"""Собрать русский слот: подставить перевод из work/case{N}.json в бандл-носитель.

Английский бандл берётся как источник содержимого, переведённые сегменты подменяются,
результат пишется поверх слота-носителя (см. common.HOST — сейчас немецкий) — так
русский становится обычным пунктом в игровом меню языков.

**Всё непереведённое остаётся английским, а не немецким.** В слот-носитель
переписываются все ассеты обоих скриптовых бандлов (399 + 44), включая другие дела
GK2 и файлы вне объёма перевода: игроку-русскому немецкий текст бесполезен,
английский хотя бы читается. Бандла именно два — `..._assets_all_`
и `..._trial_assets_all_`; второй держит дело 1 и общую механику (логические шахматы,
экран проигрыша, реакции «Логики»), и пока его не собирали, оттуда шёл немецкий.
Файлы без единого перевода копируются из английского байт-в-байт, даже не разбираясь
парсером — так их нельзя случайно испортить (в бандле есть чисто бинарные, см.
common.BINARY_ONLY_FILES).

Собирать можно на любой стадии перевода и сразу смотреть результат в игре.

При сборке 16 букв переписываются кодами-носителями (tools/carriers.py): на их
родных кодах сидит письменность вымышленной Борджинии, и отобрать эти коды у неё
нельзя — проверено, см. docs/font-atlas.md. В work/case{N}.json текст остаётся
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
from common import (SCRIPT_PAIR, WORK, bundle, game_is_running,
                    in_case_scope, load_entries, read_scripts, sha256)
import segments as S
import tps as T

STAGE = WORK / "build"


def build_assets(entries: list[dict], host_key: str, eng_key: str
                 ) -> tuple[dict[str, bytes], int, int, list[str]]:
    """Собрать содержимое одного бандла-носителя целиком.

    Возвращает (ассеты, сколько сегментов заменено, в скольких файлах есть русский, ошибки).
    В ассетах — все файлы бандла: с переводом собранные заново, остальные английские как есть.
    """
    # Разметка кодов ({E108:0008}) под подмену не попадает: в таблице только кириллица.
    carriers = C.chosen_map()

    # Английский держим рядом с русским: метка блока не уникальна в файле, и по одному
    # адресу (метка, номер) отзывается несколько блоков — см. проверку в цикле ниже.
    # Поэтому на адрес кладётся не одна пара, а список: в sce2_opening.bytes по адресу
    # FFFFFFFF|0 отзываются все одиннадцать блоков файла, и у каждого свой перевод.
    by_file: dict[str, dict[tuple[str, int], list[tuple[str, str]]]] = {}
    for entry in entries:
        if entry.get("ru"):
            by_file.setdefault(entry["file"], {}).setdefault(
                (entry["block"], entry["index"]), []).append(
                    (entry["en"], C.encode(entry["ru"], carriers)))

    eng = read_scripts(eng_key)
    # Путь внутри бандла-носителя берём из него самого: регистр в именах не всегда
    # нижний (sce1_LateDebug.bytes), а при записи он должен совпасть в точности.
    host_path = asset_paths(bundle(host_key))
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
        touched_file = False
        for block in parsed.blocks:
            segs = S.split(block.text)
            touched_block = False
            for idx, seg in enumerate(segs):
                key = (f"{block.label_id:08X}", idx)
                if key not in wanted:
                    continue
                try:
                    head, core, tail = seg.core()
                    # Метка блока в файле не уникальна: у одной и той же метки бывает
                    # до четырёх блоков, и лишние — это склейка сцены из чистых кодов,
                    # без единой буквы. Адрес (метка, номер) их не различает, поэтому
                    # подставляем, только если на месте лежит ровно тот английский,
                    # который переводили. Иначе перевод уезжал в пустой блок-заглушку
                    # и в игре всплывала реплика, которой в оригинале нет.
                    here = T.to_markup(core)
                    russian = next((ru for en, ru in wanted[key] if en == here), None)
                    if russian is None:
                        continue
                    seg.body = head + T.from_markup(russian) + tail
                except Exception as exc:
                    problems.append(f"{name} {key}: разметка не разобралась — {exc}")
                    continue
                replaced += 1
                touched_block = touched_file = True
            if touched_block:
                block.text = S.join(segs)

        assets[host_path[name]] = T.build(parsed) if touched_file else raw
        russian_files += 1 if touched_file else 0

    return assets, replaced, russian_files, problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--install", action="store_true", help="установить собранный бандл в игру")
    args = ap.parse_args()

    # Бандлы в игре одни на все дела: собираем из всех work/case{N}.json сразу,
    # иначе установка одного дела стёрла бы перевод другого. Бандлов два —
    # основной и trial (дело 1 и общая механика), см. common.SCRIPT_PAIR.
    entries = load_entries()
    if not entries:
        print("нет work/case*.json — сначала tools/extract.py", file=sys.stderr)
        return 1

    built: list[tuple] = []
    replaced = russian_files = assets_total = 0
    for host_key, eng_key in SCRIPT_PAIR:
        assets, rep, rus, problems = build_assets(entries, host_key, eng_key)
        if problems:
            print(f"ошибки разметки в {host_key} ({len(problems)}):", file=sys.stderr)
            for line in problems[:10]:
                print("  ", line, file=sys.stderr)
            return 1
        replaced += rep
        russian_files += rus
        assets_total += len(assets)
        built.append((host_key, assets, rus))

    total = len(entries)
    print(f"переведено сегментов: {replaced} из {total} ({100*replaced/total:.1f}%)")
    print(f"файлов с русским:     {russian_files}")
    print(f"английским в слот:    {assets_total - russian_files} (всё непереведённое)")
    print(f"коды-носители:        {C.CHOSEN} U+{C.CANDIDATES[C.CHOSEN]:04X}+ "
          f"для {len(C.BROKEN)} букв ({C.BROKEN})")
    if not assets_total:
        print("нечего собирать — заполни поля \"ru\" в work/case*.json")
        return 0

    outputs = []
    for host_key, assets, rus in built:
        src = bundle(host_key)
        out = STAGE / src.name
        done, size = write_text_assets(src, assets, out)
        print(f"  {host_key:18s} {done:3d} ассетов, {size:,} байт, с русским {rus}")
        outputs.append((src, out))
    print(f"-> {STAGE}")

    if not args.install:
        print("\n(это черновая сборка; для установки в игру запусти с --install)")
        return 0

    if game_is_running():
        print("\nGK12.exe запущен — закрой игру, файлы бандла заблокированы.", file=sys.stderr)
        return 1

    print()
    for src, out in outputs:
        shutil.copy2(out, src)
        print(f"установлено: {src.name}  SHA-256 {sha256(src)[:16]}...")
    print("В игре: Options -> Language -> Deutsch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
