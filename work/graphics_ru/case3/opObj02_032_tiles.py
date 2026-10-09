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

# Руки на самом логотипе — английские до пикселя (9 октября 2026, по независимому просмотру):
# нейросеть перерисовала их чуть иначе, и там, где плитка с другой позой руки открывает место
# старой руки, оставалось белое пятно в форме руки поверх тёмного рукава. Рука — светлая
# заливка (248,224,160) с тёмным контуром: маска заливки, раздутая на контур.
from scipy.ndimage import binary_dilation
skin = (np.abs(en[..., :3] - np.array([250, 226, 164])).max(-1) <= 14) & (en[..., 3] > 0)
hands = np.zeros(skin.shape, bool)
for (x0, y0, x1, y1), (dx, dy) in TILES:
    hands[y0 + dy:y1 + dy, x0 + dx:x1 + dx] = True
hands &= binary_dilation(skin, iterations=7)
ru[hands] = en[hands]
print("рук на логотипе возвращено из английского:", int(hands.sum()), "пикс.")

out = ru.copy()
for (x0, y0, x1, y1), (dx, dy) in TILES:
    t_en = en[y0:y1, x0:x1]
    l_en = en[y0 + dy:y1 + dy, x0 + dx:x1 + dx]
    l_ru = ru[y0 + dy:y1 + dy, x0 + dx:x1 + dx]
    same = (np.abs(t_en[..., :3] - l_en[..., :3]).max(-1) <= TOL) & (t_en[..., 3] > 0)
    tile = out[y0:y1, x0:x1]
    tile[same, :3] = l_ru[same, :3]
    # белый фон плитки — английский: белый нейросети на 5–10 уровней другой, и по краю старой
    # руки проступал её призрачный контур
    white = (t_en[..., :3].min(-1) >= 236) & (tile[..., :3].min(-1) >= 220)
    tile[white, :3] = t_en[white, :3]
    print((x0, y0), "из русского логотипа:", int(same.sum()), "из", (x1 - x0) * (y1 - y0))
Image.fromarray(out.astype(np.uint8), "RGBA").save(path)
