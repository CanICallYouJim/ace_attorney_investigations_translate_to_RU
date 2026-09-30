"""Рукописные пометки на планах охраны: набор шрифтом на месте английских.

На планах дела 1 поверх чертежа идут красные пометки от руки. До 15 сентября 2026
их рисовала нейросеть и вклеивал `paste_art.py`; пользователь сравнил образец набора
с оригиналом и выбрал **способ (б) — набор шрифтом**, с контуром на единицу толще
образца (`docs/decisions.md`, запись от 15 сентября).

Набор не выдумывает место, наклон и размер, а снимает их **с самой английской пометки**:

  * английские буквы пометки — связные куски английских чернил (`check_pictures.english_ink`
    по маске `text_mask.py`), красные и задевающие рамки пометки. Кусок берётся целиком,
    даже если торчит из рамки: рамки размечены под старое снятие, и верх «president»
    из них выходил (16 сентября 2026). Снимаются ровно эти куски — подложкой `_clean.png`;
    стрелки и чертёж у всех языков общие и лежат в подложке, их снятие не трогает;
  * красные пиксели кусков кластеризуются на столько строк, сколько строк в английском,
    и через каждую группу проводится прямая — это наклон, база и длина строки;
    подчёркивание (`черты` в задании) из замера исключается, иначе тянет прямую вниз;
  * кегль — замером тела строки: тело нашей строки против тела английской одной меркой
    (коэффициент «высота строчных = 0,5 кегля» давал набор в полтора раза мельче руки);
  * сжатие по ширине — **по руке, а не по месту**: тот же английский текст, набранный
    Ink Free, против английской руки. Сжатие под место (русский текст против английского)
    вбирало и то, что кириллица шире латиницы, и делало буквы уже оригинала — ровно то,
    на что пользователь жаловался 13 сентября: «шрифт уже оригинального, читается блекло»;
  * контур — по штриху английской руки при этом кегле и сжатии, плюс `толще`;
  * **кегль не мельчится никогда.** Строка длиннее места — сокращается текст: отчёт
    печатает каждую строку против английской и отдельным списком — те, что длиннее;
  * положение строки — перебор сдвигов, лишь бы не задеть рисунок по той же маске,
    которой судит `check_pictures.py` (`untouchable`), и не задеть соседние строки
    и печатные надписи `relabel.py`;
  * буквы ставятся по одной со своим наклоном, размером и сдвигом по базе;
  * волнистое подчёркивание у каждого языка своё и в подложке его нет — оно рисуется
    под русскими словами (`подчеркнуть` в задании) волной по замеру английской.

Задание — `work/graphics_ru/<дело>/notes.json`. Основа — картинка `relabel.py`
(печатное уже по-русски, рукописное ещё английское), поэтому порядок — `make notes`.

    tools\\notes.py                    набрать все картинки задания
    tools\\notes.py --only cut00_007   одну
    tools\\notes.py --check            ничего не писать: набрать в памяти и сверить с лежащим PNG
    tools\\notes.py --only cut00_010 --try "2:Жизнь президента|превыше всего!"
                                       примерить строки к пометке 2: длина каждой против английской
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import check_pictures as cp
from common import WORK
from layer_localized import NOTE_ZONE as ZONE

# Печатный слой `prints.py` отдельным файлом: поверх него ложится рукописное,
# и картинка в graphics_ru становится итоговой. Лежит здесь, а не в prints.py,
# потому что prints.py импортирует notes.py — обратный импорт замкнул бы круг.
STAGE = WORK / "graphics_masks" / "prints"
RU = WORK / "graphics_ru"
EN = WORK / "graphics_en"
MASKS = WORK / "graphics_masks"
SHEET = MASKS / "checks"
FONT = Path("C:/Windows/Fonts/Inkfree.ttf")
LABEL_FONT = Path("C:/Windows/Fonts/segoeuib.ttf")
SEED = 21
REACH = 24          # кусок английских чернил ближе этого к рамке пометки — её буква
                    # ZONE — запас вокруг рамки пометки: одна величина с разрешённым местом
                    # правки у слоя патчера, поэтому берётся из layer_localized
ROOM = 1.02         # строка длиннее английской больше этого — показать, сокращать текст
LABEL_PAD = 8       # поле вокруг печатных надписей relabel.py: пометке туда нельзя
BLACK = 1000        # цена задетого пикселя против пикселя сдвига при переборе положения
SMALL = 400         # кусок чернил не больше этого — точка, «!», запятая: к строке целиком
# Волна подчёркивания — доли тела английской строки, замер 16 сентября 2026 по трём
# английским волнам (под «we know who» и под обеими строками «The president's safety»):
# ниже базы на полтела, размах ±0,13 тела, шаг волны 1,3 тела, штрих — три четверти буквы.
UNDER_LOW, UNDER_AMP, UNDER_STEP, UNDER_PEN = 0.55, 0.13, 1.3, 0.75


def red(v) -> bool:
    """Красная ручка: красный заметно выше прочих каналов."""
    return v[0] > 90 and v[0] - max(v[1], v[2]) > 45


def dark(v) -> bool:
    """Карандаш или чёрная ручка: тёмное без оттенка (записка на шахматной диаграмме
    `cut01_027`, 27 сентября 2026 — задание с ключом `"рука": "тёмная"`)."""
    return max(v) < 150 and max(v) - min(v) < 40


def fit(points):
    """Прямая через точки строки: сдвиг и наклон."""
    n = len(points)
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    spread = sum((p[0] - mx) ** 2 for p in points)
    b = sum((p[0] - mx) * (p[1] - my) for p in points) / spread if spread else 0.0
    return my - b * mx, b


def split_lines(comps: list[list], count: int):
    """Куски английских букв пометки — на `count` строк.

    Сперва пиксели по расстоянию до прямой строки. Потом **мелкие куски — целиком**
    по своему центру: высокий «!» в конце «is paramount!» верхушкой ближе к прямой
    строки над ним, пиксельный счёт отдавал её туда, и длина той строки выходила
    на треть больше (16 сентября 2026). Крупные куски — связные слова — так переносить
    нельзя: на «Stay frosty» центры слов двух строк лежат вперемешку, и счёт сходится
    не туда."""
    points = [p for c in comps for p in c]
    ys = sorted(p[1] for p in points)
    edges = [ys[int((i + 1) * len(ys) / count)] for i in range(count - 1)]
    groups: list[list] = [[] for _ in range(count)]
    for p in points:
        i = 0
        while i < len(edges) and p[1] > edges[i]:
            i += 1
        groups[i].append(p)
    lines = [fit(g) for g in groups if g]
    for _ in range(15):
        groups = [[] for _ in lines]
        for p in points:
            d = [abs(p[1] - (a + b * p[0])) for a, b in lines]
            groups[d.index(min(d))].append(p)
        if any(not g for g in groups):
            break
        lines = [fit(g) for g in groups]
    def nearest(x: float, y: float) -> int:
        d = [abs(y - (a + b * x)) for a, b in lines]
        return d.index(min(d))

    for _ in range(3):
        groups, homes = [[] for _ in lines], [[] for _ in lines]
        for c in comps:
            if len(c) <= SMALL:
                k = nearest(sum(p[0] for p in c) / len(c), sum(p[1] for p in c) / len(c))
                groups[k].extend(c)
                homes[k].extend(c)
                continue
            votes = [0] * len(lines)
            for p in c:
                k = nearest(*p)
                groups[k].append(p)
                votes[k] += 1
            homes[votes.index(max(votes))].extend(c)
        if any(not g for g in groups):
            break
        lines = [fit(g) for g in groups]
    out = []
    # Длина строки — по кускам, чей дом эта строка: иначе нижняя ножка «R» первой строки,
    # отданная второй попиксельно, удлиняет вторую на полсотни пикселей.
    for g, home, (a, b) in zip(groups, homes, lines):
        if not g or not home:
            continue
        ang = math.atan(b)
        offs = sorted((p[1] - (a + b * p[0])) * math.cos(ang) for p in g)
        q = lambda f: offs[int(f * (len(offs) - 1))]  # noqa: E731 — квантиль по строке
        along = [p[0] * math.cos(ang) + p[1] * math.sin(ang) for p in home]
        x0, x1 = min(p[0] for p in home), max(p[0] for p in home)
        out.append({"a": a, "b": b, "angle": math.degrees(ang), "body": q(0.8) - q(0.2),
                    "x0": x0, "x1": x1, "room": max(along) - min(along)})
    return sorted(out, key=lambda st: st["a"] + st["b"] * st["x0"])


def wave(rnd: random.Random, length: float, low: float, amp: float, step: float) -> list[tuple[float, float]]:
    """Волна подчёркивания: (вдоль, поперёк). Размах меняется по полуволнам, шаг плывёт,
    в конце рука уходит вверх — как у английских волн."""
    pts, t, phase = [], 0.0, rnd.uniform(0, 2 * math.pi)
    half, a = int(phase / math.pi), amp * rnd.uniform(0.7, 1.3)
    while t <= length:
        if int(phase / math.pi) != half:
            half, a = int(phase / math.pi), amp * rnd.uniform(0.7, 1.3)
        tail = max(0.0, t - (length - 2 * step)) / (2 * step)
        pts.append((t, low + a * math.sin(phase) - tail * tail * 2.2 * amp))
        t += 2.0
        phase += 2 * math.pi * 2.0 / step * rnd.uniform(0.85, 1.15)
    return pts


def draw_line(text: str, size: int, sw: int, start, angle: float, shear: float,
              seed: int, canvas, squeeze: float = 1.0, under=(), pen: dict | None = None) -> Image.Image:
    """Строка рукой: каждая буква со своим наклоном, размером и сдвигом по базе.

    `squeeze` жмёт буквы и пробелы по ширине, не трогая высоту: рука уже Ink Free.
    Наклон ставится **после** сжатия, иначе сжалась бы и сама косина письма.
    `under` — пары (первая буква, за последней) под волну подчёркивания, `pen` — её мерки.
    """
    font = ImageFont.truetype(str(FONT), size)
    rnd = random.Random(seed)
    ang = math.radians(angle)
    u, n = (math.cos(ang), math.sin(ang)), (-math.sin(ang), math.cos(ang))
    alpha = Image.new("L", canvas, 0)
    pos, spans = 0.0, []
    for ch in text:
        adv = font.getlength(ch)
        if ch == " ":
            step = adv * squeeze * rnd.uniform(0.9, 1.2)
            spans.append((pos, pos + step))
            pos += step
            continue
        s = rnd.uniform(0.96, 1.04)
        pad = int(size * 1.3)
        g = Image.new("L", (int(adv) + 2 * pad, 2 * size + 2 * pad), 0)
        ox, oy = pad, pad + size
        ImageDraw.Draw(g).text((ox, oy), ch, font=font, fill=255, anchor="ls",
                               stroke_width=sw, stroke_fill=255)
        if squeeze != 1.0:
            g = g.resize((max(1, int(g.width * squeeze)), g.height), Image.BICUBIC)
            ox *= squeeze
        g = g.transform(g.size, Image.AFFINE, (1, shear, -shear * oy, 0, 1, 0), resample=Image.BICUBIC)
        g = g.resize((max(1, int(g.width * s)), max(1, int(g.height * s))), Image.BICUBIC)
        ox, oy = ox * s, oy * s
        g = g.rotate(-angle + rnd.uniform(-2.5, 2.5), resample=Image.BICUBIC, center=(ox, oy))
        dy = rnd.uniform(-1.5, 1.5)
        px, py = start[0] + u[0] * pos + n[0] * dy, start[1] + u[1] * pos + n[1] * dy
        alpha.paste(255, (int(round(px - ox)), int(round(py - oy))), g)
        step = adv * s * squeeze + rnd.uniform(-0.5, 1.0)
        spans.append((pos, pos + step))
        pos += step
    if under and pen:
        d = ImageDraw.Draw(alpha)
        for i0, i1 in under:
            t0 = spans[i0][0] - pen["over"]
            length = spans[i1 - 1][1] + pen["over"] - t0
            pts = [(start[0] + u[0] * (t0 + t) + n[0] * dy, start[1] + u[1] * (t0 + t) + n[1] * dy)
                   for t, dy in wave(rnd, length, pen["low"], pen["amp"], pen["step"])]
            d.line(pts, fill=255, width=pen["width"], joint="curve")
            r = pen["width"] / 2
            for x, y in (pts[0], pts[-1]):
                d.ellipse((x - r, y - r, x + r, y + r), fill=255)
    return alpha


def body_of(alpha: Image.Image, angle: float = 0.0) -> float:
    """Высота тела строки: тот же межквантильный размах поперёк, каким мерится английская."""
    ap = alpha.load()
    bb = alpha.getbbox()
    if bb is None:
        return 0.0
    ang = math.radians(angle)
    cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
    offs = []
    for y in range(bb[1], bb[3]):
        for x in range(bb[0], bb[2]):
            if ap[x, y] > 127:
                offs.append((y - cy) * math.cos(ang) - (x - cx) * math.sin(ang))
    if not offs:
        return 0.0
    offs.sort()
    q = lambda f: offs[int(f * (len(offs) - 1))]  # noqa: E731
    return q(0.8) - q(0.2)


def stroke_of(alpha: Image.Image) -> float:
    """Толщина штриха: удвоенная площадь на длину границы."""
    ap = alpha.load()
    bb = alpha.getbbox()
    area = border = 0
    for y in range(bb[1] + 1, bb[3] - 1):
        for x in range(bb[0] + 1, bb[2] - 1):
            if ap[x, y] > 127:
                area += 1
                if min(ap[x + 1, y], ap[x - 1, y], ap[x, y + 1], ap[x, y - 1]) <= 127:
                    border += 1
    return 2 * area / max(1, border)


def width_of(text: str, size: int, sw: int, shear: float, squeeze: float, canvas) -> int:
    """Длина строки при наборе — та же, что встанет на картинку (тот же разброс по буквам)."""
    bb = draw_line(text, size, sw, (0, canvas[1] // 2), 0.0, shear, SEED, canvas, squeeze).getbbox()
    return (bb[2] - bb[0]) if bb else 0


def pick_size(texts: list[str], sw: int, shear: float, squeeze: float, want: float, canvas) -> int:
    """Кегль, при котором среднее тело наших строк совпадает со средним телом английских.

    Тело растёт с кеглем монотонно — поиск делением пополам, а не перебором."""
    def body(size: int) -> float:
        return sum(body_of(draw_line(t, size, sw, (canvas[0] // 3, canvas[1] // 2), 0.0, shear, 3,
                                     canvas, squeeze)) for t in texts) / len(texts)
    lo, hi = 16, 130
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if body(mid) < want:
            lo = mid
        else:
            hi = mid
    return min((lo, hi), key=lambda s: abs(body(s) - want))


def spans_of(text: str, words: str | None) -> tuple[int, int]:
    """Буквы под подчёркивание: вся строка или слова из задания."""
    if not words:
        return 0, len(text)
    at = text.find(words)
    if at < 0:
        raise ValueError(f"подчеркнуть «{words}»: в строке «{text}» таких слов нет")
    return at, at + len(words)


def survey(name: str, cfg: dict, case: str) -> dict:
    """Всё, что снимается с английской пометки: её буквы, строки, кегль, сжатие, контур."""
    # Основа — печатный слой `prints.py`, а не итоговая картинка: иначе второй прогон
    # рисует пометки поверх собственных, края букв темнеют на 1-5 уровней и `--check`
    # валится сразу после своей же записи (разбор 20 сентября 2026).
    stage = STAGE / f"{name}.png"
    base = Image.open(stage if stage.exists() else RU / case / f"{name}.png")
    E = Image.open(EN / case / f"{name}.png").convert("RGB")
    m = cp.masks_for(name)
    C, T = m["clean"].convert("RGB"), m["mask"].convert("L")
    hole, paper = m["hole"].convert("L"), m["paper"].convert("RGB")
    eng = cp.english_ink(E, C, T, hole, paper)
    w, h = E.size
    ep = E.load()
    canvas = (w, h)

    # Чей кусок: у каждой пометки рамки, расширенные на REACH, минус «кроме».
    owner = Image.new("L", canvas, 0)
    od = ImageDraw.Draw(owner)
    for i, note in enumerate(cfg["пометки"]):
        for x0, y0, x1, y1 in note["рамки"]:
            od.rectangle((x0 - REACH, y0 - REACH, x1 + REACH, y1 + REACH), fill=i + 1)
    for note in cfg["пометки"]:
        for box in note.get("кроме", []):
            od.rectangle(tuple(box), fill=0)
    op = owner.load()
    red = dark if cfg.get("рука") == "тёмная" else globals()["red"]
    pieces: list[list] = [[] for _ in cfg["пометки"]]
    stray = []
    for comp in cp.components(eng):
        votes = [0] * (len(cfg["пометки"]) + 1)
        for p in comp:
            votes[op[p]] += 1
        best = max(range(1, len(votes)), key=lambda k: votes[k])
        # Кусок уходит пометке, если внутри её рамок **большая часть** его пикселей:
        # буква печатной надписи, задевшая рамку углом, остаётся печатной (её снимает
        # prints.py), а грязь от английских чернил на изгороди — внутри рамки целиком,
        # и снимать её надо, иначе она остаётся «остатком английского» (20 сентября 2026).
        if 2 * votes[best] > len(comp):
            pieces[best - 1].extend(comp)
        elif 2 * sum(1 for p in comp if red(ep[p])) >= len(comp) and votes[best]:
            xs, ys = [p[0] for p in comp], [p[1] for p in comp]
            stray.append((len(comp), (min(xs), min(ys), max(xs) + 1, max(ys) + 1)))

    notes = []
    for i, note in enumerate(cfg["пометки"]):
        lines_en = note["английские"]
        if len(note["строки"]) != len(lines_en):
            raise ValueError(f"{name}: пометка {i + 1} — строк {len(note['строки'])}, "
                             f"у английской {len(lines_en)}: число строк как в оригинале")
        keep = Image.new("L", canvas, 0)
        kp = keep.load()
        for p in pieces[i]:
            if red(ep[p]):
                kp[p] = 255
        dd = ImageDraw.Draw(keep)
        for line in note.get("черты", []):
            dd.line([tuple(p) for p in line["точки"]], fill=0, width=2 * line.get("полоса", 6) + 1,
                    joint="curve")
        comps = cp.components(keep)
        if not comps:
            raise ValueError(f"{name}: пометка {i + 1} — английских чернил не нашлось")
        rows = split_lines(comps, len(lines_en))
        if len(rows) != len(lines_en):
            raise ValueError(f"{name}: пометка {i + 1} — строк в чернилах {len(rows)}, в задании {len(lines_en)}")
        notes.append({"rows": rows, "pixels": pieces[i]})

    shear = cfg["наклон"]
    every = [r for nt in notes for r in nt["rows"]]
    xh = sum(r["body"] for r in every) / len(every)
    texts_ru = [t for note in cfg["пометки"] for t in note["строки"]]
    texts_en = [t for note in cfg["пометки"] for t in note["английские"]]
    hand = sum(r["room"] for r in every)

    # Кегль, сжатие и контур считаются друг через друга: кегль по телу, сжатие по руке
    # на английском тексте при этом кегле, контур по штриху при кегле и сжатии, потом
    # кегль заново — контур тело утолщает.
    size = pick_size(texts_ru, 0, shear, 1.0, xh, canvas)
    squeeze = min(1.0, hand / sum(width_of(t, size, 0, shear, 1.0, canvas) for t in texts_en))
    probe = texts_ru[0]

    def stroke_at(k: int) -> float:
        return stroke_of(draw_line(probe, size, k, (400, 500), 0, shear, 3, canvas, squeeze))

    sw = min(range(0, 5), key=lambda k: abs(stroke_at(k) - cfg["штрих"])) + cfg.get("толще", 0)
    size = pick_size(texts_ru, sw, shear, squeeze, xh, canvas)
    squeeze = min(1.0, hand / sum(width_of(t, size, sw, shear, 1.0, canvas) for t in texts_en))
    pen = {"low": UNDER_LOW * xh, "amp": UNDER_AMP * xh, "step": UNDER_STEP * xh, "over": 0.4 * xh,
           "width": max(3, round(UNDER_PEN * stroke_at(sw)))}
    return {"name": name, "base": base, "E": E, "C": C, "paper": paper, "eng": eng, "canvas": canvas,
            "notes": notes, "stray": stray, "xh": xh, "size": size, "squeeze": squeeze, "sw": sw,
            "shear": shear, "hand": hand, "pen": pen}


def fitting(sv: dict, cfg: dict, i: int, lines: list[str],
            scale: float = 1.0) -> list[tuple[str, int, float, str]]:
    """Строки пометки `i` против английских: (текст, длина, место, английская строка)."""
    rows = sv["notes"][i]["rows"]
    return [(t, width_of(t, round(sv["size"] * scale), sv["sw"], sv["shear"], sv["squeeze"], sv["canvas"]),
             rows[j]["room"], cfg["пометки"][i]["английские"][j])
            for j, t in enumerate(lines)]


def shrink_to_fit(sv: dict, cfg: dict, i: int, lines: list[str]) -> float:
    """Во сколько ужать кегль пометки, чтобы её строки влезли в места английских.

    Мельчить кегль **нельзя по умолчанию** — не влезла строка, значит сокращается текст
    (решение пользователя 16 сентября). Ключ `влезть` — его же отдельное решение
    по конкретной пометке: 20 сентября он оставил «Безопасность президента / превыше
    всего!» как есть и велел «сделать поменьше просто».
    """
    scale = 1.0
    for _, need, room, _ in fitting(sv, cfg, i, lines):
        if need > room:
            scale = min(scale, room / need)
    return max(0.7, scale)


def zone_of(cfg: dict, canvas) -> Image.Image:
    """Где русской пометке можно быть: рамки английских с запасом `ZONE`."""
    zone = Image.new("L", canvas, 0)
    d = ImageDraw.Draw(zone)
    for note in cfg["пометки"]:
        for x0, y0, x1, y1 in note["рамки"]:
            d.rectangle((x0 - ZONE, y0 - ZONE, x1 + ZONE, y1 + ZONE), fill=255)
    return zone


def forbidden_of(sv: dict, cfg: dict, labels: list) -> Image.Image:
    """Куда нельзя: рисунок по мерке check_pictures, печатные надписи relabel.py
    и всё за рамками пометок — там правку не пропустит слой патчера."""
    xs = [p[0] for nt in sv["notes"] for p in nt["pixels"]]
    ys = [p[1] for nt in sv["notes"] for p in nt["pixels"]]
    box = (min(xs) - 200, min(ys) - 120, max(xs) + 200, max(ys) + 120)
    out = cp.untouchable(sv["C"], sv["paper"], sv["eng"], box)
    out = ImageChops.lighter(out, ImageChops.invert(zone_of(cfg, sv["canvas"])))
    d = ImageDraw.Draw(out)
    for lb in labels:
        x0, y0, x1, y1 = lb["box"]
        d.rectangle((x0 - LABEL_PAD, y0 - LABEL_PAD, x1 + LABEL_PAD, y1 + LABEL_PAD), fill=255)
    return out


def place(text: str, row, sv: dict, seed: int, forbidden: Image.Image, occupied: Image.Image,
          under=(), scale: float = 1.0):
    """Положение строки: перебор сдвигов, лишь бы не задеть рисунок и соседние строки."""
    ang = math.radians(row["angle"])
    u, n = (math.cos(ang), math.sin(ang)), (-math.sin(ang), math.cos(ang))
    xh = sv["xh"]
    base0 = (row["x0"] + 4 + n[0] * (xh / 2), row["a"] + row["b"] * (row["x0"] + 4) + n[1] * (xh / 2))
    best = None

    def at(dn: float, du: float, spread: int = 0):
        nonlocal best
        start = (base0[0] + n[0] * dn + u[0] * du, base0[1] + n[1] * dn + u[1] * du)
        al = draw_line(text, round(sv["size"] * scale), sv["sw"], start, row["angle"], sv["shear"],
                       seed + spread, sv["canvas"], sv["squeeze"], under, sv["pen"])
        # Рисунок меряется **ядром** буквы, как в check_pictures: раздутый след давал
        # сорок «задетых» там, где проверка видит шесть, и перебор искал чистое место
        # по своей мерке, а не по судейской. Соседние строки — следом с запасом:
        # двум строкам касаться друг друга нельзя и близко.
        core = al.point(lambda v: 255 if v > 127 else 0)
        foot = al.point(lambda v: 255 if v > 60 else 0).filter(ImageFilter.MaxFilter(5))
        hit = ImageChops.multiply(core, forbidden).histogram()[255]
        clash = ImageChops.multiply(foot, occupied).histogram()[255]
        cost = (hit + clash) * BLACK + abs(dn) + abs(du) / 3
        if best is None or cost < best[0]:
            best = (cost, al, foot, dn, du, hit, clash)
        return hit == 0 and clash == 0

    for dn in (0, -4, 4, -8, 8, -12, 12, -18, 18):
        for du in (0, 10, -10, 20, -20, 30, -30, 40, -40):
            if at(dn, du):
                return best
    # Крупной сеткой чистого места не нашлось — досмотреть мелкой вокруг лучшего,
    # а потом и с другим разбросом букв: хвосту «р» в «тревоге» не хватало трёх
    # пикселей, чтобы не задеть линию плана, и рука пишет это место чуть иначе
    for spread in (0, 100, 200):
        for step in (2, 4, 6):
            dn0, du0 = best[3], best[4]
            for dn in (dn0, dn0 - step, dn0 + step, dn0 - 2 * step, dn0 + 2 * step):
                for du in (du0, du0 - step, du0 + step, du0 - 2 * step, du0 + 2 * step,
                           du0 - 3 * step, du0 + 3 * step):
                    if at(dn, du, spread):
                        return best
    return best


def compose(name: str, cfg: dict, case: str, labels: list):
    """Картинка с русскими пометками, маска чернил, отчёт и беды."""
    sv = survey(name, cfg, case)
    w, h = sv["canvas"]
    report, problems, long_lines = [], [], []
    report.append(f"{name}: тело английской строки {sv['xh']:.1f} px -> кегль {sv['size']}, контур {sv['sw']}; "
                  f"рука против Ink Free на том же английском тексте -> сжатие {sv['squeeze']:.3f}")
    if sv["stray"]:
        problems.append(f"{name}: красные английские чернила вне пометок задания — "
                        + ", ".join(f"{n} пикс. в {box}" for n, box in sv["stray"]))

    # Английские пометки снимаются подложкой ровно по своим буквам.
    gone = Image.new("L", sv["canvas"], 0)
    gp = gone.load()
    for nt in sv["notes"]:
        for p in nt["pixels"]:
            gp[p] = 255
    gone = gone.filter(ImageFilter.MaxFilter(7))
    alpha = sv["base"].getchannel("A") if sv["base"].mode == "RGBA" else None
    out = Image.composite(sv["C"], sv["base"].convert("RGB"), gone)
    # «стереть» у пометки — [рамки]: обрывки английских букв, которые подложка приняла
    # за рисунок (на том же месте буква немцев или французов — шахматная записка
    # `cut04_035`, 30 сентября 2026). В рамке тёмные пиксели карандаша заменяются бумагой.
    for note in cfg["пометки"]:
        for x0, y0, x1, y1 in note.get("стереть", []):
            E, P = sv["E"].load(), sv["paper"].load()
            wipe = Image.new("L", sv["canvas"], 0)
            wp = wipe.load()
            for y in range(y0, y1):
                for x in range(x0, x1):
                    if max(E[x, y]) < max(P[x, y]) - 30:
                        wp[x, y] = 255
            wipe = wipe.filter(ImageFilter.MaxFilter(3))
            out = Image.composite(sv["paper"], out, wipe)

    forbidden = forbidden_of(sv, cfg, labels)
    # «оригинал» у пометки — [рамки]: кусок английской строки остаётся как есть,
    # пикселями оригинала, и русским буквам туда нельзя (координаты «g6?» в записке
    # `cut01_027`: пользователь 28 сентября 2026 — «вырезать из оригинала и вставить
    # как есть»). Русская строка уходит от рамки перебором сдвигов `place`.
    keep = [box for note in cfg["пометки"] for box in note.get("оригинал", [])]
    if keep:
        d = ImageDraw.Draw(forbidden)
        for x0, y0, x1, y1 in keep:
            d.rectangle((x0 - 6, y0 - 6, x1 + 6, y1 + 6), fill=255)
    occupied = Image.new("L", sv["canvas"], 0)
    ink = Image.new("L", sv["canvas"], 0)
    for i, note in enumerate(cfg["пометки"]):
        marks = {m["строка"] - 1: m.get("слова") for m in note.get("подчеркнуть", [])}

        def lay(scale: float):
            """Разложить строки пометки при этом кегле: не трогая общие маски."""
            busy, out = occupied, []
            for j, (text, need, room, english) in enumerate(fitting(sv, cfg, i, note["строки"], scale)):
                row = sv["notes"][i]["rows"][j]
                under = [spans_of(text, marks[j])] if j in marks else []
                got = place(text, row, sv, SEED + 10 * i + j, forbidden, busy, under, scale)
                busy = ImageChops.lighter(busy, got[2])
                out.append((text, need, room, english, got))
            return out, sum(g[5] + g[6] for *_, g in out)

        scale = shrink_to_fit(sv, cfg, i, note["строки"]) if note.get("влезть") else 1.0
        laid, bad = lay(scale)
        # «влезть» — отмена запрета мельчить кегль для этой пометки (пользователь, 20 сентября).
        # Мало ужать до места английской строки: рядом бывают фигуры, и пометка о президенте
        # при x0,89 всё ещё задевала пешку. Ужимаем дальше, пока рисунок не станет чистым.
        if bad and note.get("влезть"):
            for k in (0.95, 0.9, 0.85, 0.8):
                trial = max(0.7, scale * k)
                laid, bad = lay(trial)
                if not bad:
                    scale = trial
                    break
            else:
                scale = max(0.7, scale * 0.8)
        if scale < 1.0:
            report.append(f"  пометка {i + 1}: кегль ужат до x{scale:.2f} — «влезть» в задании")
        for j, (text, need, room, english, got) in enumerate(laid):
            cost, al, foot, dn, du, hit, clash = got
            occupied = ImageChops.lighter(occupied, foot)
            ink = ImageChops.lighter(ink, al)
            flag = ""
            if need > room * ROOM:
                flag = " ✗ длиннее английской"
                long_lines.append(f"{name}, пометка {i + 1}, строка {j + 1}: «{text}» — {need / room:.0%} "
                                  f"места «{english}»")
            report.append(f"  {i + 1}.{j + 1} «{text}» {need} px против {room:.0f} у «{english}» "
                          f"({need / room:.0%}){flag}; сдвиг поперёк {dn}, вдоль {du}; "
                          f"задето рисунка {hit}, строк {clash}")
            if hit or clash:
                problems.append(f"{name}, пометка {i + 1}, строка {j + 1}: «{text}» задевает "
                                f"{'рисунок ' + str(hit) if hit else ''}{' и ' if hit and clash else ''}"
                                f"{'соседнюю строку ' + str(clash) if clash else ''} пикс.")

    noise = Image.effect_noise(sv["canvas"], 18).filter(ImageFilter.GaussianBlur(1))
    paint = Image.merge("RGB", [noise.point(lambda v, c=c: max(0, min(255, c + (v - 128) // 6)))
                                for c in cfg["чернила"]])
    out = Image.composite(paint, out, ink.point(lambda v: v * 245 // 255))
    base = sv["base"].convert("RGB")
    for box in keep:
        out.paste(base.crop(tuple(box)), tuple(box[:2]))
        ink.paste(0, tuple(box))
    if keep:
        report.append(f"  из оригинала оставлено рамок: {len(keep)} — " + ", ".join(map(str, keep)))
    if alpha is not None:
        out = out.convert("RGBA")
        out.putalpha(alpha)
    return out, ink.point(lambda v: 255 if v > 127 else 0), report, problems, long_lines


def remap_box(box, there, here):
    sx = (here[2] - here[0]) / (there[2] - there[0])
    sy = (here[3] - here[1]) / (there[3] - there[1])
    return [round(here[0] + (box[0] - there[0]) * sx), round(here[1] + (box[1] - there[1]) * sy),
            round(here[0] + (box[2] - there[0]) * sx), round(here[1] + (box[3] - there[1]) * sy)]


def derive(name: str, cfg: dict, parent: dict, case: str):
    """Мелкая копия плана: снять всю английскую надпись, перенести русскую с большой.

    Набирать тут нечего: на карточке улики 300×300 строчная буква руки — три пикселя,
    а печатная — двенадцать, и любой шрифт в них превращается в кашу (проверено
    25 августа 2026 на печатном, 20 сентября — на наборе по замеру). Поэтому берутся
    **пиксели надписей** уже собранной большой картинки и ужимаются в рамку ориентира —
    ровно так же, как игра рисует мелкую копию того же плана. Рисунок копии остаётся
    её собственным: переносятся только буквы, по маске `<большая>_ink.png`.
    """
    there, here = cfg["якорь_там"], cfg["якорь_тут"]
    E = Image.open(EN / case / f"{name}.png")
    alpha = E.getchannel("A") if E.mode == "RGBA" else None
    E = E.convert("RGB")
    m = cp.masks_for(name)
    C = m["clean"].convert("RGB")
    eng = cp.english_ink(E, C, m["mask"].convert("L"), m["hole"].convert("L"), m["paper"].convert("RGB"))
    out = Image.composite(C, E, eng.filter(ImageFilter.MaxFilter(3)))

    size = (here[2] - here[0], here[3] - here[1])
    big = Image.open(RU / case / f"{cfg['как']}.png").convert("RGB").crop(tuple(there))
    mask = Image.open(RU / case / f"{cfg['как']}_ink.png").convert("L").crop(tuple(there))
    patch = big.resize(size, Image.LANCZOS)
    patch_ink = mask.resize(size, Image.LANCZOS)
    out.paste(patch, (here[0], here[1]), patch_ink)
    ink = Image.new("L", E.size, 0)
    ink.paste(patch_ink, (here[0], here[1]))
    if alpha is not None:
        out = out.convert("RGBA")
        out.putalpha(alpha)
    ink = ink.point(lambda v: 255 if v > 80 else 0)
    report = [f"{name}: копия «{cfg['как']}» — снята английская надпись целиком ({cp.count(eng)} пикс.), "
              f"перенесено русских букв {cp.count(ink)} пикс. уменьшением в {size[0] / (there[2] - there[0]):.3f}"]
    return out, ink, report


def sheet(rows: list[tuple[str, list[Image.Image]]], path: Path) -> None:
    fnt = ImageFont.truetype(str(LABEL_FONT), 22)
    width = max(sum(im.width for im in ims) + 8 * len(ims) for _, ims in rows)
    height = sum(max(im.height for im in ims) + 34 for _, ims in rows) + 8
    out = Image.new("RGB", (width, height), (28, 28, 28))
    d = ImageDraw.Draw(out)
    y = 8
    for label, ims in rows:
        d.text((10, y), label, font=fnt, fill=(255, 215, 80))
        x = 0
        for im in ims:
            out.paste(im.convert("RGB"), (x, y + 28))
            x += im.width + 8
        y += max(im.height for im in ims) + 34
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", default="case1", help="папка дела (по умолчанию case1)")
    ap.add_argument("--only", help="набрать одну картинку")
    ap.add_argument("--check", action="store_true",
                    help="ничего не писать: набрать заново в памяти и сверить с лежащим PNG")
    ap.add_argument("--try", dest="tries", action="append", default=[], metavar="N:строка|строка",
                    help="с --only: примерить строки к пометке N, ничего не набирая")
    args = ap.parse_args()

    spec_path = RU / args.case / "notes.json"
    if not spec_path.exists():
        print(f"задания нет ({spec_path}) — набирать нечего")
        return 0
    spec = {k: v for k, v in json.loads(spec_path.read_text(encoding="utf-8")).items()
            if not k.startswith("_")}
    labels_path = RU / args.case / "labels.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.exists() else {}

    if args.tries:
        if not args.only:
            sys.exit("--try — только вместе с --only")
        cfg = spec[args.only]
        sv = survey(args.only, cfg, args.case)
        print(f"{args.only}: кегль {sv['size']}, контур {sv['sw']}, сжатие {sv['squeeze']:.3f}")
        for t in args.tries:
            num, _, text = t.partition(":")
            for line, need, room, english in fitting(sv, cfg, int(num) - 1, text.split("|")):
                print(f"  {num}: «{line}» {need} px против {room:.0f} у «{english}» — {need / room:.0%}"
                      f"{'  ✗ длиннее' if need > room * ROOM else ''}")
        return 0

    problems, rows, long_lines = [], [], []
    for name, cfg in sorted(spec.items(), key=lambda kv: "как" in kv[1]):   # копии — после своих больших
        if args.only and name != args.only:
            continue
        png = RU / args.case / f"{name}.png"
        if not png.exists():
            problems.append(f"{name}: нет {png} — сначала relabel.py")
            continue
        before = Image.open(png).convert("RGB")
        if "как" in cfg:
            out, ink, report = derive(name, cfg, spec[cfg["как"]], args.case)
            crop = tuple(cfg["якорь_тут"])
        else:
            out, ink, report, trouble, longer = compose(name, cfg, args.case,
                                                        labels.get(name, {}).get("labels", []))
            problems += trouble
            long_lines += longer
            frames = [b for note in cfg["пометки"] for b in note["рамки"]]
            crop = (min(b[0] for b in frames) - 30, min(b[1] for b in frames) - 30,
                    max(b[2] for b in frames) + 30, max(b[3] for b in frames) + 30)
        for line in report:
            print(line, flush=True)
        if args.check:
            if ImageChops.difference(before, out.convert("RGB")).getbbox():
                problems.append(f"{name}: PNG не совпадает с набором по заданию — tools/notes.py")
        else:
            out.save(png)
            # В маске букв — и печатное, и рукописное: печатное набрано раньше
            # (`prints.py`, порядок `make notes`), а проверка и мелкие копии берут
            # из `_ink.png` **все** русские буквы картинки.
            printed = RU / args.case / f"{name}_print_ink.png"
            if printed.exists():
                ink = ImageChops.lighter(ink, Image.open(printed).convert("L"))
            ink.save(RU / args.case / f"{name}_ink.png")
            print(f"  записано: {png}")
        english = Image.open(EN / args.case / f"{name}.png").convert("RGB")
        pair = [english.crop(crop), out.convert("RGB").crop(crop)]
        if pair[0].width < 500:      # мелкая копия: на листе её иначе не разглядеть
            pair = [im.resize((im.width * 3, im.height * 3), Image.NEAREST) for im in pair]
        rows.append((f"{name}: английские пометки | набор", pair))

    if rows and not args.check:
        sheet(rows, SHEET / "notes.png")
        print(f"лист: {SHEET / 'notes.png'}")
    if long_lines:
        print("\nдлиннее английской — сокращать текст, а не кегль:")
        for line in long_lines:
            print(f"  {line}")
    for p in problems:
        print(f"  БЕДА: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
