"""Перенос английского венчика на место венчика нейросети (opObj02_032_256, 12 октября 2026).

Ответ пользователя «2»: взять целый английский венчик и поставить туда, где он стоит у нейросети
(головка была надорвана, дыры в альфе у ручки и шарика). Венчик — маской (синий контур + шарик +
светлая кайма), поворот 3,4° вокруг шарика и сдвиг (+43, +4); «И» с каймой — перед ним, как у нейросети.
Берёт черновик из drafts/hold, пишет пробу в drafts/probe. Запуск:

    .venv\Scripts\python.exe work\graphics_ru\case3\opObj02_032_whisk.py <папка для отладочных картинок/> 3.4 43 4
"""
import sys
import numpy as np, cv2
from PIL import Image
from scipy import ndimage as nd

S = sys.argv[1]
ANG, DX, DY = float(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
EN = 'work/graphics_en/case3/opObj02_032_256.png'
RU = 'work/graphics_masks/drafts/hold/case3/opObj02_032_256.png'
OUT = 'work/graphics_masks/drafts/probe/opObj02_032_256_p1.png'
X0, Y0, X1, Y1 = 1100, 280, 1500, 820          # окно работы
en_full = np.asarray(Image.open(EN).convert('RGBA')).astype(np.float32)
ru_full = np.asarray(Image.open(RU).convert('RGBA')).astype(np.float32)
en = en_full[Y0:Y1, X0:X1]; ru = ru_full[Y0:Y1, X0:X1]
h, w = en.shape[:2]

r, g, b, a = [en[..., i] for i in range(4)]
nv = (b > r + 30) & (b > g + 10) & (a > 200)
lab, n = nd.label(nv); nv = lab == np.argmax(nd.sum(nv, lab, range(1, n + 1))) + 1
head = nd.binary_fill_holes(nd.binary_closing(np.pad(nv, 10), iterations=3))[10:-10, 10:-10]

cx, cy = 1244 - X0, 710 - Y0                    # центр шарика
yy, xx = np.mgrid[:h, :w]
ang = np.arctan2(yy - cy, xx - cx); dist = np.hypot(yy - cy, xx - cx)
NT = 180; rad = np.full(NT, 36.0)
for i, t in enumerate(np.linspace(-np.pi, np.pi, NT, endpoint=False)):
    for r_ in np.arange(10, 40, 0.5):
        py, px = int(round(cy + r_ * np.sin(t))), int(round(cx + r_ * np.cos(t)))
        if en[py, px, :3].min() >= 215 or en[py, px, 3] < 150:
            rad[i] = min(r_, 36); break
idx = ((ang + np.pi) / (2 * np.pi) * NT).astype(int) % NT
ball = dist <= rad[idx]
obj = head | ball
ow = (a > 250) & (en[..., :3].min(-1) < 200)
sil = obj | (nd.binary_dilation(obj, iterations=14) & ~ow)   # кайма — только светлое: чужие куски (буква, край торта) не везём
sil |= dist <= rad[idx] + 11                     # кайма шарика — круг целиком (под ней в оригинале край торта)
sil &= a > 0

M = cv2.getRotationMatrix2D((cx, cy), ANG, 1.0); M[0, 2] += DX; M[1, 2] += DY
pm = en.copy(); pm[..., :3] *= pm[..., 3:4] / 255.; pm *= sil[..., None]
wp = np.clip(cv2.warpAffine(pm, M, (w, h), flags=cv2.INTER_CUBIC), 0, 255)
ys, xs = np.mgrid[:h, :w]; ys = ys + Y0; xs = xs + X0
near = nd.binary_dilation(cv2.warpAffine(sil.astype(np.uint8), M, (w, h), flags=cv2.INTER_NEAREST) > 0, iterations=25)
outside = near & (((ys < 372) & (xs > 1282) & (ru[..., :3].min(-1) >= 170)) | ((ys > 740) & (xs > 1265)) | (xs > 1335))
ru = ru.copy(); ru[outside, 3] = 0
wa = wp[..., 3:4] / 255.; ra = ru[..., 3:4] / 255.
outa = wa + ra * (1 - wa)
outc = wp[..., :3] + ru[..., :3] * ra * (1 - wa)
out = ru.copy(); out[..., 3:4] = outa * 255
nz = outa[..., 0] > 0
out[nz, :3] = outc[nz] / outa[nz]
silw = cv2.warpAffine(sil.astype(np.uint8), M, (w, h), flags=cv2.INTER_NEAREST) > 0
np.save(S + 'silw.npy', silw)
full = ru_full.copy(); full[Y0:Y1, X0:X1] = out
Image.fromarray(np.clip(full + 0.5, 0, 255).astype(np.uint8), 'RGBA').save(OUT)

def on(arr, bg=(0, 160, 0, 255)):
    im = Image.fromarray(np.clip(arr + 0.5, 0, 255).astype(np.uint8), 'RGBA')
    gb = Image.new('RGBA', im.size, bg); gb.alpha_composite(im); return gb
V = Image.new('RGB', (w * 3 + 20, h), 'gray')
for i, arr in enumerate([en, ru, out]): V.paste(on(arr), (i * (w + 10), 0))
V.save(S + 'p1.png')
print('силуэт', int(sil.sum()), 'готово', OUT)

# --- «И» перед венчиком, как у нейросети: буква с каймой из нашего черновика поверх
LX0 = 1150
rr, rg, rb, ra_ = [ru[..., i] for i in range(4)]
yellow = (rr > 200) & (rg > 150) & (rb < 110) & (ra_ > 200)
red = (rr > 170) & (rg < 90) & (rb > 40) & (rb < 140) & (ra_ > 200)
pink = (rr > 200) & (rg > 110) & (rg < 200) & (rb > 130) & (ra_ > 200)
let = yellow | red | pink
let[:, :LX0 - X0] = True                          # левее — заведомо надпись
let[:, 1340 - X0:] = False
let[: 370 - Y0] = False; let[740 - Y0:] = False
lab, n = nd.label(let); keep = lab == lab[500 - Y0, 1200 - X0]
keep = nd.binary_fill_holes(keep)
keep[:, :LX0 - X0] = False
white = (ru[..., :3].min(-1) >= 200) | (ra_ < 250)
ring = nd.binary_dilation(keep, iterations=int(sys.argv[5]) if len(sys.argv) > 5 else 7) & white & ~keep
ring &= (out[..., :3].min(-1) >= 200) | (out[..., 3] < 250)   # кайма буквы — только там, где и под ней светлое
front = keep | ring
ballw = cv2.warpAffine((ball | (nd.binary_dilation(ball, iterations=11) & ~nd.binary_dilation(head, iterations=11) & (a > 0))).astype(np.uint8), M, (w, h), flags=cv2.INTER_NEAREST) > 0
fa = front[..., None].astype(np.float32)
out2 = out * (1 - fa) + ru * fa
full = ru_full.copy(); full[Y0:Y1, X0:X1] = out2
Image.fromarray(np.clip(full + 0.5, 0, 255).astype(np.uint8), 'RGBA').save(OUT)
V = Image.new('RGB', (w * 3 + 20, h), 'gray')
for i, arr in enumerate([en, ru, out2]): V.paste(on(arr), (i * (w + 10), 0))
V.save(S + 'p1.png')
m = np.zeros((h, w, 3), np.uint8); m[front] = [255, 0, 0]; m[silw & ~front] = [0, 0, 255]
Image.fromarray(m).save(S + 'front.png')
print('буква спереди', int(front.sum()))

# --- остатки венчика нейросети вне нового силуэта: светлое сверху/снизу и всё справа — прозрачным
zone = nd.binary_dilation(silw, iterations=25) & ~silw
ys, xs = np.mgrid[:h, :w]; ys = ys + Y0; xs = xs + X0
lite = out2[..., :3].min(-1) >= 170
rem = zone & (out2[..., 3] > 0) & ~front & (((ys < 372) & (xs > 1282) & lite) | ((ys > 725) & (xs > 1265) & lite) | ((ys > 740) & (xs > 1265)) | (xs > 1335))
out2[rem, 3] = 0
full = ru_full.copy(); full[Y0:Y1, X0:X1] = out2
Image.fromarray(np.clip(full + 0.5, 0, 255).astype(np.uint8), 'RGBA').save(OUT)
print('остатков снято', int(rem.sum()))
# дыры в альфе между буквой и ручкой — тёмный шоколад, как под буквами
brown = np.median(ru_full[725:735, 1195:1215, :3].reshape(-1, 3), 0)
op = out2[..., 3] >= 250
enclosed = nd.binary_fill_holes(op) & ~op
gap = (out2[..., 3] < 250) & (nd.binary_dilation(front, iterations=6)) & (nd.binary_dilation(silw, iterations=6))
holes = (enclosed | gap) & nd.binary_dilation(silw, iterations=12)
fillc = np.where((nd.binary_dilation(silw, iterations=3) & holes)[..., None], 255., brown[None, None, :])[holes]
out2[holes, :3] = fillc * (1 - out2[holes, 3:4] / 255.) + out2[holes, :3] * (out2[holes, 3:4] / 255.)
out2[holes, 3] = 255
full = ru_full.copy(); full[Y0:Y1, X0:X1] = out2
Image.fromarray(np.clip(full + 0.5, 0, 255).astype(np.uint8), 'RGBA').save(OUT)
print('дыр залито', int(holes.sum()), 'цвет', brown)
