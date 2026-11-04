"""Свести правку редактора и вердикт ревьюера в итоговый патч сцены.

Правило сведения одно на весь проход ноября 2026, чтобы итог не зависел от того,
кто сводил:

  * `accept` — правка редактора идёт как есть;
  * `reject` — правка выбрасывается, реплика остаётся прежней;
  * `alt`    — идёт текст ревьюера;
  * `missed` — пропущенный редактором брак, текст ревьюера добавляется;
  * правка без вердикта — идёт как есть (ревьюер молча согласился),
    но печатается отдельно, чтобы это было видно.

Итог — `<сцена>.final.json` в формате `apply.py`; он же проверяется
`proof_check.check`. Применение в `work/case*.json` — отдельным шагом:

    python tools/proof_merge.py work/proofread-2026-11/c4 sce3_c0_01
    python tools/apply.py work/proofread-2026-11/c4/sce3_c0_01.final.json --force
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import load_entries, load_json, save_json
from proof_check import check
from scene_dump import PACK


def merge(folder: Path, scene: str) -> tuple[dict, dict]:
    patch = load_json(folder / f"{scene}.patch.json", default={}) or {}
    review = load_json(folder / f"{scene}.review.json", default={}) or {}
    verdicts, missed = review.get("verdicts", {}), review.get("missed", {})
    final, stats = {}, {"accept": 0, "reject": 0, "alt": 0, "missed": 0, "silent": 0}
    for key, text in patch.items():
        v = (verdicts.get(key) or {}).get("v")
        if v == "reject":
            stats["reject"] += 1
            continue
        if v == "alt":
            final[key] = verdicts[key]["text"]
            stats["alt"] += 1
        else:
            final[key] = text
            stats["accept" if v == "accept" else "silent"] += 1
    for key, m in missed.items():
        if key not in final:
            final[key] = m["text"]
            stats["missed"] += 1
    return final, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("scenes", nargs="+")
    args = ap.parse_args()
    entries = {e["id"]: e for e in load_entries()}
    speakers = load_json(PACK / "speakers.json", default={}) or {}
    bad = 0
    for scene in args.scenes:
        final, stats = merge(args.folder, scene)
        out = args.folder / f"{scene}.final.json"
        save_json(out, final)
        errors, _warns = check(out, entries, speakers)
        print(f"{scene}: итог {len(final)} — " + ", ".join(f"{k} {v}" for k, v in stats.items()))
        for line in errors:
            print("  ✗", line)
        bad += len(errors)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
