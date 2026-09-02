"""Влить пачку переводов в work/case{N}.json из отдельного файла-патча.

Правка семитысячного JSON руками ненадёжна: одна съехавшая запятая — и потерян
весь файл. Патч кладётся отдельно, применяется одной командой, применение
идемпотентно. Так пачка переживает обрыв сессии: файл патча остаётся на диске.

Формат патча — JSON, идентификатор сегмента в ключ, перевод в значение:

    {
      "sce1_c0_06.bytes|01000300|0": "Что ж,{E108:0010} оценим расстановку сил.",
      "sce1_c0_06.bytes|01000300|1": "(Когда он настороже,{E108:0008} то встаёт в стойку.)"
    }

    python tools/apply.py work/patch.json           # применить
    python tools/apply.py work/patch.json --dry-run # только показать, что будет

Незнакомый идентификатор — ошибка, ничего не пишется: почти всегда это опечатка
в номере сегмента, а не новый сегмент. Перезапись уже переведённого требует
--force, иначе повторный прогон старого патча тихо откатит правки редактуры.

**Набор управляющих кодов при перезаписи обязан совпасть со старым** — иначе
сегмент не применяется. Заведено 3 сентября 2026 после ретро-прохода: коды живут
между словами, и редактура их роняет незаметно — убрал вводное «Что ж,» и вместе
с ним уехал `{E108:0008}`. `check_len.py` это ловит, но уже после записи, и правка
превращается в цикл «применил — проверил — починил — применил» (за один патч
такое случилось четырежды). Порядок кодов менять по-прежнему можно, набор — нет;
намеренная смена набора — `--codes-may-change`.
"""
from __future__ import annotations

import argparse
import collections
import re
from pathlib import Path

from common import CASES, case_json, load_json, save_json

CODES = re.compile(r"\{[^}]*\}")


def code_bag(text: str) -> collections.Counter:
    """Набор управляющих кодов реплики. Порядок менять можно, набор — нет."""
    return collections.Counter(CODES.findall(text))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("patch", type=Path, help="JSON: идентификатор сегмента -> перевод")
    ap.add_argument("--dry-run", action="store_true", help="не записывать, только отчёт")
    ap.add_argument("--force", action="store_true", help="разрешить перезапись переведённого")
    ap.add_argument("--codes-may-change", action="store_true",
                    help="разрешить менять набор управляющих кодов реплики")
    args = ap.parse_args()

    patch = load_json(args.patch)
    if patch is None:
        print(f"нет файла {args.patch}")
        return 1
    if isinstance(patch, list):  # допускаем и список записей — так удобнее выгружать
        patch = {e["id"]: e["ru"] for e in patch}

    # Патч адресуется к делу сам, по идентификаторам сегментов: пачка почти всегда
    # про один файл сценария, но раскладываем по делам честно, а пишем только те,
    # которых патч коснулся.
    loaded = {case: load_json(case_json(case)) for case in CASES}
    loaded = {case: data for case, data in loaded.items() if data}
    if not loaded:
        print("нет work/case*.json — сначала tools/extract.py")
        return 1
    by_id = {e["id"]: (case, e) for case, data in loaded.items() for e in data["entries"]}

    unknown = [k for k in patch if k not in by_id]
    if unknown:
        print(f"неизвестных идентификаторов: {len(unknown)}")
        for k in unknown[:10]:
            print("  ", k)
        return 1

    new = changed = same = 0
    conflicts: list[str] = []
    code_problems: list[tuple] = []
    touched: set[int] = set()
    for key, ru in patch.items():
        case, entry = by_id[key]
        touched.add(case)
        old = entry.get("ru", "")
        if old == ru:
            same += 1
            continue
        if old and not args.force:
            conflicts.append(key)
            continue
        # Редактура переписывает уже переведённую реплику, и коды в ней живут
        # между словами: убрал вводное «Что ж,» — вместе с ним уехал {E108:0008}.
        # check_len.py это ловит, но уже после записи; здесь ошибка стоит
        # одного прогона, а не цикла «применил — проверил — починил — применил».
        if old and not args.codes_may_change and code_bag(old) != code_bag(ru):
            was, now = code_bag(old), code_bag(ru)
            lost = sorted((was - now).elements())
            extra = sorted((now - was).elements())
            code_problems.append((key, lost, extra))
            continue
        if old:
            changed += 1
        else:
            new += 1
        if not args.dry_run:
            entry["ru"] = ru
            entry["status"] = "translated" if ru else "pending"

    if conflicts:
        print(f"уже переведены, пропущены ({len(conflicts)}, нужен --force):")
        for k in conflicts[:10]:
            print("  ", k)

    if code_problems:
        print(f"набор кодов разошёлся, НЕ применены ({len(code_problems)}):")
        for key, lost, extra in code_problems[:10]:
            what = []
            if lost:
                what.append("потеряны " + " ".join(lost))
            if extra:
                what.append("добавлены " + " ".join(extra))
            print(f"   {key}: {'; '.join(what)}")
        print("   Коды живут между словами: убрал вводное — верни его код на запятую.")
        print("   Если набор меняется намеренно — --codes-may-change.")

    if not args.dry_run:
        for case in sorted(touched):
            save_json(case_json(case), loaded[case])

    verb = "будет применено" if args.dry_run else "применено"
    print(f"{verb}: новых {new}, переписано {changed}, без изменений {same}")
    for case in sorted(touched):
        entries = loaded[case]["entries"]
        done = sum(1 for e in entries if e.get("ru"))
        print(f"дело {case}: переведено сегментов {done} из {len(entries)}")
    return 1 if conflicts or code_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
