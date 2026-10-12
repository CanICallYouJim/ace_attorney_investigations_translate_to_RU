"""Проверка русской картинки по требованиям пользователя к набору надписей.

Требования — пользователь, 13 сентября 2026, после листов дел 1 и 3:

  1. английская надпись не остаётся ни хвостом, ни чёрточкой, и русское слово
     не кладётся поверх английского («у самурая за новым словом видно старое»);
  2. буквы не наезжают на предметы рисунка — «исключено и точно не должно быть»;
  3. строк столько же, сколько в оригинале, если место есть;
  4. шрифт не уже и не тоньше оригинального — «перевод читается блекло».

Эталон — нетронутые варианты из `backup/` и подложка `text_mask.py` (правило №13),
а не живой бандл. Пиксели сравниваются по **классу** относительно местной бумаги
(`text_mask.kind`: бумага, красное, серое, цвет), а не по разнице цвета. Первая версия
сравнивала цветом и на старых картинках ошибалась так (разбор 14 сентября): одна
и та же линия у разных языков выходит из сжатия то 70, то 150 — и три четверти
«остатков английского» на плане 24 марта были стенами; светлое тело русской буквы
на светлой заливке комнаты шло в «испорченную подложку»; карточка логики, ужатая
из русского плана, вся была «правкой за надписью»; образец (б) получал «букву
на рисунке» за касание бледной линии между строками пометки.

  * **английские чернила** — пиксель маски `text_mask.py`, где английский не бумага и не того
    класса, что подложка. Дыра (подложку не показал никто) — чернила; но дыра того же класса,
    что подложка, чей кусок продолжается в нетронутый рисунок за маской, — линия рисунка;
  * **остатки английского** — английские чернила, которые в русской картинке остались
    как были и не накрыты русской буквой. Требование 1;
  * **испорченная подложка** — у надписи (6 пикселей вокруг маски) пиксель, изменённый
    против английского, который не русская буква и не совпадает с подложкой по классу:
    размазанная буква, белёсое пятно, затёртая линия. Дыры не считаются — там эталона нет.
    Требование 1;
  * **буква на рисунке** — ядро русской буквы на рисунке подложки. Цветной предмет (фигура,
    стрелка) и толстое тёмное (стена, дерево, фигурка — от 5 пикселей) — нельзя нигде, кроме
    места, где лежали сами английские чернила; толстое тёмное, **которое пересекала сама
    английская надпись**, считается как тонкая линия. Тонкая линия — нельзя вне поля английской
    надписи (чернила, замкнутые на 24 пикселя, и 6 запаса): в поле английская рука тоже
    линии пересекала. Требование 2;
  * **правка за надписью** — изменённый пиксель дальше 6 от маски и дальше 3 от русских букв;
  * **тонкий штрих** — в зоне надписи штрих русских букв тоньше 0,85 английского. Обе стороны
    меряются одинаково: всё, что отличается от подложки больше чем на 60. Требование 4.

Русские буквы проверка берёт из `<имя>_ink.png` рядом с картинкой — его пишет набор.
Без файла (картинки до 14 сентября) буквы оцениваются: ядро — изменённый пиксель не бумаги,
отличный от подложки больше чем на 60, плюс изменённое больше чем на 24 в двух пикселях
от ядра. Английский пиксель, на который русская буква легла тем же цветом, от остатка тогда
не отличить — лист об этом пишет. Строки (требование 3) по готовой картинке не посчитать:
их сверяет набор по своему заданию.

Особые случаи:

  * **уменьшенная копия** (`уменьшить` в задании — карточка логики): набирать там нечего;
    сверяется, что копия ровно равна английской с ужатой русской большой картинкой — тем же
    `picture_layer.shrink`, что у патчера. Требования проверяются на большой;
  * **подложки нет** — дыр больше 25 % маски: надпись у всех языков в одном месте (логотип
    самурая). Метод масок такую картинку не судит, и она **не проходит** с этой причиной,
    пока не будет своего способа (план 14 сентября, пункт 2).

    tools\\check_pictures.py                          все картинки work/graphics_ru/*/*.png
    tools\\check_pictures.py cut00_007 cut00_002
    tools\\check_pictures.py cut00_007 --dir <папка>  картинка и её _ink.png из другой папки
    tools\\check_pictures.py --selftest               проверка самой проверки на cut00_007

Лист — `work/graphics_masks/checks/<имя>.png` (с `--dir` — `<папка>/checks/`): оригинал,
русская картинка, находки цветом поверх русской серым (красная находка на красных чернилах
иначе не видна). Код возврата 1, если хоть одна картинка не прошла.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

import text_mask as tm
from common import WORK
from layer_localized import recipes
from picture_layer import shrink

RU = WORK / "graphics_ru"
REPORT = tm.OUT / "checks"
CORE = 60          # ядро буквы — отличие от подложки больше этого
THIN = 0.85        # штрих русских букв тоньше этой доли английского — брак
NEAR_TEXT = 6      # правка ближе этого к английской надписи — законное место правки
NEAR_INK = 3       # и к русской букве
THICK = 5          # тёмное толщиной от стольких пикселей — предмет (стена, дерево), а не линия
FIELD = 24         # поле надписи: английские чернила, замкнутые на столько пикселей,
BAND = 150         # плюс полоса строки — горизонтальное замыкание на столько (пара слов),
MARGIN = 6         # и запас вокруг
ZONE = 24          # надписи ближе этого — одна зона для сравнения штриха
NO_BASE = 0.25     # дыр больше этой доли маски — подложки нет, метод масок не судит
SAME = 2           # уменьшенная копия расходится с ужатой большой больше этого — брак
LIMITS = {"leftover": 20, "damage": 60, "on_drawing": 0, "outside": 0}   # пикселей
TITLES = {"leftover": "остатки английского", "damage": "испорченная подложка",
          "on_drawing": "буква на рисунке", "outside": "правка за надписью"}
COLOURS = {"leftover": (255, 0, 255), "damage": (255, 140, 0), "on_drawing": (230, 0, 0),
           "outside": (255, 220, 0), "holes": (0, 190, 255), "derived": (255, 0, 255)}
LEGEND = ("пурпур — остатки английского · оранжевое — испорченная подложка · красное — буква на рисунке · "
          "жёлтое — правка за надписью · рамки — сравнение штриха (красная — тоньше)")
# Картинки, которые сверять не с чем, — только с причиной.
# Штрих этой мерке здесь не по зубам. Надписи плана дела 3 — светлые буквы
# с тонким тёмным кантом на светлом полу: тело буквы отличается от подложки
# меньше чем на 60, в замер идёт один кант, и «штрих» выходит вдвое тоньше
# настоящего. Толщину канта там меряет `prints.py` **прямо** — кольцом «чернила
# минус тело» вокруг английских букв (1,5 px, взято 2), и по этому замеру набор
# не тоньше оригинала. Остальные находки для картинки судятся как обычно.
# Заведено 20 сентября 2026.
THIN_BLIND = {"cut02_003"}

UNCHECKABLE = {
    "logic02_009_s": "взята японская картинка целиком: английской надписи и немецкого варианта нет",
    # Вывеска шоу: логотип нарисован и у всех семи языков лежит на одном месте,
    # настоящей подложки под буквами не покажет никто — метод масок тут не судья.
    # Её судит `tools/sign.py --check` своим способом: английское снимается
    # по следу, посчитанному из кадра-источника, и обе находки обязаны быть нулём
    # («остатки английского», «правка за следом»). Заведено 20 сентября 2026.
    "cut02_032": "вывеска шоу: подложки нет у всех языков — проверяет tools/sign.py --check",
    # У этих свой способ вставки и своя проверка: плашки живут в спрайтах атласа,
    # заставка — кусками с рамками. Метод масок кадра их не разбирает вовсе
    # и падал на них `KeyError: bundle`, то есть «не проверено» выдавалось
    # за находку. Заведено 20 сентября 2026.
    **{f"Situation_{i}": "плашка ситуации: спрайт в атласе — проверяет tools/plates.py --check"
       for i in range(7)},
    "splash_ger2": "атлас заставки «Возражение»: куски с рамками — проверяет tools/splash.py --check",
    "titles_StEd_ger": "атлас заставок «Начало / Расследование завершено»: куски с рамками и правки "
                       "префабов — проверяет tools/titles.py --check",
    "titles_chess_ger": "атлас заставок ментальных шахмат: куски с рамками и правки префабов — "
                        "проверяет tools/titles_chess.py --check",
}


def differs(a: Image.Image, b: Image.Image, t: int) -> Image.Image:
    return tm.over(tm.maxch(ImageChops.difference(a, b)), t)


def grow(mask: Image.Image, r: int) -> Image.Image:
    """Расширить маску на r пикселей; большое окно — шагами 3×3, ранговый фильтр 49×49 идёт долго."""
    if r <= 2:
        return mask.filter(ImageFilter.MaxFilter(2 * r + 1)) if r else mask
    for _ in range(r):
        mask = mask.filter(ImageFilter.MaxFilter(3))
    return mask


def erode(mask: Image.Image, r: int) -> Image.Image:
    for _ in range(r):
        mask = mask.filter(ImageFilter.MinFilter(3))
    return mask


def count(mask: Image.Image) -> int:
    return mask.histogram()[255]


def stretch(mask: Image.Image, r: int) -> Image.Image:
    """Расширить маску по горизонтали на r пикселей в обе стороны; шаг удваивается."""
    out = mask
    done, step = 0, 1
    while done < r:
        step = min(step, r - done)
        for dx in (step, -step):
            shifted = Image.new("L", mask.size, 0)
            shifted.paste(out, (dx, 0))
            out = ImageChops.lighter(out, shifted)
        done += step
        step *= 2
    return out


def corridor(mask: Image.Image, r: int) -> Image.Image:
    """Полоса строки: горизонтальное замыкание маски.

    Силуэт букв полосой не считается: у английской строки хвост есть у `g` и `y`,
    у русской — у «р» и «у», и приходятся они на разные места. Полоса же у строки
    одна: хвост `g` в «Knight» держит её низ под всей фразой, и наш хвост «р»,
    упавший на ту же линию плана правее, — то же самое место, а не рисунок."""
    return ImageChops.invert(stretch(ImageChops.invert(stretch(mask, r)), r))


def select(cand: Image.Image, test) -> Image.Image:
    """Пиксели маски-кандидата, для которых `test(x, y)` истинно."""
    out = Image.new("L", cand.size, 0)
    box = cand.getbbox()
    if not box:
        return out
    cp, op = cand.load(), out.load()
    for y in range(box[1], box[3]):
        for x in range(box[0], box[2]):
            if cp[x, y] and test(x, y):
                op[x, y] = 255
    return out


def neighbours(p: tuple[int, int], W: int, H: int):
    for dx, dy in tm.N8:
        q = (p[0] + dx, p[1] + dy)
        if 0 <= q[0] < W and 0 <= q[1] < H:
            yield q


def components(mask: Image.Image) -> list[list[tuple[int, int]]]:
    """Связные куски маски списками пикселей, крупные первыми."""
    box = mask.getbbox()
    if not box:
        return []
    mp = mask.load()
    W, H = mask.size
    seen, out = set(), []
    for y in range(box[1], box[3]):
        for x in range(box[0], box[2]):
            if not mp[x, y] or (x, y) in seen:
                continue
            stack, comp = [(x, y)], []
            seen.add((x, y))
            while stack:
                p = stack.pop()
                comp.append(p)
                for q in neighbours(p, W, H):
                    if mp[q] and q not in seen:
                        seen.add(q)
                        stack.append(q)
            out.append(comp)
    return sorted(out, key=len, reverse=True)


def pieces(mask: Image.Image) -> list[tuple[int, tuple[int, int, int, int]]]:
    """Связные куски маски: (пикселей, рамка), крупные первыми."""
    out = []
    for comp in components(mask):
        xs = [p[0] for p in comp]
        ys = [p[1] for p in comp]
        out.append((len(comp), (min(xs), min(ys), max(xs) + 1, max(ys) + 1)))
    return out


def stroke(mask: Image.Image) -> float:
    """Толщина штриха: удвоенная площадь на длину границы."""
    box = mask.getbbox()
    if not box:
        return 0.0
    mp = mask.load()
    W, H = mask.size
    area = border = 0
    for y in range(box[1], box[3]):
        for x in range(box[0], box[2]):
            if mp[x, y]:
                area += 1
                if (x in (0, W - 1) or y in (0, H - 1)
                        or not (mp[x + 1, y] and mp[x - 1, y] and mp[x, y + 1] and mp[x, y - 1])):
                    border += 1
    return 2 * area / border if border else 0.0


def masks_for(name: str) -> dict[str, Image.Image]:
    """Подложка и маска `text_mask.py`; если их нет — построить."""
    parts = ("clean", "mask", "hole", "paper")
    paths = {p: tm.OUT / f"{name}_{p}.png" for p in parts}
    if not all(p.exists() for p in paths.values()):
        tm.OUT.mkdir(parents=True, exist_ok=True)
        res = tm.build(tm.load_variants(name), tm.label_job(name))
        for part in ("clean", "mask", "hole", "state", "traces", "drawn", "bridged", "paper"):
            res[part].save(tm.OUT / f"{name}_{part}.png")
    return {p: Image.open(path) for p, path in paths.items()}


def english_ink(E: Image.Image, C: Image.Image, T: Image.Image, hole: Image.Image,
                paper: Image.Image) -> Image.Image:
    """Английские чернила: пиксель маски, где английский не бумага и не того класса, что подложка.

    Дыра того же класса, что подложка, — линия рисунка, если её кусок продолжается
    в нетронутый рисунок за маской: у «to plane» стена у английского 73, у языков
    с надписью рядом сжатие высветлило её до 151, и дыра её закрыла — это не буква.
    """
    W, H = E.size
    ep, cp, pp, hp, tp = E.load(), C.load(), paper.load(), hole.load(), T.load()
    cand = ImageChops.lighter(ImageChops.multiply(T, differs(E, C, tm.TOL)), hole)
    ink = Image.new("L", E.size, 0)
    same = Image.new("L", E.size, 0)
    kp, sp, cdp = ink.load(), same.load(), cand.load()
    box = cand.getbbox()
    if not box:
        return ink
    for y in range(box[1], box[3]):
        for x in range(box[0], box[2]):
            if not cdp[x, y]:
                continue
            pv = pp[x, y]
            ke = tm.kind(ep[x, y], pv)
            if ke == "p":
                continue
            if ke != tm.kind(cp[x, y], pv):
                kp[x, y] = 255
            elif hp[x, y]:
                sp[x, y] = 255
    for comp in components(same):
        if not any(not tp[q] and tm.continues(ep[p], ep[q], pp[q]) for p in comp for q in neighbours(p, W, H)):
            for p in comp:
                kp[p] = 255
    return ink


def untouchable(C: Image.Image, paper: Image.Image, eng: Image.Image, box=None) -> Image.Image:
    """Где русской букве лежать нельзя — требование 2, «буква на рисунке».

    Цветной предмет (фигура, стрелка) — нельзя нигде, кроме места самих английских чернил.
    Толстое тёмное (стена, дерево, фигурка — от `THICK` пикселей) — тоже, **если его
    не пересекала сама английская надпись**: предмет, через который английская рука
    писала, разрешено пересекать и нам, но только в поле её надписи. Тонкая линия —
    нельзя вне поля надписи: в поле английская рука линии тоже пересекала.

    Уточнение про пересечённый предмет — 16 сентября 2026: «Knight to immediately escort
    president» лежит над линией плана и пересекает её хвостом `g`; наш хвост «р» пересекал
    ту же линию правее, и проверка звала это буквой на рисунке. Места, где русская строка
    не задевала бы её вовсе, у этой пометки нет: сверху изгородь, снизу линия.

    Одна функция на проверку и на набор (`notes.py` ищет положение строки по этой же
    маске): иначе набор проходит свою мерку и валится на чужой.
    """
    cp, pp = C.load(), paper.load()
    foot_img = grow(eng, 2)
    foot = foot_img.load()
    dark = tm.over(ImageChops.subtract(paper.convert("L"), C.convert("L")), tm.LINE)
    thick_img = grow(erode(dark, THICK // 2), THICK // 2)
    field = grow(ImageChops.lighter(erode(grow(eng, FIELD), FIELD), corridor(eng, BAND)),
                 MARGIN).load()
    W, H = C.size
    x0, y0, x1, y1 = box or (0, 0, W, H)
    here = Image.new("L", C.size, 0)
    ImageDraw.Draw(here).rectangle((x0 - FIELD, y0 - FIELD, x1 + FIELD, y1 + FIELD), fill=255)
    crossed = Image.new("L", C.size, 0)
    xp = crossed.load()
    for comp in components(ImageChops.multiply(thick_img, here)):
        if any(foot[p] for p in comp):
            for p in comp:
                xp[p] = 255
    thick = thick_img.load()
    out = Image.new("L", C.size, 0)
    op = out.load()
    for y in range(max(0, y0), min(H, y1)):
        for x in range(max(0, x0), min(W, x1)):
            cv, pv = cp[x, y], pp[x, y]
            k = tm.kind(cv, pv)
            if k in ("r", "c"):
                hit = not foot[x, y]
            elif k != "n" or tm.lum(cv) >= tm.lum(pv) - tm.LINE:
                hit = False
            elif thick[x, y] and not xp[x, y]:
                hit = not foot[x, y]
            else:
                hit = not field[x, y]
            if hit:
                op[x, y] = 255
    return out


def derivation(name: str, ru_path: Path) -> dict | None:
    for job in recipes(ru_path.parent).get(name, []):
        if "уменьшить" in job:
            return job["уменьшить"]
    return None


def check_derived(name: str, ru_path: Path, u: dict, eng: Image.Image, R: Image.Image,
                  report: Path) -> dict:
    """Уменьшенная копия: ровно английская с ужатой русской большой картинкой в рамке ориентира."""
    big = ru_path.with_name(f"{u['из']}.png")
    if not big.exists():
        raise ValueError(f"нет большой картинки {big.name}, из которой уменьшается эта")
    there, here = u["якорь_там"], u["якорь_тут"]
    expected = eng.convert("RGBA").copy()
    expected.paste(shrink(Image.open(big).convert("RGBA"), there, (here[2] - here[0], here[3] - here[1])),
                   (here[0], here[1]))
    off = differs(R, expected.convert("RGB"), SAME)
    report.mkdir(parents=True, exist_ok=True)
    sheet(name, eng.convert("RGB"), R, {"derived": off},
          f"пурпур — расходится с уменьшенной «{u['из']}» больше чем на {SAME} уровня").save(report / f"{name}.png")
    return {"derived": u["из"], "off": count(off), "failed": ["derived"] if count(off) else []}


def check(name: str, ru_path: Path, report: Path = REPORT) -> dict:
    V = tm.load_variants(name)
    E = V["eng"].convert("RGB")
    R = Image.open(ru_path).convert("RGB")
    if R.size != E.size:
        raise ValueError(f"размер {R.size} против оригинала {E.size}")
    u = derivation(name, ru_path)
    if u:
        return check_derived(name, ru_path, u, V["eng"], R, report)

    m = masks_for(name)
    C = m["clean"].convert("RGB")
    T = m["mask"].convert("L")
    hole = m["hole"].convert("L")
    paper = m["paper"].convert("RGB")
    W, H = E.size
    report.mkdir(parents=True, exist_ok=True)

    holes = count(hole) / max(1, count(T))
    if holes > NO_BASE:
        sheet(name, E, R, {"holes": hole},
              f"голубое — дыры: подложку под английской надписью не показал ни один язык ({holes:.0%} маски)"
              ).save(report / f"{name}.png")
        return {"no_base": holes, "failed": ["no_base"]}

    eng = english_ink(E, C, T, hole, paper)
    moved = differs(R, E, tm.LOW)
    # Остаток английского — только **видимый** и только там, где есть эталон (20 сентября 2026):
    # пиксель, уже равный подложке, сняли — снимать было нечего; дыру проверка не судит, как
    # не судит её в «испорченной подложке» (в дыре не отличить чернила от линии рисунка, и на
    # планах дела 1 дыры — ровно те места, где чернила шли по тёмной линии); а чернила, которые
    # от подложки отличаются меньше порога ядра, не видны и на глаз: на текстуре изгороди
    # оценка подложки расходится с английской на 25–44 уровня — это шум оценки, а не надпись.
    stayed = ImageChops.subtract(
        ImageChops.multiply(ImageChops.subtract(eng, moved), differs(E, C, CORE)),
        ImageChops.lighter(ImageChops.invert(differs(R, C, tm.TOL)), grow(hole, 1)))
    rp, cp, pp = R.load(), C.load(), paper.load()
    ink_file = ru_path.with_name(f"{ru_path.stem}_ink.png")
    estimated = not ink_file.exists()
    if estimated:
        core0 = select(ImageChops.multiply(differs(R, C, CORE), moved),
                       lambda x, y: tm.kind(rp[x, y], pp[x, y]) != "p")
        ink = ImageChops.multiply(ImageChops.multiply(differs(R, C, tm.TOL), moved), grow(core0, 2))
    else:
        ink = Image.open(ink_file).convert("L").point(lambda v: 255 if v > 127 else 0)
    under_ink = grow(ink, 2)
    leftover = ImageChops.subtract(stayed, under_ink)

    zone = grow(T, NEAR_TEXT)
    cand = ImageChops.multiply(ImageChops.multiply(zone, moved), differs(R, C, tm.TOL))
    cand = ImageChops.subtract(ImageChops.subtract(cand, under_ink), grow(hole, 1))

    def spoiled(x: int, y: int) -> bool:
        rv, cv, pv = rp[x, y], cp[x, y], pp[x, y]
        kc = tm.kind(cv, pv)
        return not (tm.kind(rv, pv) == kc and (kc == "p" or tm.near(rv, cv, CORE)))

    damage = select(cand, spoiled)

    core = ImageChops.multiply(ink, differs(R, C, CORE))
    box = core.getbbox()
    on_drawing = ImageChops.multiply(core, untouchable(C, paper, eng, box)) if box else core
    outside = ImageChops.subtract(differs(R, E, tm.TOL), ImageChops.lighter(zone, grow(ink, NEAR_INK)))

    # штрих: обе стороны — всё, что отличается от подложки больше чем на CORE. Русская буква,
    # легшая на английскую тем же цветом, для замера — буква: вычитать совпавшее можно только
    # у оценённых букв, иначе маска дырявится и штрих выходит тоньше (образец (б): 3,7 вместо 4,8)
    text_core = ImageChops.multiply(eng, differs(E, C, CORE))
    ru_core = ImageChops.multiply(grow(ink, 1), differs(R, C, CORE))
    if estimated:
        ru_core = ImageChops.subtract(ru_core, stayed)
    both = ImageChops.lighter(text_core, ru_core)
    small = both.resize((max(1, W // 4), max(1, H // 4)), Image.BOX).point(lambda v: 255 if v else 0)
    strokes = []
    for _, (x0, y0, x1, y1) in pieces(grow(small, ZONE // 8)):
        bb = (x0 * 4, y0 * 4, min(W, x1 * 4), min(H, y1 * 4))
        en, ru = text_core.crop(bb), ru_core.crop(bb)
        if count(en) < 150 or count(ru) < 150:
            continue
        strokes.append((bb, round(stroke(en), 1), round(stroke(ru), 1)))

    marks = {"leftover": leftover, "damage": damage, "on_drawing": on_drawing, "outside": outside}
    numbers = {k: count(v) for k, v in marks.items()}
    failed = [k for k, lim in LIMITS.items() if numbers[k] > lim]
    thin = [s for s in strokes if s[2] < THIN * s[1]]
    if thin and name not in THIN_BLIND:
        failed.append("thin")
    note = " · русские буквы оценены, файла _ink.png нет" if estimated else ""
    sheet(name, E, R, marks, LEGEND, strokes, note).save(report / f"{name}.png")
    return {"numbers": numbers, "strokes": strokes, "thin": thin, "failed": failed, "estimated": estimated,
            "marks": marks}


def sheet(name: str, E: Image.Image, R: Image.Image, marks: dict, legend: str,
          strokes: list = (), note: str = "") -> Image.Image:
    font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 18)
    W, H = E.size
    grey = Image.blend(ImageOps.grayscale(R).convert("RGB"), Image.new("RGB", R.size, (255, 255, 255)), 0.3)
    marked = grey.copy()
    for key, mask in marks.items():
        marked.paste(COLOURS[key], mask=grow(mask, 1))
    dr = ImageDraw.Draw(marked)
    for bb, en, ru in strokes:
        dr.rectangle(bb, outline=(0, 200, 255) if ru >= THIN * en else (255, 0, 0), width=3)
    w = 960 if W >= 900 else W * 3
    s = w / W
    h = int(H * s)
    how = Image.LANCZOS if s < 1 else Image.NEAREST

    union = Image.new("L", E.size, 0)
    for mask in marks.values():
        union = ImageChops.lighter(union, mask)
    zooms = []
    cell = (w - 16) // 3
    for _, bb in pieces(grow(union, 8))[:4]:
        box = (max(0, bb[0] - 16), max(0, bb[1] - 16), min(W, bb[2] + 16), min(H, bb[3] + 16))
        crops = [E.crop(box), R.crop(box), marked.crop(box)]
        k = min(2.0, cell / max(1, crops[0].width), 260 / max(1, crops[0].height))
        size = (max(1, int(crops[0].width * k)), max(1, int(crops[0].height * k)))
        zooms.append([c.resize(size, Image.NEAREST) for c in crops])

    zoom_h = sum(z[0].height + 8 for z in zooms)
    out = Image.new("RGB", (w, 3 * (h + 26) + 26 + zoom_h + 10), (30, 30, 30))
    d = ImageDraw.Draw(out)
    tiles = ((f"{name}: оригинал", E), (f"{name}: русская картинка", R),
             (f"{name}: находки поверх русской серым{note}", marked))
    for i, (title, im) in enumerate(tiles):
        y = i * (h + 26)
        d.text((6, y + 3), title, fill=(255, 255, 0), font=font)
        out.paste(im.resize((w, h), how), (0, y + 26))
    y = 3 * (h + 26)
    d.text((6, y + 3), legend + " · крупно: оригинал | русская | находки", fill=(255, 255, 0),
           font=ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 13))
    y += 26
    for crops in zooms:
        x = 0
        for c in crops:
            out.paste(c, (x, y))
            x += c.width + 8
        y += crops[0].height + 8
    return out


def targets(names: list[str], folder: Path | None) -> dict[str, Path]:
    if folder:
        if not names:
            sys.exit("с --dir назовите картинки")
        return {n: folder / f"{n}.png" for n in names}
    found = {png.stem: png for png in sorted(RU.glob("*/*.png")) if not png.stem.endswith("_ink")}
    if not names:
        return found
    missing = [n for n in names if n not in found]
    if missing:
        sys.exit(f"нет русских картинок: {', '.join(missing)}")
    return {n: found[n] for n in names}


def describe(name: str, res: dict) -> str:
    if "no_base" in res:
        return (f"{name:<16} ✗ подложки нет: дыр {res['no_base']:.0%} маски — надпись у всех языков в одном месте, "
                f"метод масок её не судит (план 14 сентября, пункт 2)")
    if "derived" in res:
        mark = "✗" if res["failed"] else "✓"
        return (f"{name:<16} {mark} уменьшенная копия «{res['derived']}»: расходится {res['off']} пикс.; "
                f"требования — по «{res['derived']}»")
    parts = [f"{TITLES[k]} {v}" for k, v in res["numbers"].items()]
    for bb, en, ru in res["strokes"]:
        flag = "" if ru >= THIN * en else " ✗"
        parts.append(f"штрих {ru}/{en}{flag} в {bb}")
    if res["estimated"]:
        parts.append("буквы оценены без _ink.png")
    return f"{name:<16} {'✗' if res['failed'] else '✓'} " + " · ".join(parts)


def selftest() -> int:
    """Проверка самой проверки на cut00_007: чистая подложка проходит, каждая порча ловится своим счётом."""
    name = "cut00_007"
    E = tm.load_variants(name)["eng"].convert("RGB")
    m = masks_for(name)
    C = m["clean"].convert("RGB")
    T = m["mask"].convert("L")
    paper = m["paper"].convert("RGB")
    cp, pp = C.load(), paper.load()
    far = ImageChops.invert(grow(T, 20))
    objects = components(select(far, lambda x, y: tm.kind(cp[x, y], pp[x, y]) in ("r", "c")))
    if not objects:
        print("✗ на подложке не нашлось цветного предмета вдали от надписи — не на чем проверять")
        return 1
    thing = objects[0]
    cx = sum(p[0] for p in thing) // len(thing)
    cy = sum(p[1] for p in thing) // len(thing)
    x, y = min(thing, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
    xs = [p[0] for p in thing]
    ys = [p[1] for p in thing]

    letter = C.copy()   # чёрная «буква» на цветном предмете: отличие от него заведомо больше порога ядра
    ImageDraw.Draw(letter).rectangle((x - 8, y - 8, x + 8, y + 8), fill=(20, 20, 20))
    letter_ink = Image.new("L", C.size, 0)
    ImageDraw.Draw(letter_ink).rectangle((x - 8, y - 8, x + 8, y + 8), fill=255)
    erased = C.copy()
    ImageDraw.Draw(erased).rectangle((min(xs), min(ys), max(xs), max(ys)), fill=pp[x, y])

    cases = (  # (что, картинка, маска букв или None, что обязано упасть)
        ("подложка без надписи", C, Image.new("L", C.size, 0), set()),
        ("английский как есть", E, None, {"leftover"}),
        (f"русская буква на предмете у ({x}, {y})", letter, letter_ink, {"on_drawing"}),
        ("стёрт предмет вдали от надписи", erased, Image.new("L", C.size, 0), {"outside"}),
    )
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, (title, picture, ink, expect) in enumerate(cases):
            folder = Path(tmp) / str(i)
            folder.mkdir()
            picture.save(folder / f"{name}.png")
            if ink is not None:
                ink.save(folder / f"{name}_ink.png")
            res = check(name, folder / f"{name}.png", report=folder)
            got = set(res["failed"])
            ok = got == expect if not expect else expect <= got
            bad += not ok
            print(f"{'✓' if ok else '✗'} {title}: упало {sorted(got) or 'ничего'}, ждали {sorted(expect) or 'ничего'} "
                  f"— {res['numbers']}")
    print("\nOK — проверка ловит, что должна, и пропускает чистое." if not bad else f"\nсамопроверка: не сошлось {bad}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="имена картинок без расширения")
    ap.add_argument("--dir", type=Path, help="папка с картинками и их _ink.png вместо work/graphics_ru")
    ap.add_argument("--selftest", action="store_true", help="проверить саму проверку на cut00_007")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    report = args.dir / "checks" if args.dir else REPORT     # чужая папка не затирает листы игры
    bad = 0
    for name, path in targets(args.names, args.dir).items():
        if name in UNCHECKABLE:
            print(f"{name:<16} исключение: {UNCHECKABLE[name]}")
            continue
        try:
            res = check(name, path, report)
        except (Exception, SystemExit) as exc:        # load_variants выходит через sys.exit
            print(f"{name:<16} ✗ не проверено: {exc}")
            bad += 1
            continue
        print(describe(name, res))
        bad += bool(res["failed"])
    print(f"\n{'OK — все картинки прошли.' if not bad else f'не прошли: {bad}'}  Листы — {report}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
