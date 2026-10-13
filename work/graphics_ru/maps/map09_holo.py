"""map09_02/03 — двор под зелёной голограммой: русская табличка и дверь переносом разницы.

Обычные кадры map09_00/01 собирает paste_art.py (плашка с принятой cut01_01f, ×1,25).
На зелёных кадрах поверх двора лежат полосы голограммы, и линейная подгонка цвета всей
вырезки даёт остаток 16 из 255 (14 октября 2026). Поэтому сюда идёт не рисунок, а только
разница «русская map09_00 минус английская map09_00», пересчитанная в зелёный тон
таблицей цветов по месту надписи (каждому обычному цвету — средний зелёный тех же
пикселей; линейная подгонка давала чёрные буквы вместо тёмно-зелёных и призрак
«Power Room» на двери), и прибавленная к английской зелёной: полосы голограммы
остаются оригинальными.
Кадры совпадают попиксельно (SIFT: оба = cut01_01f ×1,25 + (0, 90)).

    .venv\\Scripts\\python.exe work\\graphics_ru\\maps\\map09_holo.py
"""
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[3]
EN = ROOT / "work" / "graphics_en" / "maps"
RU = ROOT / "work" / "graphics_ru" / "maps"
ZONES = {"табличка": (270, 500, 450, 760), "дверь": (1390, 260, 1545, 340)}   # x0, y0, x1, y1


def rgb(path: Path) -> np.ndarray:
    return np.array(Image.open(path).convert("RGB")).astype(float)


def colour_map(nat: np.ndarray, green: np.ndarray, step: int = 8):
    """Таблица «обычный цвет → зелёный» по парам пикселей одной зоны; пустые ячейки — ближайшая."""
    keys = (nat // step).astype(int)
    flat = keys[:, 0] * 4096 + keys[:, 1] * 64 + keys[:, 2]
    uniq, inv = np.unique(flat, return_inverse=True)
    sums = np.zeros((len(uniq), 3))
    np.add.at(sums, inv, green)
    means = sums / np.bincount(inv)[:, None]
    centres = np.stack([uniq // 4096, uniq // 64 % 64, uniq % 64], 1) * step + step / 2
    tree = cKDTree(centres)
    return lambda q: means[tree.query(q)[1]]


def main() -> None:
    nat_en, nat_ru = rgb(EN / "map09_00.png"), rgb(RU / "map09_00.png")
    for name in ("map09_02", "map09_03"):
        src = Image.open(EN / f"{name}.png").convert("RGBA")
        green = np.array(src.convert("RGB")).astype(float)
        out = green.copy()
        for zone, (x0, y0, x1, y1) in ZONES.items():
            a = nat_en[y0:y1, x0:x1].reshape(-1, 3)
            b = green[y0:y1, x0:x1].reshape(-1, 3)
            to_green = colour_map(a, b)
            ru, en = nat_ru[y0:y1, x0:x1], nat_en[y0:y1, x0:x1]
            moved = np.abs(ru - en).max(2) > 8
            add = to_green(ru[moved]) - to_green(en[moved])
            patch = out[y0:y1, x0:x1]
            patch[moved] = np.clip(green[y0:y1, x0:x1][moved] + add, 0, 255)
            print(f"  {name} {zone}: пикселей {int(moved.sum())}")
        img = Image.fromarray(np.round(out).astype(np.uint8), "RGB").convert("RGBA")
        img.putalpha(src.getchannel("A"))
        img.save(RU / f"{name}.png")
        print(f"  {name} -> {RU / (name + '.png')}")


if __name__ == "__main__":
    main()
