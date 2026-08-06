"""Научить шрифты игры отдавать кириллицу по кодам-носителям.

Зачем — см. tools/carriers.py: игра подменяет 16 кириллических букв, подмена держится
за код символа, поэтому буквы уводятся на другие коды. Чтобы по новому коду рисовалась
нужная буква, в cmap встроенной гарнитуры добавляется запись «код-носителя -> тот же
глиф, что у настоящей буквы».

Сами очертания букв не трогаются: добавляются только записи в таблицу соответствий.

    python tools/patch_font_cmap.py --check      # что будет добавлено
    python tools/patch_font_cmap.py --install    # добавить и поставить в игру
"""
from __future__ import annotations

import argparse
import shutil
import struct
import sys
from io import BytesIO

import UnityPy
from fontTools.ttLib import TTFont

import carriers as C
from common import BACKUP, BUNDLES, WORK, game_is_running, load_json, save_json, sha256

MANIFEST = BACKUP / "manifest.json"
STAGE = WORK / "build"
FONT_BUNDLE_PATTERNS = ("gk_common_ui_trial*", "gk_common_ingameui*", "gk_common_title*")


class FontPatchError(RuntimeError):
    """Гарнитуру не удалось пересобрать — пропускаем её, остальные не роняем."""


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


def _apply(font, additions: dict[int, str], include_format4: bool) -> int:
    """Разложить записи по юникодным подтаблицам. Вернуть, сколько добавлено."""
    added = 0
    for table in font["cmap"].tables:
        if table.platformID not in (0, 3):
            continue
        if table.format == 4 and not include_format4:
            continue
        for code, glyph in additions.items():
            # формат 4 адресует только BMP
            if table.format == 4 and code > 0xFFFF:
                continue
            if table.cmap.get(code) == glyph:
                continue
            table.cmap[code] = glyph
            added += 1
    return added


def patch_ttf(blob: bytes, letters: str) -> tuple[bytes, int]:
    """Добавить в cmap записи «код-носителя -> глиф буквы». Вернуть (байты, сколько добавлено).

    Подтаблица формата 4 хранит свою длину в 16 битах, и у крупных гарнитур
    разрозненные новые коды её переполняют: каждый такой код заводит отдельный
    сегмент. Поэтому при переполнении формат 4 оставляем как есть и пишем только
    в формат 12 — у него длина 32-битная. FreeType всё равно предпочитает
    подтаблицу (3,10), то есть формат 12.
    """
    best = TTFont(BytesIO(blob), fontNumber=0, lazy=True).getBestCmap()

    additions: dict[int, str] = {}
    for base in C.CANDIDATES.values():
        for ch, code in C.carrier_map(base, letters).items():
            glyph = best.get(ord(ch))
            if glyph is not None:
                additions[code] = glyph
    if not additions:
        return blob, 0

    for include_format4 in (True, False):
        font = TTFont(BytesIO(blob), fontNumber=0)
        added = _apply(font, additions, include_format4)
        if not added:
            return blob, 0
        buf = BytesIO()
        try:
            font.save(buf)
        except struct.error:
            continue  # формат 4 не вместил — пробуем без него
        return buf.getvalue(), added

    raise FontPatchError("не удалось собрать шрифт даже без правки формата 4")


def patch_bundle(path, letters: str, dry_run: bool):
    """Вернуть (список пропатченных шрифтов, список сбойных, байты бандла или None)."""
    env = UnityPy.load(str(path))
    changed, failed = [], []
    for obj in env.objects:
        if obj.type.name != "Font":
            continue
        tree = obj.read_typetree()
        blob = bytes(tree.get("m_FontData") or b"")
        if not blob:
            continue
        name = tree.get("m_Name", "?")
        if dry_run:
            changed.append((name, len(blob), 0))
            continue
        try:
            new_blob, added = patch_ttf(blob, letters)
        except Exception as exc:
            # одна негодная гарнитура не должна ронять весь прогон
            failed.append((name, str(exc)[:70]))
            continue
        if not added:
            continue
        tree["m_FontData"] = list(new_blob)
        obj.save_typetree(tree)
        changed.append((name, len(blob), added))

    if dry_run or not changed:
        return changed, failed, None
    return changed, failed, env.file.save(packer="lz4")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="только показать, что будет сделано")
    ap.add_argument("--install", action="store_true", help="установить в игру")
    ap.add_argument("--all-letters", action="store_true",
                    help="раздать носители всей кириллице, а не только сломанным буквам")
    args = ap.parse_args()

    letters = C.ALPHABET if args.all_letters else C.BROKEN
    print(f"букв под носители: {len(letters)}  ({letters})")
    print(f"участков-кандидатов: {len(C.CANDIDATES)} — " +
          ", ".join(f"{n} U+{b:04X}" for n, b in C.CANDIDATES.items()))
    print(f"итого новых кодов на шрифт: {len(letters) * len(C.CANDIDATES)}\n")

    if args.check:
        for name, base in C.CANDIDATES.items():
            m = C.carrier_map(base, letters)
            sample = "  ".join(f"{ch}=U+{code:04X}" for ch, code in list(m.items())[:5])
            print(f"  {name:<10} {sample} ...")
        print()

    for path in font_bundles():
        changed, failed, blob = patch_bundle(path, letters, dry_run=args.check)
        for name, why in failed:
            print(f"      ! {name}: пропущен ({why})", file=sys.stderr)
        if not changed:
            print(f"  = {path.name[:56]}: править нечего")
            continue
        print(f"  * {path.name[:56]}")
        for name, size, added in changed:
            print(f"      {name}: {size:,} байт, добавлено кодов: {added}")

        if args.check or blob is None:
            continue

        backup = BACKUP / path.name
        if not backup.exists():
            BACKUP.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
            print(f"      бэкап -> backup/{path.name[:40]}")
        register_backup(path)

        out = STAGE / path.name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(blob)
        print(f"      собран: {len(blob):,} байт")

        if args.install:
            if game_is_running():
                print("\nGK12.exe запущен — закрой игру.", file=sys.stderr)
                return 1
            shutil.copy2(out, path)
            print(f"      установлен, sha={sha256(path)[:12]}")

    if args.install:
        print("\nТеперь собери пробу: python tools/alphabet_probe.py --set carriers --install")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
