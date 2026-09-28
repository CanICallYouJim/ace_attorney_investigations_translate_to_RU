"""Печатные надписи на картинке: снять английскую подложкой, набрать русскую по её замеру.

Наследник `relabel.py` для картинок, у которых есть подложка `text_mask.py`. Разница
в том, из-за чего пользователь 13 сентября 2026 забраковал старый набор:

  * **снятие.** `relabel.py` ищет буквы по цвету и затягивает дыру соседями. Что цветом
    не опознано — остаётся: под «Конь» на плане 24 марта так и жил хвост английской `g`.
    Здесь снимаются **куски английских чернил** (`check_pictures.english_ink`) целиком,
    а на их место кладётся настоящая подложка — та, что показали другие языки;
  * **кегль и ширина — замером, а не на глаз.** Кегль подбирается так, чтобы **тот же
    английский текст**, набранный нашей гарнитурой, сел в рамку английских чернил
    по высоте; сжатие — чтобы совпал по ширине. Поэтому русская надпись выходит
    ростом и весом в оригинал, а не «заметно уже и блёкло»;
  * **штрих.** Контур добавляется, только если наши буквы тоньше английских: сравнение
    тем же счётом, каким судит `check_pictures.py` (площадь на длину границы);
  * **маска букв.** `<имя>_ink.png` — что именно мы нарисовали. Без неё проверка
    вынуждена **угадывать** русские буквы и записывает их в «испорченную подложку».

Задание — тот же `labels.json`, картинке добавляется `"по_оригиналу": true`, а каждой
надписи — `"англ"` (что стоит в оригинале; по нему и идёт замер). `relabel.py` такие
картинки пропускает, чтобы не набрать их дважды.

    tools\\prints.py work/graphics_ru/case1/labels.json
    tools\\prints.py work/graphics_ru/case1/labels.json --only cut00_007
    tools\\prints.py work/graphics_ru/case1/labels.json --check   ничего не писать, сверить с лежащим

Пишет `<имя>.png` (основа для `notes.py`), `<имя>_print_ink.png` и `<имя>_ink.png`.
Порядок сборки картинки — `make notes`: сперва печатное, потом рукописное.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import check_pictures as cp
from common import WORK
from notes import STAGE, red
from relabel import remap

RU = WORK / "graphics_ru"
EN = WORK / "graphics_en"

FONT_DIR = Path("C:/Windows/Fonts")
REACH = 10          # кусок английских чернил ближе этого к рамке надписи — её буква
GROW = 2            # на столько расширяется снимаемый кусок: сглаживание по краю
LINE_GAP = 6        # межстрочное у многострочной надписи, как в relabel.py
THIN = 0.92         # наши буквы тоньше этой доли английских — добавить контур
FAT = 0.95          # кант растёт, пока штрих не догонит эту долю английского


def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / f"{name.split('@')[0].split('^')[0]}.ttf"), size)


def render(text: str, font_name: str, size: int, sw: float, squeeze: float):
    """Строка маской, точка опоры в ней (левый край базовой линии) и рамка чернил от опоры.

    Дробный `sw` (контур надписи, 27 сентября 2026: визитка `itm02_024` — 0 тонко, 1 жирно)
    набирается вчетверо крупнее с контуром `4·sw` и уменьшается."""
    # «гарнитура@k» — растровый шрифт: набор в k раз мельче и увеличение без сглаживания
    # (термобилет `cut03_001`: точечная печать, ступеньки видны; 27 сентября 2026)
    if "@" in font_name:
        base, k = font_name.split("@")
        k = int(k)
        im, (ox, oy), _ = render(text, base, max(4, round(size / k)), sw, squeeze)
        im = im.point(lambda v: 255 if v > 110 else 0).resize((im.width * k, im.height * k), Image.NEAREST)
        ox, oy = ox * k, oy * k
        bb = im.getbbox()
        return im, (ox, oy), (bb[0] - ox, bb[1] - oy, bb[2] - ox, bb[3] - oy)
    # «гарнитура^N» — курсив на N° сильнее, чем у самой гарнитуры: сдвиг по x
    # пропорционально высоте над базовой линией, базовая линия на месте (журнал
    # `cut04_017`: у английских букв наклон ~18°, у Century Gothic курсива ~10°;
    # 29 сентября 2026)
    if "^" in font_name:
        base, deg = font_name.split("^")
        im, (ox, oy), _ = render(text, base, size, sw, squeeze)
        t = math.tan(math.radians(float(deg)))
        extra = math.ceil(t * oy) + 2
        im = im.transform((im.width + extra, im.height), Image.AFFINE,
                          (1, t, -t * oy, 0, 1, 0), resample=Image.BICUBIC)
        bb = im.getbbox()
        return im, (ox, oy), (bb[0] - ox, bb[1] - oy, bb[2] - ox, bb[3] - oy)
    if sw != int(sw):
        im, (ox, oy), _ = render(text, font_name, size * 4, round(sw * 4), squeeze)
        im = im.resize((max(1, round(im.width / 4)), max(1, round(im.height / 4))), Image.LANCZOS)
        ox, oy = ox / 4, oy / 4
        # рамка — без бледной каймы сглаживания от уменьшения: с ней буквы «выше»
        # на 2 px сверху и снизу, и подбор кегля мельчил вдвое
        bb = im.point(lambda v: 255 if v > 64 else 0).getbbox()
        return im, (ox, oy), (bb[0] - ox, bb[1] - oy, bb[2] - ox, bb[3] - oy)
    sw = int(sw)
    font = load_font(font_name, size)
    pad = size * 2
    im = Image.new("L", (int(font.getlength(text)) + 4 * pad, 4 * size), 0)
    ImageDraw.Draw(im).text((pad, 3 * size), text, font=font, fill=255, anchor="ls",
                            stroke_width=sw, stroke_fill=255)
    ox, oy = pad, 3 * size
    if squeeze != 1.0:
        im = im.resize((max(1, round(im.width * squeeze)), im.height), Image.LANCZOS)
        ox *= squeeze
    bb = im.getbbox()
    return im, (ox, oy), (bb[0] - ox, bb[1] - oy, bb[2] - ox, bb[3] - oy)


def solid(im: Image.Image) -> Image.Image:
    """Ядро букв: сглаженный край в замер штриха и в маску не идёт."""
    return im.point(lambda v: 255 if v > 127 else 0)


def pick_size(text: str, font_name: str, sw: int, squeeze: float, want: float) -> int:
    """Кегль, при котором английский текст нашей гарнитурой равен английским чернилам по высоте."""
    def high(size: int) -> float:
        bb = render(text, font_name, size, sw, squeeze)[2]
        return bb[3] - bb[1]

    lo, hi = 6, 200
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if high(mid) < want:
            lo = mid
        else:
            hi = mid
    return min((lo, hi), key=lambda s: abs(high(s) - want))


def cyrillic_fonts() -> list[str]:
    """Шрифты машины, у которых есть кириллица: «Я» нарисована, а не подменена квадратиком."""
    out = []
    for path in sorted(FONT_DIR.glob("*.ttf")):
        try:
            font = ImageFont.truetype(str(path), 40)
            ours = font.getmask("Я", mode="L")
            none = font.getmask("￾", mode="L")
        except OSError:
            continue
        if ours.size == (0, 0) or bytes(ours) == bytes(none):
            continue
        out.append(path.stem)
    return out


def match_font(text: str, mask: Image.Image, bb, names: list[str]) -> list[tuple[float, str, int, float, int]]:
    """Какой гарнитурой набран оригинал: тот же английский текст против самих английских букв.

    Каждый шрифт подгоняется под чернила по высоте и ширине (кегль и сжатие), потом
    считается доля совпавших пикселей (IoU). Тот же замер выбрал Segoe UI Bold плашкам
    ситуации 15 сентября 2026 — глазами гарнитуру не угадать."""
    want_h, want_w = bb[3] - bb[1], bb[2] - bb[0]
    ink = mask.crop(bb)
    rows = []
    for name in names:
        try:
            size = pick_size(text, name, 0, 1.0, want_h)
            wide = render(text, name, size, 0, 1.0)[2]
            squeeze = min(1.6, max(0.45, want_w / max(1, wide[2] - wide[0])))
            size = pick_size(text, name, 0, squeeze, want_h)
            im, _, rel = render(text, name, size, 0, squeeze)
        except OSError:
            continue
        piece = solid(im)
        box = piece.getbbox()
        piece = piece.crop(box).resize((want_w, want_h), Image.LANCZOS).point(lambda v: 255 if v > 127 else 0)
        both = ImageChops.multiply(piece, ink).histogram()[255]
        union = ImageChops.lighter(piece, ink).histogram()[255]
        rows.append((both / max(1, union), name, size, squeeze, cp.stroke(piece)))
    return sorted(rows, reverse=True)


def parts_of(eng: Image.Image, E: Image.Image, labels: list, reach: int = REACH) -> list[Image.Image]:
    """Английские чернила каждой надписи: кусок уходит той рамке, где его больше.

    Рамки соседних надписей на плане стоят вплотную («Lead» над «Rook»), и кусок,
    задевший обе, по одному касанию ушёл бы в обе сразу: замер «Rook» тогда мерил
    две надписи разом и завышал высоту вдвое."""
    boxes = [(lb["box"][0] - reach, lb["box"][1] - reach, lb["box"][2] + reach, lb["box"][3] + reach)
             for lb in labels]
    out = [Image.new("L", eng.size, 0) for _ in labels]
    ops = [im.load() for im in out]
    ep = E.load()
    for comp in cp.components(eng):
        if 2 * sum(1 for p in comp if red(ep[p])) >= len(comp):
            continue                       # красное — рука, её набирает notes.py
        votes = []
        for lb, (x0, y0, x1, y1) in zip(labels, boxes):
            pts = [straight(lb, x, y) for x, y in comp] if lb.get("наклон") and "центр" in lb else comp
            votes.append(sum(1 for x, y in pts if x0 <= x < x1 and y0 <= y < y1))
        # ничья — той рамке, чья середина ближе к куску по высоте, потом по ширине (точка над «i» в «Eddie»
        # лежит и в рамке «Senior Partner» строкой выше, `itm01_017`)
        cx = sum(x for x, _ in comp) / len(comp)
        cy = sum(y for _, y in comp) / len(comp)
        best = max(range(len(votes)), key=lambda k: (votes[k], -abs((boxes[k][1] + boxes[k][3]) / 2 - cy),
                                                     -abs((boxes[k][0] + boxes[k][2]) / 2 - cx)))
        if 2 * votes[best] <= len(comp):
            continue                   # кусок больше снаружи рамки, чем внутри, — не эта надпись
        for p in comp:
            ops[best][p] = 255
    return out


def lone_values(name: str, out: Image.Image, zone: Image.Image, paper: Image.Image, t: int,
                rim: int = 6) -> Image.Image:
    """Подложка без чужих кайм: значение, которое показала одна группа языков, — не бумага.

    Ключ задания `чужие_ореолы` (27 сентября 2026, план `cut02_010`): у всех языков
    вокруг букв белая кайма светлее бумаги плана, и правило `text_mask` «бумага бьёт
    чернила» брало её за бумагу — под русской надписью оставались белые облачка
    чужих слов. Здесь в зоне снятия пиксель, который подтверждают меньше двух групп
    (в пределах `t`), заменяется медианой языков, показавших бумагу, иначе — бумагой."""
    import numpy as np
    import text_mask as tm
    V = tm.load_variants(name)
    cube = np.stack([np.asarray(V[k].convert("RGB")).astype(int) for k in V if k != "eng"])
    O = np.asarray(out.convert("RGB")).astype(int)
    Z = np.asarray(zone.convert("L")) > 0
    # Бумага — средняя светлая окрестность вне зоны снятия, а не карта `text_mask`:
    # в белых окошках плана та записала бумагой белую кайму (247, 254, 254 против
    # настоящих 220, 240, 250), и кайма проходила за бумагу.
    from scipy.ndimage import uniform_filter
    w = (~Z & (O.mean(2) > 150)).astype(float)
    den = uniform_filter(w, 41)
    P = np.asarray(paper.convert("RGB")).astype(int).copy()
    for c in range(3):
        num = uniform_filter(O[..., c] * w, 41)
        P[..., c] = np.where(den > 0.05, num / np.maximum(den, 1e-6), P[..., c])
    # Считаются группы, а не языки: у обоих китайских и японского одни иероглифы
    # одним шрифтом, и их буквы «подтверждали» друг друга (точки на `cut02_010`).
    langs = [k for k in V if k != "eng"]
    # Чернила и каймы бесцветны. Где местная бумага цветная (голубой узор под
    # `Garden`), бесцветное — всегда чужая буква; где бесцветная — если далеко от неё.
    colour_p = (P.max(2) - P.min(2)) >= 25

    def foreign_of(X):
        grey = (X.max(-1) - X.min(-1)) < 25
        return grey & (colour_p | (np.abs(X.mean(-1) - P.mean(2)) > 2 * t))
    near = np.abs(cube - O[None]).max(3) <= t
    agree = np.zeros(O.shape[:2], int)
    for g in {tm.GROUP[k] for k in langs}:
        agree += near[[i for i, k in enumerate(langs) if tm.GROUP[k] == g]].any(0)
    # Буквы и каймы, общие у двух групп («A» у немецкого AZ и французского ASC
    # на месте EL), голосованием не ловятся — их ловит бесцветность.
    clean = ~np.stack([foreign_of(c) for c in cube])
    # Первый ход — по буквам (27 сентября 2026): буквы у всех языков чёрные, а кайма
    # вокруг не шире `rim` px (ключ `кайма_чужих`). Фон в точке показывают языки,
    # чьи буквы с каймой её не покрывают. Правило «бесцветное далеко от бумаги» ниже
    # рвало светлые дуги рисунка под подписями, поэтому оно — только там, где буквы
    # с каймой есть у всех.
    from scipy.ndimage import binary_dilation
    R = O.copy()
    ys, xs = np.nonzero(Z)
    if len(ys):
        y0, y1 = max(0, ys.min() - rim), ys.max() + rim + 1
        x0, x1 = max(0, xs.min() - rim), xs.max() + rim + 1
        sub = cube[:, y0:y1, x0:x1]
        # буквы — чёрное, и белая кайма заметно светлее местной бумаги (в белых
        # окошках кайма бывает дальше `rim` от чёрного, а бумага там голубоватая)
        grey = (sub.max(-1) - sub.min(-1)) < 30
        lift = sub.mean(-1) - P[y0:y1, x0:x1].mean(-1)[None]
        ink = grey & ((sub.mean(-1) < 110) | (lift > 2 * t))
        free = np.zeros(cube.shape[:3], bool)
        free[:, y0:y1, x0:x1] = np.stack([~binary_dilation(i, iterations=rim) for i in ink])
        seen = Z & free.any(0)
        for y, x in zip(*np.nonzero(seen)):
            R[y, x] = np.median(cube[free[:, y, x], y, x], axis=0)
        Z = Z & ~seen
    bad = Z & ((agree < 2) | foreign_of(O))
    for y, x in zip(*np.nonzero(bad)):
        ok = clean[:, y, x]
        R[y, x] = np.median(cube[ok, y, x], axis=0) if ok.any() else P[y, x]
    res = Image.fromarray(R.astype("uint8"))
    return res.convert(out.mode) if out.mode != "RGB" else res


def dark_zone(E: Image.Image, box, thr: int, grow: int) -> Image.Image:
    """Ключ надписи `снять_тёмное`: тёмные пиксели оригинала в рамке — тоже снимать.

    Для кусков английских букв, которые `text_mask` счёл рисунком, потому что у другого
    языка на том же месте те же буквы («en» в `Garden` и `Garten`, `cut02_010`). Зона
    уходит в чистку `чужие_ореолы` (значение — у языков, показавших здесь фон), а без
    неё — в `cv2.inpaint`: он размазывает узор, поэтому только запасной путь."""
    import cv2
    import numpy as np
    g = np.asarray(E.convert("L"))
    D = np.zeros(g.shape, np.uint8)
    x0, y0, x1, y1 = box
    D[y0:y1, x0:x1] = (g[y0:y1, x0:x1] < thr) * 255
    return Image.fromarray(cv2.dilate(D, np.ones((2 * grow + 1, 2 * grow + 1), np.uint8)))


def centre(lb: dict) -> tuple[float, float]:
    """Точка, вокруг которой поворачивается надпись с «наклоном», — «центр» из задания
    или середина её рамки. У надписи с «наклоном» рамка задана в выпрямленных
    координатах (повёрнутой на −наклон вокруг этой точки): наклонные строки подряд
    в прямых рамках перекрываются (`cut01_027`, записка под 10°)."""
    if "центр" in lb:
        return tuple(lb["центр"])
    x0, y0, x1, y1 = lb["box"]
    return ((x0 + x1) / 2, (y0 + y1) / 2)


def straight(lb: dict, x: float, y: float) -> tuple[float, float]:
    """Точка картинки в выпрямленных координатах надписи — так же, как `Image.rotate(-наклон)`."""
    import math
    a = math.radians(-lb.get("наклон", 0))
    cx, cy = centre(lb)
    dx, dy = x - cx, y - cy
    return (cx + dx * math.cos(a) + dy * math.sin(a), cy - dx * math.sin(a) + dy * math.cos(a))


def row_layout(E: Image.Image, out: Image.Image, ink: Image.Image, row: dict, report: list):
    """Ключ «ряд»: строка подсказок «значок + слово» (кнопки под видео, `cut01_03e/03f/040`).

    Русские слова длиннее английских вдвое, и в промежутки между значками не входят —
    строка раскладывается заново от правого края: слово, «между», значок, «шаг», дальше
    влево. Фон под английской строкой — тот же ряд, сдвинутый на целое число клеток
    сетки («фон», px; сетка повторяется, замер 27 сентября 2026: сдвиг 697 даёт отличие
    не больше 11 уровней). Значок — пиксели, отличные от фона, перед началом слова.
    Задание: {"полоса": [y0, y1], "снять": [x0, x1], "фон": dx, "право": x, "шаг", "между",
    "шрифт", "кегль", "цвет", "база": y, "элементы": [{"слово_с": x, "text": "…"}]}."""
    import numpy as np
    y0, y1 = row["полоса"]
    sx0, sx1 = row["снять"]
    A = np.asarray(E).astype(int)
    # «фон»: число — сдвиг влево на столько px; или список [x0, x1, dx, dy] — для колонок
    # x0..x1 брать пиксели со сдвигом (dx влево, dy вверх). У `cut01_040` строка шире,
    # и сдвиг влево на 10 клеток попадал на «Play»; справа от кадра — клетка выше.
    segs = row["фон"] if isinstance(row["фон"], list) else [[sx0, sx1, row["фон"], 0]]
    bg = A[y0:y1, sx0:sx1].copy()
    for a, b, ddx, ddy in segs:
        a, b = max(a, sx0), min(b, sx1)
        bg[:, a - sx0:b - sx0] = A[y0 - ddy:y1 - ddy, a - ddx:b - ddx]
    diff = np.abs(A[y0:y1, sx0:sx1] - bg).max(2) > 30
    icons = []
    for it in row["элементы"]:
        xs = it["слово_с"] - sx0
        cols = diff[:, max(0, xs - 48):xs - 1].any(0)
        # значок — последний связный кусок перед словом (промежуток ≤ 2 px)
        idx = np.nonzero(cols)[0]
        if len(idx) == 0 or idx[-1] < cols.size - 10:
            icons.append(None)
            continue
        right = idx[-1]
        left = right
        while left - 1 >= 0 and (cols[left - 1] or (left - 2 >= 0 and cols[left - 2])):
            left -= 1
        x_a = max(0, xs - 48) + left
        x_b = max(0, xs - 48) + right + 1
        m = diff[:, x_a:x_b]
        icons.append((x_a + sx0, x_b + sx0, A[y0:y1, x_a + sx0:x_b + sx0].copy(), m))
    O = np.asarray(out.convert("RGB")).copy()
    O[y0:y1, sx0:sx1] = bg
    I = np.asarray(ink).copy()
    I[y0:y1, sx0:sx1] = 0
    font = load_font(row["шрифт"], row["кегль"])
    canvas = Image.fromarray(O.astype("uint8"))
    ink_im = Image.fromarray(I)
    d = ImageDraw.Draw(canvas)
    di = ImageDraw.Draw(ink_im)
    x = row["право"]
    colour = tuple(row.get("цвет", (250, 250, 250)))
    placed = []
    for it, icon in reversed(list(zip(row["элементы"], icons))):
        w = font.getlength(it["text"])
        x_text = x - w
        d.text((x_text, row["база"]), it["text"], font=font, fill=colour, anchor="ls")
        di.text((x_text, row["база"]), it["text"], font=font, fill=255, anchor="ls")
        x = x_text - row.get("между", 4)
        if icon is not None:
            a, b, pix, m = icon
            iw = b - a
            nx = round(x - iw)
            sub = np.asarray(canvas).copy()
            region = sub[y0:y1, nx:nx + iw]
            region[m] = pix[m]
            sub[y0:y1, nx:nx + iw] = region
            canvas = Image.fromarray(sub)
            d = ImageDraw.Draw(canvas)
            x = nx
        placed.append(f"{it['text']} с {x_text:.0f}")
        x -= row.get("шаг", 28)
    report.append("  ряд: " + "; ".join(reversed(placed)) + f"; левый край {x:.0f}")
    return canvas, ink_im


def compose(name: str, cfg: dict, case: str):
    """Картинка с русскими печатными надписями, маска букв и отчёт."""
    raw = Image.open(EN / case / f"{name}.png")
    alpha = raw.getchannel("A") if raw.mode == "RGBA" else None
    E = raw.convert("RGB")
    # «основа» — куски картинки другого языка, поверх которых идёт набор: [{"язык", "рамка"}].
    # Решение пользователя 27 сентября 2026: единицы (кг вместо фунтов) — готовым куском
    # у языка, где они уже стоят (записка «-10 kg» на `cut01_00c`).
    if cfg.get("основа"):
        import text_mask as tm
        V = tm.load_variants(name)
        for part in cfg["основа"]:
            r = tuple(part["рамка"])
            E.paste(V[part["язык"]].convert("RGB").crop(r), r[:2])
    # Без надписей — только «основа»: штамп времени `cut01_013` целиком у французов
    # (28 сентября 2026); маска букв — рамки кусков, набирать нечего.
    if not cfg["labels"]:
        ink = Image.new("L", E.size, 0)
        for part in cfg.get("основа", []):
            ink.paste(255, tuple(part["рамка"]))
        out = E
        if alpha is not None:
            out = out.convert("RGBA")
            out.putalpha(alpha)
        return out, ink, ["  только основа: " + ", ".join(p["язык"] for p in cfg.get("основа", []))], []
    m = cp.masks_for(name)
    C = m["clean"].convert("RGB")
    eng = cp.english_ink(E, C, m["mask"].convert("L"), m["hole"].convert("L"), m["paper"].convert("RGB"))

    report, problems = [], []
    gone = Image.new("L", E.size, 0)
    jobs = []
    for lb in cfg["labels"]:
        if "англ" not in lb:
            raise ValueError(f"{name}: у надписи «{lb['text']}» нет «англ» — замерять не по чему")
    wanted: list[int] = []
    for lb, mask in zip(cfg["labels"], parts_of(eng, E, cfg["labels"])):
        # «чернила» у надписи — список цветов английских букв и каймы: буквы — пиксели
        # этих цветов (±48) в рамке. Где у других языков те же буквы на том же месте
        # («T» в кружках `cutobj02_003`), карта `text_mask` считает их рисунком.
        # «чернила_ярче» — буквы светлее порога в рамке (светлые надписи на тёмной
        # табличке `cut02_005`: у немцев свои буквы на том же месте)
        if lb.get("чернила_ярче"):
            import numpy as np
            A = np.asarray(E.convert("L")).astype(int)
            x0, y0, x1, y1 = lb["box"]
            hit = np.zeros(A.shape, bool)
            hit[y0:y1, x0:x1] = A[y0:y1, x0:x1] > lb["чернила_ярче"]
            mask = Image.fromarray((hit * 255).astype("uint8"))
        # «чернила_канал» — [канал, порог]: буквы — пиксели, у которых этот канал выше порога.
        # Полупрозрачные сезоны `cut02_011` светлее фона только по красному (≈50 против
        # 17–26), а по яркости не отделяются от голубого градиента внизу (28 сентября 2026)
        if lb.get("чернила_канал"):
            import numpy as np
            ch, thr = lb["чернила_канал"]
            A = np.asarray(E).astype(int)
            x0, y0, x1, y1 = lb["box"]
            hit = np.zeros(A.shape[:2], bool)
            hit[y0:y1, x0:x1] = A[y0:y1, x0:x1, ch] > thr
            mask = Image.fromarray((hit * 255).astype("uint8"))
        if lb.get("чернила"):
            import numpy as np
            A = np.asarray(E).astype(int)
            # «чернила_допуск» — вместо 48: бледная стёртая буква на бумаге (169–220 против
            # бумаги 226–240, шахматная записка `cut04_035`, 29 сентября 2026) с допуском 48
            # захватывала бумагу целиком
            tol = lb.get("чернила_допуск", 48)
            x0, y0, x1, y1 = lb["box"]
            hit = np.zeros(A.shape[:2], bool)
            if lb.get("наклон") and "центр" in lb:
                # рамка задана в выпрямленных координатах — берём пиксели, чья
                # выпрямленная точка лежит в рамке (перчатка `itm01_002`, 45°)
                cx, cy = centre(lb)
                rad = int(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 / 2) + 2
                gy, gx = np.mgrid[max(0, int(cy) - rad):int(cy) + rad, max(0, int(cx) - rad):int(cx) + rad]
                a = math.radians(-lb["наклон"])
                sx = cx + (gx - cx) * math.cos(a) + (gy - cy) * math.sin(a)
                sy = cy - (gx - cx) * math.sin(a) + (gy - cy) * math.cos(a)
                inside = (sx >= x0) & (sx < x1) & (sy >= y0) & (sy < y1)
                gx, gy = gx[inside], gy[inside]
                for c in lb["чернила"]:
                    hit[gy, gx] |= np.abs(A[gy, gx] - np.array(c)).max(1) <= tol
            else:
                for c in lb["чернила"]:
                    hit[y0:y1, x0:x1] |= np.abs(A[y0:y1, x0:x1] - np.array(c)).max(2) <= tol
            mask = Image.fromarray((hit * 255).astype("uint8"))
        bb = mask.getbbox()
        if bb is None:
            raise ValueError(f"{name}: у надписи «{lb['text']}» английских чернил в рамке не нашлось")
        gone = ImageChops.lighter(gone, mask)
        # «наклон» (градусы, против часовой) — строка на карточке в перспективе
        # (`itm02_024`, 27 сентября 2026): замер идёт по выпрямленным английским
        # буквам, русская строка набирается прямо и поворачивается обратно.
        if lb.get("наклон"):
            # одиночные пиксели шума растягивают рамку выпрямленной строки вдвое
            # (визитка `itm01_017`: пиксель у края рамки — высота 24 вместо 11)
            for comp in cp.components(mask):
                if len(comp) < 4:
                    for p in comp:
                        mask.putpixel(p, 0)
            mask = mask.rotate(-lb["наклон"], resample=Image.NEAREST, center=centre(lb))
            bb = mask.getbbox()
        jobs.append((lb, mask, bb))

    # «снять_шире» — светлая кайма английских букв бывает шире GROW (cut02_004, «Garden»)
    grow = cfg.get("снять_шире", GROW)
    out = Image.composite(C, E, gone.filter(ImageFilter.MaxFilter(2 * grow + 1)))
    zone = gone.filter(ImageFilter.MaxFilter(2 * grow + 1))
    # «затереть» у надписи (радиус, px): её английские буквы с ореолом затираются
    # соседями (`cv2.inpaint`), а не подложкой — шапка плана `cut02_010`: заголовок
    # во всю ширину есть у всех семи языков, неба под ним не показывает никто.
    for (lb, mask, bb) in jobs:
        if lb.get("затереть"):
            import cv2
            import numpy as np
            r = lb["затереть"]
            own = mask
            if lb.get("наклон"):
                own = mask.rotate(lb["наклон"], resample=Image.NEAREST, center=centre(lb))
            hole = own.filter(ImageFilter.MaxFilter(2 * r + 1))
            if lb.get("залить"):
                # «залить»: true — дыра заливается одним цветом фона вокруг надписи
                # (медиана кольца), а не размывкой соседей: у облаков `cutobj02_004`
                # размывка тянула светлую кромку, и по бокам слова вставали белёсые
                # пятна (пользователь 28 сентября 2026: «сделай просто розовым»)
                # Каждая точка дыры берёт цвет ближайшей точки снаружи, и всё, что
                # близко к цвету фона, становится ровно им: светлая кромка внутри
                # облака уходит в розовое, а сиреневая кайма за краем облака
                # (английская «A» доходила до края) остаётся сиреневой.
                from scipy import ndimage
                O = np.asarray(out.convert("RGB")).copy()
                H = np.asarray(hole) > 0
                ring = np.asarray(hole.filter(ImageFilter.MaxFilter(9))) > 0
                ring &= ~H
                base = np.median(O[ring], axis=0)
                # сосед ищется по столбцу — над и под строкой: сбоку от «A» у края облака
                # лежит сиреневая кайма, и ближайший боковой сосед выгрызал край
                _, (iy, ix) = ndimage.distance_transform_edt(H, sampling=(1, 50), return_indices=True)
                near = O[iy, ix].astype(float)
                close = np.abs(near - base).max(2) <= 45
                fill = np.where(close[..., None], base, near)
                O[H] = fill[H].astype(O.dtype)
                out = Image.fromarray(O)
            else:
                out = Image.fromarray(cv2.inpaint(np.asarray(out.convert("RGB")),
                                                  np.asarray(hole), 9, cv2.INPAINT_TELEA))
            zone = ImageChops.subtract(zone, hole)
    # «фон_язык» у надписи — {"язык", "радиус", "кроме": [рамки]}: снятое место английских
    # букв берётся пикселями того языка, чья надпись короче, — рисунок под английскими
    # буквами у него открыт; в рамках «кроме» (его собственные знаки) остаётся затирание.
    # Крыша павильона `cut03_006`: у японцев «展望台» только посередине, а затирание
    # размывало линии крыши (пользователь 28 сентября 2026: «скопируй с оригинала»).
    for (lb, mask, bb) in jobs:
        spec = lb.get("фон_язык")
        if spec:
            import text_mask as tm
            src = tm.load_variants(name)[spec["язык"]].convert("RGB")
            r = spec.get("радиус", 6)
            take = mask.filter(ImageFilter.MaxFilter(2 * r + 1))
            for rect in spec.get("кроме", []):
                take.paste(0, tuple(rect))
            out = Image.composite(src, out.convert("RGB"), take)
    for lb in cfg["labels"]:
        if "снять_тёмное" in lb:
            dark = dark_zone(E, lb["box"], lb["снять_тёмное"], grow)
            zone = ImageChops.lighter(zone, dark)
            if "чужие_ореолы" not in cfg:
                import cv2
                import numpy as np
                out = Image.fromarray(cv2.inpaint(np.asarray(out.convert("RGB")),
                                                  np.asarray(dark), 5, cv2.INPAINT_TELEA))
    # «заплатки» у надписи: [dx, dy] — где её буквы с каймой сидели, взять пиксели
    # оригинала со сдвигом (соседняя пустая клетка той же сетки, `cut01_027`: кайма
    # фигур перекрывала линии доски, и подложки там не показал ни один язык).
    # Красное (пометка кружком) не трогается.
    for (lb, mask, bb) in jobs:
        if lb.get("заплатка"):
            import numpy as np
            dx, dy = lb["заплатка"]
            own = mask
            if lb.get("наклон"):
                own = mask.rotate(lb["наклон"], resample=Image.NEAREST, center=centre(lb))
            zone_p = np.asarray(own.filter(ImageFilter.MaxFilter(2 * lb.get("заплатка_шире", 6) + 1))) > 0
            O = np.asarray(out.convert("RGB")).copy()
            S = np.asarray(E).astype(int)
            ys, xs = np.nonzero(zone_p)
            ok = (ys + dy >= 0) & (ys + dy < O.shape[0]) & (xs + dx >= 0) & (xs + dx < O.shape[1])
            ys, xs = ys[ok], xs[ok]
            src = S[ys + dy, xs + dx]
            here = S[ys, xs]
            keep = (here[:, 0] > 150) & (here[:, 1] < 110)       # красный кружок
            O[ys[~keep], xs[~keep]] = src[~keep]
            out = Image.fromarray(O)
    if "чужие_ореолы" in cfg:
        out = lone_values(name, out, zone, m["paper"], cfg["чужие_ореолы"], cfg.get("кайма_чужих", 6))
    ink = Image.new("L", E.size, 0)
    # Область та же, какой её берёт судья (`check_pictures`: рамка русских чернил
    # на всей картинке), а не «рамка английских ±40»: от запаса поле надписи
    # замыкается шире, набор считал место свободным, а судья — занятым рисунком.
    if jobs:
        area = (min(b[0] for _, _, b in jobs), min(b[1] for _, _, b in jobs),
                max(b[2] for _, _, b in jobs), max(b[3] for _, _, b in jobs))
        forbidden = cp.untouchable(C, m["paper"].convert("RGB"), eng, area)
    else:
        forbidden = Image.new("L", E.size, 0)

    def geometry(lb: dict, mask: Image.Image, bb):
        """Что снимается с английской надписи: гарнитура, строки, кегль, сжатие, контур."""
        font_name = lb.get("шрифт", cfg.get("font", "segoeuib"))
        lines_en = lb["англ"].split("|")
        lines_ru = lb["text"].split("|")
        want_h = (bb[3] - bb[1] - LINE_GAP * (len(lines_en) - 1)) / len(lines_en)
        want_w = bb[2] - bb[0]
        # «вычесть» у надписи (px) — английские чернила включают обводку и белую кайму
        # вокруг буквы (фигуры на шахматной диаграмме `cut01_027`); сама буква меньше
        if lb.get("вычесть"):
            want_h -= 2 * lb["вычесть"]
            want_w -= 2 * lb["вычесть"]
        size = pick_size(lines_en[0], font_name, 0, 1.0, want_h)
        wide = render(lines_en[0], font_name, size, 0, 1.0)[2]
        squeeze = (min(1.25, max(0.45, want_w / max(1, wide[2] - wide[0])))
                   if len(lines_en) == 1 else 1.0)
        size = pick_size(lines_en[0], font_name, 0, squeeze, want_h)
        # Русское слово длиннее английского — жмём по ширине, а не мельчим: так же сделали
        # немцы и французы («Springer» и «Latour» стоят в росте «Knight» и «Rook», но уже).
        room = lb.get("max_width", lb["box"][2] - lb["box"][0])
        for text in lines_ru:
            mine = render(text, font_name, size, 0, squeeze)[2]
            if mine[2] - mine[0] > room:
                squeeze = max(0.4, squeeze * room / (mine[2] - mine[0]))
        size = pick_size(lines_en[0], font_name, 0, squeeze, want_h)
        # «кегль» и «сжатие» у надписи — руками. Замер по английской букве даёт «А» и «Ко»
        # в соседних кружках разный кегль, а пользователь просит один на все кружки
        # (`cutobj01_015`); растяжка по ширине английской строки раздувает короткую русскую
        # (журнал `cut04_017`, 1,22; табличка `cut04_011`, 1,24). 29 сентября 2026.
        # Одно «сжатие» — кегль по высоте, как обычно; один «кегль» — сжатие по месту
        if "сжатие" in lb and "кегль" not in lb:
            squeeze = lb["сжатие"]
            size = pick_size(lines_en[0], font_name, 0, squeeze, want_h)
        if "кегль" in lb:
            size = lb["кегль"]
            squeeze = lb.get("сжатие", 1.0)
            for text in lines_ru:
                mine = render(text, font_name, size, 0, squeeze)[2]
                if "сжатие" not in lb and mine[2] - mine[0] > room:
                    squeeze = max(0.4, squeeze * room / (mine[2] - mine[0]))
        en_stroke = cp.stroke(mask)
        sw = 0
        # «контур» в задании — задать руками: замер штриха рассчитан на светлые буквы
        # с тёмным кантом и на обратной палитре (тёмные буквы, светлая кайма, cut02_004)
        # ошибается вдвое. Судит глаз по листу (курс 23 сентября 2026).
        if "контур" in lb or "контур" in cfg:
            sw = lb.get("контур", cfg.get("контур"))
            if "кегль" not in lb:
                size = pick_size(lines_en[0], font_name, sw, squeeze, want_h)
        elif cp.stroke(solid(render(lines_en[0], font_name, size, 0, squeeze)[0])) < THIN * en_stroke:
            sw = 1
            if "кегль" not in lb:
                size = pick_size(lines_en[0], font_name, sw, squeeze, want_h)
        return font_name, lines_en, lines_ru, want_h, want_w, size, squeeze, sw, en_stroke

    # Кант подбирается **замером** и один на всю картинку: у англичан он один,
    # а русская строка сжата по ширине — её штрихи тоньше, и на «Лифт» и на
    # «Комната Густо» одна и та же толщина даёт разный штрих. Считаем, какой кант
    # нужен каждой надписи, чтобы догнать английский штрих, и берём медиану:
    # разнобой «1 и 4» на соседних комнатах виден глазом, а число из задания —
    # не замер (правило от 20 сентября 2026).
    # `stroke_width: 0` в задании — «канта нет»: у планов дела 1 надписи печатные,
    # тёмные чернила на светлой бумаге, кант им не положен.
    wants_edge = bool(cfg.get("stroke")) and cfg.get("stroke_width", 2) != 0
    edge_w = 0
    measured = 0.0
    if wants_edge:
        # Толщина канта снимается **с самих английских букв**, а не подбирается под
        # число находок: у надписи светлое тело и тёмный кант вокруг; кант — это
        # кольцо «чернила минус тело», и его средняя толщина равна площади кольца
        # на длину границы тела. Подбор «пока штрих не догонит» сюда не годился:
        # мерка `stroke` растёт, когда буквы слипаются кантом, и у длинного
        # «Gusto's Room» показывала 17,5 против 11,6 у «Elevator» при одном канте.
        fill = tuple(cfg["fill"])
        seen = []
        for lb, mask, bb in jobs:
            core = Image.new("L", mask.size, 0)
            cp_, mp_ = core.load(), mask.load()
            ep = E.load()
            for y in range(bb[1], bb[3]):
                for x in range(bb[0], bb[2]):
                    if mp_[x, y] and max(abs(ep[x, y][i] - fill[i]) for i in range(3)) < 60:
                        cp_[x, y] = 255
            ring = cp.count(mask) - cp.count(core)
            edge_len = 2 * cp.count(core) / max(1e-6, cp.stroke(core))
            if edge_len > 0:
                seen.append(ring / edge_len)
        # Половину пикселя округляем **вверх**: наши буквы сжаты по ширине, и при
        # равном канте штрих выходит тоньше английского.
        edge_w = max(1, math.ceil(statistics.median(seen) - 0.01)) if seen else cfg.get("stroke_width", 2)
        if "кант" in cfg:
            edge_w = cfg["кант"]      # задан руками — см. «контур» выше
        measured = statistics.median(seen) if seen else 0.0
        report.append(f"  кант снят с английских букв: "
                      + ", ".join(f"{v:.1f}" for v in seen)
                      + f" -> {edge_w} px на всю картинку")

    for lb, mask, bb in jobs:
        (font_name, lines_en, lines_ru, want_h, want_w,
         size, squeeze, sw, en_stroke) = geometry(lb, mask, bb)
        # «кант» у надписи — свой: шапка плана `cut02_010` без канта, но с ореолом
        edge_w_all, edge_w = edge_w, lb.get("кант", edge_w)
        ru_stroke = cp.stroke(solid(render(lines_ru[0], font_name, size,
                                           sw + edge_w, squeeze)[0]))

        # Точка опоры — из замера: тот же английский текст нашей гарнитурой ложится
        # в рамку английских чернил, и его базовая линия становится нашей.
        _, _, en_bb = render(lines_en[0], font_name, size, sw, squeeze)
        bx, by = bb[0] - en_bb[0], bb[1] - en_bb[1]
        # «вычесть» мельчит букву внутри английской рамки — и сверху тоже: без этого
        # строка прижималась к верху рамки («Осеннее крыло», `cutobj02_004`)
        if lb.get("вычесть"):
            bx, by = bx + lb["вычесть"], by + lb["вычесть"]
        step = want_h + LINE_GAP
        colour = tuple(lb.get("fill", cfg["fill"]))
        # У английских надписей этого пласта буквы белые, а вокруг тёмный кант:
        # без него набор читается бледно, а замер штриха сравнивает наше «только
        # буквы» с английским «буквы вместе с кантом» и всегда кричит «тоньше».
        # «stroke» у надписи — свой цвет каймы (накладки плана `cutobj02_004`: жёлтая
        # кайма у бурых букв и белая у сиреневых на одной картинке)
        edge = tuple(lb.get("stroke", cfg["stroke"])) if wants_edge else None
        where = lb.get("по", "центр")
        pieces = []
        mine = Image.new("L", E.size, 0)
        for j, text in enumerate(lines_ru):
            ru_im, (ox, oy), ru_bb = render(text, font_name, size, sw, squeeze)
            dx = 0.0
            # Центр и правый край — по **настоящим** английским чернилам `bb`, а не по
            # английской строке нашей гарнитурой `en_bb`: та сжимается вместе с русской
            # (длинное слово жмётся по ширине) и остаётся прижатой к левому краю —
            # середина уезжала влево тем дальше, чем сильнее сжатие («Комната Морозова»
            # при 0,52, кружки плана; замечание пользователя 28 сентября 2026).
            if where == "центр":
                dx = (bb[0] + bb[2]) / 2 - bx - (ru_bb[0] + ru_bb[2]) / 2
            elif where == "право":
                dx = bb[2] - bx - ru_bb[2]
            # «ось» — середина надписи на этом x: «Лифт» по середине прямоугольника,
            # «Вход» и «Сад» по оси лестницы (`cut02_010`), а не по английским буквам
            if "ось" in lb:
                dx = lb["ось"] - bx - (ru_bb[0] + ru_bb[2]) / 2
            # «ось_y» — середина чернил строки на этом y (однострочные надписи): буква
            # в кружке по центру круга вместе с выносными элементами («Д», `cutobj02_003`)
            dy = 0.0
            if "ось_y" in lb and len(lines_ru) == 1:
                dy = lb["ось_y"] - by - (ru_bb[1] + ru_bb[3]) / 2
            at = (round(bx + dx - ox), round(by + j * step + dy - oy))
            wide = render(text, font_name, size, sw + edge_w, squeeze)[0] if edge_w else None
            pieces.append((ru_im, wide, at))
            mine.paste(255, at, solid(wide if wide is not None else ru_im))
        # Русское слово короче или длиннее английского, и буква попадает туда, где у англичан
        # был пробел, — на точку или линию плана. Тогда надпись сдвигается на пару пикселей:
        # глазу это незаметно, а на рисунок она уже не ложится (20 сентября 2026).
        shift = (0, 0)
        if lb.get("наклон"):
            a, c = lb["наклон"], centre(lb)
            body, rim = Image.new("L", E.size, 0), Image.new("L", E.size, 0)
            for ru_im, wide, at in pieces:
                body.paste(255, at, ru_im)
                if wide is not None:
                    rim.paste(255, at, wide)
            body = body.rotate(a, resample=Image.BICUBIC, center=c)
            if edge_w:
                rim = rim.rotate(a, resample=Image.BICUBIC, center=c)
                out.paste(edge, (0, 0), rim)
                ink.paste(255, (0, 0), solid(rim))
            out.paste(colour, (0, 0), body)
            ink.paste(255, (0, 0), solid(body))
            report.append(f"  {lb['text'].replace('|', ' / ')}: кегль {size}, сжатие {squeeze:.3f}, "
                          f"наклон {a}°; высота {want_h:.0f} px, ширина {want_w} px")
            edge_w = edge_w_all
            continue
        # «обход»: false — не отодвигать надпись от рисунка: «Garden» у англичан лежит
        # прямо на линии перил, и обход уводил «Сад» на 14 px в сторону (`cut02_010`)
        if lb.get("обход", True) and cp.count(ImageChops.multiply(mine, forbidden)):
            best = None
            # Шаг поиска был ±8 px и не вытягивал «Комната Сдобиной» из коридора
            # на шесть пикселей. Диапазон шире, порядок прежний — от нуля наружу,
            # так что при прочих равных надпись остаётся на месте англичанина.
            for dy in (0, -2, 2, -4, 4, -6, 6):
                for dx_ in (0, -2, 2, -4, 4, -6, 6, -8, 8, -10, 10, -12, 12, -14, 14):
                    moved = Image.new("L", E.size, 0)
                    moved.paste(mine, (dx_, dy))
                    hits = cp.count(ImageChops.multiply(moved, forbidden))
                    cost = hits * 1000 + abs(dx_) + abs(dy)
                    if best is None or cost < best[0]:
                        best = (cost, dx_, dy, hits)
                    if not hits:
                        break
                if best and not best[3]:
                    break
            shift = (best[1], best[2])
        for j, (ru_im, wide, at) in enumerate(pieces):
            # «сдвиг» надписи — поправка глазом по листу (cut02_004: «В» заходила на стену)
            nudge = lb.get("сдвиг", (0, 0))
            place = (at[0] + shift[0] + nudge[0], at[1] + shift[1] + nudge[1])
            # «ореол» у надписи — мягкое свечение под буквами: {"цвет", "радиус", "сила"}
            glow = lb.get("ореол")
            if glow:
                r = glow["радиус"]
                halo = ru_im.filter(ImageFilter.MaxFilter(2 * (r // 2) + 1)).filter(
                    ImageFilter.GaussianBlur(r / 2)).point(
                    lambda v, k=glow.get("сила", 1.0): min(255, int(v * k)))
                out.paste(tuple(glow["цвет"]), place, halo)
            # «тень» у надписи — {"сдвиг": [dx, dy], "цвет"}: сплошное выдавливание контура
            # букв в сторону сдвига, как у газетного заголовка `cut04_005` (белые буквы,
            # чёрная обводка и чёрная тень вправо-вниз; 29 сентября 2026)
            drop = lb.get("тень")
            if drop:
                body = wide if wide is not None else ru_im
                dx_, dy_ = drop["сдвиг"]
                steps = max(abs(dx_), abs(dy_), 1)
                for s_ in range(1, steps + 1):
                    at_s = (place[0] + round(dx_ * s_ / steps), place[1] + round(dy_ * s_ / steps))
                    out.paste(tuple(drop.get("цвет", edge or (0, 0, 0))), at_s, body)
                    ink.paste(255, at_s, solid(body))
            if wide is not None:
                out.paste(edge, place, wide)
                ink.paste(255, place, solid(wide))
            out.paste(colour, place, ru_im)
            # «выделение» — слово строки своим цветом: {"слово", "цвет"} (шапка таблицы
            # сезонов `cut02_011`: «temperature» зелёным среди белого, 28 сентября 2026)
            mark = lb.get("выделение")
            if mark and mark["слово"] in lines_ru[j]:
                pre = lines_ru[j][:lines_ru[j].index(mark["слово"])]
                font = load_font(font_name, size)
                ox = render(lines_ru[j], font_name, size, sw, squeeze)[1][0]
                x0 = round(ox + font.getlength(pre) * squeeze)
                x1 = round(ox + font.getlength(pre + mark["слово"]) * squeeze)
                part = Image.new("L", ru_im.size, 0)
                part.paste(ru_im.crop((x0, 0, x1, ru_im.height)), (x0, 0))
                out.paste(tuple(mark["цвет"]), place, part)
            ink.paste(255, place, solid(ru_im))
        report.append(f"  {lb['text'].replace('|', ' / ')}: кегль {size}, сжатие {squeeze:.3f}, контур {sw}; "
                      f"высота {want_h:.0f} px, ширина {want_w} px; штрих наш {ru_stroke:.1f} против "
                      f"английского {en_stroke:.1f}; кант {edge_w}"
                      + (f"; сдвиг {shift}" if shift != (0, 0) else ""))
        edge_w = edge_w_all
    # Сравнение «штрих против штриха» по мерке `stroke` здесь не судья: она растёт,
    # когда соседние буквы слипаются кантом, и у длинного «Gusto's Room» показывает
    # 17,5 против 11,6 у «Elevator» при одном и том же канте. Судим по прямому
    # замеру кольца: наш кант не должен быть тоньше английского.
    if wants_edge and edge_w < 0.85 * measured:
        problems.append(f"{name}: кант тоньше английского — {edge_w} px против "
                        f"{measured:.1f} px замеренных")
    if cfg.get("ряд"):
        out, ink = row_layout(E, out, ink, cfg["ряд"], report)
    if alpha is not None:
        out = out.convert("RGBA")
        out.putalpha(alpha)
    return out, ink, report, problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path, help="JSON с заданием (labels.json)")
    ap.add_argument("--only", help="одна картинка")
    ap.add_argument("--check", action="store_true", help="ничего не писать, сверить с лежащим PNG")
    ap.add_argument("--fonts", action="store_true",
                    help="с --only: какой гарнитурой набран оригинал — замер всех шрифтов машины")
    args = ap.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    case = args.spec.parent.name
    problems = []
    done = 0

    if args.fonts:
        if not args.only:
            sys.exit("--fonts — только вместе с --only")
        cfg = spec[args.only]
        E = Image.open(EN / case / f"{args.only}.png").convert("RGB")
        m = cp.masks_for(args.only)
        eng = cp.english_ink(E, m["clean"].convert("RGB"), m["mask"].convert("L"),
                             m["hole"].convert("L"), m["paper"].convert("RGB"))
        names = cyrillic_fonts()
        print(f"шрифтов с кириллицей на машине: {len(names)}")
        for lb, mask in zip(cfg["labels"], parts_of(eng, E, cfg["labels"])):
            bb = mask.getbbox()
            print(f"\n«{lb['англ']}» -> «{lb['text']}», чернила {bb[2] - bb[0]}x{bb[3] - bb[1]}, "
                  f"штрих {cp.stroke(mask):.2f}")
            for iou, font, size, squeeze, stroke in match_font(lb["англ"].split("|")[0], mask, bb, names)[:8]:
                print(f"   {iou:.3f}  {font:<16} кегль {size}, сжатие {squeeze:.2f}, штрих {stroke:.2f}")
        return 0
    for name, cfg in spec.items():
        if not isinstance(cfg, dict) or (args.only and name != args.only):
            continue
        if "как" in cfg:               # мелкая копия: рамки и надписи пересчитываются от большой
            own = {k: v for k, v in cfg.items() if k not in ("как", "якорь_там", "якорь_тут")}
            cfg = {**remap(spec[cfg["как"]], cfg["якорь_там"], cfg["якорь_тут"]), **own}
        if not cfg.get("по_оригиналу"):
            continue
        out, ink, report, trouble = compose(name, cfg, case)
        problems += trouble
        print(f"{name}: надписей {len(cfg['labels'])}")
        for line in report:
            print(line, flush=True)
        png = RU / case / f"{name}.png"
        stage = STAGE / f"{name}.png"
        if args.check:
            # Сверять с `png` нельзя: на нём уже лежат рукописные пометки `notes.py`.
            if not stage.exists():
                problems.append(f"{name}: нет печатного слоя {stage} — прогнать make notes")
            elif ImageChops.difference(Image.open(stage).convert("RGB"),
                                       out.convert("RGB")).getbbox():
                problems.append(f"{name}: печатный слой не совпадает с набором по заданию — tools/prints.py")
        else:
            out.save(png)
            STAGE.mkdir(parents=True, exist_ok=True)
            out.save(stage)
            ink.save(RU / case / f"{name}_print_ink.png")
            ink.save(RU / case / f"{name}_ink.png")
            print(f"  записано: {png}")
        done += 1
    for p in problems:
        print(f"  БЕДА: {p}", file=sys.stderr)
    if not done:
        # Сверять нечего — в режиме сверки это провал (см. sign.py).
        print(f"в {args.spec} нет картинок с «по_оригиналу» — набирать нечего")
        if args.check:
            return 2
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
