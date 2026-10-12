"""cut01_009: ножка «Р» под хоботом — кусок ножки «К» той же строки, сдвинутый влево (замечание «р дорисуй ножку», 13 октября).
Слон остаётся спереди: пишется только туда, где сейчас ровный фон вывески, кант или тело буквы."""
import sys, numpy as np
from PIL import Image
from scipy import ndimage as nd
src, dst, DX, Y0, Y1 = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
P = np.asarray(Image.open(src).convert('RGB')).astype(float)
KX0, KX1 = 905, 957                                   # ножка «К» с кантами
patch = P[Y0:Y1, KX0:KX1]
reg = P[Y0:Y1, KX0 + DX:KX1 + DX]
L = reg.mean(-1)
sd = nd.generic_filter(L, np.std, size=5)
ok = (sd < 9) | (np.abs(reg - patch).max(-1) < 20)    # ровное (фон/кант/тело), не слон с его линиями
EN = np.asarray(Image.open('work/graphics_en/case2/cut01_009.png').convert('RGB')).astype(float)[Y0:Y1, KX0 + DX:KX1 + DX]
fg = (np.abs(EN - reg).max(-1) < 8) & (np.abs(reg.mean(-1) - 146) > 12)   # слон и клыки — те же пиксели, что в оригинале
fg = nd.binary_dilation(nd.binary_opening(fg, iterations=1), iterations=2)
ok &= ~fg
ok = nd.binary_opening(ok, iterations=1)
lb, n = nd.label(ok); sz = nd.sum(ok, lb, range(1, n + 1)); ok = np.isin(lb, np.where(sz > 300)[0] + 1)
a = np.clip(nd.gaussian_filter(ok.astype(float), 0.8), 0, 1) * ok
ramp = np.ones(L.shape); ramp[:6] = np.linspace(0, 1, 6)[:, None]; ramp[-8:] = np.linspace(1, 0, 8)[:, None]
a = (a * ramp)[..., None]
P[Y0:Y1, KX0 + DX:KX1 + DX] = reg * (1 - a) + patch * a
Image.fromarray(np.clip(P + 0.5, 0, 255).astype(np.uint8)).save(dst)
