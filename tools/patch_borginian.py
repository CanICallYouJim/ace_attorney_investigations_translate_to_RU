"""Освободить коды кириллицы от борджинийской письменности.

Причина подмены букв. В Ace Attorney есть вымышленная страна **Борджиния** со своей
письменностью. Её алфавит лежит в игре двумя частями, и обе сидят на кодах кириллицы —
разработчики заняли диапазон как свободный, по-русски игра не говорит:

  * гарнитура `borujinia` (5 КБ, 18 глифов) в `GK12_Data/data.unity3d`;
  * **TMP-ассет `borujinia SDF` там же** — с готовой таблицей символов на 17 записей
    и своим запечённым атласом.

Ровно 16 из них — кириллица, буква в букву совпадающая с тем, что ломалось в игре:

    Д Ж З Й К Ф Ш Ю     а б в г е ё л п

Игра не ломалась: её просили нарисовать борджинийский знак, и она его рисовала.

Почему важен именно TMP-ассет. Глифы берутся из его **запечённой таблицы**, а не из
файла гарнитуры, поэтому правка cmap самой `borujinia` ничего не меняет — проверено
в игре. Освобождать надо таблицу.

Как. Таблица символов — массив по 16 байт на запись: тип, код, индекс глифа, масштаб.
Коды кириллицы переписываются на незанятые из области частного использования
(`U+F0000`+). Размер объекта не меняется, всё остальное в ассете нетронуто. TMP
перестаёт находить эти коды у борджинийской гарнитуры, запрос уходит дальше
по цепочке, и букву рисует основная гарнитура.

Типовое дерево для ассета недоступно: игра на IL2CPP, UnityPy не знает её типов —
из 5442 MonoBehaviour в `data.unity3d` читаются 79. Поэтому правка идёт по сырым
байтам, а запись опознаётся по сигнатуре целиком, а не по жёсткому смещению.

Безопасность проверена: в оригинальных скриптах GK2 всех семи локализаций и в строковых
таблицах борджинийского текста ноль вхождений.

    python tools/patch_borginian.py --check      # что найдено, ничего не менять
    python tools/patch_borginian.py --install    # освободить кириллицу
"""
from __future__ import annotations

import argparse
import shutil
import struct
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
# Куда уводим освобождённые коды: область частного использования, игрой не занята.
SPARE_BASE = 0xF0000

ENTRY_SIZE = 16  # тип(4) + код(4) + индекс глифа(4) + масштаб(4)


def register_backup(path) -> None:
    manifest = load_json(MANIFEST, default={}) or {}
    key = f"font_{path.name.split('_assets_all_')[0]}"
    if key in manifest:
        return
    manifest[key] = {"file": path.name, "source": str(path), "sha256": sha256(BACKUP / path.name)}
    save_json(MANIFEST, manifest)


def find_entries(raw: bytes) -> list[tuple[int, int, int]]:
    """Записи таблицы символов с кириллицей: (смещение записи, код, индекс глифа).

    Запись опознаётся целиком по сигнатуре — тип 1, код из диапазона кириллицы,
    правдоподобный индекс глифа, масштаб ровно 1.0, — чтобы не привязываться
    к смещению, которое поедет при любом обновлении игры.
    """
    out = []
    for off in range(0, len(raw) - ENTRY_SIZE + 1, 4):
        etype, code, glyph = struct.unpack_from("<III", raw, off)
        if etype != 1 or code not in CYRILLIC or glyph > 0xFFFF:
            continue
        if struct.unpack_from("<f", raw, off + 12)[0] != 1.0:
            continue
        out.append((off, code, glyph))
    return out


def strip_ttf_cyrillic(blob: bytes) -> tuple[bytes, list[int]]:
    """Убрать кириллицу из cmap самой гарнитуры. На отрисовку не влияет
    (глифы берутся из таблицы TMP-ассета), но оставлять занятым незачем."""
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
    ap.add_argument("--check", action="store_true", help="показать найденное, ничего не менять")
    ap.add_argument("--install", action="store_true", help="установить в игру")
    args = ap.parse_args()

    env = UnityPy.load(str(MAIN_DATA))

    asset = None       # TMP-ассет borujinia SDF
    face = None        # сама гарнитура borujinia
    for obj in env.objects:
        if obj.type.name == "MonoBehaviour":
            raw = bytes(obj.get_raw_data())
            if b"borujinia" in raw:
                asset = (obj, raw)
        elif obj.type.name == "Font":
            tree = obj.read_typetree()
            if tree.get("m_Name") == FONT_NAME:
                face = (obj, tree)

    if asset is None:
        print("TMP-ассет borujinia SDF не найден", file=sys.stderr)
        return 1

    obj, raw = asset
    entries = find_entries(raw)
    print(f"TMP-ассет borujinia SDF: {len(raw):,} байт, записей с кириллицей: {len(entries)}")
    for off, code, glyph in entries:
        print(f"    @{off:<6} U+{code:04X} {chr(code)!r}  глиф={glyph}")

    if face is not None:
        blob = bytes(face[1].get("m_FontData") or b"")
        cmap = TTFont(BytesIO(blob), fontNumber=0, lazy=True).getBestCmap()
        cyr = sorted(c for c in cmap if c in CYRILLIC)
        print(f"\nгарнитура borujinia: {len(blob):,} байт, кириллицы в cmap: {len(cyr)}")

    if args.check:
        return 0
    if not entries:
        print("\nосвобождать нечего — таблица уже правлена")
        return 0

    patched = bytearray(raw)
    for i, (off, code, _glyph) in enumerate(entries):
        struct.pack_into("<I", patched, off + 4, SPARE_BASE + i)
    assert len(patched) == len(raw), "размер объекта изменился — так нельзя"
    obj.set_raw_data(bytes(patched))
    print(f"\nосвобождено кодов в таблице: {len(entries)} — "
          + " ".join(chr(c) for _, c, _ in entries))

    if face is not None:
        new_blob, removed = strip_ttf_cyrillic(bytes(face[1].get("m_FontData") or b""))
        if removed:
            face[1]["m_FontData"] = list(new_blob)
            face[0].save_typetree(face[1])
            print(f"освобождено кодов в cmap гарнитуры: {len(removed)}")

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
