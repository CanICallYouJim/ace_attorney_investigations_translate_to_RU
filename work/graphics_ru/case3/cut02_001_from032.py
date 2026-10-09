"""Вывеска шоу cut02_001 (проба 6, 9 октября 2026): логотип и лента — с принятой cut02_032.

Замер: задник cut02_001 — тот же рисунок, что cut02_032, на том же месте (SIFT по английским,
128 опорных: гомография — единичная, невязка меньше 0,3 px). Перед ним стоят персонажи (венчик,
руки, причёска, платье), и свет другой: cut02_001 ≈ cut02_032 × 1,08 + 4 по каналам (точнее — кривой по каналам),
плюс пологая поправка до ±4 уровней (по краям темнее). Поэтому логотип не рисуется заново,
а переносится с принятой русской cut02_032 — срез верхним краем кадра, размер и буквы те же
(замечание пользователя: у английского половина высоты букв срезана, у нейросети слово целиком).

Где перед вывеской персонаж, остаётся английский кадр; на краю персонажа пиксель — смесь
персонажа и вывески, и русская вывеска подмешивается с долей фона (матирование по известному
фону — английской cut02_032 при свете cut02_001). Запуск:

    .venv\\Scripts\\python.exe work\\graphics_ru\\case3\\cut02_001_from032.py <выход.png>
"""
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, distance_transform_edt, gaussian_filter, label

RAW = Image.open("work/graphics_en/case3/cut02_001.png")
E1 = np.asarray(RAW.convert("RGB")).astype(float)
E2 = np.asarray(Image.open("work/graphics_en/case3/cut02_032.png").convert("RGB")).astype(float)
R2 = np.asarray(Image.open("work/graphics_ru/case3/cut02_032.png").convert("RGB")).astype(float)
Y0, Y1, X0, X1 = 0, 340, 450, 1500     # рамка вывески: всё, где русская cut02_032 отличается
RESID = 12                              # невязка света, выше — перед вывеской что-то стоит
SPECK = 40                              # куски меньше — шум сжатия, а не персонаж
EDGE = 1                                # ширина края персонажа, где пиксель — смесь (шире — контур
                                        # руки считался смесью кожи с вывеской и выцветал)
BIG = 5000                              # островок вывески больше — сама вывеска, не просвет
ISLAND = 6                              # медиана невязки просвета; выше — причёска
GAP = 60                                # островок меньше — черта лица или пряди, а не просвет (брови)

a1, a2, r2 = E1[Y0:Y1, X0:X1], E2[Y0:Y1, X0:X1], R2[Y0:Y1, X0:X1]

# свет: линейно по каналам на пикселях вывески, итерациями без персонажей
bg = np.ones(a1.shape[:2], bool)
for _ in range(10):
    k = [np.linalg.lstsq(np.vstack([a2[..., c][bg], np.ones(bg.sum())]).T, a1[..., c][bg], rcond=None)[0]
         for c in range(3)]
    pred = np.stack([a2[..., c] * k[c][0] + k[c][1] for c in range(3)], -1)
    bg = np.abs(a1 - pred).max(-1) < RESID
# свет точнее прямой: кривая по каналам (медиана cut02_001 при каждом уровне cut02_032 на пикселях
# вывески) — прямая оставляла невязку до 10 уровней в форме английских букв: светлое переносится
# иначе, чем тёмное (независимый просмотр 9 октября)
lut = []
for c in range(3):
    v = a2[..., c][bg].astype(int)
    t = a1[..., c][bg]
    curve = k[c][0] * np.arange(256) + k[c][1]
    for lv in range(256):
        sel = t[v == lv]
        if sel.size >= 20:
            curve[lv] = np.median(sel)
    curve = np.maximum.accumulate(gaussian_filter(curve, 2))
    lut.append(curve)


def light(img):
    return np.stack([lut[c][np.clip(np.round(img[..., c]), 0, 255).astype(int)] for c in range(3)], -1)


pred = light(a2)
# пологая поправка: средняя невязка по вывеске, σ 30 px (по краям кадр темнее)
corr = np.zeros_like(pred)
den = gaussian_filter(bg.astype(float), 30)
for c in range(3):
    num = gaussian_filter((a1[..., c] - pred[..., c]) * bg, 30)
    corr[..., c] = np.where(den > 1e-3, num / np.maximum(den, 1e-3), 0)
pred += corr
fg = np.abs(a1 - pred).max(-1) >= RESID

# крапины: мелкие куски «персонажа» на краях букв — шум сжатия
lab, n = label(fg)
sizes = np.bincount(lab.ravel())
fg &= sizes[lab] >= SPECK
# островки «вывески» внутри персонажа: настоящий просвет (между прутьями венчика) совпадает
# с вывеской почти точно, а тёмные пряди причёски на тёмных английских буквах ленты — на грани
# допуска; такие островки — причёска (иначе по ней жёлтые пятна русской ленты)
resid = np.abs(a1 - pred).max(-1)
lab, n = label(~fg)
sizes = np.bincount(lab.ravel())
for i in range(1, n + 1):
    if sizes[i] < GAP or (sizes[i] < BIG and np.median(resid[lab == i]) > ISLAND):
        fg[lab == i] = True

# доля фона: 1 на вывеске, 0 в глубине персонажа, на краю — проекция на «цвет персонажа»
beta = (~fg).astype(float)
depth, (iy, ix) = distance_transform_edt(fg, return_indices=True)
deep = depth > EDGE
_, (dy, dx) = distance_transform_edt(~deep, return_indices=True)
edge = fg & ~deep
F = a1[dy, dx]                         # цвет ближайшего пикселя персонажа в глубине
d_px = a1 - pred
d_fb = F - pred
alpha = np.clip((d_px * d_fb).sum(-1) / np.maximum((d_fb ** 2).sum(-1), 1.0), 0, 1)
beta[edge] = 1 - alpha[edge]

# русская cut02_032 при свете cut02_001. На вывеске — она сама (а не «английский кадр + разница»:
# так тянулась невязка света в форме английских букв); на краю персонажа — английский пиксель,
# где доля фона заменена на русскую
ru_lit = light(r2) + corr
changed = binary_dilation(np.abs(r2 - a2).max(-1) > 0, iterations=1)
mix = np.where((beta >= 1)[..., None], ru_lit, a1 + beta[..., None] * (ru_lit - pred))
out = E1.copy()
sub = out[Y0:Y1, X0:X1]
sub[changed] = np.clip(mix, 0, 255)[changed]
print("свет:", [f"{lut[c][0]:.0f}..{lut[c][128]:.0f}..{lut[c][255]:.0f}" for c in range(3)],
      "персонаж:", int(fg.sum()), "край:", int(edge.sum()), "перенесено:", int(changed.sum()))
res = Image.fromarray(np.round(out).astype(np.uint8))
if RAW.mode == "RGBA":
    res.putalpha(RAW.getchannel("A"))
res.save(sys.argv[1])
