"""map0b: ледяные панели «Кастор и Поллукс» / «Плеяды» (13 октября 2026).
Подложка — поэлементный минимум семи языковых вариантов (текст белый, у каждого языка свои буквы),
набор — Segoe UI Bold, сжатие по ширине английской строки, белый со слабой каймой r=1 как у английского."""
import sys, numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as nd
D = sys.argv[1]                      # папка с выгрузкой map0b_<язык>.png
OUT = sys.argv[2]
LANGS = ['eng', 'ger', 'fre', 'kor', 'sim', 'tra', '']
A = np.stack([np.asarray(Image.open(f'{D}/map0b{"_" + l if l else ""}.png').convert('RGB')).astype(float) for l in LANGS])
EN = A[0]; BG = A.min(0)
ZONES = [(148, 812, 345, 970), (1998, 812, 2180, 912)]
txt = np.zeros(EN.shape[:2], bool)
for a in A: txt |= (a.mean(-1) - BG.mean(-1)) > 25
txt = nd.binary_dilation(txt, iterations=2)
zone = np.zeros_like(txt)
for x0, y0, x1, y1 in ZONES: zone[y0:y1, x0:x1] = True
txt &= zone
# остаточные белые точки в подложке (где все языки писали) — медиана соседей
med = nd.median_filter(BG, size=(7, 7, 1))
spot = txt & ((BG.mean(-1) - med.mean(-1)) > 12)
BG[spot] = med[spot]
out = EN.copy(); out[txt] = BG[txt]
K = 4; COND = 167 / 211          # тело: ширина английской строки / Segoe UI Bold 13; заголовок — без сжатия (130/123)
FT = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 15 * K)
FB = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 13 * K)
def line(text, font, x, base, maxw=None):
    w = font.getbbox(text)[2] + 20; h = 30 * K
    im = Image.new('L', (w, h), 0); ImageDraw.Draw(im).text((0, h - 8 * K), text, font=font, fill=255, anchor='ls')
    a = np.asarray(im).astype(np.float32) / 255
    cond = 1.0 if font is FT else COND
    ww = int(round(w * cond / K)); hh = h // K
    if maxw and np.where(a.max(0) > 0)[0].max() * cond / K > maxw: cond *= maxw / (np.where(a.max(0) > 0)[0].max() * cond / K)
    ww = int(round(w * cond / K))
    a = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).resize((ww, hh), Image.LANCZOS)).astype(float) / 255
    y0 = base - (hh - 8)
    return a, x, y0
alpha = np.zeros(EN.shape[:2])
def put(a, x, y):
    h, w = a.shape; alpha[y:y + h, x:x + w] = np.maximum(alpha[y:y + h, x:x + w], a)
L = [("Кастор и Поллукс", FT, 155, 830),
     ("Каждый год в декабре из этого", FB, 155, 856), ("созвездия видны бессчётные", FB, 155, 872), ("падающие звёзды.", FB, 155, 888),
     ("Кастор и Поллукс — два брата,", FB, 155, 915), ("которые так любили друг друга,", FB, 155, 931), ("что после смерти стали звёздами.", FB, 155, 947),
     ("Плеяды", FT, 2004, 830),
     ("Группа из семи звёзд", FB, 2004, 867), ("в созвездии Тельца.", FB, 2004, 883), ("Её ещё называют «Субару».", FB, 2004, 898)]
for t, f, x, b in L:
    a, x, y = line(t, f, x, b, maxw=(186 if x < 1000 else 170)); put(a, x, y)
glow = np.clip(nd.gaussian_filter(alpha, 0.8) * 0.12, 0, 1)
col = np.array([243, 249, 252.])
o = out * (1 - glow[..., None]) + np.minimum(out + 30, 255) * glow[..., None]
o = o * (1 - alpha[..., None]) + col * alpha[..., None]
Image.fromarray(np.clip(o + 0.5, 0, 255).astype(np.uint8)).save(OUT)
print('готово', OUT)
