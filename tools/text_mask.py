"""Маска английской надписи и настоящая подложка под ней — по языковым вариантам картинки.

Зачем. 13 сентября 2026 пользователь забраковал способ, которым снималась английская
надпись (`relabel.py`, `paste_art.py`): маска по цвету букв в рамке не видит сглаживание,
путает надпись с рисунком того же цвета и затягивает дыру соседями — отсюда хвосты
букв, затёртые стены и светлые пятна. Требование: сперва доказать, что машина видит
**все** пиксели надписи, и только потом набирать.

Как устроено. У локализованной картинки в игре семь вариантов: английский, немецкий,
французский, корейский, два китайских и японский без хвоста. Рисунок у них общий
пиксель в пиксель (медиана разницы 0), расходятся только надписи. Поэтому:

  1. Подложка в пикселе — значение, которое показывают другие языки там, где у них
     самих нет надписи. Чужие чернила отсеиваются правилами:
       * бумага (не тёмное и не красное) — если её показывают две группы языков,
         или одна, но цвет совпадает с местной бумагой и по яркости, и по оттенку;
       * тёмная линия под красной английской буквой — рисунок, хватит одного языка;
       * значение цвета английских чернил — рисунок, только если соседство 9×9
         у двух групп совпадает: линия продолжается, а буквы разных языков
         разбегаются сразу; красное — только если его показывают все группы
         (стрелки, красный конь);
       * японский и оба китайских — одна группа: у них общие иероглифы одним шрифтом.
     Выбор — по числу подтверждающих групп; при равенстве тёмная линия под красной
     буквой, потом бумага, потом «рисунок цвета чернил».
  2. Маска — пиксели, где английский расходится с подложкой больше чем на 24,
     и кромка сглаживания в четырёх пикселях вокруг, если медиана других языков
     там — бумага.
  3. Дыра — пиксель английских чернил, подложку под которым не показал ни один язык.
     Короткий разрыв линии (до 10 пикселей) тянется вдоль строки или столбца, если
     концы похожи, не красные и темнее бумаги; остальное — размыванием только от
     надёжных соседей, иначе в дыру затекает кромка английской буквы.

Каждый пиксель маски помечен: подтверждено (две группы и больше), одно наблюдение,
дыра. Лист — оригинал, маска с дырами, подложка.

Где метод не помогает — надпись у всех языков стоит в одном месте: подписи комнат,
вывеска, логотип. Там дыр 38–40 % маски, и подложку нужно получать иначе (замер
14 сентября: план дела 3, табличка «Тортофеерии», афиша самурая). На планах
с рукописными пометками подтверждено 93 %, дыр 4–5 %.

Правила подбирались на плане 24 марта (`cut00_007`) за десять прогонов, разбор —
[`docs/STATE.md`](../docs/STATE.md), раздел о графике.

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
LOW = 10        # кромка сглаживания
AGREE = 0.7     # совпадение соседства 9×9 для рисунка цвета чернил
AGREE_DARK = 0.8
PAPER = 20      # «похоже на местную бумагу»
GAP = 10        # короткий разрыв линии
ZONE = 9        # окно зоны разбора вокруг английских чернил (4 пикселя в стороны)
N8 = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1))
HOLE, SINGLE, CONFIRMED = 1, 2, 3


def maxch(im: Image.Image) -> Image.Image:
    r, g, b = im.split()
    return ImageChops.lighter(ImageChops.lighter(r, g), b)


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


def paperlike(v, paper) -> bool:
    return near(v, paper, PAPER) and max(v) - min(v) <= max(paper) - min(paper) + 8


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
    others_all = [l for l in langs if l != "eng"]
    groups_here = {GROUP[l] for l in others_all}

    region = Image.new("L", E.size, 0)
    agree = {}
    for a, b in combinations(langs, 2):
        d = over(maxch(ImageChops.difference(V[a], V[b])), TOL)
        region = ImageChops.lighter(region, d)
        if GROUP[a] != GROUP[b] and "eng" not in (a, b):
            agree[frozenset((a, b))] = ImageChops.invert(d).filter(ImageFilter.BoxBlur(4)).load()
    region = region.filter(ImageFilter.MaxFilter(7))
    small = (max(1, W // 4), max(1, H // 4))
    paper = E.resize(small, Image.BILINEAR).filter(ImageFilter.MedianFilter(5)).resize((W, H), Image.BILINEAR)
    pp, ep, rp = paper.load(), E.load(), region.load()
    P = {l: V[l].load() for l in langs}

    inkE = Image.new("L", E.size, 0)
    redE = Image.new("L", E.size, 0)
    ip, rdp = inkE.load(), redE.load()
    for y in range(H):
        for x in range(W):
            if rp[x, y]:
                c = ink(ep[x, y])
                if c:
                    ip[x, y] = 255
                if c == "r":
                    rdp[x, y] = 255
    zone = inkE.filter(ImageFilter.MaxFilter(ZONE)).load()
    zone_r = redE.filter(ImageFilter.MaxFilter(5)).load()

    B = E.copy()
    bp = B.load()
    state = Image.new("L", E.size, 0)
    sp = state.load()
    for y in range(H):
        for x in range(W):
            if not rp[x, y]:
                continue
            ev = ep[x, y]
            ec = "r" if zone_r[x, y] else ink(ev)
            if ec is None and not zone[x, y]:
                continue
            clusters = []
            for l in langs:
                v = P[l][x, y]
                for c in clusters:
                    if near(c[0], v):
                        c[1].append(l)
                        break
                else:
                    clusters.append([v, [l]])
            best = best_key = None
            for rep, mem in clusters:
                oth = [l for l in mem if l != "eng"]
                og = {GROUP[l] for l in oth}
                c = ink(rep)
                if c is None:
                    ok = len(og) >= 2 or (len(og) == 1 and paperlike(rep, pp[x, y]))
                    tier = 1
                elif c == "d" and ec == "r":
                    ok = len(og) >= 1
                    tier = 2
                else:
                    pairs = [agree[frozenset((a, b))][x, y] for a, b in combinations(oth, 2)
                             if frozenset((a, b)) in agree]
                    mean = sum(pairs) / len(pairs) if pairs else 0
                    if c == "r":
                        ok = og == groups_here and mean >= AGREE * 255
                    else:
                        ok = len(og) >= 2 and mean >= AGREE_DARK * 255
                    tier = 0
                if not ok:
                    continue
                key = (len(og), tier, "eng" not in mem)
                if best_key is None or key > best_key:
                    best, best_key = (oth, og), key
            if best is None:
                if ink(ev) is not None or zone_r[x, y]:
                    sp[x, y] = HOLE
                continue
            oth, og = best
            vals = [P[l][x, y] for l in oth]
            bp[x, y] = tuple(sum(v[k] for v in vals) // len(vals) for k in range(3))
            sp[x, y] = CONFIRMED if len(og) >= 2 else SINGLE

    hole = state.point(lambda v: 255 if v == HOLE else 0)
    core = ImageChops.lighter(over(maxch(ImageChops.difference(E, B)), TOL), hole)
    T = core.copy()
    tp = T.load()
    ring = ImageChops.subtract(core.filter(ImageFilter.MaxFilter(ZONE)), core).load()
    for y in range(H):
        for x in range(W):
            if not ring[x, y]:
                continue
            vals = [P[l][x, y] for l in others_all]
            med = tuple(sorted(v[k] for v in vals)[len(vals) // 2] for k in range(3))
            if ink(med) is None and paperlike(med, pp[x, y]) and not near(ep[x, y], med, LOW):
                bp[x, y] = med
                tp[x, y] = 255

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
    filled = set(done)

    def trusted(xx, yy):
        if (xx, yy) in filled:
            return cp[xx, yy]
        if sp[xx, yy] >= SINGLE:
            return bp[xx, yy]
        if not zone[xx, yy]:
            return cp[xx, yy]
        return None

    for _ in range(80):
        if not todo:
            break
        step = []
        for (x, y) in todo:
            acc = []
            for dx, dy in N8:
                xx, yy = x + dx, y + dy
                if 0 <= xx < W and 0 <= yy < H and (xx, yy) not in todo:
                    v = trusted(xx, yy)
                    if v is not None:
                        acc.append(v)
            if len(acc) >= 3:
                step.append(((x, y), tuple(sum(a[k] for a in acc) // len(acc) for k in range(3))))
        if not step:
            break
        for p, v in step:
            cp[p] = v
            todo.discard(p)
            filled.add(p)
    for (x, y) in todo:
        cp[x, y] = pp[x, y]

    counts = {HOLE: 0, SINGLE: 0, CONFIRMED: 0}
    for y in range(H):
        for x in range(W):
            if tp[x, y] and sp[x, y] in counts:
                counts[sp[x, y]] += 1
    total = T.histogram()[255]
    clean = C.convert("RGBA")
    clean.putalpha(images["eng"].getchannel("A"))
    return {
        "eng": E, "clean": clean, "mask": T, "hole": hole, "state": state,
        "stats": {
            "mask_px": total,
            "confirmed": counts[CONFIRMED], "single": counts[SINGLE], "holes": hole.histogram()[255],
            "confirmed_share": round(counts[CONFIRMED] / total, 4) if total else 0,
            "hole_share": round(hole.histogram()[255] / total, 4) if total else 0,
            "languages": langs, "dropped_as_duplicates": dropped,
        },
    }


def sheet(name: str, res: dict) -> Image.Image:
    font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 18)
    E, C = res["eng"], res["clean"].convert("RGB")
    ov = E.copy()
    ov.paste((255, 0, 255), mask=res["mask"])
    ov.paste((0, 200, 255), mask=res["hole"])
    w = 960 if E.width >= 900 else E.width * 3
    s = w / E.width
    h = int(E.height * s)
    how = Image.LANCZOS if s < 1 else Image.NEAREST
    tiles = (("оригинал", E),
             ("пурпур — английская надпись; голубое — подложку не показал ни один язык", ov),
             ("подложка без надписи", C))
    out = Image.new("RGB", (w, 3 * (h + 24)), (30, 30, 30))
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
        for part in ("clean", "mask", "hole", "state"):
            res[part].save(OUT / f"{name}_{part}.png")
        sheet(name, res).save(OUT / f"sheet_{name}.png")
        st = res["stats"]
        stats[name] = st
        print(f"{name}: маска {st['mask_px']} px; подтверждено {st['confirmed_share']:.1%}, "
              f"одно наблюдение {st['single'] / max(1, st['mask_px']):.1%}, дыр {st['hole_share']:.1%}; "
              f"{time.time() - t0:.0f} c")
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
