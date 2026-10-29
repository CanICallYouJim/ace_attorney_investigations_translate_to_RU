"""Маска английской надписи и настоящая подложка под ней — по языковым вариантам картинки.

Зачем. 13 сентября 2026 пользователь забраковал способ, которым снималась английская
надпись (`relabel.py`, `paste_art.py`): маска по цвету букв в рамке не видит сглаживание,
путает надпись с рисунком того же цвета и затягивает дыру соседями — отсюда хвосты
букв, затёртые стены и светлые пятна. Требование: сперва доказать, что машина видит
**все** пиксели надписи, и только потом набирать.

Как устроено. У локализованной картинки в игре семь вариантов: английский, немецкий,
французский, корейский, два китайских и японский без хвоста. Рисунок у них общий,
расходятся надписи — и шум сжатия BC7 возле них. В каждом пикселе у английских
чернил (зона — 4 пикселя вокруг) другие языки дают показания одного из классов:
бумага, красное, серое или тёмное без оттенка, прочий цвет.

  * **Местная бумага** — самый частый цвет в клетке 8×8 среди пикселей, где все языки
    согласны и нет чернил; клетки внутри надписей берут значение у соседей. Не медиана
    по языкам (пометки у всех языков в одних местах — в рукописи она розовая) и не
    среднее (в него входят серые линии и тени — бумага выходила на 20–30 темнее
    настоящей, и белое поле таблички переставало опознаваться бумагой).
  * **Английский сам показывает рисунок** — только серое у красной английской пометки
    (печатный английский текст сам серый, и на зернистой ксерокопии это правило
    оставляло его буквы): если то же значение есть у другого языка и небумажные пиксели
    английского и этого языка в окне 9×9 совпадают (пересечение к объединению ≥ 0,7).
    Групп «за» должно быть больше, чем групп, показывающих здесь бумагу. Так остаются
    стены и перила, которые сжатие высветлило у языков с красной пометкой рядом.
  * **Под английской надписью рисунок** — если его показывают хотя бы две группы, их
    небумажные пиксели в окне совпадают и групп «за» больше, чем групп с бумагой.
    У красной пометки серое и тёмное — одно показание, значение — медиана тёмной
    половины: сжатие рисует там одну линию то 70, то 150. У печатного текста —
    только одинаковые значения и простая медиана, иначе на зернистой шапке
    проступали буквы. Под красной английской буквой тёмное принимается и от одной
    группы, если бумагу здесь не показал никто.
  * **Бумага** — хватает одной группы, берётся медиана показаний.

Японский и оба китайских — одна группа: у них общие иероглифы одним шрифтом. Группа,
у которой один язык показал бумагу, а другой — что-то нарисованное, не голосует.

Принятый рисунок проверяется целым куском: остаётся, если продолжается в нетронутый
рисунок того же цвета за зоной надписи (красное — красным, серое — тёмным) и в куске
не меньше 12 пикселей, если его показали все группы или если три группы показывают
весь кусок одной формой (совпадение по рамке куска ≥ 0,8). Иначе это совпадение букв
(цифры корейской и китайской даты, штрихи «Rook» у трёх языков в табличке): пиксели
идут в бумагу или в дыру. Тонкую линию, перечёркнутую буквой, дыра не теряет — её
восстанавливает протяжка короткого разрыва.

Дыра — пиксель английских чернил, где ни бумаги, ни рисунка не подтвердил никто.
Короткий разрыв линии (до 10 пикселей) тянется вдоль строки или столбца, если концы
похожи, не красные и темнее бумаги; остальное — размыванием от решённых соседей.

**След** — пиксель подложки у бывшей надписи, который не бумага, не подтверждён
двумя группами и не прилегает к рисунку. Это остатки букв; их число — в `stats.json`
и оранжевым на листе.

Где голоса языков врут — надпись у всех языков стоит в одном месте: подписи комнат,
вывеска, логотип. Буквы чужих подписей совпадают друг с другом, два-три языка
«подтверждают» их как рисунок, и в подложке остаются призраки букв (план дела 3,
14 сентября). **Подписи на ровной заливке** (`labels.json`: рамки и цвета букв) после
голосования чистятся по палитре — в рамке подписи, если фон вокруг букв ровная
заливка (оттенки плотно в ±8, шум сжатия; бумага плана с текстурой сюда не попадает).
Включается ключом `"подложка": "заливка"` в задании картинки — только там, где чистка
проверена глазами (`label_job`):

  * пиксель заливки и пиксель не на треугольнике палитры (цвет букв, обводка, фон и их
    смеси) остаются английскими — это фон и рисунок: стены, балки, лепестки, лестница;
  * на треугольнике, и хоть один язык показывает здесь чистую заливку, — английская
    буква: подложка = цвет фона;
  * на треугольнике, чистую заливку не показал никто, — буква, если её кусок не уходит
    за рамку в нетронутый рисунок; уходит — это рисунок того же цвета.

Цвет фона — самый частый среди пикселей рамки, где все языки согласны: у «Сада» это
серое поле, хотя над лестницей рядом пол зала. Вывеска на текстуре и рисованный
логотип так не чистятся: там дыр 15 и 67 % маски (табличка «Тортофеерии», афиша
самурая) — подложку нужно получать иначе.

    tools\\text_mask.py cut00_007 cut00_010    маска, подложка, лист — в work/graphics_masks/
    tools\\text_mask.py --all                  все картинки из work/graphics_ru/*/labels.json и art.json

Картинки — кадры игры, в репозиторий не идут (`.gitignore`).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from itertools import combinations
from pathlib import Path

import UnityPy
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from common import WORK, load_json
from layer_localized import index, material_specs, original, recipes, variants
from picture_layer import FLIP, leaf, model_texture, short

OUT = WORK / "graphics_masks"
EN = WORK / "graphics_en"
RU = WORK / "graphics_ru"
ORDER = ("ger", "fre", "kor", "sim", "tra", "base", "eng")   # английский последним
GROUP = {"eng": "eng", "ger": "ger", "fre": "fre", "kor": "kor", "sim": "cjk", "tra": "cjk", "base": "cjk"}
TOL = 24        # «то же значение» с учётом шума сжатия BC7
LOW = 10        # изменение меньше этого в маску не идёт
AGREE = 0.7     # совпадение небумажных пикселей двух языков в окне 9×9
SHAPE = 0.8     # совпадение небумажных пикселей по рамке целого куска рисунка
MIN_UNION = 10  # окно, где небумажного меньше трёх пикселей, не судит
SKIP = 12       # английский пиксель ближе этого к бумаге не трогается
PAPER = 20      # «похоже на местную бумагу» по яркости
TINT = 8        # и по оттенку
LINE = 30       # «линия рисунка» — темнее местной бумаги на столько
GAP = 10        # короткий разрыв линии
ZONE = 9        # окно зоны разбора вокруг английских чернил
CELL = 8        # клетка оценки бумаги
MIN_PIECE = 12  # кусок рисунка меньше этого — не рисунок; линию через букву восстановит протяжка
WALLED = 60     # кусок «рисунка», приклеенный к чернилам и больше этого, — предмет, который обвела надпись
PAPERED = 4     # и в нём кусок от стольких пикселей, где язык показал бумагу; зазор печатается в отчёте
FLAT_PAD = 12   # подпись на ровной заливке: запас вокруг рамки из labels.json,
FLAT_RING = 10  # кольцо вокруг — если фона внутри рамки мало,
FLAT_TRI = 20   # «на треугольнике палитры» — расстояние до смеси цвета букв, обводки и фона,
FLAT_TIGHT = 8  # оттенок заливки — только шум сжатия,
FLAT_DENSE = 0.85  # доля фона плотно у своего цвета; меньше — текстура, а не заливка
N8 = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1))
HOLE, SINGLE, CONFIRMED = 1, 2, 3


def maxch(im: Image.Image) -> Image.Image:
    r, g, b = im.split()
    return ImageChops.lighter(ImageChops.lighter(r, g), b)


def minch(im: Image.Image) -> Image.Image:
    r, g, b = im.split()
    return ImageChops.darker(ImageChops.darker(r, g), b)


def over(mask: Image.Image, t: int) -> Image.Image:
    return mask.point(lambda v, t=t: 255 if v > t else 0)


def ink(v) -> str | None:
    """Цвет чернил: `r` — красный маркер, `d` — тёмное, None — бумага и светлое."""
    r, g, b = v
    if r > 90 and r - max(g, b) > 45:
        return "r"
    if max(v) < 130:
        return "d"
    return None


def near(a, b, t: int = TOL) -> bool:
    return abs(a[0] - b[0]) <= t and abs(a[1] - b[1]) <= t and abs(a[2] - b[2]) <= t


def lum(v) -> int:
    return (v[0] * 3 + v[1] * 6 + v[2]) // 10


def chroma(v) -> int:
    return max(v) - min(v)


def paperlike(v, paper) -> bool:
    return near(v, paper, PAPER) and chroma(v) <= chroma(paper) + TINT


def kind(v, paper) -> str:
    """Класс показания: `p` бумага, `r` красное, `n` серое или тёмное без оттенка, `c` прочий цвет."""
    if paperlike(v, paper):
        return "p"
    if ink(v) == "r":
        return "r"
    if chroma(v) <= chroma(paper) + TINT + 16:
        return "n"
    return "c"


def continues(value, outside, paper) -> bool:
    """Нетронутый пиксель за зоной продолжает рисунок того же цвета: красное — красным, серое — тёмным."""
    k = kind(value, paper)
    if k == "r":
        return ink(outside) == "r"
    if k == "n":
        return kind(outside, paper) == "n" and lum(outside) < lum(paper) - LINE
    return kind(outside, paper) == k


def median(values):
    return tuple(sorted(v[k] for v in values)[len(values) // 2] for k in range(3))


def pick(values, k: str):
    """Значение рисунка по показаниям: у серого — медиана тёмной половины, сжатие только высветляет."""
    if k == "n":
        values = sorted(values, key=lum)[: (len(values) + 1) // 2]
    return median(values)


def local_paper(E: Image.Image, differ: Image.Image) -> Image.Image:
    """Цвет бумаги под надписями — самый частый цвет согласных пикселей без чернил в клетке 8×8."""
    W, H = E.size
    r, g, b = E.split()
    dark = ImageChops.invert(maxch(E)).point(lambda v: 255 if v > 125 else 0)
    red = ImageChops.multiply(r.point(lambda v: 255 if v > 90 else 0),
                              over(ImageChops.subtract(r, ImageChops.lighter(g, b)), 45))
    usable = ImageChops.multiply(ImageChops.invert(differ.filter(ImageFilter.MaxFilter(5))),
                                 ImageChops.invert(ImageChops.lighter(dark, red)))
    up, ep = usable.load(), E.load()
    gw, gh = (W + CELL - 1) // CELL, (H + CELL - 1) // CELL
    known = {}
    for cy in range(gh):
        for cx in range(gw):
            bins: dict[int, list] = {}
            for y in range(cy * CELL, min(H, (cy + 1) * CELL)):
                for x in range(cx * CELL, min(W, (cx + 1) * CELL)):
                    if up[x, y]:
                        v = ep[x, y]
                        bins.setdefault(lum(v) // 6, []).append(v)
            if sum(len(vs) for vs in bins.values()) < 12:
                continue
            top = max(bins, key=lambda k: len(bins[k]) + len(bins.get(k - 1, ())) + len(bins.get(k + 1, ())))
            known[(cx, cy)] = median(bins[top] + bins.get(top - 1, []) + bins.get(top + 1, []))
    missing = {(cx, cy) for cy in range(gh) for cx in range(gw)} - set(known)
    while missing:
        step = {}
        for cx, cy in missing:
            vals = [known[q] for q in ((cx + dx, cy + dy) for dx, dy in N8) if q in known]
            if vals:
                step[(cx, cy)] = median(vals)
        if not step:
            break
        known.update(step)
        missing -= step.keys()
    grid = Image.new("RGB", (gw, gh), (230, 230, 230))
    gp = grid.load()
    for q, v in known.items():
        gp[q] = v
    return grid.resize((gw * CELL, gh * CELL), Image.BILINEAR).crop((0, 0, W, H))


def case_of(name: str) -> str | None:
    for manifest in sorted(EN.glob("*/manifest.json")):
        if name in (load_json(manifest) or {}):
            return manifest.parent.name
    return None


def load_variants(name: str) -> dict[str, Image.Image]:
    """Все языковые варианты картинки из нетронутого бандла, лицом вверх."""
    case = case_of(name)
    if not case:
        sys.exit(f"{name}: нет в work/graphics_en/*/manifest.json")
    man = load_json(EN / case / "manifest.json")[name]
    hits = [e for e in index().get(name, []) if short(e[0]) == man["bundle"]]
    if not hits:
        sys.exit(f"{name}: нет в переписи для {man['bundle']}")
    bundle, gerkey, _ = hits[0]
    path = original(bundle)
    if path is None:
        sys.exit(f"{name}: нетронутого оригинала нет — сверять не с чем")
    env = UnityPy.load(str(path))
    out = {}
    material = material_specs().get(name) if man.get("kind") == "material" else None
    for key in variants(gerkey, env.container):
        lf = leaf(key)
        lang = "base" if lf == (material["model"] if material else name) else lf.rsplit("_", 1)[-1]
        if material:
            stem = material["source_texture"].rsplit("_", 1)[0]
            texture_name = stem if lang == "base" else f"{stem}_{lang}"
            im = model_texture(env, key, texture_name)[1].read().image.convert("RGBA")
        else:
            im = env.container[key].read().image.convert("RGBA")
        if man["flipped"]:
            im = im.transpose(FLIP)
        out[lang] = im
    return out


def label_job(name: str) -> dict | None:
    """Задание подписей на ровной заливке (`labels.json` дела с ключом `"подложка": "заливка"`).

    Ключ ставится там, где чистка проверена глазами. Сама по себе ровность рамки не довод:
    у планов дела 1 белая рамка подписи тоже ровная, но в ней фигурки и перегородка, а у миниатюр
    запас в 12 пикселей — полкарточки, и 14 сентября чистка утроила там следы.
    """
    case = case_of(name)
    if not case:
        return None
    for job in recipes(RU / case).get(name, []):
        if job.get("подложка") == "заливка" and job.get("labels") and "fill" in job and "stroke" in job:
            return job
    return None


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _seg2(v, p, q) -> float:
    d = (q[0] - p[0], q[1] - p[1], q[2] - p[2])
    w = (v[0] - p[0], v[1] - p[1], v[2] - p[2])
    dd = _dot(d, d)
    t = 0.0 if dd == 0 else max(0.0, min(1.0, _dot(w, d) / dd))
    return (w[0] - t * d[0]) ** 2 + (w[1] - t * d[1]) ** 2 + (w[2] - t * d[2]) ** 2


def palette_distance(v, a, b, c) -> float:
    """Расстояние от цвета до треугольника смесей трёх цветов: буквы, обводка, фон."""
    u = (a[0] - c[0], a[1] - c[1], a[2] - c[2])
    w = (b[0] - c[0], b[1] - c[1], b[2] - c[2])
    r = (v[0] - c[0], v[1] - c[1], v[2] - c[2])
    uu, ww, uw, ur, wr = _dot(u, u), _dot(w, w), _dot(u, w), _dot(u, r), _dot(w, r)
    det = uu * ww - uw * uw
    if det > 1e-9:
        t = (ur * ww - wr * uw) / det
        s = (wr * uu - ur * uw) / det
        if t >= 0 and s >= 0 and t + s <= 1:
            e = (r[0] - t * u[0] - s * w[0], r[1] - t * u[1] - s * w[1], r[2] - t * u[2] - s * w[2])
            return math.sqrt(_dot(e, e))
    return math.sqrt(min(_seg2(v, a, b), _seg2(v, b, c), _seg2(v, a, c)))


def flatten_labels(job: dict, V: dict[str, Image.Image], C: Image.Image, T: Image.Image,
                   hole: Image.Image, state: Image.Image, paper: Image.Image, disagree) -> dict:
    """Подписи на ровной заливке: в рамке подписи подложка — цвет фона там, где английская буква.

    Правила — в шапке модуля. `disagree` — доступ к маске «языки расходятся» с запасом.
    Цвет фона пишется и в оценку бумаги: тёмную заливку (серое поле у «Сада») та не видит,
    и без этого следы и проверка картинок принимали фон за тёмный предмет.
    """
    E = V["eng"]
    W, H = E.size
    others = [l for l in V if l != "eng"]
    ep, cp, tp, hp, sp, pap = E.load(), C.load(), T.load(), hole.load(), state.load(), paper.load()
    P = {l: V[l].load() for l in others}
    fill, stroke = tuple(job["fill"]), tuple(job["stroke"])
    out = {"labels": 0, "skipped": 0, "filled": 0, "kept": 0}
    for lab in job["labels"]:
        bx0, by0, bx1, by1 = lab["box"]
        x0, y0 = max(0, bx0 - FLAT_PAD), max(0, by0 - FLAT_PAD)
        x1, y1 = min(W, bx1 + FLAT_PAD), min(H, by1 + FLAT_PAD)

        def inside(q, x0=x0, y0=y0, x1=x1, y1=y1) -> bool:
            return x0 <= q[0] < x1 and y0 <= q[1] < y1

        inner = [(x, y) for y in range(y0, y1) for x in range(x0, x1) if not disagree[x, y]]
        ring = [(x, y) for y in range(max(0, y0 - FLAT_RING), min(H, y1 + FLAT_RING))
                for x in range(max(0, x0 - FLAT_RING), min(W, x1 + FLAT_RING))
                if not inside((x, y)) and not disagree[x, y]]
        pool = inner if len(inner) >= 20 else ring
        bins: dict = {}
        for q in pool:
            v = ep[q]
            bins.setdefault((v[0] // 8, v[1] // 8, v[2] // 8), []).append(v)
        if not bins:
            out["skipped"] += 1
            continue
        room = median(max(bins.values(), key=len))
        close = [ep[q] for q in pool + ring if near(ep[q], room)]
        if len(close) < 20 or sum(1 for v in close if near(v, room, FLAT_TIGHT)) < FLAT_DENSE * len(close):
            out["skipped"] += 1           # фон с текстурой (бумага плана) — по палитре не чистится
            continue
        out["labels"] += 1
        undecided = set()
        for y in range(y0, y1):
            for x in range(x0, x1):
                ev = ep[x, y]
                if near(ev, room, FLAT_TIGHT) or palette_distance(ev, fill, stroke, room) > FLAT_TRI:
                    cp[x, y] = ev                                   # заливка или рисунок другого цвета
                elif any(near(P[l][x, y], room, FLAT_TIGHT) and not near(P[l][x, y], ev, 12) for l in others):
                    cp[x, y] = room                                 # язык показал здесь чистую заливку
                    sp[x, y] = CONFIRMED
                    out["filled"] += 1
                else:
                    undecided.add((x, y))
        seen = set()
        for start in list(undecided):
            if start in seen:
                continue
            comp, stack, touches = [], [start], False
            seen.add(start)
            while stack:
                p = stack.pop()
                comp.append(p)
                for dx, dy in N8:
                    q = (p[0] + dx, p[1] + dy)
                    if not (0 <= q[0] < W and 0 <= q[1] < H):
                        continue
                    if q in undecided:
                        if q not in seen:
                            seen.add(q)
                            stack.append(q)
                    elif not inside(q) and not near(ep[q], room):
                        touches = True
            for p in comp:
                if touches:                                         # уходит за рамку в рисунок — рисунок
                    cp[p] = ep[p]
                    out["kept"] += 1
                else:
                    cp[p] = room
                    sp[p] = SINGLE
                    out["filled"] += 1
        for y in range(y0, y1):
            for x in range(x0, x1):
                c, e = cp[x, y], ep[x, y]
                changed = max(abs(c[0] - e[0]), abs(c[1] - e[1]), abs(c[2] - e[2])) > LOW
                tp[x, y] = 255 if changed else 0
                hp[x, y] = 0
                pap[x, y] = room
                if not changed:
                    sp[x, y] = 0
    return out


def build(images: dict[str, Image.Image], labels: dict | None = None) -> dict:
    V = {l: images[l].convert("RGB") for l in ORDER if l in images}
    E = V["eng"]
    W, H = E.size
    dropped = []
    for l in list(V):
        if l != "eng" and over(maxch(ImageChops.difference(V[l], E)), TOL).histogram()[255] < 0.001 * W * H:
            dropped.append(l)          # несёт ту же надпись, что английский, — не голосует
            del V[l]
    langs = list(V)
    others = [l for l in langs if l != "eng"]
    if not others:
        raise ValueError("других языков с отличающейся надписью нет — сравнивать не с чем")
    groups_total = len({GROUP[l] for l in others})

    region = Image.new("L", E.size, 0)
    for a, b in combinations(langs, 2):
        region = ImageChops.lighter(region, over(maxch(ImageChops.difference(V[a], V[b])), TOL))
    rp = region.filter(ImageFilter.MaxFilter(7)).load()

    paper = local_paper(E, region)
    pp, ep = paper.load(), E.load()
    P = {l: V[l].load() for l in langs}

    paper_l = paper.convert("L")
    paper_c = ImageChops.subtract(maxch(paper), minch(paper))
    marked = {}
    for l in langs:
        darker = over(ImageChops.subtract(paper_l, V[l].convert("L")), PAPER)
        tinted = over(ImageChops.subtract(ImageChops.subtract(maxch(V[l]), minch(V[l])), paper_c), TINT)
        marked[l] = ImageChops.lighter(darker, tinted)
    overlap = {}
    for a, b in combinations(langs, 2):
        if GROUP[a] == GROUP[b]:
            continue
        same = ImageChops.invert(over(maxch(ImageChops.difference(V[a], V[b])), TOL))
        inter = ImageChops.multiply(ImageChops.multiply(marked[a], marked[b]), same)
        union = ImageChops.lighter(marked[a], marked[b])
        overlap[frozenset((a, b))] = (inter.filter(ImageFilter.BoxBlur(4)).load(),
                                      union.filter(ImageFilter.BoxBlur(4)).load())

    def agrees(a: str, b: str, x: int, y: int) -> bool:
        pair = overlap.get(frozenset((a, b)))
        return bool(pair) and pair[1][x, y] >= MIN_UNION and pair[0][x, y] >= AGREE * pair[1][x, y]

    ink_e = Image.new("L", E.size, 0)
    red_e = Image.new("L", E.size, 0)
    ip, rdp = ink_e.load(), red_e.load()
    for y in range(H):
        for x in range(W):
            if rp[x, y]:
                c = ink(ep[x, y])
                if c:
                    ip[x, y] = 255
                    if c == "r":
                        rdp[x, y] = 255
    zone = ink_e.filter(ImageFilter.MaxFilter(ZONE)).load()
    zone_r = red_e.filter(ImageFilter.MaxFilter(5)).load()
    zone_r4 = red_e.filter(ImageFilter.MaxFilter(ZONE)).load()

    B = E.copy()
    bp = B.load()
    state = Image.new("L", E.size, 0)
    sp = state.load()
    drawn = {}        # принятый рисунок: пиксель -> (сколько групп, какие языки)
    fallback = {}     # принятый рисунок: пиксель -> (бумага, групп), если бумагу тоже показывали
    for y in range(H):
        for x in range(W):
            if not rp[x, y] or not zone[x, y]:
                continue
            ev, pv = ep[x, y], pp[x, y]
            if near(ev, pv, SKIP) and chroma(ev) <= chroma(pv) + TINT:
                continue
            ek = kind(ev, pv)
            flat, flat_langs, shown = [], [], {}
            for l in others:
                v = P[l][x, y]
                k = kind(v, pv)
                if k == "p":
                    flat.append(v)
                    flat_langs.append(l)
                else:
                    shown.setdefault(k, []).append((l, v))
            painted = {GROUP[l] for items in shown.values() for l, _ in items}
            split = {GROUP[l] for l in flat_langs} & painted      # у одного бумага, у другого рисунок
            flat_groups = {GROUP[l] for l in flat_langs} - split
            paper_pick = median(flat) if flat else None

            choice = None
            if ek == "n" and zone_r4[x, y] and "n" in shown:   # английский сам показывает рисунок у красной пометки
                backers = [l for l, v in shown["n"] if GROUP[l] not in split
                           and near(v, ev) and agrees("eng", l, x, y)]
                backing = {GROUP[l] for l in backers}
                if len(backing) > len(flat_groups):
                    choice = (ev, len(backing), frozenset(backers) | {"eng"})
            if choice is None:                   # под английской надписью рисунок
                for k, items in shown.items():
                    if k == "n" and zone_r4[x, y]:      # у красной пометки сжатие рисует одну линию разными серыми
                        clusters = [items]
                    else:
                        clusters = []
                        for l, v in items:
                            for cl in clusters:
                                if near(cl[0][1], v):
                                    cl.append((l, v))
                                    break
                            else:
                                clusters.append([(l, v)])
                    for cl in clusters:
                        voters = [(l, v) for l, v in cl if GROUP[l] not in split]
                        sg = {GROUP[l] for l, _ in voters}
                        if len(sg) >= 2:
                            ok = len(sg) > len(flat_groups) and any(
                                agrees(a, b, x, y) for (a, _), (b, _) in combinations(voters, 2))
                        elif len(sg) == 1:
                            ok = k == "n" and not flat_groups and bool(zone_r[x, y])
                        else:
                            ok = False
                        if ok and (choice is None or len(sg) > choice[1]):
                            shades = [v for _, v in voters]
                            value = pick(shades, k) if zone_r4[x, y] else median(shades)
                            choice = (value, len(sg), frozenset(l for l, _ in voters))

            if choice is not None:
                value, n, who = choice
                bp[x, y] = value
                sp[x, y] = CONFIRMED if n >= 2 else SINGLE
                drawn[(x, y)] = (n, who)
                if paper_pick:
                    fallback[(x, y)] = (paper_pick, len(flat_groups))
            elif paper_pick:
                bp[x, y] = paper_pick
                sp[x, y] = CONFIRMED if len(flat_groups) >= 2 else SINGLE
            elif ink(ev):
                sp[x, y] = HOLE

    def whole_shape(comp: list, votes: dict) -> bool:
        """Три группы показывают весь кусок одной формой — рисунок, а не совпадение букв."""
        common = [l for l, c in votes.items() if l != "eng" and 2 * c >= len(comp)]
        if len({GROUP[l] for l in common}) < 3:
            return False
        xs = [p[0] for p in comp]
        ys = [p[1] for p in comp]
        box = (max(0, min(xs) - 4), max(0, min(ys) - 4), min(W, max(xs) + 5), min(H, max(ys) + 5))
        matched = set()
        for a, b in combinations(common, 2):
            if GROUP[a] == GROUP[b]:
                continue
            ma, mb = marked[a].crop(box), marked[b].crop(box)
            same = ImageChops.invert(over(maxch(ImageChops.difference(V[a].crop(box), V[b].crop(box))), TOL))
            inter = ImageChops.multiply(ImageChops.multiply(ma, mb), same).histogram()[255]
            union = ImageChops.lighter(ma, mb).histogram()[255]
            if union and inter >= SHAPE * union:
                matched.update((GROUP[a], GROUP[b]))
        return len(matched) >= 3

    eng_ink = marked["eng"].load()      # где у англичанина его собственные чернила
    dropped_share, kept_share = 10 ** 9, 0   # зазор у порога PAPERED
    seen, coincidences = set(), 0
    for start in list(drawn):
        if start in seen or start not in drawn:
            continue
        comp, stack, strongest, touches, votes = [], [start], 0, False, {}
        comp_set = set()
        glued = False         # кусок приклеен к английским чернилам того же цвета
        spills = False        # и тот же цвет продолжается не в чернила, а в рисунок
        seen.add(start)
        while stack:
            cx, cy = stack.pop()
            comp.append((cx, cy))
            comp_set.add((cx, cy))
            n, who = drawn[(cx, cy)]
            strongest = max(strongest, n)
            for l in who:
                votes[l] = votes.get(l, 0) + 1
            for dx, dy in N8:
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < W and 0 <= ny < H):
                    continue
                q = (nx, ny)
                if q in drawn:
                    if q not in seen:
                        seen.add(q)
                        stack.append(q)
                else:
                    if not paperlike(ep[nx, ny], pp[nx, ny]) and near(ep[cx, cy], ep[nx, ny]):
                        if eng_ink[nx, ny]:
                            glued = True      # продолжение того же штриха англичанина
                        else:
                            spills = True     # тот же цвет уходит в рисунок — это не буква
                    if not zone[nx, ny] and continues(bp[cx, cy], ep[nx, ny], pp[nx, ny]):
                        touches = True
        # «Все группы показали тёмное» — не довод, если кусок **сам приклеен
        # к английским чернилам того же цвета и никуда не ведёт**. Это не деталь
        # рисунка, а часть самой буквы: стык, внутренний угол, засечка. Голоса
        # других языков подтверждают тут не рисунок, а каждый свою букву — в этом
        # месте бумаги не видел никто.
        # Так в подложке плана 24 марта жил стык английской `k` из `Rook`: 21 px,
        # `touches=False`, приклеен к штриху `k`, голоса всех четырёх групп
        # (у немцев `m` в `Turm`, у французов `r` в `Latour`, у корейцев черта
        # в `로`, у китайцев в `城`). Набор перерисовал его как рисунок, и он вылез
        # в пустоту буквы «я» — нашёл пользователь 21 сентября 2026.
        # Два ограничителя обязательны, оба поставлены глазом по листам, а не числом.
        # Широкая правка «нет выхода — не рисунок» съела край коридора на плане
        # дела 3; «приклеен к чернилам» без `spills` подъедала край стены там же,
        # где английская буква стояла к стене вплотную: тот же тёмный цвет уходил
        # **в стену**, а не в букву. Настоящий кусок рисунка выдаёт себя тем, что
        # его цвет продолжается за пределы чернил.
        # И решающее: **бумага бьёт чернила**. Надпись может только закрыть
        # подложку, осветлить её она не может. Значит, если хоть один язык
        # показал в этом пикселе бумагу (`fallback` — он и хранит такое
        # наблюдение), то бумага там и есть, а тёмное у прочих языков — их
        # собственные буквы. Где бумаги не показал никто и все семь языков дают
        # один и тот же цвет до единицы — это рисунок, и трогать его нельзя:
        # на плане дела 3 так подъедался край стены.
        # Наблюдение бумаги считается **куском**, а не долей: одиночный пиксель,
        # где чей-то язык прочитал бумагу, — это край рисунка, размытый сжатием,
        # и по нему подложку рвать нельзя (так подъедался обод вентилятора
        # на плане 24 марта: 44 px, бумага ровно в одном). Кусок бумаги в четыре
        # пикселя и больше — это уже просвет между чужими буквами.
        seen_p, papered = set(), 0
        for q in comp:
            if q not in fallback or q in seen_p:
                continue
            stack, size = [q], 0
            seen_p.add(q)
            while stack:
                a, b = stack.pop()
                size += 1
                for dx, dy in N8:
                    r = (a + dx, b + dy)
                    if r in fallback and r not in seen_p and r in comp_set:
                        seen_p.add(r)
                        stack.append(r)
            papered = max(papered, size)
        if not touches and glued and not spills and len(comp) <= WALLED:
            # Зазор у порога печатается: без него «ноль находок» ничего не значит.
            # Замер на плане 24 марта: стык английской `k` — кусок бумаги 10
            # (обязан уйти), обод вентилятора рядом — 1 (обязан остаться).
            if papered >= PAPERED:
                dropped_share = min(dropped_share, papered)
            else:
                kept_share = max(kept_share, papered)
        if not touches and glued and not spills and papered >= PAPERED and len(comp) <= WALLED:
            pass                      # это часть буквы, а не рисунок
        elif (touches and len(comp) >= MIN_PIECE) or strongest >= groups_total                 or whole_shape(comp, votes):
            continue
        for q in comp:
            del drawn[q]
            coincidences += 1
            fb = fallback.get(q)
            if fb:
                bp[q] = fb[0]
                sp[q] = CONFIRMED if fb[1] >= 2 else SINGLE
            elif ink(ep[q]):
                bp[q] = ep[q]
                sp[q] = HOLE
            else:
                bp[q] = ep[q]
                sp[q] = 0

    hole = state.point(lambda v: 255 if v == HOLE else 0)
    T = ImageChops.lighter(over(maxch(ImageChops.difference(E, B)), LOW), hole)
    tp = T.load()

    C = Image.composite(B, E, T)
    cp, hp = C.load(), hole.load()
    done = set()
    for y in range(H):
        for x in range(W):
            if not hp[x, y]:
                continue
            ends = {}
            for side, dx, dy in (("l", -1, 0), ("r", 1, 0), ("u", 0, -1), ("d", 0, 1)):
                k, xx, yy = 1, x + dx, y + dy
                while 0 <= xx < W and 0 <= yy < H and k <= GAP and hp[xx, yy]:
                    k, xx, yy = k + 1, xx + dx, yy + dy
                if 0 <= xx < W and 0 <= yy < H and k <= GAP:
                    ends[side] = (k, cp[xx, yy])
            for a, b in (("l", "r"), ("u", "d")):
                if (a in ends and b in ends and near(ends[a][1], ends[b][1])
                        and ink(ends[a][1]) != "r" and ink(ends[b][1]) != "r"
                        and max(lum(ends[a][1]), lum(ends[b][1])) < lum(pp[x, y]) - 12):
                    (ka, va), (kb, vb) = ends[a], ends[b]
                    cp[x, y] = tuple((va[i] * kb + vb[i] * ka) // (ka + kb) for i in range(3))
                    done.add((x, y))
                    break

    todo = {(x, y) for y in range(H) for x in range(W) if hp[x, y]} - done
    for _ in range(80):
        if not todo:
            break
        step = []
        for (x, y) in todo:
            acc = [cp[x + dx, y + dy] for dx, dy in N8
                   if 0 <= x + dx < W and 0 <= y + dy < H and (x + dx, y + dy) not in todo]
            if len(acc) >= 3:
                step.append(((x, y), tuple(sum(a[k] for a in acc) // len(acc) for k in range(3))))
        if not step:
            break
        for p, v in step:
            cp[p] = v
            todo.discard(p)
    for (x, y) in todo:
        cp[x, y] = pp[x, y]
    flat = flatten_labels(labels, V, C, T, hole, state, paper, rp) if labels else None

    # следы: не бумага, не подтверждено двумя группами, к рисунку не прилегает
    traces = Image.new("L", E.size, 0)
    trp = traces.load()
    for y in range(H):
        for x in range(W):
            if not tp[x, y] or (x, y) in drawn or (x, y) in done:
                continue
            v = cp[x, y]
            if paperlike(v, pp[x, y]):
                continue
            if len({GROUP[l] for l in others if near(P[l][x, y], v)}) >= 2:
                continue
            beside = False
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < W and 0 <= ny < H and ((nx, ny) in drawn or (nx, ny) in done
                            or (not zone[nx, ny] and lum(ep[nx, ny]) < lum(pp[nx, ny]) - LINE)):
                        beside = True
                        break
                if beside:
                    break
            if not beside:
                trp[x, y] = 255

    drawn_map = Image.new("L", E.size, 0)
    bridged = Image.new("L", E.size, 0)
    dmp, brp = drawn_map.load(), bridged.load()
    for q, (n, _) in drawn.items():
        dmp[q] = min(255, 60 * n)          # яркость — сколько групп показали рисунок
    for q in done:
        brp[q] = 255

    counts = {HOLE: 0, SINGLE: 0, CONFIRMED: 0}
    for y in range(H):
        for x in range(W):
            if tp[x, y] and sp[x, y] in counts:
                counts[sp[x, y]] += 1
    total = T.histogram()[255]
    clean = C.convert("RGBA")
    clean.putalpha(images["eng"].getchannel("A"))
    n_holes, n_traces = hole.histogram()[255], traces.histogram()[255]
    return {
        "eng": E, "clean": clean, "mask": T, "hole": hole, "state": state, "traces": traces,
        "drawn": drawn_map, "bridged": bridged, "paper": paper,
        "stats": {
            "mask_px": total,
            "confirmed": counts[CONFIRMED], "single": counts[SINGLE], "holes": n_holes,
            "confirmed_share": round(counts[CONFIRMED] / total, 4) if total else 0,
            "hole_share": round(n_holes / total, 4) if total else 0,
            "traces": n_traces, "coincidences_rejected": coincidences,
            # Зазор у порога PAPERED: что лежит по обе стороны. Зазор в ноль
            # значит, что порог уже слеп (правило №13, 20 сентября 2026).
            "papered_dropped": dropped_share if dropped_share < 10 ** 9 else None,
            "papered_kept": kept_share,
            "languages": langs, "dropped_as_duplicates": dropped, "flat_labels": flat,
        },
    }


def sheet(name: str, res: dict) -> Image.Image:
    font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 18)
    E, C = res["eng"], res["clean"].convert("RGB")
    ov = E.copy()
    ov.paste((255, 0, 255), mask=res["mask"])
    ov.paste((0, 200, 255), mask=res["hole"])
    marked = C.copy()
    marked.paste((255, 140, 0), mask=res["traces"].filter(ImageFilter.MaxFilter(3)))
    w = 960 if E.width >= 900 else E.width * 3
    s = w / E.width
    h = int(E.height * s)
    how = Image.LANCZOS if s < 1 else Image.NEAREST
    tiles = (("оригинал", E),
             ("пурпур — английская надпись; голубое — подложку не показал ни один язык", ov),
             ("подложка без надписи", C),
             ("оранжевое — следы букв на подложке", marked))
    out = Image.new("RGB", (w, len(tiles) * (h + 24)), (30, 30, 30))
    dr = ImageDraw.Draw(out)
    for k, (title, im) in enumerate(tiles):
        out.paste(im.resize((w, h), how), (0, k * (h + 24) + 24))
        dr.text((6, k * (h + 24) + 2), f"{name}: {title}", fill=(255, 255, 0), font=font)
    return out


def all_names() -> list[str]:
    names = set()
    for spec in list(RU.glob("*/labels.json")) + list(RU.glob("*/art.json")):
        # Ключ `_` в задании — пояснение для человека, а не картинка (так же
        # его пропускает `layer_localized.recipes`). Без этого `--all` падал
        # на первом же задании с пояснением.
        names.update(k for k, v in (load_json(spec) or {}).items() if isinstance(v, dict))
    return sorted(names)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="имена картинок без языкового хвоста")
    ap.add_argument("--all", action="store_true", help="все картинки из заданий work/graphics_ru")
    args = ap.parse_args()
    names = all_names() if args.all else args.names
    if not names:
        ap.error("назовите картинки или --all")
    OUT.mkdir(parents=True, exist_ok=True)
    stats_path = OUT / "stats.json"
    stats = load_json(stats_path, default={}) or {}
    for name in names:
        t0 = time.time()
        res = build(load_variants(name), label_job(name))
        for part in ("clean", "mask", "hole", "state", "traces", "drawn", "bridged", "paper"):
            res[part].save(OUT / f"{name}_{part}.png")
        sheet(name, res).save(OUT / f"sheet_{name}.png")
        st = res["stats"]
        stats[name] = st
        fl = st["flat_labels"]
        flat = (f"подписей на заливке {fl['labels']} (с текстурой {fl['skipped']}), залито {fl['filled']} px, "
                f"оставлено рисунком {fl['kept']} px; " if fl else "")
        print(f"{name}: маска {st['mask_px']} px; подтверждено {st['confirmed_share']:.1%}, "
              f"одно наблюдение {st['single'] / max(1, st['mask_px']):.1%}, дыр {st['hole_share']:.1%}, "
              f"следов {st['traces']} px, отброшено совпадений букв {st['coincidences_rejected']} px; "
              f"зазор у порога бумаги {st['papered_kept']} | {st['papered_dropped']}; "
              f"{flat}{time.time() - t0:.0f} c")
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
