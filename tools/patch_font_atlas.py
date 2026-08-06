"""Увеличить страницу атласа у динамических TMP-шрифтов игры.

Зачем. Атлас у этих шрифтов наполняется в рантайме и очищен при сборке
(m_ClearDynamicDataOnBuild = 1, текстура 1x1). Страница всего 1024x1024, а глифы
рендерятся крупно: m_PointSize 54 при m_LineHeight 108. Латиницы с французскими
диакритиками уже почти хватает, чтобы её забить, и добавленная кириллица уезжает
на вторую страницу. Материал при этом остаётся привязан к первой текстуре, поэтому
буквы со второй страницы рисуются кусками чужих глифов — те самые «пиктограммы».
Набор испорченных букв меняется от показа к показу, потому что зависит от того,
какие глифы успели занять первую страницу.

Если страница достаточно большая, вторая не создаётся и проблема не возникает.
Память: страница 4096x4096 в Alpha8 — это 16 МБ, приемлемо.

    python tools/patch_font_atlas.py --check      # что сейчас
    python tools/patch_font_atlas.py --install    # увеличить и поставить в игру
"""
from __future__ import annotations

import argparse
import shutil
import sys

import UnityPy

from common import BACKUP, BUNDLES, WORK, game_is_running, load_json, save_json, sha256

MANIFEST = BACKUP / "manifest.json"


def register_backup(path) -> None:
    """Занести оригинал в манифест, чтобы tools/restore.py умел его вернуть."""
    manifest = load_json(MANIFEST, default={}) or {}
    key = f"font_{path.name.split('_assets_all_')[0]}"
    if key in manifest:
        return
    manifest[key] = {"file": path.name, "source": str(path), "sha256": sha256(BACKUP / path.name)}
    save_json(MANIFEST, manifest)

SIZE = 4096
STAGE = WORK / "build"
# Бандлы, где лежат TMP-шрифты (найдены tools/find_fonts.py)
FONT_BUNDLE_PATTERNS = ("gk_common_ui_trial*", "gk_common_ingameui*", "gk_common_title*")


def font_bundles():
    seen = {}
    for pat in FONT_BUNDLE_PATTERNS:
        for path in BUNDLES.glob(pat + ".bundle"):
            seen[path.name] = path
    return [seen[k] for k in sorted(seen)]


def patch_bundle(path, size: int, dry_run: bool):
    """Вернуть (список изменённых шрифтов, байты нового бандла или None)."""
    env = UnityPy.load(str(path))
    changed = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception:
            continue
        if "m_CharacterTable" not in tree or tree.get("m_AtlasPopulationMode") != 1:
            continue

        name = tree.get("m_Name", "?")
        before = (tree.get("m_AtlasWidth"), tree.get("m_AtlasHeight"))
        if before == (size, size):
            continue
        changed.append((name, before))
        if dry_run:
            continue

        tree["m_AtlasWidth"] = size
        tree["m_AtlasHeight"] = size
        # свободная область должна описывать всю новую страницу
        tree["m_FreeGlyphRects"] = [{"m_X": 0, "m_Y": 0, "m_Width": size - 1, "m_Height": size - 1}]
        tree["m_UsedGlyphRects"] = []
        obj.save_typetree(tree)

    if dry_run or not changed:
        return changed, None
    return changed, env.file.save(packer="lz4")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="только показать текущее состояние")
    ap.add_argument("--install", action="store_true", help="установить в игру")
    ap.add_argument("--size", type=int, default=SIZE, help=f"сторона страницы (по умолчанию {SIZE})")
    args = ap.parse_args()

    bundles = font_bundles()
    print(f"бандлов со шрифтами: {len(bundles)}\n")

    total = 0
    for path in bundles:
        changed, blob = patch_bundle(path, args.size, dry_run=args.check)
        if not changed:
            print(f"  = {path.name[:58]}: менять нечего")
            continue
        total += len(changed)
        print(f"  * {path.name[:58]}")
        for name, before in changed:
            print(f"      {name}: {before[0]}x{before[1]} -> {args.size}x{args.size}")

        if args.check or blob is None:
            continue

        # бэкап оригинала, если его ещё нет
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

    if args.check:
        print(f"\nшрифтов к правке: {total}")
    else:
        print(f"\nизменено шрифтов: {total}")
        if args.install:
            print("Запусти игру и проверь тот же алфавит.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
