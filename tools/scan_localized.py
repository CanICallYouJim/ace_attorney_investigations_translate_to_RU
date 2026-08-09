"""Перепись всех ассетов игры, у которых есть языковые варианты.

Зачем: сюжетный текст и строковые таблицы — не весь язык в игре. Часть надписей
запечена в картинки, префабы и видео: заставки «Расследование», даты в «ситуации»,
кат-ины с уликами, титульные логотипы, 3D-модель предмета с текстом на текстуре.
Игрок на слоте-носителе (`common.HOST`) видит их **по-немецки**.

Раскладка в бандлах одинаковая: рядом лежат `<имя>.png`, `<имя>_eng.png`,
`<имя>_ger.png`, ... то есть у каждой немецкой картинки есть английская пара.
Подмена сводится к «взять данные из `_eng` и положить в `_ger`».

Скрипт ничего не меняет. Он строит перепись в `work/localized_assets.json`:
для каждой «семьи» (базовое имя без языкового хвоста) — бандл, тип, размеры
текстур по языкам. Плюс печатает сводку по бандлам.

    .venv\\Scripts\\python.exe tools\\scan_localized.py            # сводка
    .venv\\Scripts\\python.exe tools\\scan_localized.py --list ger # все немецкие ассеты
"""
from __future__ import annotations

import re
import sys
import time
from collections import defaultdict

import UnityPy

from common import BUNDLES, WORK, save_json

# Языковые хвосты в именах ассетов. `jpn` встречается не везде: часть картинок
# без хвоста — это и есть японский оригинал.
LANGS = ("eng", "ger", "fre", "jpn", "kor", "sim", "tra")
SUFFIX = re.compile(r"_(" + "|".join(LANGS) + r")(?=\.|$)", re.IGNORECASE)

# Хвост не всегда в самом конце: `GK1_Logo_Small_eng_R.png`, `cut01_03e_X_sim.png`.
INFIX = re.compile(r"_(" + "|".join(LANGS) + r")(?=_|\.)", re.IGNORECASE)


def split_lang(path: str) -> tuple[str, str] | None:
    """`.../cut03_024_ger.png` -> ('.../cut03_024.png', 'ger'). None — если ассет не языковой."""
    for rx in (SUFFIX, INFIX):
        m = rx.search(path)
        if m:
            return path[: m.start()] + path[m.end():], m.group(1).lower()
    return None


def texture_info(obj) -> dict | None:
    """Размер и формат Texture2D — по ним видно, ляжет ли английская картинка на место немецкой."""
    try:
        data = obj.read()
        fmt = data.m_TextureFormat
        return {
            "w": int(data.m_Width),
            "h": int(data.m_Height),
            "fmt": getattr(fmt, "name", str(fmt)),
            "bytes": int(len(data.image_data)) if data.image_data else 0,
        }
    except Exception as exc:  # noqa: BLE001 — перепись не должна падать из-за одного ассета
        return {"error": str(exc)[:80]}


def scan() -> dict:
    families: dict[str, dict] = {}
    per_bundle: dict[str, dict] = defaultdict(lambda: {"langs": defaultdict(int), "types": defaultdict(int), "total": 0})

    bundles = sorted(BUNDLES.glob("*.bundle"))
    for i, path in enumerate(bundles, 1):
        t = time.time()
        env = UnityPy.load(str(path))
        stat = per_bundle[path.name]
        found = 0
        for asset_path, obj in env.container.items():
            stat["total"] += 1
            split = split_lang(asset_path)
            if not split:
                continue
            base, lang = split
            found += 1
            stat["langs"][lang] += 1
            stat["types"][obj.type.name] += 1

            key = f"{path.name}::{base}::{obj.type.name}"
            fam = families.setdefault(key, {
                "bundle": path.name,
                "base": base,
                "type": obj.type.name,
                "variants": {},
            })
            entry = {"path": asset_path}
            if obj.type.name == "Texture2D":
                entry.update(texture_info(obj) or {})
            fam["variants"][lang] = entry
        print(f"[{i:3}/{len(bundles)}] {path.name[:60]:60} {found:5} языковых  ({time.time()-t:.1f} c)",
              file=sys.stderr)

    for stat in per_bundle.values():
        stat["langs"] = dict(stat["langs"])
        stat["types"] = dict(stat["types"])
    return {"families": families, "bundles": dict(per_bundle)}


def summary(data: dict) -> None:
    fams = data["families"]
    print(f"\nВсего семей с языковыми вариантами: {len(fams)}\n")
    print(f"{'бандл':66} {'ger':>5} {'eng':>5} {'тип':<14} {'пара eng?':>9}")
    print("-" * 104)
    by_bundle: dict[str, list] = defaultdict(list)
    for fam in fams.values():
        by_bundle[fam["bundle"]].append(fam)
    total_ger = total_pairs = 0
    for name, group in sorted(by_bundle.items()):
        ger = [f for f in group if "ger" in f["variants"]]
        eng = [f for f in group if "eng" in f["variants"]]
        pairs = [f for f in ger if "eng" in f["variants"]]
        types = ",".join(sorted({f["type"] for f in group}))
        total_ger += len(ger)
        total_pairs += len(pairs)
        print(f"{name[:66]:66} {len(ger):5} {len(eng):5} {types[:14]:<14} {len(pairs):9}")
    print("-" * 104)
    print(f"{'ИТОГО':66} {total_ger:5} {'':5} {'':14} {total_pairs:9}")

    orphans = [f for f in fams.values() if "ger" in f["variants"] and "eng" not in f["variants"]]
    if orphans:
        print(f"\nНемецкие без английской пары ({len(orphans)}):")
        for f in orphans[:20]:
            print(f"   {f['base']}")

    mismatch = [
        f for f in fams.values()
        if f["type"] == "Texture2D" and {"ger", "eng"} <= set(f["variants"])
        and (f["variants"]["ger"].get("w"), f["variants"]["ger"].get("h"))
        != (f["variants"]["eng"].get("w"), f["variants"]["eng"].get("h"))
    ]
    print(f"\nТекстур, где размер ger != eng: {len(mismatch)}")
    for f in mismatch[:20]:
        g, e = f["variants"]["ger"], f["variants"]["eng"]
        print(f"   {f['base'].split('/')[-1]:40} ger {g.get('w')}x{g.get('h')} {g.get('fmt')}"
              f"   eng {e.get('w')}x{e.get('h')} {e.get('fmt')}")


if __name__ == "__main__":
    out = WORK / "localized_assets.json"
    if "--reuse" in sys.argv and out.exists():
        import json
        data = json.loads(out.read_text(encoding="utf-8"))
    else:
        data = scan()
        save_json(out, data)
        print(f"\nперепись: {out}", file=sys.stderr)
    summary(data)
