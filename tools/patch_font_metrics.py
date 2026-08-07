"""Сделать кириллицу пропорциональной: убрать разрядку в окне реплик.

Симптом. Русский текст в игре идёт вразрядку, «С к о л ь к о  о н и», хотя латиница
набрана плотно. Это не настройка интервала, а ширина самих глифов: гарнитуры японские
(Adobe-Japan1, CID-keyed CFF), и кириллица в них нарисована **полноширинной** — каждая
буква занимает целую кегельную площадку в 1000 единиц, независимо от того, `Ж` это
или `о`. Так набирают японский, вперемешку с кандзи это правильно, для русского — нет.

    буква   очертания   ширина места   отступы
    H       814         858            22 + 22     латиница, норма
    о       554         1000           223 + 223   кириллица, полная ширина

Что делает. Для каждой кириллической буквы: очертания сдвигаются влево к нормальному
боковому отступу, ширина места ставится «очертания + два отступа». Сами формы букв
не трогаются, меняются только метрики. Норма отступа взята из латиницы этих же
гарнитур — там медиана 22 единицы на сторону, и по 14 буквам, которые совпадают
очертаниями с латинскими (А≡A, Н≡H, Е≡E), видно ту же величину.

Игра кириллицей не пользуется, так что портить нечего: все её собственные тексты
набраны латиницей и иероглифами, у которых полная ширина как раз нужна.

Правится GK12_Data/data.unity3d — копии гарнитур в бандлах игра не читает.
Ставить после tools/patch_font_cmap.py: тот раздаёт коды-носители, этот чинит метрики,
порядок между ними не важен, но оба нужны.

    python tools/patch_font_metrics.py --check      # что будет сделано
    python tools/patch_font_metrics.py --install    # починить и поставить в игру
    python tools/patch_font_metrics.py --sidebearing 30 --install   # пошире
"""
from __future__ import annotations

import argparse
import shutil
import sys
from io import BytesIO

import UnityPy
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

from common import BACKUP, GAME, WORK, game_is_running, load_json, save_json, sha256
from patch_font_cmap import LATIN_FONTS

MANIFEST = BACKUP / "manifest.json"
STAGE = WORK / "build"
MAIN_DATA = GAME / "GK12_Data" / "data.unity3d"

# Вся кириллица, включая Ё и ё — они лежат отдельно от основного блока.
CYRILLIC = list(range(0x0410, 0x0450)) + [0x0401, 0x0451]

# Боковой отступ по умолчанию: медиана латиницы этих гарнитур.
DEFAULT_SIDEBEARING = 22


class MetricsError(RuntimeError):
    """Гарнитуру не удалось перебрать — пропускаем её, остальные не роняем."""


def register_backup(path) -> None:
    manifest = load_json(MANIFEST, default={}) or {}
    key = f"font_{path.name.split('_assets_all_')[0]}"
    if key in manifest:
        return
    manifest[key] = {"file": path.name, "source": str(path), "sha256": sha256(BACKUP / path.name)}
    save_json(MANIFEST, manifest)


def plan_for(font: TTFont, sidebearing: int) -> dict[str, tuple[int, int]]:
    """Что менять: глиф -> (новая ширина места, сдвиг очертаний по x).

    Берём только те буквы, что сейчас полноширинные: если гарнитура уже
    пропорциональная (LiberationSans), трогать нечего.
    """
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    upm = font["head"].unitsPerEm
    glyphs = font.getGlyphSet()

    plan: dict[str, tuple[int, int]] = {}
    for code in CYRILLIC:
        name = cmap.get(code)
        if name is None or hmtx[name][0] != upm:
            continue
        pen = BoundsPen(glyphs)
        glyphs[name].draw(pen)
        if pen.bounds is None:      # пустой глиф, например пробел
            continue
        x_min, _, x_max, _ = pen.bounds
        ink = x_max - x_min
        plan[name] = (round(ink) + 2 * sidebearing, round(sidebearing - x_min))
    return plan


def retype(blob: bytes, sidebearing: int) -> tuple[bytes, int, tuple[int, int]]:
    """Перебрать метрики кириллицы. Возвращает (байты, сколько букв, было/стало в среднем)."""
    font = TTFont(BytesIO(blob), fontNumber=0)
    plan = plan_for(font, sidebearing)
    if not plan:
        # Кириллица уже пропорциональная — так у LiberationSans, он не японский.
        return blob, 0, (0, 0)
    if "CFF " not in font:
        raise MetricsError("полноширинная кириллица в не-CFF гарнитуре — путь не написан")

    cff = font["CFF "].cff
    charstrings = cff[cff.fontNames[0]].CharStrings
    glyphs = font.getGlyphSet()
    hmtx = font["hmtx"]

    was = sum(hmtx[n][0] for n in plan) // len(plan)
    for name, (advance, dx) in plan.items():
        old = charstrings[name]
        old.decompile()
        pen = T2CharStringPen(advance, glyphs)
        glyphs[name].draw(TransformPen(pen, (1, 0, 0, 1, dx, 0)))
        charstrings[name] = pen.getCharString(private=old.private,
                                              globalSubrs=old.globalSubrs)
        hmtx[name] = (advance, sidebearing)
    became = sum(adv for adv, _ in plan.values()) // len(plan)

    buf = BytesIO()
    font.save(buf)
    return buf.getvalue(), len(plan), (was, became)


def check_result(blob: bytes, sidebearing: int) -> list[str]:
    """Перечитать собранный шрифт и убедиться, что очертания на месте, а метрики новые."""
    font = TTFont(BytesIO(blob), fontNumber=0)
    cmap, hmtx, glyphs = font.getBestCmap(), font["hmtx"], font.getGlyphSet()
    upm = font["head"].unitsPerEm
    bad = []
    for code in CYRILLIC:
        name = cmap.get(code)
        if name is None:
            continue
        pen = BoundsPen(glyphs)
        glyphs[name].draw(pen)
        if pen.bounds is None:
            bad.append(f"U+{code:04X}: очертания пропали")
            continue
        x_min, _, x_max, _ = pen.bounds
        advance = hmtx[name][0]
        if advance == upm:
            bad.append(f"U+{code:04X}: ширина осталась полной")
        elif abs(x_min - sidebearing) > 1.5:
            bad.append(f"U+{code:04X}: левый отступ {x_min:.0f}, ждали {sidebearing}")
        elif abs(advance - (x_max - x_min) - 2 * sidebearing) > 2:
            bad.append(f"U+{code:04X}: ширина {advance} не сходится с очертаниями")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="только показать, что будет сделано")
    ap.add_argument("--install", action="store_true", help="установить в игру")
    ap.add_argument("--sidebearing", type=int, default=DEFAULT_SIDEBEARING,
                    help=f"боковой отступ в единицах шрифта (по умолчанию {DEFAULT_SIDEBEARING})")
    args = ap.parse_args()

    print(f"боковой отступ: {args.sidebearing} единиц на сторону")
    print(f"гарнитур в правке: {len(LATIN_FONTS)}\n")

    env = UnityPy.load(str(MAIN_DATA))
    changed, failed = [], []
    for obj in env.objects:
        if obj.type.name != "Font":
            continue
        tree = obj.read_typetree()
        name = tree.get("m_Name", "?")
        if name not in LATIN_FONTS:
            continue
        blob = bytes(tree.get("m_FontData") or b"")
        if not blob:
            continue
        try:
            new_blob, count, (was, became) = retype(blob, args.sidebearing)
        except Exception as exc:
            failed.append((name, str(exc)[:70]))
            continue
        if not count:
            print(f"  = {name}: кириллица уже пропорциональная")
            continue
        problems = check_result(new_blob, args.sidebearing)
        if problems:
            failed.append((name, "; ".join(problems[:3])))
            continue
        print(f"  * {name}: букв {count}, ширина места {was} -> {became} "
              f"({100 * became / was - 100:+.0f}%)")
        if not args.check:
            tree["m_FontData"] = list(new_blob)
            obj.save_typetree(tree)
            changed.append(name)

    for name, why in failed:
        print(f"  ! {name}: пропущена ({why})", file=sys.stderr)
    if args.check or not changed:
        return 1 if failed else 0

    backup = BACKUP / MAIN_DATA.name
    if not backup.exists():
        BACKUP.mkdir(parents=True, exist_ok=True)
        shutil.copy2(MAIN_DATA, backup)
    register_backup(MAIN_DATA)

    out = STAGE / MAIN_DATA.name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(env.file.save(packer="lz4"))
    print(f"\nсобран: {out.stat().st_size:,} байт")

    if args.install:
        if game_is_running():
            print("\nGK12.exe запущен — закрой игру.", file=sys.stderr)
            return 1
        shutil.copy2(out, MAIN_DATA)
        print(f"установлен, sha={sha256(MAIN_DATA)[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
