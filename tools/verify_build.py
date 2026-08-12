"""Проверить собранный бандл перед установкой в игру.

Последний рубеж: смотрим не на JSON с переводом, а на то, что реально получилось
внутри бандла. Проверяется:

  * бандл читается, все .bytes разбираются парсером TPS;
  * файлы, которые мы не трогали, побайтово совпадают с оригиналом слота-носителя;
  * в изменённых файлах появилась кириллица;
  * все 16 букв на кодах-носителях, ни одна не уехала в игру своим кодом;
  * управляющие коды в изменённых блоках не потерялись относительно английского.

Про носители — tools/carriers.py: 16 букв в собранном бандле записаны глаголицей,
потому что на их родных кодах сидит письменность Борджинии. Здесь текст сначала
раскодируется обратно, чтобы проверки и сообщения читались по-человечески.

    python tools/verify_build.py
"""
from __future__ import annotations

import collections
import sys

from bundle_io import read_text_assets
import carriers as C
from common import BACKUP, SCRIPT_PAIR, bundle, in_case_scope, load_entries, read_scripts
import tps as T

STAGE_DIR = "build"


def has_cyrillic(text: str) -> bool:
    return any("Ѐ" <= c <= "ӿ" for c in text)


def visible_text(raw: str) -> str:
    """Только то, что игра рисует: параметры управляющих кодов выброшены.

    Разделять обязательно. Параметр кода лежит в тех же 16-битных словах, что и текст,
    и запросто совпадает с кодовой точкой буквы: например `{E23E}` с параметром 0x0424
    неотличим от буквы «Ф», если смотреть на сырой текст блока. В нетронутом немецком
    бандле таких совпадений 6 файлов из 399 — то есть проверка по сырому тексту ругалась
    бы на оригинал игры.
    """
    return "".join(t for t in T.tokenize(raw) if isinstance(t, str))


def native_leaks(raw: str) -> set[str]:
    """Буквы, уехавшие в бандл своим кодом вместо носителя, — их игра нарисует значками."""
    return {c for c in visible_text(raw) if c in C.BROKEN}


def opcode_bag(text: str) -> collections.Counter:
    return collections.Counter(
        (t.code, t.params) for t in T.tokenize(text) if isinstance(t, T.Op))


def check_bundle(host_key: str, eng_key: str, problems: list[str]) -> tuple[list[str], int, int, list[str]]:
    """Проверить один собранный бандл. Возвращает (изменённые, английские, с кириллицей, немецкие)."""
    from common import WORK

    src = bundle(host_key)
    built = WORK / STAGE_DIR / src.name
    if not built.exists():
        problems.append(f"нет собранного бандла {built.name} — сначала tools/build.py")
        return [], 0, 0, []

    german = read_text_assets(BACKUP / src.name)
    new = read_text_assets(built)
    eng = read_scripts(eng_key)

    if set(german) != set(new):
        problems.append(f"{host_key}: состав ассетов изменился — так быть не должно")
        return [], 0, 0, []

    changed, untouched_english = [], 0
    cyrillic_files = 0
    still_german = []

    for path, blob in new.items():
        name = path.split("/")[-1].lower()
        # Эталон теперь английский, а не немецкий: всё непереведённое обязано уехать
        # в слот английским, иначе игрок увидит немецкий текст.
        if name not in eng:
            problems.append(f"{name}: нет такого файла в английском бандле")
            continue
        if blob == eng[name]:
            untouched_english += 1
            continue
        if blob == german[path]:
            still_german.append(name)
            continue
        changed.append(name)

        try:
            parsed = T.parse(blob)
        except T.TpsError as exc:
            problems.append(f"{name}: не разбирается после сборки — {exc}")
            continue
        if T.build(parsed) != blob:
            problems.append(f"{name}: собранный файл не переживает round-trip")

        if not in_case_scope(name):
            problems.append(f"{name}: изменён файл вне дел в работе")

        raw_text = "".join(b.text for b in parsed.blocks)
        leaked = native_leaks(raw_text)
        if leaked:
            problems.append(f"{name}: буквы {''.join(sorted(leaked))} ушли своим кодом "
                            f"мимо носителей — игра нарисует их значками Борджинии")
        text = C.decode(raw_text, C.chosen_map())
        if has_cyrillic(text):
            cyrillic_files += 1

        # коды не должны пропадать относительно английского оригинала
        if name in eng:
            src_bag = opcode_bag("".join(b.text for b in T.parse(eng[name]).blocks))
            lost = src_bag - opcode_bag(text)
            if lost:
                codes = ", ".join(f"{c:04X}" for c, _p in list(lost)[:5])
                problems.append(f"{name}: потеряны коды {codes}")

    print(f"  {host_key:18s} ассетов {len(new):3d}, английских {untouched_english:3d}, "
          f"с русским {len(changed):3d}, с кириллицей {cyrillic_files:3d}")
    if changed:
        print(f"      {', '.join(sorted(changed)[:6])}")
    return changed, untouched_english, cyrillic_files, still_german


def main() -> int:
    problems: list[str] = []
    changed: list[str] = []
    cyrillic_files = 0

    # Бандла два, и проверять надо оба: немецкий доходил до игрока именно из второго.
    for host_key, eng_key in SCRIPT_PAIR:
        ch, _eng_as_is, cyr, still_german = check_bundle(host_key, eng_key, problems)
        changed += ch
        cyrillic_files += cyr
        if still_german:
            problems.append(f"{host_key}: остались немецкими {len(still_german)} файлов "
                            f"({', '.join(sorted(still_german)[:4])}) — должны быть английскими")

    translated = sum(1 for e in load_entries() if e.get("ru"))
    print(f"переведено сегментов: {translated}")

    if problems:
        print(f"\nпроблемы ({len(problems)}):")
        for line in problems[:15]:
            print("  ", line)
        return 1

    if changed and cyrillic_files != len(changed):
        print("\nне во всех изменённых файлах есть кириллица — подозрительно")
        return 1

    print("\nOK — бандл целостный, изменения только в делах в работе, кириллица на месте.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
