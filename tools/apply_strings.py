"""Влить пачку переводов в work/strings.json из отдельного файла-патча.

Парный к apply.py, но для второго конвейера — строковых таблиц. Причина та же:
strings.json это 2823 записи, править его руками ненадёжно, а патч лежит отдельным
файлом и переживает обрыв сессии.

Формат патча — JSON, ключ `таблица|m_Id`, значение — перевод:

    {
      "gk_common_button|38870646787": "Осмотреть",
      "gk_common_title|40317681664": "Продолжить"
    }

Допускается и вложенная форма, так удобнее писать пачку по таблицам:

    {
      "gk_common_button": {"38870646787": "Осмотреть"},
      "gk_common_title": {"40317681664": "Продолжить"}
    }

    python tools/apply_strings.py work/patch_ui.json           # применить
    python tools/apply_strings.py work/patch_ui.json --dry-run # только показать
    python tools/apply_strings.py work/patch_ui.json --force   # переписать переведённое

Незнакомый ключ — ошибка, ничего не пишется: почти всегда это опечатка в m_Id,
а не новая запись. Идентификаторы таблиц числовые и длинные, промахнуться легко.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from common import WORK, load_json, save_json


def flatten(patch: dict) -> dict[tuple[str, str], str]:
    """Обе формы патча -> {(таблица, id): перевод}."""
    out: dict[tuple[str, str], str] = {}
    for key, value in patch.items():
        if isinstance(value, dict):
            for row_id, ru in value.items():
                out[(key, str(row_id))] = ru
        else:
            table, _, row_id = key.partition("|")
            if not row_id:
                raise SystemExit(f"ключ {key!r} без разделителя '|' и не таблица")
            out[(table, row_id)] = value
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("patch", type=Path, help="JSON: 'таблица|id' -> перевод")
    ap.add_argument("--dry-run", action="store_true", help="не записывать, только отчёт")
    ap.add_argument("--force", action="store_true", help="разрешить перезапись переведённого")
    args = ap.parse_args()

    raw = load_json(args.patch)
    if raw is None:
        print(f"нет файла {args.patch}")
        return 1
    patch = flatten(raw)

    data = load_json(WORK / "strings.json")
    if not data:
        print("нет work/strings.json — сначала tools/extract_strings.py")
        return 1
    tables = data["tables"]

    unknown = [f"{t}|{k}" for (t, k) in patch if k not in tables.get(t, {})]
    if unknown:
        print(f"неизвестных ключей: {len(unknown)}")
        for key in unknown[:10]:
            print("  ", key)
        return 1

    new = changed = same = 0
    conflicts: list[str] = []
    for (table, row_id), ru in patch.items():
        entry = tables[table][row_id]
        old = entry.get("ru", "")
        if old == ru:
            same += 1
            continue
        if old and not args.force:
            conflicts.append(f"{table}|{row_id}")
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
        for key in conflicts[:10]:
            print("  ", key)

    if not args.dry_run:
        save_json(WORK / "strings.json", data)

    total = sum(len(rows) for rows in tables.values())
    done = sum(1 for rows in tables.values() for e in rows.values() if e.get("ru"))
    verb = "будет применено" if args.dry_run else "применено"
    print(f"{verb}: новых {new}, переписано {changed}, без изменений {same}")
    print(f"переведено записей: {done} из {total}")
    return 1 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
