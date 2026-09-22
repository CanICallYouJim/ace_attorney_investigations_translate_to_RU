"""Экран заставки: вывеска шоу «Пеки и пляши» на экране телевизора (`cut02_037`).

Четвёртый способ набора картинки, рядом с `prints.py`, `notes.py` и `sign.py`.
Та же вывеска, что над тортом (`sign.py`, `cut02_032`), но кадр другой по природе
(разбор 21–22 сентября 2026, `docs/STATE.md`):

  * **подложку показывают другие языки — но не везде.** У семи языков надписи на тех
    же местах, `text_mask.py` честной подложки не даёт (логотип стирался призраком).
    Зато буквы у всех свои: где у немцев, корейцев, японцев своей надписи нет, там
    видна настоящая доска, кант доски, крем торта. Подложка берётся **оттуда**,
    а где её не показал никто — достраивается;
  * **свой у каждого языка — по сравнению языков, а не по рамке.** Надпись языка —
    насыщенные пиксели, которые не совпали с большинством других языков. Правило
    «общее — где совпало большинство» ошибается на цвете самих логотипов: нижние
    канты и заливки семи логотипов лежат на одной дуге и совпадают. Поэтому цвет
    материала логотипа (розовая заливка, кант, контур) общим рисунком не бывает;
  * **перед логотипом стоят венчик с шариком и два безе** — общие для всех языков.
    Они задаются точками с радиусом: без радиуса связность утекала по тонким общим
    линиям (кромка доски, край ленты) через весь логотип;
  * **экран выцвел бликом.** Цвета слова нейросети переносятся на цвета оригинала
    по материалам (таблица пар «нейросеть → экран»), пончику — своя таблица: его
    глазурь по цвету совпадает с бурым краем канта нейросети;
  * **кант и ореол — как у оригинала.** У англичан кант плоский хаки 11–15 px и белый
    ореол 4–8 px; у слова нейросети после сжатия 0,696 кант 8×12,5 px, ореол 1–2 px,
    и местами кант закрыт её нотой и венчиком. Буквы (красный контур и всё внутри,
    пончик) берутся у нейросети, кант и ореол строятся заново;
  * **нота английская, на родном месте.** Перенос её туда, где её рисует нейросеть,
    закрывал бабочку Самсона (проба №12, 22 сентября).

Задание — `work/graphics_ru/<дело>/screen.json`. Проверки (правило №13 — ни одна
не пользуется следом, который вычислила работа, кроме «правки за следом»):

  1. **остатки английского** — пиксель, где английский не совпал ни с одним из шести
     языков (то есть чисто английская надпись), а у нас остался как был;
  2. **правка за следом** — изменённое против английского вне следа и наших букв;
  3. **чужая краска** — цвет материала логотипа (розовая заливка, кант, контур)
     в зоне логотипа вне наших букв, переднего плана и ноты.

    tools\\screen.py                 набрать, записать PNG, маску букв и лист
    tools\\screen.py --check         ничего не писать, пересобрать и сверить с лежащим PNG
    tools\\screen.py --selftest      проверки обязаны краснеть на порче, посеянной по картинке

Пишет `<имя>.png`, `<имя>_ink.png`, лист — `work/graphics_masks/checks/screen.png`.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from common import WORK

RU = WORK / "graphics_ru"
EN = WORK / "graphics_en"
SHEET = WORK / "graphics_masks" / "checks" / "screen.png"
LANGS = ["eng", "ger", "fre", "kor", "sim", "tra", "base"]
T0 = time.time()


def say(*a) -> None:
    print(f"[{time.time() - T0:5.1f}s]", *a, flush=True)


def disk(r: int) -> np.ndarray:
    y, x = np.ogrid[-r:r + 1, -r:r + 1]
    return x * x + y * y <= r * r


# ---------------------------------------------------------------- материалы


def pinkfill(a: np.ndarray) -> np.ndarray:
    """Заливка букв логотипа: светлое розоватое — красный и синий выше зелёного."""
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (a.min(-1) >= 170) & (r - g >= 4) & (b - g >= 0)


def logolike(a: np.ndarray) -> np.ndarray:
    """Цвет материала логотипа: заливка, кант (хаки), контур (насыщенный розовый)."""
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    kant = (r - b > 40) & (g > 170) & (np.abs(r - g) < 30)
    outline = (a.max(-1) - a.min(-1) > 32) & (r > g) & (b > g)
    return pinkfill(a) | kant | outline


def boardlike(a: np.ndarray) -> np.ndarray:
    """Доска вывески и её торец: серое без оттенка, не белое, не синее."""
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return ((a.max(-1) - a.min(-1)) <= 20) & (lum >= 60) & (lum <= 185) & ((b - r) <= 15)


def normconv(vals: np.ndarray, weight: np.ndarray, radii, need: np.ndarray):
    """Нормированная свёртка: значение в `need` по весам источников, от мелкого радиуса
    к крупному. Возвращает значения и то, что не закрылось ни на одном радиусе."""
    thr = [0.25, 0.25, 0.2, 0.15, 0.1, 0.05, 0.02, 0.01]
    out = np.zeros(vals.shape, np.float32)
    todo = need.copy()
    for rad, t in zip(radii, thr):
        if not todo.any():
            break
        den = ndi.gaussian_filter(weight, rad)
        ok = todo & (den >= t)
        for c in range(vals.shape[-1]):
            num = ndi.gaussian_filter(vals[..., c] * weight, rad)
            out[..., c][ok] = num[ok] / den[ok]
        todo &= ~ok
    return out, todo


def remap(px: np.ndarray, pairs, power: float = 2.0) -> np.ndarray:
    """Перенос цвета по парам «материал нейросети → материал на экране»: смещение цвета
    интерполируется по обратным расстояниям до пар (Шепард). Переходы между материалами
    получают смесь смещений соседних пар, поэтому сглаживание краёв не ломается."""
    a = np.array([p[0] for p in pairs], np.float32)
    e = np.array([p[1] for p in pairs], np.float32)
    d2 = ((px[:, None, :] - a[None]) ** 2).sum(-1)
    w = 1.0 / (d2 + 1.0) ** power
    w /= w.sum(1, keepdims=True)
    return px + w @ (e - a)


# ---------------------------------------------------------------- кадр


class Frame:
    """Семь языковых вариантов кадра, обрезанные до рабочего окна."""

    def __init__(self, name: str, cfg: dict, variants: dict | None = None):
        import text_mask
        self.name = name
        self.win = tuple(cfg["окно"])
        x0, y0, x1, y1 = self.win
        full = variants or text_mask.load_variants(name)
        missing = [k for k in LANGS if k not in full]
        if missing:
            raise SystemExit(f"{name}: нет языковых вариантов {missing}")
        self.S = np.stack([np.asarray(full[k].convert("RGB"), np.int16)[y0:y1, x0:x1] for k in LANGS])
        self.full_en = np.asarray(full["eng"].convert("RGB"), np.int16)
        self.EN = self.S[0]
        self.N, self.H, self.W, _ = self.S.shape
        self.yy, self.xx = np.indices((self.H, self.W))
        tol = cfg.get("допуск", 10)
        self.match = np.zeros((self.N, self.H, self.W), np.int8)
        for i in range(self.N):
            for j in range(self.N):
                if i != j:
                    self.match[i] += np.abs(self.S[i] - self.S[j]).max(-1) <= tol
        self.sat = self.S.max(-1) - self.S.min(-1)
        # общий рисунок — совпал у большинства и не цвет материала логотипа
        self.common = (self.match >= cfg.get("большинство", 5)) & \
            ~np.stack([logolike(self.S[i]) for i in range(self.N)])

    def box(self, b) -> tuple[int, int, int, int]:
        """Рамка кадра -> рамка окна."""
        x0, y0 = self.win[:2]
        return b[0] - x0, b[1] - y0, b[2] - x0, b[3] - y0

    def pt(self, x: int, y: int) -> tuple[int, int]:
        return x - self.win[0], y - self.win[1]

    def zone(self, b) -> np.ndarray:
        m = np.zeros((self.H, self.W), bool)
        x0, y0, x1, y1 = self.box(b)
        m[max(0, y0):y1, max(0, x0):x1] = True
        return m


def front_of(F: Frame, cfg: dict) -> np.ndarray:
    """Передний план: общий кусок вокруг точки из задания в пределах радиуса. Венчик —
    синее и белое (у французов он сдвинут, отсюда «большинство», а не «все»), безе
    и шарик — любое не-доска."""
    bluish = ((F.EN[..., 2] - F.EN[..., 0]) > 6) | (F.EN.min(-1) > 200)
    front = np.zeros((F.H, F.W), bool)
    for x, y, rad, kind in cfg.get("передний_план", []):
        px, py = F.pt(x, y)
        pred = (F.match[0] >= cfg.get("большинство", 5)) & (bluish if kind == "венчик" else ~boardlike(F.EN))
        near = (F.xx - px) ** 2 + (F.yy - py) ** 2 <= rad * rad
        lab, _ = ndi.label(pred & near)
        if not lab[py, px]:
            raise SystemExit(f"передний план «{kind}» ({x}, {y}): точка не на общем рисунке — поправь задание")
        front |= lab == lab[py, px]
    return ndi.binary_dilation(front, iterations=1)


def own_parts(F: Frame, i: int, zone: np.ndarray, floor: int, piece: int, sat: int,
              frame=None) -> tuple[np.ndarray, np.ndarray]:
    """Своя надпись языка i: насыщенное и не общее; синее (нота) отдельно; куски
    от `piece` пикселей выше `floor`. С `frame` — только куски с центром в рамке:
    бабочка и роза Самсона насыщенные и «не общие» (над ними у немцев и французов
    свои ноты), но это персонаж, а не логотип (проба №13, 22 сентября 2026)."""
    own = (F.sat[i] > sat) & ~F.common[i] & zone
    blue = own & ((F.S[i][..., 2] - F.S[i][..., 0]) > 6)
    res = []
    fy = floor - F.win[1]
    for m in (own & ~blue, blue):
        lab, n = ndi.label(m)
        keep = np.zeros_like(m)
        if n:
            idx = range(1, n + 1)
            sizes = ndi.sum(m, lab, idx)
            ys = ndi.mean(F.yy, lab, idx)
            xs = ndi.mean(F.xx, lab, idx)
            ok = [k for k in range(n) if sizes[k] >= piece and ys[k] < fy]
            if frame is not None:
                fx0, fy0, fx1, fy1 = F.box(frame)
                ok = [k for k in ok if fx0 <= xs[k] <= fx1 and fy0 <= ys[k] <= fy1]
            keep = np.isin(lab, [k + 1 for k in ok])
        res.append(keep)
    return res[0], res[1]


def grow(m: np.ndarray, img: np.ndarray, fill_steps: int = 40, jump: int = 4,
         white_steps: int = 10, soft: int = 2) -> np.ndarray:
    """Рост маски надписи по самой картинке, а не вслепую:
    по розоватой заливке букв (до 40 px — у букв с разрывом насыщенного контура
    «закрыть пустоты» середину штриха не берёт, немецкая «e»), шаг через тёмный
    контур (4 px — ореол пончика за тёмным контуром), по белому ореолу (до 10 px:
    у англичан ореол 4–8 px, за ним сразу доска, и слепой рост на 14 px съедал
    полосу доски под буквами), сглаживание (2 px)."""
    g = m.copy()
    if fill_steps:
        pf = pinkfill(img)
        for _ in range(fill_steps):
            nxt = g | (ndi.binary_dilation(g) & pf)
            if (nxt == g).all():
                break
            g = nxt
    g = ndi.binary_dilation(g, structure=disk(jump))
    white = img.min(-1) > 200
    for _ in range(white_steps):
        g = g | (ndi.binary_dilation(g) & white)
    return ndi.binary_dilation(g, structure=disk(soft))


# ---------------------------------------------------------------- логотип


def substrate(F: Frame, foot: np.ndarray, front: np.ndarray, masks: list[np.ndarray],
              report: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Подложка под следом из других языков.

    Кандидат — язык, у которого здесь нет своей надписи и значение не похоже на
    материал логотипа. Берётся согласие двух (±10); иначе — ближайший к местному
    фону кандидат, если он от фона не дальше 10: японский логотип рисует под буквами
    тёмные тени на доске (в среднем на 6 уровней темнее, местами на 25), и одиночный
    японский кандидат приносил их призраками. Разнобой двух — дыра, а не среднее
    двух разных вещей.
    """
    ENf = F.EN.astype(np.float32)
    known = ~foot & ~front
    cand = np.stack([~masks[i - 1] & ~logolike(F.S[i]) & foot for i in range(1, F.N)])
    vals = F.S[1:].astype(np.float32)
    cnt = cand.sum(0)
    v = vals.copy()
    v[~cand] = np.nan
    with np.errstate(all="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        med = np.nanmedian(v, axis=0)
        spread = np.nan_to_num(np.nanmax(v, axis=0) - np.nanmin(v, axis=0)).max(-1)
    consensus = (cnt >= 2) & (spread <= 10)
    sub = ENf.copy()
    sub[consensus] = med[consensus]
    ref, _ = normconv(sub, (known | consensus).astype(np.float32), (3, 6, 12, 24, 48, 96),
                      foot & ~consensus)
    dist = np.abs(vals - ref[None]).max(-1)
    dist[~cand] = np.inf
    best, bestd = dist.argmin(0), dist.min(0)
    pick = ~consensus & foot & (bestd <= 10)
    py, px = np.nonzero(pick)
    sub[py, px] = vals[best[py, px], py, px]
    hole = foot & ~consensus & ~pick
    report.append(f"  подложка из языков: согласие {int(consensus.sum())}, один близкий к фону "
                  f"{int(pick.sum())}, дыр {int(hole.sum())} из {int(foot.sum())}")

    # доска ровная — кладётся гладким полем по её настоящим пикселям рядом;
    # подложка языков несёт их шум сжатия и тени
    kb = (known & boardlike(F.EN)).astype(np.float32)
    board, _ = normconv(ENf, kb, (4, 8, 16, 32, 64, 128), foot)
    smooth = foot & ~hole & boardlike(sub) & (np.abs(sub - board).max(-1) <= 14)
    sub[smooth] = board[smooth]
    kn = (known | consensus | pick).astype(np.float32)
    frac = ndi.gaussian_filter(kn * boardlike(sub), 8) / np.maximum(ndi.gaussian_filter(kn, 8), 1e-6)
    hole_board = hole & (frac >= 0.6)
    sub[hole_board] = board[hole_board]
    hole_rest = hole & ~hole_board
    report.append(f"  доска гладким полем: {int(smooth.sum())} + дыр на доске {int(hole_board.sum())}; "
                  f"прочих дыр {int(hole_rest.sum())}")
    return sub, hole_rest, known


def place(img: np.ndarray, art_box, art_kant, kant, win, fill_mode: str):
    """Кроп нейросети -> окно кадра: масштаб по канту, дробный сдвиг ресэмплингом.
    Рамка ресэмплинга не может начинаться левее нуля — отсюда поля по краям."""
    ax0, ay0, ax1, ay1 = art_box
    kx = (kant[2] - kant[0]) / (art_kant[2] - art_kant[0])
    ky = (kant[3] - kant[1]) / (art_kant[3] - art_kant[1])
    fx0 = kant[0] + (ax0 - art_kant[0]) * kx - win[0]
    fy0 = kant[1] + (ay0 - art_kant[1]) * ky - win[1]
    ix0, iy0 = int(np.floor(fx0)), int(np.floor(fy0))
    nw = int(np.ceil(fx0 + (ax1 - ax0) * kx)) - ix0
    nh = int(np.ceil(fy0 + (ay1 - ay0) * ky)) - iy0
    pad = 8
    padw = ((pad, pad), (pad, pad), (0, 0)) if img.ndim == 3 else pad
    im = Image.fromarray(np.pad(img, padw, mode=fill_mode))
    box = ((ix0 - fx0) / kx + pad, (iy0 - fy0) / ky + pad,
           (ix0 - fx0 + nw) / kx + pad, (iy0 - fy0 + nh) / ky + pad)
    return np.asarray(im.resize((nw, nh), Image.LANCZOS, box=box), np.float32), ix0, iy0, kx, ky


def paste(canvas_shape, patch: np.ndarray, ix0: int, iy0: int) -> np.ndarray:
    out = np.zeros(canvas_shape + patch.shape[2:], np.float32)
    H, W = canvas_shape
    y0, x0 = max(0, iy0), max(0, ix0)
    y1, x1 = min(H, iy0 + patch.shape[0]), min(W, ix0 + patch.shape[1])
    out[y0:y1, x0:x1] = patch[y0 - iy0:y1 - iy0, x0 - ix0:x1 - ix0]
    return out


def word_of(cfg: dict, spec_dir: Path, report: list[str]):
    """Буквы слова из рисунка нейросети: наклейка без тёмного фона, обрезанная по стене
    канта (с нотой нейросети в стене — иначе «П» не замыкается), без ноты, венчика
    и шарика нейросети. Белая обводка делится по расстоянию: ближе к канту — буква,
    ближе к ноте или венчику — вон."""
    art = np.asarray(Image.open((spec_dir / cfg["арт"]).resolve()).convert("RGB"), np.int16)
    ax0, ay0, ax1, ay1 = cfg["рамка_в_арте"]
    crop = art[ay0:ay1, ax0:ax1]
    r, g, b = crop[..., 0], crop[..., 1], crop[..., 2]
    yy, xx = np.indices(r.shape)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    lab0, _ = ndi.label(lum < cfg.get("фон_темнее", 105))
    edge = set(np.unique(np.concatenate([lab0[0], lab0[-1], lab0[:, 0], lab0[:, -1]]))) - {0}
    old = ~np.isin(lab0, list(edge))
    gold = (r > 150) & (g > 90) & (g < 215) & (b < 110) & (r - b > 90)
    gl_lab, gl_n = ndi.label(gold)
    idx = range(1, gl_n + 1)
    gsz = ndi.sum(gold, gl_lab, idx)
    gtop = ndi.minimum(yy, gl_lab, idx)
    # кант слова начинается выше; лента нейросети («золотая» тоже) — ниже
    top_limit = cfg.get("кант_выше", 600) - ay0
    gold = np.isin(gl_lab, [k + 1 for k in range(gl_n) if gsz[k] >= 2000 and gtop[k] < top_limit])
    note_x = cfg.get("нота_левее", 800) - ax0
    blue = (b - r > 25) & (b > 50)
    orange = (r > 200) & (g > 70) & (g < 170) & (b < 90) & (r - b > 120)
    orange[:, :cfg["кант_в_арте"][2] - 60 - ax0] = False
    occl = ndi.binary_dilation(blue | orange, iterations=1)
    wh = crop.min(-1) > 190
    d_gold = ndi.distance_transform_edt(~gold)
    d_occ = ndi.distance_transform_edt(~occl)
    theirs = occl | (wh & (d_occ < d_gold) & (d_occ <= 8))
    # пончик — глазурь формой: сплошное пятно, а не тонкий бурый край канта того же цвета
    gl = (r > 110) & (r < 200) & (g < 95) & (b < 60) & (r - g > 50)
    op = ndi.binary_opening(gl, structure=disk(4))
    lab2, n2 = ndi.label(op)
    s2 = ndi.sum(op, lab2, range(1, n2 + 1))
    donut = ndi.binary_dilation(ndi.binary_fill_holes(lab2 == int(np.argmax(s2)) + 1), structure=disk(9))
    # буквы: красный контур и всё, что он обносит, + пончик
    red = (r > 140) & (g < 90) & (b < 120) & (r - g > 80)
    wall = red | ndi.binary_dilation(blue & (xx < note_x), structure=disk(8))
    letters = ndi.binary_fill_holes(ndi.binary_closing(wall, structure=disk(2))) | donut
    letters &= ~theirs & old
    lab3, n3 = ndi.label(letters)
    s3 = ndi.sum(letters, lab3, range(1, n3 + 1))
    letters = np.isin(lab3, [k + 1 for k in range(n3) if s3[k] >= 1500])
    src = crop.astype(np.float32)
    out = src.copy()
    m1, m2 = letters & ~donut, letters & donut
    out[m1] = remap(src[m1], cfg["палитра"])
    out[m2] = remap(src[m2], cfg["пончик"])
    report.append(f"  буквы нейросети: {int(letters.sum())} пикс. (пончик {int(m2.sum())}), "
                  f"вынуто ноты и венчика нейросети {int((old & theirs).sum())}")
    return out, letters, gold


def logo(F: Frame, cfg: dict, front: np.ndarray, spec_dir: Path, report: list[str]):
    """Русский логотип вместо английского. Возвращает картинку окна, маску наших букв
    (с нотой), след английской надписи и сведения для проверок."""
    L = cfg["логотип"]
    zone = F.zone(L["зона"])
    piece, sat = L.get("кусок_от", 300), L.get("насыщенность", 32)
    # рамка своих кусков: кант с запасом, справа шире — там кант «p» уходит за венчик
    # и виден сквозь его петлю (куски у 1341–1351 при крае канта 1315)
    kant_frame = [L["кант"][0] - 15, L["кант"][1] - 15, L["кант"][2] + 45, L["кант"][3] + 15]
    # у английского — куски от 20 px: петля венчика сквозная, и между прутьями видны
    # кусочки канта «p» меньше 300 px; отбор «от 300» их выбрасывал, и они оставались
    # (поймала проверка «остатки английского», 22 сентября 2026)
    ink_en, _ = own_parts(F, 0, zone, L["низ"], L.get("свой_кусок_от", 20), sat, frame=kant_frame)
    _, blue_en = own_parts(F, 0, zone, L["низ"], piece, sat)
    core = ndi.binary_fill_holes(ink_en)
    white_en = (F.EN.min(-1) > 215) & (F.sat[0] < 30)
    note = blue_en.copy()
    for _ in range(10):
        note |= ndi.binary_dilation(note) & white_en
    note = ndi.binary_dilation(note, iterations=1)
    # у английских букв контур замкнут — роста по заливке не нужно, а в розоватый
    # крем торта он уходил и оставлял пятно на руке Самсона (проба №10)
    foot = ((core | grow(core, F.EN, fill_steps=0)) | note) & ~front
    report.append(f"  английский логотип: ядро {int(core.sum())}, след {int(foot.sum())}, "
                  f"нота {int(note.sum())}, передний план {int(front.sum())}")
    masks = []
    for i in range(1, F.N):
        ink, blue = own_parts(F, i, zone, L["низ"], piece, sat)
        masks.append(grow(ndi.binary_fill_holes(ink | blue), F.S[i]))
    sub, hole_rest, known = substrate(F, foot, front, masks, report)

    rgb, letters, gold = word_of(L, spec_dir, report)
    win = F.win
    rgb_t, ix0, iy0, kx, ky = place(np.clip(rgb, 0, 255).astype(np.uint8), L["рамка_в_арте"],
                                    L["кант_в_арте"], L["кант"], win, "edge")
    let_t, *_ = place((letters * 255).astype(np.uint8), L["рамка_в_арте"], L["кант_в_арте"], L["кант"], win, "constant")
    gold_t, *_ = place((gold * 255).astype(np.uint8), L["рамка_в_арте"], L["кант_в_арте"], L["кант"], win, "constant")
    word_rgb = paste((F.H, F.W), rgb_t, ix0, iy0)
    aL = np.clip(paste((F.H, F.W), let_t, ix0, iy0) / 255.0, 0, 1)
    goldT = paste((F.H, F.W), gold_t, ix0, iy0) > 127
    report.append(f"  слово по канту: масштаб {kx:.4f} x {ky:.4f} (сжатие {kx / ky:.3f})")

    # кант и ореол по образцу оригинала: кант — полоса вокруг букв, просветы, залитые
    # у нейросети золотом (у «П», «ш»), — тоже кант, щели до 8 px смыкаются кантом,
    # как у англичан сливаются канты соседних букв; ореол — снаружи
    K, Hh = L["кант_px"], L["ореол_px"]
    Lm = aL > 0.5
    kant_m = ndi.binary_dilation(Lm, structure=disk(K))
    kant_m |= goldT & ndi.binary_dilation(Lm, structure=disk(K + 4))
    kant_m = ndi.binary_closing(kant_m, structure=disk(4))
    d_out = ndi.distance_transform_edt(~kant_m)
    a_kant = ndi.gaussian_filter(kant_m.astype(np.float32), 0.6)
    a_halo = np.clip(Hh + 0.5 - d_out, 0, 1)
    halo_rgb = np.array(L["цвет_ореола"], np.float32)
    kant_rgb = np.array(L["цвет_канта"], np.float32)
    st = np.ones((F.H, F.W, 3), np.float32) * halo_rgb
    st = st * (1 - a_kant[..., None]) + kant_rgb * a_kant[..., None]
    st = st * (1 - aL[..., None]) + word_rgb * aL[..., None]
    alpha = np.maximum(np.maximum(a_halo, aL), a_kant)

    # прочие дыры — реставрацией от краёв (левый нижний угол: крем, кромка торта, сцена)
    under = ndi.binary_erosion(alpha > 0.999, structure=disk(2))
    need = hole_rest & ~under
    # источники реставрации — только фон за логотипом: безе и венчик стоят перед ним,
    # лента ниже (по цвету она как кант); их цвет тёк в дыру у ножки «p» (22 сентября)
    not_source = hole_rest | front | (logolike(sub) & ~foot)
    base8 = np.clip(sub, 0, 255).astype(np.uint8)
    rest = cv2.cvtColor(cv2.inpaint(cv2.cvtColor(base8, cv2.COLOR_RGB2BGR),
                                    not_source.astype(np.uint8) * 255, 6, cv2.INPAINT_TELEA),
                        cv2.COLOR_BGR2RGB).astype(np.float32)
    filled = sub.copy()
    filled[need] = rest[need]
    report.append(f"  прочих дыр вне слова {int(need.sum())} — реставрация от краёв")

    out = filled * (1 - alpha[..., None]) + st * alpha[..., None]
    ENf = F.EN.astype(np.float32)
    out[front] = ENf[front]
    out[note] = ENf[note]                              # нота на родном месте, поверх
    ink = ((alpha > 0.5) & ~front) | note
    report.append(f"  наклейка: буквы {int(Lm.sum())}, кант {K} px, ореол {Hh} px; "
                  f"наших пикселей {int(ink.sum())}")
    return out, ink, foot, note


# ---------------------------------------------------------------- проверки


def english_only(F: Frame, tol: int) -> np.ndarray:
    """Чисто английское: пиксель, где английский не совпал ни с одним из шести языков.
    Считается по языкам, без следа и масок работы."""
    return F.match[0] == 0 if tol == F.__dict__.get("_tol") else \
        np.all(np.stack([np.abs(F.S[0] - F.S[i]).max(-1) > tol for i in range(1, F.N)]), 0)


def checks(F: Frame, cfg: dict, out: np.ndarray, ink: np.ndarray, allowed: np.ndarray,
           keep: np.ndarray, front: np.ndarray, least: int = 15):
    """Три находки. Возвращает словарь масок находок и строки отчёта."""
    ENf = F.EN.astype(np.float32)
    same = np.abs(out - ENf).max(-1) <= 6
    mine = ndi.binary_dilation(ink, structure=disk(2))
    judged = F.zone(cfg["судить"])
    # 1. остатки английского: чисто английское осталось как было, и это не мы
    only = english_only(F, cfg.get("допуск_языков", 24))
    # Чисто английским бывает и английский ФОН: где у всех шести других языков буквы,
    # английская доска «ни с кем не совпала». Надписью доска не бывает — её цвет
    # (серое без оттенка у медианы доски в зоне суда) из остатков вычитается.
    bl = boardlike(ENf) & judged
    board_med = np.median(ENf[bl], axis=0) if bl.any() else np.array([132, 129, 136], np.float32)
    board_en = boardlike(ENf) & (np.abs(ENf - board_med).max(-1) <= cfg.get("допуск_доски", 16))
    left = only & same & ~mine & ~keep & judged & ~board_en
    # 2. правка за следом: изменено против английского вне разрешённого
    moved = (~same) & ~ndi.binary_dilation(allowed | ink, structure=disk(2))
    # 3. чужая краска: цвет материала логотипа в зоне логотипа вне наших букв.
    # Крем торта розоватый, как заливка букв. Наш пиксель — рисунок, а не краска, если
    # его значение показывают хотя бы два языка: английский остаток показывает один
    # английский, а крем, взятый из подложки других языков, — все, у кого он виден
    # Цвет канта и контура так не прощается: нижние канты семи логотипов лежат на одной
    # дуге, и пятно канта под словом «показывают» три языка — самопроверка его не видела
    # (22 сентября). Кант и контур — рисунок, только если их показывают почти все
    # (лента, кромка торта — все семь).
    lz = F.zone(cfg["логотип"]["зона_краски"])
    shown = np.zeros(same.shape, np.int8)
    for i in range(F.N):
        shown += np.abs(out - F.S[i]).max(-1) <= cfg.get("допуск", 10)
    oc = np.clip(out, 0, 255)
    ours = ndi.binary_dilation(ink, structure=disk(3)) | front | keep
    strong = logolike(oc) & ~pinkfill(oc)
    paint = lz & ~ours & ((strong & (shown < 5)) | (pinkfill(oc) & (shown < 2)))
    found, lines = {}, []
    for key, m, what in (("остатки", left, "остатки английского"),
                         ("за_следом", moved, "правка за следом"),
                         ("краска", paint, "чужая краска цвета логотипа")):
        lab, n = ndi.label(m)
        sizes = ndi.sum(m, lab, range(1, n + 1)) if n else []
        big = [k + 1 for k in range(n) if sizes[k] >= least]
        found[key] = np.isin(lab, big)
        boxes = []
        for k in big[:4]:
            ys, xs = np.nonzero(lab == k)
            boxes.append(f"{int(sizes[k - 1])} пикс. ({xs.min() + F.win[0]}, {ys.min() + F.win[1]}, "
                         f"{xs.max() + F.win[0]}, {ys.max() + F.win[1]})")
        lines.append(f"  {what}: {int(found[key].sum())} пикс. в {len(big)} кусках"
                     + (" — " + "; ".join(boxes) if boxes else ""))
    lines.append(f"  судили пикселей: {int(judged.sum())}, из них чисто английских в оригинале "
                 f"{int((only & judged).sum())}")
    return found, lines


# ---------------------------------------------------------------- сборка


def compose(name: str, cfg: dict, case: str, variants=None):
    spec_dir = RU / case
    report: list[str] = [f"{name}:"]
    F = Frame(name, cfg, variants)
    report.append(f"  окно {F.win}, языков {F.N}")
    front = front_of(F, cfg)
    out, ink, foot, note = logo(F, cfg, front, spec_dir, report)
    allowed = foot.copy()
    return F, out, ink, allowed, note, front, report


def to_full(F: Frame, win_img: np.ndarray) -> np.ndarray:
    full = F.full_en.astype(np.float32).copy()
    x0, y0, x1, y1 = F.win
    full[y0:y1, x0:x1] = win_img
    return full


def mask_full(F: Frame, m: np.ndarray) -> np.ndarray:
    full = np.zeros(F.full_en.shape[:2], bool)
    x0, y0, x1, y1 = F.win
    full[y0:y1, x0:x1] = m
    return full


def sheet(rows, path: Path) -> None:
    pad, gap = 26, 8
    w = max(im.shape[1] for _, ims in rows for im in ims)
    h = sum(pad + sum(im.shape[0] for im in ims) + gap for _, ims in rows)
    canvas = Image.new("RGB", (w, h), (20, 20, 20))
    d = ImageDraw.Draw(canvas)
    y = 0
    for title, ims in rows:
        d.text((6, y + 6), title, fill=(235, 235, 235))
        y += pad
        for im in ims:
            canvas.paste(Image.fromarray(np.clip(im, 0, 255).astype(np.uint8)), (0, y))
            y += im.shape[0]
        y += gap
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def verdict_map(F: Frame, out: np.ndarray, found: dict, ink: np.ndarray, keep: np.ndarray,
                front: np.ndarray, judged: np.ndarray) -> np.ndarray:
    """Лист в три цвета: красное — находки, зелёное — наши буквы, синее — не судили
    (нота, передний план, всё вне зоны суда)."""
    v = out * 0.45
    v[~judged | keep | front] = v[~judged | keep | front] * 0.5 + np.array([0, 0, 110])
    v[ink & ~keep] = v[ink & ~keep] * 0.5 + np.array([0, 110, 0])
    for m in found.values():
        v[m] = (255, 30, 30)
    return v


def run_one(name: str, cfg: dict, case: str, mode: str, variants=None) -> tuple[list[str], list]:
    F, out, ink, allowed, note, front, report = compose(name, cfg, case, variants)
    found, lines = checks(F, cfg, out, ink, allowed, note, front)
    report += lines
    problems = [f"{name}: {what}" for what, m in (("остатки английского", found["остатки"]),
                                                   ("правка за следом", found["за_следом"]),
                                                   ("чужая краска", found["краска"])) if m.any()]
    full = to_full(F, out)
    png = RU / case / f"{name}.png"
    if mode == "check":
        if not png.exists():
            problems.append(f"{name}: нет {png} — прогнать tools/screen.py")
        else:
            have = np.asarray(Image.open(png).convert("RGB"), np.int16)
            if np.abs(have - np.clip(np.round(full), 0, 255).astype(np.int16)).max() > 0:
                problems.append(f"{name}: PNG не совпадает с набором по заданию — tools/screen.py")
    elif mode == "write":
        Image.fromarray(np.clip(np.round(full), 0, 255).astype(np.uint8)).save(png)
        Image.fromarray((mask_full(F, ink) * 255).astype(np.uint8)).save(RU / case / f"{name}_ink.png")
        report.append(f"  записано: {png}")
    judged = F.zone(cfg["судить"])
    V = F.box(cfg.get("лист", cfg["судить"]))
    rows = [(f"{name}: оригинал | результат | красное — находки, зелёное — наши буквы, синее — не судили",
             [F.EN[V[1]:V[3], V[0]:V[2]].astype(np.float32), out[V[1]:V[3], V[0]:V[2]],
              verdict_map(F, out, found, ink, note, front, judged)[V[1]:V[3], V[0]:V[2]]])]
    return report + [f"  БЕДА: {p}" for p in problems], (problems, rows, F, out, ink, allowed, note, front)


def selftest(name: str, cfg: dict, case: str) -> int:
    """Проверки обязаны краснеть. Порча сеется по картинке, а не по маске набора:
    кусок английского оригинала на место, где у англичан были буквы (берутся точки,
    где английский чисто свой по языкам); правка на занавесе вдали от надписей."""
    lines, (problems, _, F, out, ink, allowed, note, front) = run_one(name, cfg, case, "none")
    for ln in lines:
        print(ln)
    bad = 0
    if problems:
        print("  самопроверка: чистый набор уже не проходит — сначала починить набор")
        return 1
    ENf = F.EN.astype(np.float32)
    only = english_only(F, cfg.get("допуск_языков", 24)) & F.zone(cfg["судить"])
    ys, xs = np.nonzero(only & ~ndi.binary_dilation(ink, structure=disk(6)))
    if not len(ys):
        print("  самопроверка: не нашлось чисто английского вне наших букв — посеять нечего")
        return 1
    y, x = int(np.median(ys)), int(xs[np.argsort(np.abs(ys - np.median(ys)))[0]])
    spoiled = out.copy()
    spoiled[max(0, y - 12):y + 12, max(0, x - 12):x + 12] = ENf[max(0, y - 12):y + 12, max(0, x - 12):x + 12]
    found, _ = checks(F, cfg, spoiled, ink, allowed, note, front)
    ok1 = found["остатки"].any()
    print(f"  порча «вернули английский кусок у ({x + F.win[0]}, {y + F.win[1]})»: "
          f"{'поймана' if ok1 else 'НЕ ПОЙМАНА'}")
    bad += not ok1
    # правка вдали: точка окна дальше 30 px от всего, что работа имела право менять
    far = ~ndi.binary_dilation(allowed | ink, structure=disk(30))
    far[:20] = far[-20:] = False
    far[:, :20] = far[:, -20:] = False
    ys, xs = np.nonzero(far)
    cy, cx = int(ys[len(ys) // 2]), int(xs[len(xs) // 2])
    spoiled = out.copy()
    spoiled[cy:cy + 20, cx:cx + 20] += 40
    found, _ = checks(F, cfg, spoiled, ink, allowed, note, front)
    ok2 = found["за_следом"].any()
    print(f"  порча «правка вдали от надписей у ({cx + F.win[0]}, {cy + F.win[1]})»: "
          f"{'поймана' if ok2 else 'НЕ ПОЙМАНА'}")
    bad += not ok2
    # пятно канта на доске: доска в зоне краски дальше 8 px от наших букв
    lz = F.zone(cfg["логотип"]["зона_краски"])
    free = lz & boardlike(np.clip(out, 0, 255)) & ~ndi.binary_dilation(ink | front | note, structure=disk(8))
    ys, xs = np.nonzero(ndi.binary_erosion(free, structure=disk(6)))
    zy, zx = int(ys[len(ys) // 2]), int(xs[len(xs) // 2])
    spoiled = out.copy()
    spoiled[zy - 5:zy + 5, zx - 5:zx + 5] = cfg["логотип"]["цвет_канта"]
    found, _ = checks(F, cfg, spoiled, ink, allowed, note, front)
    ok3 = found["краска"].any()
    print(f"  порча «пятно канта на доске у ({zx + F.win[0]}, {zy + F.win[1]})»: "
          f"{'поймана' if ok3 else 'НЕ ПОЙМАНА'}")
    bad += not ok3
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", default="case3")
    ap.add_argument("--only")
    ap.add_argument("--check", action="store_true", help="ничего не писать, сверить с лежащим PNG")
    ap.add_argument("--selftest", action="store_true", help="проверки обязаны краснеть на порче")
    args = ap.parse_args()
    spec_path = RU / args.case / "screen.json"
    if not spec_path.exists():
        # «нечего сверять» — провал, а не тишина (класс упавшего пути prints.py --check)
        print(f"нет задания {spec_path} — набирать нечего")
        return 2 if (args.check or args.selftest) else 0
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    names = [n for n, c in spec.items() if isinstance(c, dict) and (not args.only or n == args.only)]
    if not names:
        print("в задании нет картинок — сверять нечего")
        return 2
    if args.selftest:
        return max(selftest(n, spec[n], args.case) for n in names)
    all_rows, problems = [], []
    for name in names:
        lines, (probs, rows, *_rest) = run_one(name, spec[name], args.case, "check" if args.check else "write")
        for ln in lines:
            print(ln)
        problems += probs
        all_rows += rows
    if all_rows and not args.check:
        sheet(all_rows, SHEET)
        print(f"лист: {SHEET}")
    print(f"сверено картинок: {len(names)}")
    for p in problems:
        print(f"  БЕДА: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
