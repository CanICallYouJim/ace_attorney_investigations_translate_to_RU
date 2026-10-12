"""cut01_009 — вывеска «CIRCUS SHOW» → «ЦИРКОВОЕ ШОУ» набором шрифтом (вместо рисунков нейросети).

Метод (задание 13 октября 2026, после «цицирковое» / «Ц РКОВОЕ» у нейросети):
  * передний план (слон, хвост, клыки, борода, лев, тигр) — пиксели оригинала, которые
    одинаковы у английской, японской (_base) и французской картинок и не являются ровной
    заливкой вывески: у трёх языков разные буквы, общее у них только то, что стоит перед ними;
  * фон под английскими буквами, не закрытый русскими, — японский/французский там, где у них
    ровная заливка вывески, остальное — заливка соседями (вывеска ровная, 158);
  * буквы: Bahnschrift Bold Condensed, раскладка по огибающей английской строки (верх и низ
    сняты с английских букв), ширина буквы пропорциональна местной высоте; стиль снят
    с английских букв замером: кайма 118 (низ 112) шириной ~19 px, внутренний кант 174 ~5 px,
    переход к телу 244 за ~12 px (снизу ~17 px);
  * огненное кольцо полупрозрачное: под огнём русская картинка строится из двух языков
    (английский и французский видят один и тот же огонь над разными буквами) — см. fire().

Запуск: .venv\\Scripts\\python.exe work\\graphics_ru\\case2\\cut01_009_sign.py [--out PNG]
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as nd
from scipy.interpolate import PchipInterpolator

ROOT = Path(__file__).resolve().parents[3]
EN = ROOT / "work/graphics_en/case2/cut01_009.png"
JA = ROOT / "work/localized/_base/cut01_009.png"
FR = ROOT / "work/localized/gk2_upcutlocal/cut01_009_fre.png"
OUT = ROOT / "work/graphics_masks/drafts/cut01_009_набор.png"

FONT = "C:/Windows/Fonts/bahnschrift.ttf"
VAR = "Bold Condensed"

# огибающая английской строки: внешний край каймы (замер по столбцам, см. отчёт)
TOP = [(420, 350), (450, 338), (480, 325), (800, 205), (900, 150), (1000, 120), (1080, 100),
       (1340, 78), (1520, 66), (1660, 74), (1900, 90)]
BOT = [(420, 640), (480, 642), (530, 620), (590, 601), (680, 577), (800, 558), (870, 545),
       (1000, 555), (1100, 575), (1130, 585), (1250, 585), (1390, 580), (1550, 600),
       (1660, 620), (1900, 620)]

WORDS = [("ЦИРКОВОЕ", 420, 1110), ("ШОУ", 1222, 1868)]
POW = 0.0               # ширина буквы ∝ h**POW: у английской строки шаг букв почти ровный (~78 px слева)
OUTLINE = 19.0          # ширина каймы, px
STEM = 0.17             # толщина основного штриха Bahnschrift Bold Condensed, доля высоты прописной
EMBOLD = 0.6            # насколько вернуть штрих, потерянный при сжатии строки (1 — целиком)
MAXK = 0.9              # не больше этой доли штриха: иначе у «Ц», «И», «Ш» пропадает просвет
SLANT = 0.0             # наклон (сдвиг верха вправо на высоту), доля


def load(p):
    return np.array(Image.open(p).convert("RGBA")).astype(np.float32)


def env():
    t = PchipInterpolator(*zip(*TOP))
    b = PchipInterpolator(*zip(*BOT))
    x = np.arange(1920, dtype=np.float64)
    return t(np.clip(x, 420, 1900)), b(np.clip(x, 420, 1900))


PAD = 80


def glyphs(word, size=600):
    f = ImageFont.truetype(FONT, size)
    f.set_variation_by_name(VAR)
    asc = f.getbbox("Н")
    cap_top, base = asc[1], asc[3]
    out = []
    for ch in word:
        bb = f.getbbox(ch)
        im = Image.new("L", (bb[2] - bb[0] + 2 * PAD, size * 2), 0)
        ImageDraw.Draw(im).text((PAD - bb[0], 0), ch, font=f, fill=255)
        a = np.array(im)[cap_top:, :]
        out.append((ch, a, base - cap_top, bb[2] - bb[0]))
    return out


def word_layer(word, x0, x1, top, bot, H, W):
    """Маска тела букв слова (0..1) в координатах картинки, огибающая — по каймe наружу."""
    gl = glyphs(word)
    capH = gl[0][2]
    # плоская строка: глифы подряд с трекингом
    track = 0.06 * capH
    widths = [g[3] for g in gl]
    flatW = sum(widths) + track * (len(gl) - 1)
    flat = np.zeros((gl[0][1].shape[0], int(flatW) + 2 * PAD + 2), np.float32)
    # масштабы: по вертикали sy = h/capH, по горизонтали sx — ширина слова / плоская ширина
    hc = (bot - top - 2 * OUTLINE)
    seg = np.arange(int(x0 + OUTLINE), int(x1 - OUTLINE) + 1)
    wts = 1.0 / np.maximum(hc[seg], 1) ** POW
    cumw = np.concatenate([[0], np.cumsum(wts)])
    u = 0.0
    for ch, a, _, iw in gl:
        # середина буквы на экране
        uc = (u + iw / 2) / flatW * cumw[-1]
        xc = seg[min(np.searchsorted(cumw, uc), len(seg) - 1)]
        sy = hc[xc] / capH
        sx = (x1 - x0 - 2 * OUTLINE) / flatW * (wts[min(xc - seg[0], len(wts) - 1)] * len(wts) / cumw[-1])
        stem = STEM * capH
        k = int(round(np.clip(stem * (sy / sx - 1) * EMBOLD, 0, MAXK * stem)))
        g = a / 255.0
        if k > 0:
            g = nd.grey_dilation(g, footprint=np.ones((1, 2 * (k // 2) + 1), bool))
        flat[:a.shape[0], int(u):int(u) + a.shape[1]] = np.maximum(
            flat[:a.shape[0], int(u):int(u) + a.shape[1]], g)
        u += iw + track
    # отображение x -> u: du/dx ∝ 1/h(x)
    h = (bot - top - 2 * OUTLINE)
    xs = np.arange(W)
    inv = np.where((xs >= x0 + OUTLINE) & (xs <= x1 - OUTLINE), 1.0 / np.maximum(h, 1) ** POW, 0.0)
    cum = np.cumsum(inv)
    cum = cum / cum[-1] * flatW + PAD
    mapx = np.zeros((H, W), np.float32)
    mapy = np.zeros((H, W), np.float32)
    yy = np.arange(H, dtype=np.float32)[:, None]
    t_in = (top + OUTLINE)[None, :]
    hh = h[None, :]
    v = (yy - t_in) / hh * capH
    # наклон: верх сдвинут вправо
    shift = SLANT * (capH - v) * (h[None, :] / capH)
    xx = np.arange(W, dtype=np.float32)[None, :] - shift
    ui = np.interp(xx.ravel(), xs, cum).reshape(H, W)
    mapx[:] = ui
    mapy[:] = v
    out = cv2.remap(flat, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    out[:, :int(x0 + OUTLINE)] = 0
    out[:, int(x1 - OUTLINE) + 1:] = 0
    return out


def style(body):
    """Тело (0..1) -> (значение, альфа) в стиле английских букв."""
    m = body > 0.5
    din = nd.distance_transform_edt(m)                 # внутрь от края тела
    dout = nd.distance_transform_edt(~m)               # наружу
    # расстояние до края снизу (по вертикали) — для более длинной тени у низа
    H, W = m.shape
    down = np.zeros_like(din)
    run = np.zeros(W, np.float32)
    for y in range(H - 1, -1, -1):
        run = np.where(m[y], run + 1, 0)
        down[y] = run
    def ramp(d, a, w):
        s = np.clip((d - a) / w, 0, 1)
        return s * s * (3 - 2 * s)
    v_side = 174 + 70 * ramp(din, 4.5, 12.0)
    v_bot = 169 + 75 * ramp(down, 1.0, 17.0)
    v = np.minimum(v_side, v_bot)
    # кайма: 118 сверху, к низу 112
    yy = np.arange(H, dtype=np.float32)[:, None]
    out_v = np.full_like(v, 118.0)
    v = np.where(m, v, out_v)
    # мягкий край тела (1.5 px) к кайме
    soft = np.clip(0.5 + (din - dout) / 1.5, 0, 1)
    v = soft * np.where(m, v, 174) + (1 - soft) * out_v
    alpha = np.clip(OUTLINE + 0.5 - dout, 0, 1)
    return v, alpha


def masks(E, J, F):
    L, B, Fr = E[..., 0], J[..., 0], F[..., 0]
    common = (np.abs(L - B) <= 6) & (np.abs(L - Fr) <= 6)
    m = nd.uniform_filter(L, 5)
    s = np.sqrt(np.maximum(nd.uniform_filter(L * L, 5) - m * m, 0))
    pal = np.zeros(L.shape, bool)
    for v in (110, 118, 158, 174, 244, 255):
        pal |= np.abs(L - v) <= 4
    flat = pal & (s < 2.5)
    occ = common & ~flat
    lab, n = nd.label(occ, structure=np.ones((3, 3)))
    sz = nd.sum(np.ones_like(L), lab, range(1, n + 1))
    keep = np.zeros(n + 1, bool)
    keep[1:] = sz >= 40
    occ = keep[lab]
    # тонкие дуги — совпавшие края букв трёх языков, а не предмет: предмет — то, что
    # держится после размыкания, плюс тонкое, что к нему примыкает (хвост слона, обод)
    core = nd.binary_opening(occ, iterations=2)
    cl, cn = nd.label(core, structure=np.ones((3, 3)))
    cs = nd.sum(np.ones_like(L), cl, range(1, cn + 1))
    ck = np.zeros(cn + 1, bool)
    ck[1:] = cs >= 300
    core = ck[cl]
    occ = nd.binary_dilation(core, iterations=12, mask=occ) | core
    holes = nd.binary_fill_holes(occ) & ~occ
    hl, hn = nd.label(holes)
    hs = nd.sum(np.ones_like(L), hl, range(1, hn + 1))
    sm = np.zeros(hn + 1, bool)
    sm[1:] = hs < 600
    occ |= sm[hl]
    # ровные места внутри предмета (брюхо слона залито 114 — «ровная кайма» по палитре):
    # закрытая предметом дыра, одинаковая у трёх языков, — тоже предмет
    holes = nd.binary_fill_holes(occ) & ~occ
    panel_flat = (np.abs(L - 158) <= 4) & (s < 2.5)
    occ |= holes & common & ~panel_flat
    # белая шерсть тигра и блики у края предмета — ровные 240+, к предмету примыкают
    near = nd.binary_dilation(occ, iterations=3) & ~occ
    occ |= near & common & (L >= 235)
    # английские буквы: отличаются от другого языка и по цвету — буква (кайма или тело)
    # английские буквы: в полосе строки всё, что похоже на букву (кайма или тело)
    # и не передний план; полоса — огибающая с запасом
    top, bot = env()
    yy = np.arange(L.shape[0])[:, None]
    band = (yy >= top[None, :] - 4) & (yy <= bot[None, :] + 8)
    band[:, :412] = False
    # кайма 108–125; тёмное (< 100) — это не кайма, а мрак за вывеской справа и замок слева
    enl = band & (((L >= 100) & (L <= 130)) | ((L >= 165) & (L < 250))) & ~occ
    enl = nd.binary_opening(enl, iterations=1)
    return common, occ, enl, flat


def background(E, J, F, enl, occ):
    """Вывеска без английских букв."""
    L, B, Fr = E[..., 0], J[..., 0], F[..., 0]
    unk = nd.binary_dilation(enl, iterations=3) & ~occ
    unk[:, :405] = False
    bg = L.copy()

    def panel(X):
        m = nd.uniform_filter(X, 5)
        s = np.sqrt(np.maximum(nd.uniform_filter(X * X, 5) - m * m, 0))
        return (np.abs(X - 158) <= 5) & (s < 2.0)
    pj, pf = panel(B), panel(Fr)
    use_j = unk & pj
    bg[use_j] = B[use_j]
    rest = unk & ~use_j
    use_f = rest & pf
    bg[use_f] = Fr[use_f]
    rest &= ~use_f
    rest = nd.binary_dilation(rest, iterations=1) & ~occ
    # вывеска ровная: заливка гладкой моделью по чистым пикселям заливки рядом
    m = nd.uniform_filter(L, 5)
    s = np.sqrt(np.maximum(nd.uniform_filter(L * L, 5) - m * m, 0))
    clean = (np.abs(L - 158) <= 8) & (s < 2.0) & ~occ & ~nd.binary_dilation(enl, iterations=4)
    filled = bg.copy()
    left = rest.copy()
    for sig, thr in ((12, 0.02), (30, 0.005), (80, 1e-9)):
        num = nd.gaussian_filter(np.where(clean, L, 0), sig)
        den = nd.gaussian_filter(clean.astype(np.float32), sig)
        ok = left & (den > thr)
        filled[ok] = num[ok] / den[ok]
        left &= ~ok
    # слева (замок) и справа (буква заходила за край вывески, на тёмное) — заливка соседями
    castle = rest.copy()
    castle[:, 520:1700] = False
    img = np.clip(filled, 0, 255).astype(np.uint8)
    tel = cv2.inpaint(img, castle.astype(np.uint8) * 255, 6, cv2.INPAINT_TELEA).astype(np.float32)
    filled[castle] = tel[castle]
    # низ вывески: под буквами светлая кромка и скос — тянуть их вдоль кромки
    # (строки, параллельные нижней огибающей), а не заливать ровным серым
    top, bot = env()
    known = ~(unk | occ)
    for v in range(-40, 17):
        xs = np.arange(1100, 1700)
        ys = np.round(bot[xs] + v).astype(int)
        ok = (ys >= 0) & (ys < L.shape[0])
        xs, ys = xs[ok], ys[ok]
        kn = known[ys, xs]
        un = unk[ys, xs] & ~occ[ys, xs]
        if kn.sum() < 2 or not un.any():
            continue
        vals = np.interp(xs[un], xs[kn], L[ys[kn], xs[kn]])
        filled[ys[un], xs[un]] = vals
    return filled, rest


# Огненное кольцо полупрозрачное: в оригинале сквозь огонь видны английские «S» и «H».
# Разложить огонь и буквы по двум языкам (английский и французский видят один огонь
# над разными буквами) не вышло: тела букв под огнём порогом не находятся, оценка
# пропускания шумит — проба 2, 13 октября 2026. Поэтому «огонь над ровной вывеской» —
# вырезка нейросети (Codex): из оригинальной вырезки убраны только буквы за огнём,
# огонь, обод, тигр и клыки оставлены. Букв нейросеть не рисует — только фон под огнём.
FIRE_BOX = (980, 0, 1330, 640)
FIRE_ART = ROOT / "work/graphics_ai/case2/cut01_009_fire_1.png"


def fire(res, Ien, top, bot, occ, body_alpha):
    x0, y0, x1, y1 = FIRE_BOX
    w, h = x1 - x0, y1 - y0
    P = np.array(Image.open(FIRE_ART).convert("L").resize((w, h), Image.LANCZOS)).astype(np.float32)
    E = Ien[y0:y1, x0:x1]
    m = np.zeros((h, w), np.uint8)
    m[280:520, 240:350] = 1          # тигр
    m[470:640, 0:120] = 1            # клыки внизу
    m[0:120, 0:120] = 1              # клык вверху
    warp = np.eye(2, 3, dtype=np.float32)
    cc, warp = cv2.findTransformECC(E, P, warp, cv2.MOTION_AFFINE,
                                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), m, 5)
    P = cv2.warpAffine(P, warp, (w, h), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
                       borderMode=cv2.BORDER_REPLICATE)
    # тон: нейросеть красит вывеску на ~7 темнее — поправка полем по чистой вывеске
    # тон: нейросеть красит вывеску темнее и неровно (внутри кольца ещё темнее) —
    # своя ровная вывеска нейросети приводится к 158, огонь — отклонение от неё
    mu = nd.uniform_filter(P, 7)
    sd = np.sqrt(np.maximum(nd.uniform_filter(P * P, 7) - mu * mu, 0))
    pflat = (sd < 1.6) & (np.abs(P - 150) < 14)
    num = nd.gaussian_filter(np.where(pflat, P, 0), 30)
    den = nd.gaussian_filter(pflat.astype(np.float32), 30)
    level = np.where(den > 1e-4, num / np.maximum(den, 1e-6), float(np.median(P[pflat])))
    P = P - level + 158.0
    # где огонь и обод: отличие от ровной вывески
    flat = nd.gaussian_filter(P, 25)
    dev = np.abs(P - 158.0)
    firem = dev > 5
    firem = nd.binary_opening(firem, iterations=1)
    firem = nd.binary_dilation(firem, iterations=8)
    wgt = nd.gaussian_filter(firem.astype(np.float32), 4)
    # поверх русской буквы: I = P + s·(R − 158), пропускание s — по силе огня
    s = 1.0 - np.clip(dev / 100.0, 0, 0.8)
    s = nd.gaussian_filter(s, 1.0)
    R = res[y0:y1, x0:x1]
    cand = P + s * (R - 158.0)
    blend = R * (1 - wgt) + cand * wgt
    o = occ[y0:y1, x0:x1]
    blend[o] = R[o]
    out = res.copy()
    out[y0:y1, x0:x1] = blend
    return out, cc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--debug", default="")
    a = ap.parse_args()
    E, J, F = load(EN), load(JA), load(FR)
    H, W = E.shape[:2]
    top, bot = env()
    common, occ, enl, flat = masks(E, J, F)
    bg, inp = background(E, J, F, enl, occ)
    body = np.zeros((H, W), np.float32)
    for word, x0, x1 in WORDS:
        body = np.maximum(body, word_layer(word, x0, x1, top, bot, H, W))
    v, al = style(body)
    res = bg * (1 - al) + v * al
    dbg = {}
    res, cc = fire(res, E[..., 0], top, bot, occ, al)
    print(f"огонь: совмещение ECC {cc:.3f}")
    o1 = nd.binary_dilation(occ, iterations=1)
    res[o1] = E[..., 0][o1]
    # вне зоны вывески — оригинал
    zone = np.zeros((H, W), bool)
    zone[0:700, 405:1920] = True
    res[~zone] = E[..., 0][~zone]
    # картинка почти серая (каналы расходятся на 1–7): правка — сдвигом всех трёх каналов,
    # нетронутые пиксели остаются байт в байт
    delta = np.round(res - E[..., 0])
    rgb = np.clip(E[..., :3] + delta[..., None], 0, 255).astype(np.uint8)
    outa = np.dstack([rgb, E[..., 3].astype(np.uint8)])
    Image.fromarray(outa, "RGBA").save(a.out)
    if a.debug:
        d = Path(a.debug)
        d.mkdir(parents=True, exist_ok=True)
        np.save(d / "occ.npy", occ)
        np.save(d / "body.npy", body)
        np.save(d / "alpha.npy", al)
        np.save(d / "inp.npy", inp)
        Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).save(d / "bg.png")
        for k, v2 in dbg.items():
            np.save(d / f"fire_{k}.npy", v2)
    print("готово:", a.out)


if __name__ == "__main__":
    sys.exit(main())
