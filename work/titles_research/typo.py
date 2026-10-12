"""Общий набор: слово шрифтом, наклон, калибровка по немецкому, обводка."""
import numpy as np, pickle
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
FONTS = "C:/Windows/Fonts/"
CRIMSON = (152, 0, 56); OUT = 17; SHEAR = 0.16
def render(text, font, size, shear, track=0.0, wght=None):
    f = ImageFont.truetype(FONTS + font, size)
    if wght:
        try: f.set_variation_by_axes([wght])
        except Exception: pass
    asc, desc = f.getmetrics()
    w = int(f.getlength(text) + track * len(text) + size)
    m = Image.new("L", (w + int(shear * (asc + desc)) + 40, asc + desc + 40), 0)
    d = ImageDraw.Draw(m); x = 20 + shear * (asc + desc)
    for i, ch in enumerate(text):
        d.text((x, 20), ch, font=f, fill=255)
        x += f.getlength(text[i:i+2]) - f.getlength(text[i+1]) if i + 1 < len(text) else 0
        x += track
    base = 20 + asc
    if shear:
        m = m.transform(m.size, Image.AFFINE, (1, shear, -shear * base, 0, 1, 0), Image.BICUBIC)
    return m.crop(m.getbbox()), base
def stroke(mask):
    a = np.asarray(mask) > 128; runs = []
    for row in a[::2]:
        r = np.diff(np.concatenate([[0], row.astype(int), [0]])); s = np.nonzero(r == 1)[0]; e = np.nonzero(r == -1)[0]
        runs += list(e - s)
    runs = np.array(runs); return float(np.median(runs[runs > 4]))
def slant(mask):
    best = None
    for s in np.arange(-0.05, 0.40, 0.005):
        u = mask.transform(mask.size, Image.AFFINE, (1, -s, s * mask.height / 2, 0, 1, 0), Image.BILINEAR)
        prof = np.asarray(u, dtype=float).sum(axis=0); sc = (np.diff(prof) ** 2).sum()
        if best is None or sc > best[0]: best = (sc, s)
    return best[1]
def colour(mask, out=OUT, pad=None):
    pad = out + 4
    a = np.zeros((mask.height + 2 * pad, mask.width + 2 * pad), bool)
    a[pad:pad + mask.height, pad:pad + mask.width] = np.asarray(mask) > 128
    dist = ndimage.distance_transform_edt(~a)
    wal = np.clip(out + 0.5 - dist, 0, 1)
    im = np.zeros(a.shape + (4,), np.uint8); im[..., :3] = 255; im[..., 3] = (wal * 255).astype(np.uint8)
    base = Image.fromarray(im, "RGBA")
    big = Image.new("L", base.size, 0); big.paste(mask, (pad, pad))
    lay = Image.new("RGBA", base.size, CRIMSON + (0,)); lay.putalpha(big)
    base.alpha_composite(lay); return base
def calibrate(font, ref_mask, ref_text, shear, wght=None):
    """Кегль по высоте тела немецкого слова, сжатие по ширине."""
    p, _ = render(ref_text, font, 200, shear, wght=wght)
    size = round(200 * ref_mask.height / p.height)
    p, _ = render(ref_text, font, size, shear, wght=wght)
    return size, ref_mask.width / p.width, p

def weight(mask, delta):
    """Утолщить (delta>0) или утончить (delta<0) штрих на delta px с каждой стороны."""
    if not delta: return mask
    a = np.asarray(mask) > 127
    pad = int(abs(delta)) + 3
    a = np.pad(a, pad)
    if delta > 0:
        d = ndimage.distance_transform_edt(~a); r = np.clip(delta + 0.5 - d, 0, 1)
    else:
        d = ndimage.distance_transform_edt(a); r = np.clip(d - (-delta) - 0.5, 0, 1)
    return Image.fromarray((r * 255).astype(np.uint8)[pad:-pad, pad:-pad])
