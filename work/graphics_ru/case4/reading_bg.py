"""Фоны чтения писем `Sousa_TextCutBG_R_*`: русские строки набором в полном размере, по прогибу страницы.

Класс картинки (9 октября 2026, замечания пользователя к пробе переноса с улики): тёмный кадр 1920×1080
(бумага ~25 уровней из 255), на нём раскрытое письмо-книжка и карточка поверх. Перенос с улики 300 px
растягивал буквы ×3,8 — ступеньки, «шрифт не тот»; строки на раскрытой книжке у оригинала прогибаются
к корешку, у переноса — плоские. Поэтому строки набираются заново:

* **подложка** — медиана семи языков (бумага и карточка у всех одни, надписи в разных местах); где буквы
  совпали у большинства — максимум семи; остаток (крапины, где буквы у всех) — затягивается соседями;
* **строка** — по замеру английской: в полосе вокруг грубой средней линии (`центр`, `полувысота`) берётся
  английская краска, по окнам вдоль строки — низ строчных (`x`-полоса) и её высота; низ сглаживается
  сплайном — это кривая строки с прогибом у корешка;
* **набор** — русский текст во весь размер (×4 и усреднение), кегль — чтобы строчные были той же высоты,
  что английские, тем же замером; буквы ставятся по кривой, перпендикулярно ей; `размытие` — как мягкость
  английских букв; цвет — доля бумаги, как у английской краски (умножением: в тени корешка буквы темнеют);
* **заслон** — карточка поверх письма: кромки уточняются по подложке (тёмная обводка карточки), всё,
  что за кромкой, не рисуется;
* **`прямая_до`** (x в кадре) — видимая часть строки лежит на прямой, замеренной по столбцам левее этой
  точки; **`прямая_по`** (x) — докуда прямая (кромка косая, верх букв виден правее), дальше под карточкой
  плавный переход к замеренной кривой; для строк, у которых буквы у кромки срезаны снизу и горбят замер
  (R_04 «Now we ca»); `"прямая_до": "вся"` — прямая вся строка (у плоского листа строки прямые, а замер
  по окнам цепляет запятые и апострофы — R_03).

Проверка способа — `--english`: тот же набор английским текстом гарнитурой оригинала (ITC Kristen) должен
лечь на английские буквы. Задание — `reading_bg.json` рядом. Запуск:

    .venv\\Scripts\\python.exe work\\graphics_ru\\case4\\reading_bg.py Sousa_TextCutBG_R_03 [--english] [--out путь]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import (binary_dilation, gaussian_filter, gaussian_filter1d, label, map_coordinates,
                           maximum_filter, median_filter)
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = Path(__file__).with_name("reading_bg.json")
FONTS = Path("C:/Windows/Fonts")
SS = 4                 # набор и выборка в ×4, потом усреднение
INK = 0.62             # краска — темнее этой доли бумаги
SMOOTH = 20            # сглаживание кривой низа строки, px вдоль строки
BLEND = 100            # `прямая_до`: переход от прямой к кривой под карточкой, px вдоль строки
GHOST = 0.95           # край английских букв — темнее подложки на 5 % и больше (с 10 % оставались крапины)
SLOPE = 0.15           # ровный — и перепад опоры меньше этого, уровней на пиксель
FLAT = 0.8             # ровный рисунок: разброс опоры в окне σ 3 px меньше этого, уровней
LANGS = ("eng", "ger", "fre", "jpn", "kor", "sim", "tra")


def value(img):
    return img.max(-1) if img.ndim == 3 else img


def paper_of(v):
    """Бумага вокруг: максимум в окне 21 px, сглаженный — тень корешка и градиенты сохраняются."""
    return gaussian_filter(maximum_filter(v, 21), 4) + 1e-3


def dense(points, step):
    p = np.asarray(points, float)
    s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
    t = np.arange(0, s[-1] + step / 2, step)
    return t, np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], 1)


def normals(c):
    d = np.gradient(c, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    return d, np.stack([-d[:, 1], d[:, 0]], 1)      # нормаль вниз при строке слева направо


def strip(img, c, n, h):
    v = np.arange(-h, h + 1, dtype=float)
    ys = c[None, :, 1] + v[:, None] * n[None, :, 1]
    xs = c[None, :, 0] + v[:, None] * n[None, :, 0]
    return map_coordinates(img, [ys, xs], order=1, mode="nearest"), v


def columns(ink):
    """По столбцам полосы: есть ли краска, её верх и низ (номера строк полосы)."""
    has = ink.any(0)
    top = np.where(has, ink.argmax(0), 0)
    bot = np.where(has, ink.shape[0] - 1 - ink[::-1].argmax(0), 0)
    return has, top, bot


def measure(ink, h, win=24, step=4, blocked=None, straight=False):
    """Низ строки по окнам (медиана нижних краёв столбцов — хвосты «y», «g» в меньшинстве),
    сглаженный сплайном, и высота строчных — медиана высоты столбцов над низом по всей строке
    (строчных в строке больше половины, заглавные и выносные её не сдвигают)."""
    has, top, bot = columns(ink)
    # столбцы у кромки карточки: буквы там срезаны снизу, их «низ» — кромка, а не строка
    meas = has & ~blocked if blocked is not None else has
    us, vs = [], []
    for u0 in range(0, ink.shape[1] - win + 1, step):
        sel = meas[u0:u0 + win]
        if sel.sum() < win * 0.4:
            continue
        us.append(u0 + win / 2)
        vs.append(float(np.median(bot[u0:u0 + win][sel])) + 0.5 - h)
    if len(us) < 3:
        return None
    us, vs = np.array(us), np.array(vs)
    # выбросы (окно из одних хвостов) — к медиане соседей
    med = np.array([np.median(vs[max(0, i - 3):i + 4]) for i in range(len(vs))])
    vs = np.where(np.abs(vs - med) > 2.5, med, vs)
    # гладкая кривая: буквы ставятся перпендикулярно ей, и на мелкой волне их складывает —
    # радиус изгиба обязан быть много больше высоты букв; прогиб к корешку (~100 px) остаётся
    grid = np.arange(us.min(), us.max() + 1)
    if straight:
        # карточка плоская: низ строки — прямая (излом грубой средней линии гнал буквы вверх-вниз)
        smooth = np.polyval(np.polyfit(us, vs, 1), grid)
    else:
        smooth = gaussian_filter1d(np.interp(grid, us, vs), SMOOTH, mode="nearest")

    def spl(x, grid=grid, smooth=smooth):
        return np.interp(x, grid, smooth)
    cols = np.nonzero(meas)[0]
    xh = float(np.median(spl(np.clip(cols, us.min(), us.max())) - (top[cols] - 0.5 - h)))
    return spl, (us.min(), us.max()), xh, top, bot


def stem_width(ink, lo, hi):
    """Медиана длины горизонтальных отрезков краски в x-полосе — толщина штриха."""
    runs = []
    for r in ink[max(0, int(lo)):int(hi) + 1]:
        run = 0
        for v in list(r) + [False]:
            if v:
                run += 1
            elif run:
                if run <= 12:
                    runs.append(run)
                run = 0
    return float(np.median(runs)) if runs else 0.0


def x_height(font_path, ch):
    """Высота строчной над низом строки по метрике гарнитуры."""
    f = ImageFont.truetype(str(font_path), 400)
    return -f.getbbox(ch, anchor="ls")[1] / 400


class Line:
    def __init__(self, cfg, v_norm, own_ink, blocked=None):
        self.cfg = cfg
        t, c = dense(cfg["центр"], 1.0)
        c[:, 0] = gaussian_filter(c[:, 0], 3, mode="nearest")
        c[:, 1] = gaussian_filter(c[:, 1], 3, mode="nearest")
        self.t, self.c = t, c
        self.d, self.n = normals(c)
        h = cfg["полувысота"]
        s_ink, self.v = strip(own_ink.astype(float), c, self.n, h)
        self.ink = s_ink > 0.5
        near = None
        if blocked is not None:
            # срезан тот столбец, где низ краски упирается в карточку (1–5 px под ним — карточка:
            # у кромки краску отрезает запас 2 px и порог; целые буквы над кромкой — в 6–8 px от неё);
            # столбцы, где полоса строки лишь касается карточки, низ строки честно показывают
            s_b, _ = strip(blocked.astype(float), c, self.n, h + 4)
            has, _, bot = columns(self.ink)
            rows = np.clip(bot[None, :] + 4 + np.arange(1, 6)[:, None], 0, s_b.shape[0] - 1)
            near = has & (np.take_along_axis(s_b, rows, 0).max(0) > 0.5)
        got = measure(self.ink, h, blocked=near, straight=cfg.get("прямая", False))
        if got is None:
            sys.exit(f"{cfg['англ']}: краски в полосе почти нет — проверь «центр»")
        self.base_v, self.u_meas, self.xh, top, bot = got
        self.base_v_raw = self.base_v
        x_to = cfg.get("прямая_до")
        if x_to is not None:
            # видимая часть строки до кромки карточки — прямая в кадре, как у английского: у кромки
            # буквы срезаны снизу («ca» в «Now we ca», R_04), автомат их не отсёк, и низ строки шёл
            # горбом вверх — «мы» вставало под углом (замечание пользователя 10 октября 2026).
            # Замер — по столбцам левее `прямая_до`; прямая — до `прямая_по` (кромка карточки косая:
            # верх букв виден правее, чем низ, — «обе» у R_04 до x≈950); дальше под карточкой —
            # плавный переход к прежней кривой (там букв не видно, а за карточкой строка как была)
            # «вся» — прямая вся строка (R_03 «Дорогая», «волнуйся»: окна замера цепляли запятую
            # и апостроф, и буквы гуляли вверх-вниз до 9 px — замечание пользователя 10 октября 2026)
            if x_to == "вся":
                u_m, u_x = np.inf, np.inf
            else:
                u_m = float(t[np.abs(c[:, 0] - x_to).argmin()])
                u_x = float(t[np.abs(c[:, 0] - cfg.get("прямая_по", x_to)).argmin()])
            cut = np.arange(self.ink.shape[1]) >= u_m
            if near is not None:
                cut |= near
            left = measure(self.ink, h, blocked=cut, straight=True)
            us = np.linspace(left[1][0], left[1][1], 50)
            px = np.interp(us, t, c[:, 0]) + left[0](us) * np.interp(us, t, self.n[:, 0])
            py = np.interp(us, t, c[:, 1]) + left[0](us) * np.interp(us, t, self.n[:, 1])
            ka, kb = np.polyfit(px, py, 1)

            def base_v(u, old=self.base_v, t=t, c=c, n=self.n):
                u = np.asarray(u, float)
                cx, cy = np.interp(u, t, c[:, 0]), np.interp(u, t, c[:, 1])
                nx, ny = np.interp(u, t, n[:, 0]), np.interp(u, t, n[:, 1])
                v_line = (ka * cx + kb - cy) / (ny - ka * nx)      # c + v·n — на прямой
                s = np.clip((u - u_x) / BLEND, 0, 1)
                s = s * s * (3 - 2 * s)
                return v_line * (1 - s) + old(u) * s
            self.base_v = base_v
        mid = self.base_v((self.u_meas[0] + self.u_meas[1]) / 2) + h
        self.stem = stem_width(self.ink, mid - self.xh * 0.8, mid - self.xh * 0.2)
        cols = np.nonzero(self.ink.any(0))[0]
        self.u_start, self.u_end = float(cols.min()), float(cols.max() + 1)
        vals = map_coordinates(v_norm, [c[None, :, 1] + self.v[:, None] * self.n[None, :, 1],
                                        c[None, :, 0] + self.v[:, None] * self.n[None, :, 0]], order=1)
        self.ink_ratio = float(np.percentile(vals[self.ink], 8))

    def baseline(self, u_lo, u_hi, step=0.25):
        """Кривая низа в кадре от u_lo до u_hi (длина по средней линии); вне замера — по касательной."""
        a, b = self.u_meas
        u = np.arange(u_lo, u_hi + step, step)
        uc = np.clip(u, a, b)
        v = self.base_v(uc)
        # продолжение прямой: наклон по крайним 150 px замера (производная сплайна на краю скачет)
        ka = np.polyfit(np.linspace(a, min(b, a + 150), 11), self.base_v(np.linspace(a, min(b, a + 150), 11)), 1)[0]
        kb = np.polyfit(np.linspace(max(a, b - 150), b, 11), self.base_v(np.linspace(max(a, b - 150), b, 11)), 1)[0]
        v = np.where(u < a, v + (u - a) * ka, v)
        v = np.where(u > b, v + (u - b) * kb, v)
        # точки средней линии и нормали — с продолжением прямой
        ti = np.clip(u, 0, self.t[-1])
        cx = np.interp(ti, self.t, self.c[:, 0]) + np.where(u < 0, u, 0) * self.d[0, 0] \
            + np.where(u > self.t[-1], u - self.t[-1], 0) * self.d[-1, 0]
        cy = np.interp(ti, self.t, self.c[:, 1]) + np.where(u < 0, u, 0) * self.d[0, 1] \
            + np.where(u > self.t[-1], u - self.t[-1], 0) * self.d[-1, 1]
        nx = np.interp(ti, self.t, self.n[:, 0])
        ny = np.interp(ti, self.t, self.n[:, 1])
        return np.stack([cx + v * nx, cy + v * ny], 1)


def parallel(la, lb, own_ink, cfg):
    """Строка той же формы, что lb, ниже на шаг строк (разница низов la и lb по вертикали)."""
    import copy
    ln = copy.copy(lb)
    ln.cfg = cfg
    # форма — по замеру соседней строки, без её `прямая_до`: та правит видимые буквы своей строки,
    # а у этой видимое — левее, и подгонка по кусочкам от правки соседа прыгала на 10 px (R_04)
    ln.base_v = lb.base_v_raw
    # шаг строк — медиана по всей длине, где обе строки замерены (в одной точке под карточкой
    # кривая интерполирована, и шаг выходил вдвое больше)
    steps = []
    for u in np.linspace(lb.u_meas[0], lb.u_meas[1], 40):
        pb = ln.baseline(u, u)[0]
        k = np.abs(la.c[:, 0] - pb[0]).argmin()
        ua = float(la.t[k])
        if la.u_meas[0] <= ua <= la.u_meas[1] and abs(la.c[k, 0] - pb[0]) < 2:
            steps.append(pb[1] - la.baseline(ua, ua)[0][1])
    ln.c = lb.c + np.array([0.0, float(np.median(steps))])
    ys, xs = np.nonzero(own_ink)
    if len(xs):
        _, k = cKDTree(ln.c).query(np.stack([xs, ys], 1))
        ln.u_start, ln.u_end = float(ln.t[k].min()), float(ln.t[k].max())
    return ln


def render_strip(text, font_path, size, comp, stroke):
    font = ImageFont.truetype(str(font_path), int(round(size * SS)))
    w = int(font.getlength(text)) + 8 * SS
    asc, desc = font.getmetrics()
    im = Image.new("L", (w, asc + desc + 8 * SS), 0)
    ImageDraw.Draw(im).text((4 * SS, 4 * SS + asc), text, font=font, fill=255, anchor="ls",
                            stroke_width=int(round(stroke * SS)), stroke_fill=255)
    a = np.asarray(im, float) / 255
    if comp != 1:
        a = cv2.resize(a, (max(1, int(round(a.shape[1] * comp))), a.shape[0]), interpolation=cv2.INTER_AREA)
    # u_r = 0 в начале текста (столбец 4*SS*comp), низ — строка 4*SS+asc
    return a, 4 * SS * comp, 4 * SS + asc, font


def place(line, text, font_path, size, comp, stroke, u0, shape, blur):
    """Альфа строки в кадре: набор вдоль кривой низа, начало текста в u0 (длина по средней линии)."""
    a, col0, row0, font = render_strip(text, font_path, size, comp, stroke)
    length = (a.shape[1] - col0) / SS
    b = line.baseline(u0 - 20, u0 + length + 20)
    seg = np.r_[0, np.cumsum(np.hypot(*np.diff(b, axis=0).T))]
    arc = seg - seg[80]                       # длина по низу от начала текста (u0 - 20 с шагом 0,25)
    d = np.gradient(b, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    nrm = np.stack([-d[:, 1], d[:, 0]], 1)
    tree = cKDTree(b)
    pad = a.shape[0] / SS + 4
    x0, y0 = np.floor(b.min(0) - pad).astype(int)
    x1, y1 = np.ceil(b.max(0) + pad).astype(int)
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, shape[1]), min(y1, shape[0])
    gy, gx = np.mgrid[y0 * SS:y1 * SS, x0 * SS:x1 * SS]
    q = np.stack([(gx + 0.5) / SS - 0.5, (gy + 0.5) / SS - 0.5], -1).reshape(-1, 2)
    _, i = tree.query(q)
    rel = q - b[i]
    along = arc[i] + (rel * d[i]).sum(1)
    across = (rel * nrm[i]).sum(1)
    col = col0 + along * SS
    row = row0 + across * SS
    vals = map_coordinates(a, [row, col], order=1, cval=0.0).reshape(gy.shape)
    out = np.zeros(shape)
    out[y0:y1, x0:x1] = vals.reshape(y1 - y0, SS, x1 - x0, SS).mean((1, 3))
    if blur:
        out = gaussian_filter(out, blur)
    return out


def occluder(spec, plate_v, shape):
    """Карточка поверх письма: полуплоскости за кромками; кромка — внешний край тёмной обводки на подложке."""
    mask = np.ones(shape, bool)
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    paper = paper_of(plate_v)
    for (ax, ay), (bx, by) in spec["кромки"]:
        t, c = dense([(ax, ay), (bx, by)], 2.0)
        d, n = normals(c)
        prof, v = strip(plate_v / paper, c, n, 14)      # нормаль смотрит внутрь карточки
        pts = []
        for j in range(prof.shape[1]):
            k = np.nonzero(prof[:, j] < 0.4)[0]
            if len(k):
                pts.append(c[j] + (v[k[0]] - 0.5) * n[j])
        pts = np.array(pts)
        if len(pts) < 10:
            sys.exit(f"кромка {ax},{ay}–{bx},{by}: обводки не нашлось")
        # прямая через точки (кромка карточки прямая), со стороны карточки
        vx, vy, px, py = cv2.fitLine(pts.astype(np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        if vx * d[0, 0] + vy * d[0, 1] < 0:
            vx, vy = -vx, -vy
        side = (xx - px) * (-vy) + (yy - py) * vx         # >0 — по нормали внутрь
        mask &= side > -0.5
    return mask


def build(name, english=False):
    spec = json.loads(SPEC.read_text(encoding="utf-8"))[name]
    from text_mask import load_variants
    V = load_variants(name)
    eng_rgba = V["eng"].convert("RGBA")
    E = np.asarray(eng_rgba.convert("RGB")).astype(float)
    stack = np.stack([np.asarray(V[k].convert("RGB")).astype(float) for k in LANGS])
    shape = E.shape[:2]

    # Опора — самый светлый из семи языков в каждой точке: рисунок (бумага, тень и обводка
    # карточки, корешок) у всех один, буквы у языков в разных местах, и хоть один из семи там
    # показывает рисунок (второй по яркости — нет: где буквы шести языков легли в одно место,
    # английские оставались). Краска английского — что темнее опоры. Сама опора в кадр не идёт
    # (у медианы остаются буквы немцев и французов — они почти там же, у максимума шум сжатия
    # светлее бумаги — крапины): английские буквы затягиваются бумагой вокруг.
    ref = stack.max(-1).max(0)
    gain = 235.0 / np.percentile(value(E), 99.5)
    v_eng = value(E)
    norm = v_eng / np.maximum(ref, 1e-3)
    eng_ink = norm < INK
    card = occluder(spec["заслон"], ref, shape) if "заслон" in spec else np.zeros(shape, bool)

    # краска английской строки — своей: ближайшая средняя линия
    lines_cfg = spec["строки"]
    centres = [dense(lc["центр"], 1.0)[1] for lc in lines_cfg]
    owner_tree = cKDTree(np.concatenate(centres))
    owner_idx = np.concatenate([np.full(len(c), i) for i, c in enumerate(centres)])
    ys, xs = np.nonzero(eng_ink)
    _, nearest = owner_tree.query(np.stack([xs, ys], 1))
    owner = np.full(shape, -1)
    owner[ys, xs] = owner_idx[nearest]

    lines = []
    owns = []
    for i, lc in enumerate(lines_cfg):
        # своя краска — только в полосе строки (ближайшая средняя линия по всему кадру
        # собирала чужое: края страниц, пятно)
        t_, c_ = dense(lc["центр"], 1.0)
        d_, n_ = normals(c_)
        ext = np.concatenate([c_[:1] - np.arange(30, 0, -1)[:, None] * d_[:1], c_,
                              c_[-1:] + np.arange(1, 31)[:, None] * d_[-1:]])
        nn = np.concatenate([np.repeat(n_[:1], 30, 0), n_, np.repeat(n_[-1:], 30, 0)])
        hh = lc["полувысота"] + 6
        band = np.zeros(shape, np.uint8)
        cv2.fillPoly(band, [np.concatenate([ext - hh * nn, (ext + hh * nn)[::-1]]).round().astype(np.int32)], 1)
        own = (owner == i) & band.astype(bool)
        if not lc.get("на_заслоне"):
            # у строки почти целиком под карточкой видимое — у самой кромки, его не отрезать
            own &= ~(card if "как_строка" in lc else binary_dilation(card, iterations=2))
        owns.append(own)
        blocked = None if lc.get("на_заслоне") else card
        lines.append(None if "как_строка" in lc else Line(lc, norm, own, blocked))
    # строка почти вся под карточкой (видны крохи — низ не замерить): кривая соседней строки,
    # сдвинутая на шаг строк [a, b] — «как b, ниже на расстояние от a до b»
    for i, lc in enumerate(lines_cfg):
        if "как_строка" in lc:
            a, b = lc["как_строка"]
            lines[i] = parallel(lines[a], lines[b], owns[i], lc)

    # поле правки — весь английский текст: что темнее самого светлого языка (рисунок у всех один),
    # на светлом (на чёрном фоне отношение — шум); верхушки заглавных за полосой строки тоже
    # растёт только от настоящих букв (краска): край обводки карточки у языков чуть разный, и по
    # отношению он тоже «темнее» — без привязки к буквам по обводке шёл пунктир
    light = ref > 0.3 * np.percentile(ref, 99.5)
    # буквы — темнее медианы языков (у обводки карточки медиана тоже темна: край обводки у языков
    # чуть разный, и от самого светлого по нему шёл пунктир)
    med_v = np.median(stack.max(-1), 0)
    # обводка — тёмная у всех семи языков (самый светлый тоже тёмен); по медиане туда попадало
    # имя на карточке — у немцев и французов «Rosie Ringer» там же
    outline = ref < 0.5 * paper_of(ref)
    lab_o, _ = label(outline)
    outline &= np.bincount(lab_o.ravel())[lab_o] > 500
    # где буквы большинства языков в одной точке, медиана тоже темна — там мерка по самому
    # светлому, но не у обводки
    core = light & ((v_eng / np.maximum(med_v, 1e-3) < INK)
                    | (eng_ink & ~binary_dilation(outline, iterations=3)))
    zone = binary_dilation(light & (norm < GHOST) & binary_dilation(core, iterations=5), iterations=3)
    # Заливка — среднее по языкам, у которых в этой точке чистая бумага: у каждого языка его буквы
    # (темнее самого светлого на 2 уровня) с запасом 2 px — размытый край буквы тоже не бумага.
    # Рисунок (тень и обводка карточки, корешок) у всех языков один и попадает как есть; среднее
    # не смещено (самый светлый из семи светлее бумаги — светлые контуры), без краёв букв не темнеет
    # (среднее «почти светлых» оставляло тёмные контуры). Где чистой бумаги нет ни у кого — затянуть
    # соседями (английская бумага вокруг).
    vals = stack.max(-1)
    clean = np.stack([~binary_dilation(v < ref - 2, iterations=2) for v in vals])
    count = clean.sum(0)
    fill = (stack * clean[..., None]).sum(0) / np.maximum(count, 1)[..., None]
    # сжатие кладёт градиент у корешка у каждого языка со своим сдвигом в уровень — сдвиг против
    # английской бумаги меряется рядом (σ 6 px) и вычитается, иначе по градиенту светлые контуры
    paper_px = clean[0] & ~zone & (count > 1)
    den = gaussian_filter(paper_px.astype(float), 6)
    shift = np.stack([gaussian_filter((fill[..., c] - E[..., c]) * paper_px, 6) for c in range(3)], -1)
    fill -= shift / np.maximum(den, 1e-3)[..., None]
    # обводка и тёмные края рисунка (темнее половины бумаги у самого светлого языка): там у всех
    # один рисунок — медиана семи; «чистая бумага» на крае обводки не находилась, и затягивание
    # соседями оставляло по обводке пунктир
    dark = ref < 0.5 * paper_of(ref)
    # обводка — длинный кусок; мелкое тёмное пятно у всех языков — их буквы в одной точке
    lab, _ = label(dark)
    dark &= np.bincount(lab.ravel())[lab] > 500
    # и переход от обводки к тени и бумаге (4 px вокруг длинных тёмных кусков): заливка «по чистым
    # языкам» там светлее рисунка на 4–5 уровней — выщерблина на кромке
    dark |= binary_dilation(outline, iterations=4)
    fill[dark] = np.median(stack, 0)[dark]
    count = np.where(dark, 7, count)
    # буквы всех семи языков в одной точке: опора и там темна — пятно темнее медианы окрестности
    # (медиана идёт за тенью корешка, максимум окна — нет: пятно сливалось с тенью); у обводки не искать
    spots = zone & (ref < 0.93 * median_filter(ref, 15)) & ~binary_dilation(dark, iterations=3)
    lab, _ = label(spots)
    sizes = np.bincount(lab.ravel())
    spots = binary_dilation((sizes[lab] < 300) & (lab > 0), iterations=1)
    count = np.where(spots, 0, count)
    # ровный рисунок (красное пятно, гладкая бумага): заливка по языкам оставляет тень букв
    # в 1–2 уровня (шум сжатия у каждого языка свой) — там затянуть соседями; у краёв рисунка
    # (обводка, кромка пятна, тень карточки) — по языкам, иначе край размажется
    mean = gaussian_filter(ref, 3)
    flat = np.sqrt(np.maximum(gaussian_filter(ref ** 2, 3) - mean ** 2, 0)) < FLAT
    # и без градиента: в тени корешка затягивание рвало тень светлым пятном
    flat &= np.hypot(*np.gradient(gaussian_filter(ref, 3))) < SLOPE
    flat = ~binary_dilation(~flat, iterations=3)
    count = np.where(zone & flat & ~dark, 0, count)
    hole = (zone | spots) & (count == 0)
    e8 = np.clip(np.round(np.where(hole[..., None], E, fill) * gain), 0, 255).astype(np.uint8)
    f8 = cv2.inpaint(e8, binary_dilation(hole, iterations=1).astype(np.uint8), 5, cv2.INPAINT_TELEA)
    fill = np.where(binary_dilation(hole, iterations=1)[..., None], f8.astype(float) / gain, fill)
    base = E.copy()
    base[zone] = fill[zone]

    # Кегль англичан — по длине: английский текст гарнитурой оригинала (ITC Kristen) обязан занять
    # столько же, сколько английская строка. Строки, у которых часть под карточкой (`заслонена`),
    # длину не дают — им кегль своей `группы` (письмо, карточка), медиана по открытым строкам.
    # Русский кегль — тот же, умноженный на отношение высот строчных двух гарнитур (метрика шрифта,
    # а не замер по размытой картинке).
    en_font = FONTS / spec["шрифт_англ"]
    en_stroke = spec.get("обводка_англ", 0)
    measured: dict[str, list[float]] = {}
    for ln in lines:
        if ln.cfg.get("заслонена"):
            continue
        a_, _, _, _ = render_strip(ln.cfg["англ_целиком"], en_font, 40.0, 1.0, en_stroke)
        cols = np.nonzero(a_.max(0) > 0.5)[0]
        size40 = (cols.max() - cols.min() + 1) / SS
        measured.setdefault(ln.cfg.get("группа", "письмо"), []).append(40.0 * (ln.u_end - ln.u_start) / size40)
    group = {g: float(np.median(v)) for g, v in measured.items()}

    # Низ строки по столбцам смещён: у круглых букв боковые столбцы кончаются выше строки — оценка
    # выше настоящей на несколько px (R_03: «worry» стоит на 405–410, оценка — 402). Смещение
    # меряется на себе: английский текст гарнитурой оригинала ставится на оценку и меряется тем же
    # способом; разница «намерено − поставлено» — смещение оценки, оно вычитается.
    for ln in lines:
        lc = ln.cfg
        if "как_строка" in lc:
            continue
        size_g = group[lc.get("группа", "письмо")]
        a_en = place(ln, lc["англ_целиком"], en_font, size_g, 1.0, en_stroke, ln.u_start, shape,
                     spec.get("размытие", 0.8))
        s_a, _ = strip(a_en, ln.c, ln.n, lc["полувысота"])
        got = measure(1 - s_a * (1 - ln.ink_ratio) < INK, lc["полувысота"], straight=lc.get("прямая", False))
        if not got:
            continue
        us = np.linspace(max(got[1][0], ln.u_meas[0]), min(got[1][1], ln.u_meas[1]), 30)
        bias = float(np.median(got[0](us) - ln.base_v(us)))
        old_v = ln.base_v
        ln.base_v = lambda x, f=old_v, b=bias: f(x) - b
        print(f"{lc['англ']!r}: смещение оценки низа {bias:+.1f} px")

    # строка почти вся под карточкой (`как_строка`): форма — соседней, а высота — по видимым
    # кусочкам: английский текст гарнитурой оригинала, сдвинутый на dy, должен лечь на них
    for i, ln in enumerate(lines):
        lc = ln.cfg
        if "как_строка" not in lc:
            continue
        size_g = group[lc.get("группа", "письмо")]
        best = None
        c0 = ln.c.copy()
        for dy in np.arange(-20, 20.5, 1.0):
            ln.c = c0 + np.array([0.0, dy])
            a_en = place(ln, lc["англ_целиком"], en_font, size_g, 1.0, en_stroke, ln.u_start, shape, 0) * ~card
            ours = a_en > 0.5
            inter = (ours & owns[i]).sum()
            score = inter / max(1, (ours | owns[i]).sum())
            if best is None or score > best[0]:
                best = (score, dy)
        if best[0] < 0.2 or abs(best[1]) >= 20:
            sys.exit(f"{lc['англ']!r}: видимые кусочки не сошлись (совпадение {best[0]:.2f}, сдвиг {best[1]:+.0f})")
        ln.c = c0 + np.array([0.0, best[1]])
        print(f"{lc['англ']!r}: по видимым кусочкам сдвиг {best[1]:+.0f} px, совпадение {best[0]:.2f}")

    out = base.copy()
    report = [f"кегль англичан по группам: " + ", ".join(f"{g} {v:.1f} ({len(measured[g])} строк)"
                                                         for g, v in group.items())]
    for ln in lines:
        lc = ln.cfg
        text = lc["англ_целиком"] if english else lc["текст"]
        font = FONTS / (spec["шрифт_англ"] if english else lc.get("шрифт", spec["шрифт"]))
        comp = 1.0 if english else lc.get("сжатие", spec.get("сжатие", 1.0))
        stroke = en_stroke if english else lc.get("обводка", spec.get("обводка", 0))
        blur = spec.get("размытие", 0.8)
        size = group[lc.get("группа", "письмо")]
        if not english:
            size *= x_height(en_font, "x") / x_height(font, "х") * lc.get("кегль_доля", spec.get("кегль_доля", 1.0))
        # где начинается текст: по английскому началу, концу, середине или якорю
        a_full, col0, _, f = render_strip(text, font, size, comp, stroke)
        width = f.getlength(text) / SS * comp
        how = "лево" if english else lc.get("по", "лево")
        if how == "лево":
            u0 = ln.u_start
        elif how == "право":
            u0 = ln.u_end - width
        elif how == "центр":
            u0 = (ln.u_start + ln.u_end) / 2 - width / 2
        else:                                   # якорь: {"с": подстрока, "x": где она начинается в кадре}
            pre = f.getlength(text[:text.index(how["с"])]) / SS * comp
            u0 = float(ln.t[np.abs(ln.c[:, 0] - how["x"]).argmin()]) - pre
        alpha = place(ln, text, font, size, comp, stroke, u0, shape, blur)
        if not lc.get("на_заслоне"):
            alpha *= ~card
            # огрызок буквы у кромки (верх «п» читался дефисом, кусок «и» — точкой на фаске):
            # видимый кусок ниже `огрызок` px по высоте — убрать
            stub = lc.get("огрызок", spec.get("огрызок", 0))
            if stub:
                lab_a, n_a = label(alpha > 0.2)
                edge_near = binary_dilation(card, iterations=3)
                for k in range(1, n_a + 1):
                    piece = lab_a == k
                    ys_k = np.nonzero(piece.any(1))[0]
                    if (piece & edge_near).any() and ys_k.max() - ys_k.min() + 1 < stub:
                        alpha[binary_dilation(piece, iterations=2)] = 0
        r = ln.ink_ratio
        out *= (1 - alpha * (1 - r))[..., None]
        s_a, _ = strip(alpha, ln.c, ln.n, lc["полувысота"])
        ours = 1 - s_a * (1 - r) < INK
        mm = measure(ours, lc["полувысота"])
        stem = 0.0
        if mm:
            mid = mm[0]((mm[1][0] + mm[1][1]) / 2) + lc["полувысота"]
            stem = stem_width(ours, mid - mm[2] * 0.8, mid - mm[2] * 0.2)
        report.append(f"{lc['англ']!r}: кегль {size:.1f}, строчные {ln.xh:.1f} px, штрих {ln.stem:.1f} (наш {stem:.1f}), "
                      f"краска {r:.2f}, начало u {u0:.0f} (англ {ln.u_start:.0f}–{ln.u_end:.0f}), длина {width:.0f}")
    # `вернуть` — рамки, где кадр — оригинал до пикселя (правка задела рисунок вне надписей:
    # R_03 — светлая черта на внутренней тени правого края карточки, 10 октября 2026)
    for x0, y0, x1, y1 in spec.get("вернуть", []):
        out[y0:y1, x0:x1] = E[y0:y1, x0:x1]
    res = np.clip(np.round(out), 0, 255).astype(np.uint8)
    img = Image.fromarray(res).convert("RGBA")
    img.putalpha(eng_rgba.getchannel("A"))
    return img, report, lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--english", action="store_true", help="проверка способа: набрать английским")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    img, report, _ = build(a.name, a.english)
    for r in report:
        print(r)
    out = a.out or ROOT / "work" / "graphics_ru" / "case4" / f"{a.name}.png"
    img.save(out)
    print("записано:", out)


if __name__ == "__main__":
    main()
