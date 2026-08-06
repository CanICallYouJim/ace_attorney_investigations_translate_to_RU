"""Опознать шрифт окна реплик и проверить, доходят ли правки шрифта до игры.

Два вопроса, которые до сих пор путались:

  1. Доходят ли наши правки встроенной гарнитуры до рантайма? Правка cmap с кодами-
     носителями не дала в игре ничего, хотя записи легли в подтаблицу (3,1) — ровно ту,
     которую выбирает FreeType. Возможно, игра вообще не спрашивает эту гарнитуру.
  2. Какой гарнитурой рисуется окно реплик? По начертанию похоже на FOTK-YOONMINCHO750,
     но полноширинная разрядка на скриншотах говорит за FOT-MODEMINALARGEPRO-M,
     а полный Latin Extended-A есть только у первого. Признаки противоречат друг другу.

Проба отвечает на оба сразу. В каждой встроенной гарнитуре буквы А Б В Г Д
переклеиваются на её собственный опознавательный знак — свой у каждой. В игре
показывается строка «АБВГД», и по знаку видно, чья это гарнитура:

    ХХХХХ  -> правки доходят, и шрифт опознан по таблице ниже
    АБВГД  -> правки НЕ доходят: игра читает исходную гарнитуру,
              а значит обе прошлые неудачи (атлас и носители) объясняются этим

Переклейка идёт по той же схеме, что и коды-носители: меняется только запись
в cmap, очертания не трогаются.

    python tools/font_ident_probe.py --check
    python tools/font_ident_probe.py --install
"""
from __future__ import annotations

import argparse
import shutil
import struct
import sys
from io import BytesIO

import UnityPy
from fontTools.ttLib import TTFont

from common import BACKUP, BUNDLES, WORK, game_is_running, load_json, save_json, sha256

MANIFEST = BACKUP / "manifest.json"
STAGE = WORK / "build"
FONT_BUNDLE_PATTERNS = ("gk_common_ui_trial*", "gk_common_ingameui*", "gk_common_title*",
                        "gk2_message_todo_delete_trial*")

# Буквы, которые подменяем, и знак-опознаватель у каждой гарнитуры.
MARKED = "АБВГД"
MARKERS = {
    "FOTK-YOONMINCHO750": "1",
    "FOT-MODEMINALARGEPRO-M": "2",
    "FOT-UDKAKUGO_SMALLPR6-M": "3",
    "FOTK-YOONGOTHIC750": "4",
    "FOT-MODEMINALARGEPRO-R": "5",
    "FOT-MODEMINALARGEPRO-B": "6",
    "MSUNGHK-MEDIUM": "7",
    "MSUNGHK-BOLD": "8",
    "MSUNGPRC-MEDIUM": "9",
    "MSUNGPRC-BOLD": "0",
}


def font_bundles():
    seen = {}
    for pat in FONT_BUNDLE_PATTERNS:
        for path in BUNDLES.glob(pat + ".bundle"):
            seen[path.name] = path
    return [seen[k] for k in sorted(seen)]


def register_backup(path) -> None:
    manifest = load_json(MANIFEST, default={}) or {}
    key = f"font_{path.name.split('_assets_all_')[0]}"
    if key in manifest:
        return
    manifest[key] = {"file": path.name, "source": str(path), "sha256": sha256(BACKUP / path.name)}
    save_json(MANIFEST, manifest)


def remark_ttf(blob: bytes, marker: str) -> tuple[bytes, int]:
    """Переклеить А Б В Г Д на глиф знака-опознавателя."""
    probe = TTFont(BytesIO(blob), fontNumber=0, lazy=True)
    target = probe.getBestCmap().get(ord(marker))
    if target is None:
        return blob, 0

    font = TTFont(BytesIO(blob), fontNumber=0)
    changed = 0
    for table in font["cmap"].tables:
        if table.platformID not in (0, 3):
            continue
        for ch in MARKED:
            if table.cmap.get(ord(ch)) is None:
                continue
            table.cmap[ord(ch)] = target
            changed += 1
    if not changed:
        return blob, 0

    buf = BytesIO()
    try:
        font.save(buf)
    except struct.error:
        return blob, 0
    return buf.getvalue(), changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="только показать таблицу знаков")
    ap.add_argument("--install", action="store_true", help="установить в игру")
    args = ap.parse_args()

    print("знаки-опознаватели:")
    for name, mark in MARKERS.items():
        print(f"  {mark}  {name}")
    print(f"\nподменяются буквы: {MARKED}\n")
    if args.check:
        return 0

    for path in font_bundles():
        env = UnityPy.load(str(path))
        done = []
        for obj in env.objects:
            if obj.type.name != "Font":
                continue
            tree = obj.read_typetree()
            blob = bytes(tree.get("m_FontData") or b"")
            name = tree.get("m_Name", "?")
            mark = MARKERS.get(name)
            if not blob or mark is None:
                continue
            new_blob, n = remark_ttf(blob, mark)
            if not n:
                print(f"      ! {name}: не переклеилось", file=sys.stderr)
                continue
            tree["m_FontData"] = list(new_blob)
            obj.save_typetree(tree)
            done.append((name, mark, n))

        if not done:
            print(f"  = {path.name[:56]}: гарнитур нет")
            continue
        print(f"  * {path.name[:56]}")
        for name, mark, n in done:
            print(f"      {name} -> «{mark}» ({n} записей)")

        backup = BACKUP / path.name
        if not backup.exists():
            BACKUP.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
            print(f"      бэкап -> backup/{path.name[:40]}")
        register_backup(path)

        blob = env.file.save(packer="lz4")
        out = STAGE / path.name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(blob)

        if args.install:
            if game_is_running():
                print("\nGK12.exe запущен — закрой игру.", file=sys.stderr)
                return 1
            shutil.copy2(out, path)
            print(f"      установлен, sha={sha256(path)[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
