"""Лист приёмки картинки: оригинал | результат | где менялось, и зона надписи крупно.

Один инструмент на все картинки (курс от 23 сентября 2026): качество судит
пользователь глазом по этому листу, машина только показывает. Эталон —
английский кадр из `work/graphics_en/` (его равенство нетронутому бандлу
сторожит `check_etalon.py`), результат — `work/graphics_ru/<дело>/<имя>.png`.

    .venv\\Scripts\\python.exe tools\\sheet.py cut02_037
    .venv\\Scripts\\python.exe tools\\sheet.py cut02_037 --zoom 3 --pad 24

Сверху — оба кадра целиком и карта разницы: красное — пиксель изменён
больше чем на `--tol` уровней. Ниже — каждая зона правки (связные куски
изменённого, слитые с запасом `--pad`) крупно, оригинал слева, результат
справа. Лист — `work/graphics_masks/checks/<имя>_лист.png`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
EN = ROOT / "work" / "graphics_en"
RU = ROOT / "work" / "graphics_ru"
OUT = ROOT / "work" / "graphics_masks" / "checks"
PANEL = 900          # ширина панели целого кадра
ZONE_W = 1800        # ширина строки зон крупно


def find(folder: Path, name: str) -> Path | None:
    hits = sorted(folder.glob(f"*/{name}.png"))
    return hits[0] if hits else None


def font(size: int):
    for f in ("arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def changed_mask(a: Image.Image, b: Image.Image, tol: int) -> Image.Image:
    d = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
    r, g, bl = d.split()
    m = ImageChops.lighter(ImageChops.lighter(r, g), bl)
    return m.point(lambda v: 255 if v > tol else 0)


def zones(mask: Image.Image, pad: int) -> list[tuple[int, int, int, int]]:
    """Прямоугольники правки: маска раздувается на pad, куски — по связности."""
    grown = mask.filter(ImageFilter.MaxFilter(2 * (pad // 2) + 1)) if pad else mask
    w, h = grown.size
    px = grown.load()
    seen = bytearray(w * h)
    boxes = []
    for y in range(h):
        for x in range(w):
            if px[x, y] and not seen[y * w + x]:
                stack = [(x, y)]
                seen[y * w + x] = 1
                x0 = x1 = x
                y0 = y1 = y
                while stack:
                    cx, cy = stack.pop()
                    x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if 0 <= nx < w and 0 <= ny < h and px[nx, ny] and not seen[ny * w + nx]:
                            seen[ny * w + nx] = 1
                            stack.append((nx, ny))
                boxes.append((max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad + 1), min(h, y1 + pad + 1)))
    return sorted(boxes, key=lambda b: (b[1], b[0]))


def fit(im: Image.Image, width: int) -> Image.Image:
    k = width / im.width
    return im.resize((width, max(1, round(im.height * k))), Image.LANCZOS)


def build(name: str, tol: int, pad: int, zoom: float) -> Path:
    en_path, ru_path = find(EN, name), find(RU, name)
    if not en_path or not ru_path:
        sys.exit(f"нет пары для {name}: эталон {en_path}, результат {ru_path}")
    en = Image.open(en_path).convert("RGB")
    ru = Image.open(ru_path).convert("RGB")
    if en.size != ru.size:
        sys.exit(f"размеры разные: {en.size} против {ru.size}")
    mask = changed_mask(en, ru, tol)
    n = sum(1 for v in mask.tobytes() if v)
    if n == 0:
        sys.exit(f"{name}: результат совпадает с оригиналом — показывать нечего")

    diff = Image.blend(en, Image.new("RGB", en.size, (255, 255, 255)), 0.6)
    diff.paste((220, 0, 0), mask=mask)
    top = [fit(im, PANEL) for im in (en, ru, diff)]

    rows = []
    for box in zones(mask, pad):
        a, b = en.crop(box), ru.crop(box)
        k = min(zoom, (ZONE_W / 2 - 10) / a.width)
        size = (max(1, round(a.width * k)), max(1, round(a.height * k)))
        rows.append((box, a.resize(size, Image.NEAREST), b.resize(size, Image.NEAREST)))

    f, fs = font(28), font(20)
    W = max(PANEL * 3 + 40, ZONE_W)
    H = 60 + top[0].height + 40 + sum(r[1].height + 50 for r in rows)
    sheet = Image.new("RGB", (W, H), (40, 40, 40))
    d = ImageDraw.Draw(sheet)
    d.text((10, 10), f"{name}: оригинал | результат | где менялось (> {tol} уровней, {n} пикс.)",
           fill="white", font=f)
    for i, im in enumerate(top):
        sheet.paste(im, (10 + i * (PANEL + 10), 60))
    y = 60 + top[0].height + 40
    for box, a, b in rows:
        d.text((10, y), f"зона {box}  ×{a.width / (box[2] - box[0]):.1f}   слева оригинал, справа результат",
               fill="white", font=fs)
        y += 30
        sheet.paste(a, (10, y))
        sheet.paste(b, (20 + a.width, y))
        y += a.height + 20
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}_лист.png"
    sheet.save(path)
    print(f"{name}: изменено {n} пикс., зон {len(rows)}; лист {path}")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="+", help="имена картинок, например cut02_037")
    ap.add_argument("--tol", type=int, default=24, help="порог «изменён», уровней (по умолчанию 24)")
    ap.add_argument("--pad", type=int, default=16, help="запас вокруг зоны правки, px")
    ap.add_argument("--zoom", type=float, default=2.0, help="увеличение зон, не больше влезающего")
    args = ap.parse_args()
    for name in args.names:
        build(name, args.tol, args.pad, args.zoom)
    return 0


if __name__ == "__main__":
    sys.exit(main())
