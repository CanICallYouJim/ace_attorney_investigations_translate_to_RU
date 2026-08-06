"""Освободить кириллицу от борджинийского алфавита.

Причина подмены букв найдена. В `GK12_Data/data.unity3d` лежит гарнитура `borujinia`
на 5 КБ — вымышленная письменность страны **Борджиния** из Ace Attorney. В ней ровно
17 кодов: одна хирагана и **16 кириллических букв**, на которые разработчики посадили
борджинийские знаки как на свободное место — по-русски игра не говорит, диапазон
казался незанятым.

Совпадение точное, буква в букву:

    Д Ж З Й К Ф Ш Ю   а б в г е ё л п

Именно они и подменялись в игре чужими значками: это не мусор и не сбой атласа,
а борджинийские буквы, честно нарисованные по запросу. Всё остальное сходится —
подмена детерминированная, от размера атласа не зависит, cmap основной гарнитуры
для этих кодов не спрашивается, латиница не затронута.

Исправление: убрать из cmap `borujinia` эти 16 кодов, оставив хирагану. Тогда запрос
уходит дальше по цепочке и букву рисует основная гарнитура.

Безопасность проверена: в оригинальных скриптах GK2 всех семи локализаций и в строковых
таблицах борджинийского текста **ноль вхождений**, терять нечего.

    python tools/patch_borginian.py --check      # что лежит в гарнитуре
    python tools/patch_borginian.py --install    # освободить кириллицу
"""
from __future__ import annotations

import argparse
import shutil
import sys
from io import BytesIO

import UnityPy
from fontTools.ttLib import TTFont

from common import BACKUP, GAME, WORK, game_is_running, load_json, save_json, sha256

MANIFEST = BACKUP / "manifest.json"
STAGE = WORK / "build"
MAIN_DATA = GAME / "GK12_Data" / "data.unity3d"
FONT_NAME = "borujinia"

CYRILLIC = range(0x0400, 0x0500)


def register_backup(path) -> None:
    manifest = load_json(MANIFEST, default={}) or {}
    key = f"font_{path.name.split('_assets_all_')[0]}"
    if key in manifest:
        return
    manifest[key] = {"file": path.name, "source": str(path), "sha256": sha256(BACKUP / path.name)}
    save_json(MANIFEST, manifest)


def strip_cyrillic(blob: bytes) -> tuple[bytes, list[int]]:
    """Убрать из cmap все кириллические коды. Вернуть (байты, какие коды убраны)."""
    font = TTFont(BytesIO(blob), fontNumber=0)
    removed: set[int] = set()
    for table in font["cmap"].tables:
        for code in [c for c in table.cmap if c in CYRILLIC]:
            del table.cmap[code]
            removed.add(code)
    if not removed:
        return blob, []
    buf = BytesIO()
    font.save(buf)
    return buf.getvalue(), sorted(removed)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="показать содержимое гарнитуры, ничего не менять")
    ap.add_argument("--install", action="store_true", help="установить в игру")
    args = ap.parse_args()

    env = UnityPy.load(str(MAIN_DATA))
    target = None
    for obj in env.objects:
        if obj.type.name != "Font":
            continue
        tree = obj.read_typetree()
        if tree.get("m_Name") == FONT_NAME:
            target = (obj, tree)
            break

    if target is None:
        print(f"гарнитура {FONT_NAME!r} не найдена в {MAIN_DATA.name}", file=sys.stderr)
        return 1

    obj, tree = target
    blob = bytes(tree.get("m_FontData") or b"")
    font = TTFont(BytesIO(blob), fontNumber=0, lazy=True)
    codes = sorted(font.getBestCmap())
    print(f"{FONT_NAME}: {len(blob):,} байт, кодов в cmap: {len(codes)}")
    for code in codes:
        mark = "  <- кириллица, освобождаем" if code in CYRILLIC else ""
        print(f"    U+{code:04X}  {chr(code)!r}{mark}")

    if args.check:
        return 0

    new_blob, removed = strip_cyrillic(blob)
    if not removed:
        print("\nкириллицы в гарнитуре нет — менять нечего")
        return 0
    print(f"\nосвобождено кодов: {len(removed)} — " + " ".join(chr(c) for c in removed))

    tree["m_FontData"] = list(new_blob)
    obj.save_typetree(tree)

    backup = BACKUP / MAIN_DATA.name
    if not backup.exists():
        BACKUP.mkdir(parents=True, exist_ok=True)
        shutil.copy2(MAIN_DATA, backup)
        print(f"бэкап -> backup/{MAIN_DATA.name}")
    register_backup(MAIN_DATA)

    out = STAGE / MAIN_DATA.name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(env.file.save(packer="lz4"))
    print(f"собран: {out.stat().st_size:,} байт")

    if args.install:
        if game_is_running():
            print("\nGK12.exe запущен — закрой игру.", file=sys.stderr)
            return 1
        shutil.copy2(out, MAIN_DATA)
        print(f"установлен, sha={sha256(MAIN_DATA)[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
