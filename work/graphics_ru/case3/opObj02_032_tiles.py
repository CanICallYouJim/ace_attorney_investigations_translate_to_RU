"""Кадры анимации рук в атласе заставки opObj02_032_256 (9 октября 2026): текст под руками — с русского логотипа.

Атлас хранит, кроме логотипа, четыре плитки 135×156 (x 1440–1980, y 24–180): руки персонажей
в двух позах вместе с куском надписи «Samson … Judy's» за ними. Плитка = кусок логотипа + своя рука.
Где плитка совпадает с английским логотипом (то же место, `сдвиг`), берётся русский логотип;
где отличается (другая поза руки) — остаётся плитка. Запуск после paste_art.py:

    .venv\Scripts\python.exe work\graphics_ru\case3\opObj02_032_tiles.py <русский атлас.png>
"""
import sys
import numpy as np
from PIL import Image

EN = "work/graphics_en/case3/opObj02_032_256.png"
TILES = [((1440, 24, 1575, 180), (-1080, 135)), ((1575, 24, 1710, 180), (-630, 135)),
         ((1710, 24, 1845, 180), (-1350, 135)), ((1845, 24, 1980, 180), (-900, 135))]
TOL = 12

path = sys.argv[1]
en = np.asarray(Image.open(EN).convert("RGBA")).astype(int)
ru = np.asarray(Image.open(path).convert("RGBA")).astype(int)
out = ru.copy()
for (x0, y0, x1, y1), (dx, dy) in TILES:
    t_en = en[y0:y1, x0:x1]
    l_en = en[y0 + dy:y1 + dy, x0 + dx:x1 + dx]
    l_ru = ru[y0 + dy:y1 + dy, x0 + dx:x1 + dx]
    same = (np.abs(t_en[..., :3] - l_en[..., :3]).max(-1) <= TOL) & (t_en[..., 3] > 0)
    tile = out[y0:y1, x0:x1]
    tile[same, :3] = l_ru[same, :3]
    print((x0, y0), "из русского логотипа:", int(same.sum()), "из", (x1 - x0) * (y1 - y0))
Image.fromarray(out.astype(np.uint8), "RGBA").save(path)
