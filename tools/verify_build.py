"""Проверить собранный бандл перед установкой в игру.

Последний рубеж: смотрим не на JSON с переводом, а на то, что реально получилось
внутри бандла. Проверяется:

  * бандл читается, все .bytes разбираются парсером TPS;
  * файлы, которые мы не трогали, побайтово совпадают с оригиналом французского слота;
  * в изменённых файлах появилась кириллица;
  * управляющие коды в изменённых блоках не потерялись относительно английского.

    python tools/verify_build.py
"""
from __future__ import annotations

import collections
import sys

from bundle_io import read_text_assets
from common import BACKUP, bundle, in_case_scope, load_json, read_scripts
import tps as T

STAGE_DIR = "build"


def has_cyrillic(text: str) -> bool:
    return any("Ѐ" <= c <= "ӿ" for c in text)


def opcode_bag(text: str) -> collections.Counter:
    return collections.Counter(
        (t.code, t.params) for t in T.tokenize(text) if isinstance(t, T.Op))


def main() -> int:
    from common import WORK

    src = bundle("script_fre")
    built = WORK / STAGE_DIR / src.name
    if not built.exists():
        print(f"нет собранного бандла {built} — сначала tools/build.py", file=sys.stderr)
        return 1

    original = read_text_assets(BACKUP / src.name)
    new = read_text_assets(built)
    eng = read_scripts("script_eng")

    if set(original) != set(new):
        print("состав ассетов в бандле изменился — так быть не должно", file=sys.stderr)
        return 1

    changed, unchanged = [], 0
    problems: list[str] = []
    cyrillic_files = 0

    for path, blob in new.items():
        name = path.split("/")[-1].lower()
        if blob == original[path]:
            unchanged += 1
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
            problems.append(f"{name}: изменён файл вне дела 2")

        text = "".join(b.text for b in parsed.blocks)
        if has_cyrillic(text):
            cyrillic_files += 1

        # коды не должны пропадать относительно английского оригинала
        if name in eng:
            src_bag = opcode_bag("".join(b.text for b in T.parse(eng[name]).blocks))
            lost = src_bag - opcode_bag(text)
            if lost:
                codes = ", ".join(f"{c:04X}" for c, _p in list(lost)[:5])
                problems.append(f"{name}: потеряны коды {codes}")

    data = load_json(WORK / "case2.json") or {"entries": []}
    translated = sum(1 for e in data["entries"] if e.get("ru"))

    print(f"ассетов в бандле:     {len(new)}")
    print(f"не изменились:        {unchanged}")
    print(f"изменены:             {len(changed)}  {', '.join(sorted(changed)[:6])}")
    print(f"с кириллицей:         {cyrillic_files}")
    print(f"переведено сегментов: {translated}")

    if problems:
        print(f"\nпроблемы ({len(problems)}):")
        for line in problems[:15]:
            print("  ", line)
        return 1

    if changed and cyrillic_files != len(changed):
        print("\nне во всех изменённых файлах есть кириллица — подозрительно")
        return 1

    print("\nOK — бандл целостный, изменения только в деле 2, кириллица на месте.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
