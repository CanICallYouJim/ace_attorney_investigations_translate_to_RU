"""Свести сплошную вычитку целого дела в один патч: сцены, копии, конфликты.

`proof_merge.py` сводит одну сцену; дело — это десятки сцен, и копии одной реплики
правят разные редакторы в разных сценах. Поэтому дело сводится целиком:

  1. каждая сцена — по правилу proof_merge (accept/reject/alt/missed);
  2. копии (тот же английский, `copies.py`), чей русский совпадал с прежним текстом
     правленой реплики, получают ту же правку;
  3. **конфликт** — две сцены поправили копии одной реплики по-разному; печатается
     группой со всеми вариантами, сводит человек (`--choose`);
  4. **разошедшаяся копия** — была переведена иначе ещё до вычитки; печатается,
     потому что разница бывает законной (другой адресат, сторона границы ты/вы).

Выход в каталоге дела: `_case.final.json` (патч для `apply.py --force`),
`_conflicts.json`, `_diverged.json`.

    python tools/proof_case.py 5                       # свести и показать конфликты
    python tools/proof_case.py 5 --choose choose.json  # {английский: id-образец} — свести группы
    python tools/proof_case.py 5 --skip sce4_c0_01     # сцены, уже применённые раньше
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

from common import WORK, load_entries, load_json, save_json
from copies import norm
from proof_check import check
from proof_merge import merge
from scene_dump import PACK


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("case", type=int)
    ap.add_argument("--choose", type=Path, help="JSON {английский без кодов: id, чей текст брать}")
    ap.add_argument("--skip", nargs="*", default=[], help="сцены, которые уже применены")
    args = ap.parse_args()

    folder = WORK / "proofread-2026-11" / f"c{args.case}"
    entries = {e["id"]: e for e in load_entries()}
    scenes = sorted(p.name[:-len(".patch.json")] for p in folder.glob("*.patch.json")
                    if not p.name.startswith("_"))
    scenes = [s for s in scenes if s not in args.skip]
    missing = [s for s in scenes if not (folder / f"{s}.review.json").exists()]
    if missing:
        print(f"! без ревью: {missing}")

    own: dict[str, str] = {}
    stats: collections.Counter = collections.Counter()
    for scene in scenes:
        final, st = merge(folder, scene)
        stats.update(st)
        own.update(final)

    by_en: dict[str, list[dict]] = collections.defaultdict(list)
    for e in entries.values():
        by_en[norm(e["en"])].append(e)

    spread: dict[str, str] = {}
    diverged = []
    for key, text in own.items():
        me = entries[key]
        for other in by_en[norm(me["en"])]:
            oid = other["id"]
            if oid == key or oid in own:
                continue
            if other["ru"] == me["ru"] and other["en"] == me["en"]:
                spread.setdefault(oid, text)
            elif norm(other["ru"]) != norm(text):
                diverged.append({"src": key, "copy": oid, "en": norm(me["en"]),
                                 "was": norm(me["ru"]), "now": norm(text),
                                 "copy_ru": norm(other["ru"])})
    final = {**spread, **own}

    if args.choose:
        for en, src in (load_json(args.choose) or {}).items():
            text = final[src]
            for e in by_en[en]:
                if e["en"] == entries[src]["en"]:
                    final[e["id"]] = text
                else:
                    print(f"! другая разметка, свести вручную: {e['id']}")

    # Копии с одинаковой английской разметкой обязаны совпасть буква в букву —
    # вместе с переносом строки и кодами (check_repeats сравнивает так же). Сравнение
    # без переносов пропустило копию напарника в деле 5, где разошёлся только `\n`.
    groups: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for key, text in final.items():
        groups[entries[key]["en"]][key] = text
    conflicts = {norm(en): {k: v for k, v in g.items()} for en, g in groups.items()
                 if len(set(g.values())) > 1}

    diverged = [d for d in diverged if d["copy"] not in final]
    save_json(folder / "_case.final.json", final)
    save_json(folder / "_conflicts.json", conflicts)
    save_json(folder / "_diverged.json", diverged)

    print(f"сцен {len(scenes)}: " + ", ".join(f"{k} {v}" for k, v in stats.items()))
    print(f"правок по сценам {len(own)}, по копиям {len(spread)}, итог {len(final)}")
    print(f"групп-конфликтов {len(conflicts)}, разошедшихся копий {len(diverged)}")
    errors, _ = check(folder / "_case.final.json", entries,
                      load_json(PACK / "speakers.json", default={}) or {})
    for line in errors:
        print("  ✗", line)
    return 1 if errors or conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
