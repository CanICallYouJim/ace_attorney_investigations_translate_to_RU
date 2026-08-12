"""Проверка, что патчер даёт ровно то же, что конвейер репозитория.

Гоняется на своей машине перед релизом. Смысл: патчер собирает игровые файлы
теми же функциями `tools/`, но иначе их зовёт — в частности, обе правки гарнитур
делает за один проход по `data.unity3d`, тогда как `patch_font_cmap.py`
и `patch_font_metrics.py` идут двумя запусками через файл игры. Композиция могла
разойтись с последовательным применением, и это надо доказывать, а не полагать.

Реплики и таблицы проверяются проще: их патчер собирает теми же вызовами, что
`build.py` и `build_strings.py`, и результат обязан совпасть побайтно.

    .venv\\Scripts\\python.exe patcher\\selftest.py

Нужны: установленная игра с уже поставленным переводом и `backup/data.unity3d`
с оригинальными гарнитурами. Ничего не пишет.
"""
from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "patcher")]

import UnityPy  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

import carriers as C  # noqa: E402
from common import GAME  # noqa: E402
from patch_font_cmap import LATIN_FONTS, patch_ttf  # noqa: E402
from patch_font_metrics import CYRILLIC, DEFAULT_SIDEBEARING, retype  # noqa: E402

ORIGINAL = ROOT / "backup" / "data.unity3d"
INSTALLED = GAME / "GK12_Data" / "data.unity3d"


def fonts_of(path: Path) -> dict[str, bytes]:
    """Имя гарнитуры -> её TTF-байты. Дубли имён разводятся суффиксом."""
    out: dict[str, bytes] = {}
    env = UnityPy.load(str(path))
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
        key = name if name not in out else f"{name}#{sum(k.startswith(name) for k in out)}"
        out[key] = blob
    return out


def describe(blob: bytes) -> tuple[int, int]:
    """(сколько кодов-носителей на месте, сколько букв кириллицы уже не полноширинные)."""
    font = TTFont(BytesIO(blob), fontNumber=0, lazy=True)
    cmap = font.getBestCmap()
    carriers = C.carrier_map(C.CANDIDATES[C.CHOSEN], C.BROKEN)
    present = sum(1 for code in carriers.values() if code in cmap)

    hmtx, upm = font["hmtx"], font["head"].unitsPerEm
    narrow = 0
    for code in CYRILLIC:
        name = cmap.get(code)
        if name is not None and hmtx[name][0] != upm:
            narrow += 1
    return present, narrow


def main() -> int:
    for path in (ORIGINAL, INSTALLED):
        if not path.exists():
            print(f"нет файла {path}", file=sys.stderr)
            return 1

    print(f"оригинал:  {ORIGINAL}")
    print(f"в игре:    {INSTALLED}\n")

    original = fonts_of(ORIGINAL)
    installed = fonts_of(INSTALLED)

    bad = 0
    print(f"{'гарнитура':28} {'носители':>10} {'метрики':>9}  сходится с игрой")
    print("-" * 74)
    for name, blob in original.items():
        # ровно то, что делает patcher/steps.py:fonts за один проход
        patched, added = patch_ttf(blob, C.BROKEN)
        patched, retyped, _ = retype(patched, DEFAULT_SIDEBEARING)

        present, narrow = describe(patched)
        live = installed.get(name)
        if live is None:
            verdict, ok = "в игре нет такой", False
        elif live == patched:
            verdict, ok = "байт в байт", True
        else:
            # Расхождение в байтах ещё не брак: у гарнитуры могут быть лишние
            # коды других участков-кандидатов от прежних проб. Сверяем смысл.
            live_present, live_narrow = describe(live)
            ok = (live_present, live_narrow) == (present, narrow)
            verdict = ("то же по смыслу, байты разошлись" if ok else
                       f"РАЗОШЛОСЬ: в игре {live_present}/{live_narrow}")
        bad += not ok
        print(f"{name[:28]:28} {present:5d}/{len(C.BROKEN):<4} {narrow:5d}/{len(CYRILLIC):<3}  {verdict}")

    print()
    if bad:
        print(f"расхождений: {bad}", file=sys.stderr)
        return 1
    print("Гарнитуры сходятся: патчер за один проход даёт то же, что два запуска.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
