"""Вывеска шоу «Пеки и пляши»: русские буквы логотипа на место английских.

Третий способ набора картинки, рядом с `prints.py` (печатное шрифтом) и `notes.py`
(рукописное шрифтом). Здесь надпись **нарисована**, шрифтом её не набрать, и берётся
она куском из рисунка нейросети — как в `paste_art.py`. Отдельный инструмент нужен
из-за трёх вещей, которых у тех нет (разбор 20 сентября 2026, `docs/decisions.md`):

  * **одна вывеска в двух кадрах.** Крупный план над тортом (`cut02_032`) и экран
    заставки (`cut02_037`) — одна и та же картинка, увеличенная в 1,4249 раза.
    Замер снят по краям четырёх слов ленты, общей для обоих кадров (невязка до
    1,1 px); проверен на том, что в подгонке не участвовало, — по краям букв
    логотипа совпало 85 %. Поэтому место русского слова не подбирается на глаз,
    а **считается**: английский золотой кант из заставки переводится формулой
    `x = k*x + dx`, и слово ставится в него;
  * **подложки нет.** Логотип у всех семи языков в одном месте, `text_mask.py`
    настоящего фона под буквами не покажет. Значит английское не «снимается
    по цвету букв» (так оставались серые тени под белым ореолом — брак августа),
    а **выкашивается полосой просвета** и заливается полем вывески;
  * **занавесы стоят перед вывеской, свет — прожектор снизу.** Просвет между
    занавесами — трапеция, красить за неё нельзя; у краёв вывеска уходит в тень,
    и русские буквы обязаны темнеть так же, иначе у занавеса они горят ярче
    оригинала. Тень замеряется по коричневому полю вывески в чистой строке.

Задание — `work/graphics_ru/<дело>/sign.json`, по ключу на картинку:

    "cut02_032": {
      "слово":   {"арт": "<путь от задания>", "рамка": [...], "фон_темнее": 105,
                  "кусок_от": 2500, "кант": [x0, y0, x1, y1]},
      "из":      {"кадр": "cut02_037", "масштаб": 1.4249, "сдвиг": [-399.8, -796.9],
                  "кант": [546, 408, 1315, 645]},
      "основа":  "готовое",
      "просвет": {"левый": [646, -0.578], "правый": [1298, 0.433], "отступ": 2},
      "полоса":  134,
      "поле":    {"верх": [36, 16, 8], "низ": [44, 21, 16], "до": 110},
      "тень":    148
    }

`слово.рамка` — где слово лежит в рисунке нейросети, `слово.кант` — рамка его
золотого канта там же; `из.кант` — рамка английского канта в кадре-источнике.

    tools\\sign.py                  набрать, записать PNG и лист
    tools\\sign.py --only cut02_032
    tools\\sign.py --check          ничего не писать, сверить с лежащим PNG

Пишет `<имя>.png` и `<имя>_ink.png` (маска наших букв — её читает `check_pictures.py`),
лист — `work/graphics_masks/checks/sign.png`.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from common import WORK

RU = WORK / "graphics_ru"
EN = WORK / "graphics_en"
SHEET = WORK / "graphics_masks" / "checks" / "sign.png"


def lum(c) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def background(im: Image.Image, dark: int) -> Image.Image:
    """Маска наклейки: всё, что не фон. Фон — тёмное, связное с краем кропа.

    Наклейка обведена белым ореолом, вокруг тёмная кондитерская лента, поэтому
    заливка от краёв останавливается ровно на ореоле и режет слово без порогов
    по цвету букв.
    """
    px, (W, H) = im.load(), im.size
    seen = [[False] * H for _ in range(W)]
    q: deque = deque()
    edge = [(x, y) for x in range(W) for y in (0, H - 1)]
    edge += [(x, y) for y in range(H) for x in (0, W - 1)]
    for x, y in edge:
        if lum(px[x, y]) < dark and not seen[x][y]:
            seen[x][y] = True
            q.append((x, y))
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H and not seen[nx][ny] and lum(px[nx, ny]) < dark:
                seen[nx][ny] = True
                q.append((nx, ny))
    m = Image.new("L", (W, H), 0)
    mp = m.load()
    for x in range(W):
        for y in range(H):
            if not seen[x][y]:
                mp[x, y] = 255
    return m


def parts(m: Image.Image, least: int) -> tuple[Image.Image, list]:
    """Куски маски от `least` пикселей. Слово распадается на «Пеки», «и», «пляши»,
    а нота, венчик, крем и оранжевый шарик остаются мелочью и отбрасываются."""
    px, (W, H) = m.load(), m.size
    seen = [[False] * H for _ in range(W)]
    kept, report = [], []
    for sx in range(W):
        for sy in range(H):
            if not px[sx, sy] or seen[sx][sy]:
                continue
            q, cur = deque([(sx, sy)]), []
            seen[sx][sy] = True
            while q:
                x, y = q.popleft()
                cur.append((x, y))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < W and 0 <= ny < H and px[nx, ny] and not seen[nx][ny]:
                        seen[nx][ny] = True
                        q.append((nx, ny))
            if len(cur) >= least:
                xs = [x for x, _ in cur]
                ys = [y for _, y in cur]
                report.append((len(cur), (min(xs), min(ys), max(xs), max(ys))))
                kept += cur
    out = Image.new("L", (W, H), 0)
    op = out.load()
    for x, y in kept:
        op[x, y] = 255
    return out, report


def curtain_of(im: Image.Image, cfg: dict) -> Image.Image:
    """Занавесы: они стоят **перед** вывеской, и за них красить нельзя.

    Считается не сам занавес, а **просвет**: заливка от точки внутри вывески по
    всему, что не бархат. Так и должно быть — у бархата есть блики с синевой,
    и заливка «по бархату от края кадра» оставляла в занавесе островки, сквозь
    которые русские буквы вылезали поверх занавеса (20 сентября 2026). Прямой
    линией край занавеса тоже не описать: прямая по двум строкам промахивалась
    на пару десятков пикселей, и справа уцелел кусок английского логотипа.
    """
    g_max, b_max = cfg["занавес"]["зелёный"], cfg["занавес"]["синий"]
    seed = tuple(cfg["занавес"]["точка"])
    px, (W, H) = im.load(), im.size
    seen = [[False] * H for _ in range(W)]

    def velvet(x, y):
        r, g, b = px[x, y]
        return g <= g_max and b <= b_max and r >= g

    q: deque = deque([seed])
    seen[seed[0]][seed[1]] = True
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H and not seen[nx][ny] and not velvet(nx, ny):
                seen[nx][ny] = True
                q.append((nx, ny))
    m = Image.new("L", (W, H), 255)
    mp = m.load()
    for x in range(W):
        for y in range(H):
            if seen[x][y]:
                mp[x, y] = 0
    # Мягкий край занавеса: пара пикселей смешанного цвета не бархат и не вывеска.
    # Отдаём их занавесу — красить по ним нечего, а заливка иначе подтекает.
    return m.filter(ImageFilter.MaxFilter(2 * cfg["занавес"].get("запас", 1) + 1))


def relight(cfg: dict, case: str, name: str, en: Image.Image, where: Image.Image):
    """Карта света: во сколько раз этот кадр темнее того же места в кадре-источнике.

    Свет на сцене — прожектор снизу по центру, и тень занавеса ложится наискось;
    по столбцам её не описать. Зато вывеска целиком видна в кадре-источнике,
    там она освещена ровно, и отношение яркостей даёт тень как она есть.
    Считается только там, где есть обе картинки (`where`), и сглаживается,
    чтобы буквы источника не отпечатались в карте.
    """
    src = cfg["из"]
    k, (dx, dy) = src["масштаб"], src["сдвиг"]
    ref = Image.open(EN / case / f"{src['кадр']}.png").convert("RGB")
    big = ref.resize((round(ref.width * k), round(ref.height * k)), Image.LANCZOS)
    here = Image.new("RGB", en.size, (0, 0, 0))
    here.paste(big, (round(dx), round(dy)))

    a, b = en.convert("L"), here.convert("L")
    m = where.point(lambda v: 1 if v else 0)
    blur = cfg["из"].get("сглаживание", 24)
    num = ImageChops.multiply(a, where).filter(ImageFilter.GaussianBlur(blur))
    den = ImageChops.multiply(b, where).filter(ImageFilter.GaussianBlur(blur))
    np_, dp_ = num.load(), den.load()
    W, H = en.size
    vals = []
    for y in range(0, H, 4):
        for x in range(0, W, 4):
            if dp_[x, y] > 6:
                vals.append(np_[x, y] / dp_[x, y])
    vals.sort()
    top = vals[int(len(vals) * 0.95)] if vals else 1.0

    def at(x: int, y: int) -> float:
        if dp_[x, y] <= 6:
            return 1.0
        return min(1.0, max(0.10, (np_[x, y] / dp_[x, y]) / top))

    return at


def footprint_of(cfg: dict, case: str, size) -> Image.Image:
    """След английской надписи в этом кадре — посчитанный, а не объявленный рамкой.

    Логотип целиком виден в кадре-источнике (там он не срезан рамкой и не в тени),
    и там он отделяется от фона **насыщенностью**: буквы, кант и пончик цветные,
    фон серый. Белый ореол насыщенности не имеет, поэтому след разрастается
    на его толщину. Потом след переводится сюда тем же пересчётом, каким ставится
    слово, — и накрывает ровно то, что надо снять.
    """
    src = cfg["из"]
    im = Image.open(EN / case / f"{src['кадр']}.png").convert("RGB")
    box = tuple(src["рамка"])
    crop = im.crop(box)
    px, (w, h) = crop.load(), crop.size
    sat = Image.new("L", (w, h), 0)
    sp = sat.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if max(r, g, b) - min(r, g, b) > src["насыщенность"]:
                sp[x, y] = 255
    sat, pieces = parts(sat, src.get("кусок_от", 500))
    here = Image.new("L", im.size, 0)
    here.paste(sat, (box[0], box[1]))
    grow = src.get("ореол", 12)
    here = here.filter(ImageFilter.MaxFilter(2 * grow + 1))

    k, (dx, dy) = src["масштаб"], src["сдвиг"]
    big = here.resize((round(im.width * k), round(im.height * k)), Image.NEAREST)
    out = Image.new("L", size, 0)
    out.paste(big, (round(dx), round(dy)))
    return out, len(pieces)


def board_of(im: Image.Image, curtain: Image.Image, cfg: dict):
    """Цвет доски вывески при полном свете — медиана по чистым строкам под надписью.

    Берутся только пиксели вида r > g > b: крем у края синее, лента ленты желтее,
    в доску не идут. Одного цвета хватает: доска ровная, а неровность освещения
    несёт карта света.
    """
    row = cfg["поле"]["строка"]
    px, cp = im.load(), curtain.load()
    vals = []
    for x in range(im.width):
        for y in range(row - 6, row + 9):
            if cp[x, y]:
                continue
            r, g, b = px[x, y]
            if r > g > b and 8 <= r - b <= 45:
                vals.append((r, g, b))
    if not vals:
        raise ValueError("поля вывески не нашлось — проверь «поле.строка» в задании")
    vals.sort(key=lum)
    return vals[int(len(vals) * cfg["поле"].get("доля", 0.75))]


def compose(name: str, cfg: dict, case: str):
    """Картинка с русским логотипом, маска наших букв, след надписи и отчёт."""
    spec_dir = RU / case
    report: list[str] = []

    word_cfg = cfg["слово"]
    art = Image.open((spec_dir / word_cfg["арт"]).resolve()).convert("RGB")
    crop = tuple(word_cfg["рамка"])
    art = art.crop(crop)
    mask, pieces = parts(background(art, word_cfg["фон_темнее"]), word_cfg["кусок_от"])
    report.append(f"{name}: слово вырезано из рисунка — кусков {len(pieces)}, "
                  + ", ".join(f"{n} пикс. {b}" for n, b in pieces))

    gx0, gy0, gx1, gy1 = word_cfg["кант"]
    gb = (gx0 - crop[0], gy0 - crop[1], gx1 - crop[0], gy1 - crop[1])

    src = cfg["из"]
    k, (dx, dy) = src["масштаб"], src["сдвиг"]
    ex0, ey0, ex1, ey1 = (k * src["кант"][0] + dx, k * src["кант"][1] + dy,
                          k * src["кант"][2] + dx, k * src["кант"][3] + dy)
    sx = (ex1 - ex0) / (gb[2] - gb[0])
    sy = (ey1 - ey0) / (gb[3] - gb[1])
    report.append(f"  английский кант «{src['кадр']}» -> ({ex0:.0f}, {ey0:.0f}, "
                  f"{ex1:.0f}, {ey1:.0f}); масштаб слова {sx:.3f} x {sy:.3f} "
                  f"-> сжатие {sx / sy:.3f} при равной высоте букв")

    word = art.copy()
    word.putalpha(mask)
    word = word.resize((max(1, round(art.width * sx)), max(1, round(art.height * sy))),
                       Image.LANCZOS)
    at = (round(ex0 - gb[0] * sx), round(ey0 - gb[1] * sy))

    en = Image.open(EN / case / f"{name}.png").convert("RGB")
    base = spec_dir / f"{name}.png"
    ready = cfg.get("основа") == "готовое" and base.exists()
    start = Image.open(base).convert("RGB") if ready else en
    report.append(f"  основа: {'готовая картинка с лентой' if ready else 'английский оригинал'}")

    curtain = curtain_of(en, cfg)
    trace, seen_parts = footprint_of(cfg, case, en.size)
    trace = ImageChops.subtract(trace, curtain)
    # Ниже надписи начинается кондитерская лента — чужая работа и чужая зона.
    # Без этой границы разрастание следа на ореол съедало её жёлтый верх.
    floor = cfg.get("не_ниже")
    if floor is not None:
        cut = Image.new("L", trace.size, 0)
        cut.paste(Image.new("L", (trace.width, floor), 255), (0, 0))
        trace = ImageChops.multiply(trace, cut)
    report.append(f"  след английской надписи: {trace.histogram()[255]} пикс. "
                  f"(из {seen_parts} кусков кадра «{src['кадр']}»), "
                  f"занавес {curtain.histogram()[255]} пикс.")

    # Свет считается до заливки: им же красится поле вывески под снятой надписью.
    shade = relight(cfg, case, name, en, trace)
    board = board_of(en, curtain, cfg)
    report.append(f"  поле вывески: {board} при полном свете")

    def field(x: int, y: int):
        q = shade(x, y)
        return tuple(min(255, round(v * q)) for v in board)

    def not_board(x: int, y: int, colour) -> bool:
        """Пиксель — не доска вывески. Порог **по свету**: в тени у занавеса все
        различия сжимаются, и постоянный порог там слепнет — именно так дуга
        пончика (разница 4 уровня при полном свете это 11) проходила мимо
        и проверки, и снятия."""
        f = field(x, y)
        t = max(2, round(cfg["поле"].get("допуск", 8) * shade(x, y)))
        return max(abs(colour[i] - f[i]) for i in range(3)) > t

    # След **дорастает по самой картинке**: посчитанный из кадра-источника, он
    # обрывается там, где у источника надпись обесцвечена (тёмный кант пончика
    # в насыщенность не попал), и от английского остаётся дуга. Рост идёт от следа
    # наружу по всему, что не доска, не занавес и не крем (у крема синий выше
    # зелёного, у доски наоборот), на ограниченное число шагов. Претензия
    # пользователя 20 сентября 2026: «а это что за остаток пончика от оригинала?»
    tol = cfg["поле"].get("допуск", 8)
    tp, xp = trace.load(), en.load()
    reach = cfg.get("дорастить", 40)
    if reach:
        grown = trace.copy()
        gp2, cp2 = grown.load(), curtain.load()
        wave = [(x, y) for y in range(en.height) for x in range(en.width) if tp[x, y]]
        limit = floor if floor is not None else en.height
        for _ in range(reach):
            nxt = []
            for x, y in wave:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < en.width and 0 <= ny < limit) or gp2[nx, ny] or cp2[nx, ny]:
                        continue
                    r, g, b = xp[nx, ny]
                    if b >= g:                       # крем: он перед вывеской, не трогаем
                        continue
                    if not not_board(nx, ny, (r, g, b)):
                        continue
                    gp2[nx, ny] = 255
                    nxt.append((nx, ny))
            if not nxt:
                break
            wave = nxt
        report.append(f"  след дорощен по картинке: {trace.histogram()[255]} -> "
                      f"{grown.histogram()[255]} пикс.")
        trace = grown
        tp = trace.load()
    eng = Image.new("L", en.size, 0)
    ep = eng.load()
    for y in range(en.height):
        for x in range(en.width):
            if tp[x, y] and not_board(x, y, xp[x, y]):
                ep[x, y] = 255
    report.append(f"  английских чернил в следе: {eng.histogram()[255]} пикс. "
                  f"из {trace.histogram()[255]}")

    out = start.copy()
    op = out.load()
    for y in range(en.height):
        for x in range(en.width):
            if tp[x, y]:
                op[x, y] = field(x, y)

    # Свет (снят выше) ложится и на русские буквы: прожектор снизу по центру,
    # тень занавеса наискось — у края буквы обязаны темнеть как английские.
    # Считать карту второй раз нельзя: `field` — замыкание над ней, и пересчёт
    # разводил заливку с проверкой (ловилось как 1979 «остатков»).
    patch = Image.new("RGBA", en.size, (0, 0, 0, 0))
    patch.paste(word, at, word)
    patch.putalpha(ImageChops.multiply(patch.getchannel("A"),
                                       ImageChops.invert(curtain)))
    pp = patch.load()
    for y in range(en.height):
        for x in range(en.width):
            r, g, b, a = pp[x, y]
            if a:
                q = shade(x, y)
                if q != 1.0:
                    pp[x, y] = (round(r * q), round(g * q), round(b * q), a)

    final = out.convert("RGBA")
    final.alpha_composite(patch)
    ink = patch.getchannel("A").point(lambda v: 255 if v > 128 else 0)
    report.append(f"  русских букв в кадре: {ink.histogram()[255]} пикс.")

    # Остаток английского — не «пиксель не изменился» (поле мы кладём поверх поля,
    # и такой пиксель честно остаётся прежним), а **чернила, которые так и стоят
    # чернилами**: были не полем у англичан и остались не полем у нас, и наша
    # буква их не накрыла.
    done = final.convert("RGB")
    # Мягкий край наших букв (альфа от 1) — тоже наша краска, а не остаток
    # английского: по жёсткой маске он попадал в находки контуром вокруг слова.
    soft = patch.getchannel("A").point(lambda v: 255 if v else 0)
    dp, ip = done.load(), soft.load()
    stayed = Image.new("L", en.size, 0)
    sp = stayed.load()
    for y in range(en.height):
        for x in range(en.width):
            if ep[x, y] and not ip[x, y] and not_board(x, y, dp[x, y]):
                sp[x, y] = 255
    return done, ink, eng, trace, start, stayed, curtain, not_board, report


def strays(ru: Image.Image, curtain: Image.Image, ink: Image.Image, not_board, cfg: dict,
           least: int = 40):
    """Чужая краска на вывеске — **независимо от следа, по которому снимали**.

    Это и есть главная проверка. Та, что смотрит внутрь следа, наследует его
    слепое пятно: 20 сентября 2026 след обрывался на тёмном канте пончика,
    и дуга английского осталась, а проверка честно показывала ноль.

    Здесь след не участвует вовсе. Над кондитерской лентой у вывески может быть
    ровно три вещи: доска, крем (он перед вывеской, у него синий выше зелёного)
    и **наши** буквы. Всё остальное — чужое: связный кусок от `least` пикселей
    попадает в находки, где бы он ни лежал.
    """
    floor = cfg.get("не_ниже") or ru.height
    mine = ink.filter(ImageFilter.MaxFilter(5))
    px, cp, mp = ru.load(), curtain.load(), mine.load()
    odd = Image.new("L", ru.size, 0)
    op = odd.load()
    for y in range(floor):
        for x in range(ru.width):
            if cp[x, y] or mp[x, y]:
                continue
            r, g, b = px[x, y]
            if b >= g:
                continue
            if not_board(x, y, (r, g, b)):
                op[x, y] = 255
    kept, found = parts(odd, least)
    return kept, found


def outside(base: Image.Image, ru: Image.Image, trace: Image.Image, ink: Image.Image,
            grow: int = 3, tol: int = 3):
    """Правка за надписью: изменённый против основы пиксель вне чернил и вне наших букв.

    Сверка идёт с основой (картинкой, какой её отдал предыдущий шаг), а не
    с английским оригиналом: перевод ленты на торте — работа `paste_art.py`,
    и в чужую зону этот инструмент не лезет.
    """
    diff = ImageChops.difference(base, ru).convert("L").point(lambda v: 255 if v > tol else 0)
    zone = ImageChops.lighter(trace, ink).filter(ImageFilter.MaxFilter(2 * grow + 1))
    return ImageChops.subtract(diff, zone)


def sheet(rows, path: Path) -> None:
    pad, gap = 26, 8
    w = max(im.width for _, pair in rows for im in pair)
    h = sum(pad + sum(im.height for im in pair) + gap for _, pair in rows)
    out = Image.new("RGB", (w, h), (20, 20, 20))
    d = ImageDraw.Draw(out)
    y = 0
    for title, pair in rows:
        d.text((6, y + 6), title, fill=(235, 235, 235))
        y += pad
        for im in pair:
            out.paste(im, (0, y))
            y += im.height
        y += gap
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", default="case3", help="папка дела (по умолчанию case3)")
    ap.add_argument("--only", help="одна картинка")
    ap.add_argument("--check", action="store_true", help="ничего не писать, сверить с лежащим")
    args = ap.parse_args()

    spec_path = RU / args.case / "sign.json"
    if not spec_path.exists():
        # В режиме сверки «нечего сверять» — провал, а не тишина: иначе
        # `check_all --full` зеленеет, ни разу не посмотрев на картинку.
        # Тот же класс, что упавший по пути `prints.py --check` 20 сентября 2026.
        print(f"нет задания {spec_path} — набирать нечего")
        return 2 if args.check else 0
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    problems, rows = [], []
    for name, cfg in spec.items():
        if not isinstance(cfg, dict) or (args.only and name != args.only):
            continue
        out, ink, eng, trace, base, stayed, curtain, not_board, report = compose(name, cfg, args.case)
        en = Image.open(EN / args.case / f"{name}.png").convert("RGB")

        # Две проверки, обе без подложки и без веры в рамку задания.
        beyond = outside(base, out, trace, ink)
        odd, blobs = strays(out, curtain, ink, not_board, cfg)
        left, over = stayed.histogram()[255], beyond.histogram()[255]
        report.append(f"  остатки английского {left} пикс., правка за следом {over} пикс., "
                      f"чужая краска на вывеске {sum(n for n, _ in blobs)} пикс. "
                      f"в {len(blobs)} кусках")
        if blobs:
            problems.append(f"{name}: на вывеске осталась чужая краска — "
                            + ", ".join(f"{n} пикс. {b}" for n, b in blobs[:4])
                            + f" (карта: {SHEET.with_name(name + '_чужое.png')})")
            odd.save(SHEET.parent / f"{name}_чужое.png")
        if left > cfg.get("допуск_остатков", 0):
            problems.append(f"{name}: английская надпись снята не целиком — "
                            f"{left} пикс. внутри следа остались как в оригинале "
                            f"(карта: {SHEET.with_name(name + '_остатки.png')})")
            stayed.save(SHEET.parent / f"{name}_остатки.png")
        if over > cfg.get("допуск_за_следом", 0):
            problems.append(f"{name}: правка вышла за след надписи — {over} пикс.")
            beyond.save(SHEET.parent / f"{name}_за_следом.png")

        for line in report:
            print(line, flush=True)
        png = RU / args.case / f"{name}.png"
        if args.check:
            if not png.exists():
                problems.append(f"{name}: нет {png} — прогнать tools/sign.py")
            elif ImageChops.difference(Image.open(png).convert("RGB"), out).getbbox():
                problems.append(f"{name}: PNG не совпадает с набором по заданию — tools/sign.py")
        else:
            out.save(png)
            ink.save(RU / args.case / f"{name}_ink.png")
            print(f"  записано: {png}")
        crop = tuple(cfg.get("лист", [500, 0, 1460, 200]))
        rows.append((f"{name}: оригинал | русский логотип | что менялось",
                     [en.crop(crop), out.crop(crop),
                      Image.merge("RGB", (stayed.crop(crop), ink.crop(crop),
                                          eng.crop(crop)))]))
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    if rows and not args.check:
        sheet(rows, SHEET)
        print(f"лист: {SHEET}")
    for p in problems:
        print(f"  БЕДА: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
