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

Где метод не помогает — надпись у всех языков стоит в одном месте: подписи комнат,
вывеска, логотип. Там дыр 38–40 % маски, и подложку нужно получать иначе (замер
14 сентября: план дела 3, табличка «Тортофеерии», афиша самурая).

    tools\\text_mask.py cut00_007 cut00_010    маска, подложка, лист — в work/graphics_masks/
    tools\\text_mask.py --all                  все картинки из work/graphics_ru/*/labels.json и art.json

Картинки — кадры игры, в репозиторий не идут (`.gitignore`).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from itertools import combinations
from pathlib import Path

import UnityPy
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from common import WORK, load_json
from layer_localized import index, original, variants
from picture_layer import FLIP, leaf, short

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
    for key in variants(gerkey, env.container):
        im = env.container[key].read().image.convert("RGBA")
        if man["flipped"]:
            im = im.transpose(FLIP)
        lf = leaf(key)
        out["base" if lf == name else lf.rsplit("_", 1)[-1]] = im
    return out


def build(images: dict[str, Image.Image]) -> dict:
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

    seen, coincidences = set(), 0
    for start in list(drawn):
        if start in seen or start not in drawn:
            continue
        comp, stack, strongest, touches, votes = [], [start], 0, False, {}
        seen.add(start)
        while stack:
            cx, cy = stack.pop()
            comp.append((cx, cy))
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
                elif not zone[nx, ny] and continues(bp[cx, cy], ep[nx, ny], pp[nx, ny]):
                    touches = True
        if (touches and len(comp) >= MIN_PIECE) or strongest >= groups_total or whole_shape(comp, votes):
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
            "languages": langs, "dropped_as_duplicates": dropped,
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
        names.update((load_json(spec) or {}).keys())
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
        res = build(load_variants(name))
        for part in ("clean", "mask", "hole", "state", "traces", "drawn", "bridged", "paper"):
            res[part].save(OUT / f"{name}_{part}.png")
        sheet(name, res).save(OUT / f"sheet_{name}.png")
        st = res["stats"]
        stats[name] = st
        print(f"{name}: маска {st['mask_px']} px; подтверждено {st['confirmed_share']:.1%}, "
              f"одно наблюдение {st['single'] / max(1, st['mask_px']):.1%}, дыр {st['hole_share']:.1%}, "
              f"следов {st['traces']} px, отброшено совпадений букв {st['coincidences_rejected']} px; "
              f"{time.time() - t0:.0f} c")
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
