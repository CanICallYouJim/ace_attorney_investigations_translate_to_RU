"""Проверить, сможет ли игра нарисовать кириллицу.

Это ворота всего перевода: если глифов А-Я/а-я взять неоткуда, русский текст
отрисуется квадратами, и до перевода нужно сначала решать вопрос со шрифтом.

Проверка двухступенчатая, потому что TMP умеет два режима атласа:

  m_AtlasPopulationMode = 0 (Static)  — глифы запечены заранее, набор символов
      зафиксирован в m_CharacterTable. Чего там нет, того не будет.
  m_AtlasPopulationMode = 1 (Dynamic) — атлас наполняется в рантайме из встроенного
      файла гарнитуры. Тогда важна не таблица символов (она пустая), а cmap самого
      шрифта: что покрывает гарнитура, то игра и нарисует.

Поэтому скрипт смотрит и таблицы TMP-ассетов, и cmap встроенных файлов шрифтов.

    python tools/find_fonts.py
"""
from __future__ import annotations

import sys

import UnityPy

from common import BUNDLES

CYRILLIC = [(0x0410, 0x044F, "А-я основной"), (0x0401, 0x0401, "Ё"), (0x0451, 0x0451, "ё")]
ASCII_SAMPLE = (0x41, 0x5A)


def font_assets(path):
    """TMP_FontAsset из бандла: (имя, множество кодов символов в таблице)."""
    env = UnityPy.load(str(path))
    found = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception:
            continue
        if "m_CharacterTable" not in tree:
            continue
        chars = {entry.get("m_Unicode", -1) for entry in tree.get("m_CharacterTable", [])}
        found.append((tree.get("m_Name", "?"), chars, tree))
    return found


def describe(name: str, chars: set[int]) -> str:
    total = len(chars)
    ascii_ok = sum(1 for c in range(*ASCII_SAMPLE) if c in chars)
    parts = [f"{total:>6} символов", f"латиница A-Z: {ascii_ok}/25"]
    for lo, hi, label in CYRILLIC:
        have = sum(1 for c in range(lo, hi + 1) if c in chars)
        need = hi - lo + 1
        parts.append(f"{label}: {have}/{need}")
    return f"  {name:<45} " + "  ".join(parts)


def embedded_fonts(path):
    """Файлы гарнитур, встроенные в бандл: (имя, байты шрифта)."""
    env = UnityPy.load(str(path))
    out = []
    for obj in env.objects:
        if obj.type.name != "Font":
            continue
        data = obj.read()
        blob = getattr(data, "m_FontData", None)
        if blob:
            out.append((data.m_Name, bytes(blob)))
    return out


def cmap_coverage(blob: bytes) -> tuple[set[int], str]:
    from io import BytesIO
    from fontTools.ttLib import TTFont

    font = TTFont(BytesIO(blob), fontNumber=0, lazy=True)
    codes: set[int] = set()
    for table in font["cmap"].tables:
        codes.update(table.cmap.keys())
    name = ""
    for rec in font["name"].names:
        if rec.nameID == 4:
            name = rec.toUnicode()
            break
    font.close()
    return codes, name


def main() -> int:
    bundles = sorted(BUNDLES.glob("*.bundle"), key=lambda p: p.stat().st_size)
    print(f"бандлов к просмотру: {len(bundles)}\n")

    static_cyrillic = dynamic_cyrillic = False
    seen_fonts: set[str] = set()

    for path in bundles:
        try:
            tmp_fonts = font_assets(path)
            raw_fonts = embedded_fonts(path)
        except Exception as exc:
            print(f"  ! {path.name[:60]}: {exc}", file=sys.stderr)
            continue
        if not tmp_fonts and not raw_fonts:
            continue

        print(f"{path.name}")
        for name, chars, tree in tmp_fonts:
            mode = tree.get("m_AtlasPopulationMode")
            kind = "динамический" if mode == 1 else "запечённый"
            print(describe(name, chars) + f"  атлас: {kind}")
            if mode != 1 and all(sum(1 for c in range(lo, hi + 1) if c in chars) == hi - lo + 1
                                 for lo, hi, _ in CYRILLIC):
                static_cyrillic = True

        for name, blob in raw_fonts:
            if name in seen_fonts:
                continue
            seen_fonts.add(name)
            try:
                codes, full_name = cmap_coverage(blob)
            except Exception as exc:
                print(f"    гарнитура {name}: не разобрать ({exc})")
                continue
            print(f"    гарнитура {name!r} ({full_name}, {len(blob):,} байт)")
            print(describe("  -> cmap", codes))
            if all(sum(1 for c in range(lo, hi + 1) if c in codes) == hi - lo + 1
                   for lo, hi, _ in CYRILLIC):
                dynamic_cyrillic = True
        print()

    print("=" * 70)
    if dynamic_cyrillic:
        print("КИРИЛЛИЦА ЕСТЬ в самой гарнитуре, атлас динамический ->")
        print("игра нарисует русский текст без пересборки шрифта.")
    elif static_cyrillic:
        print("КИРИЛЛИЦА ЕСТЬ в запечённом атласе -> нужно лишь указать нужный шрифт.")
    else:
        print("КИРИЛЛИЦЫ НЕТ -> нужен свой шрифт (Unity 2022.3.17f1 + TMP).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
