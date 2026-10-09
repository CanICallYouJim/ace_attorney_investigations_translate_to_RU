"""Газеты дела 1: снять английские надписи с бумаги и набрать русские по замеру английских.

Курс 23 сентября 2026 (скилл /graphics): качество судит пользователь по листу,
инструмент ничего не доказывает. Способ найден на `cut00_003`:

* **снятие.** Бумага газеты гладкая, тень идёт по столбцам (лист изогнут). Буквы —
  всё, что темнее бумаги своего столбца (85-й перцентиль по рамке) больше чем
  на `t`; их место заливается прямой по высоте, подогнанной к чистой бумаге того
  же столбца. Подложка `text_mask.py` здесь не годится: у немцев и французов
  название и заголовок почти на том же месте;
* **угол со свечением** («Evening Edition»): у зелёных букв всех латинских языков
  белое свечение, чистой бумаги под ним нет ни у кого. В углу берётся самый
  светлый пиксель из англ/нем/фр, остатки зелёного затягиваются по строке,
  русская строка получает такое же мягкое свечение (`glow`);
* **набор.** Кегль и сжатие — тот же английский текст нашим шрифтом в рамку
  английских чернил; базовая линия — английская. Русская строка длиннее —
  сжимается по ширине до `maxw`. `bold` — обводка при наборе в 4-кратном
  размере (края зелёных букв были светлее английских, 23 сентября).

    .venv\\Scripts\\python.exe tools\\newspaper.py work\\graphics_ru\\case1\\newspaper.json
    .venv\\Scripts\\python.exe tools\\newspaper.py work\\graphics_ru\\case1\\newspaper.json --only cut00_005

Пишет `<имя>.png` рядом с заданием; лист — `tools/sheet.py <имя>`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy.ndimage import binary_dilation, uniform_filter1d

sys.path.insert(0, str(Path(__file__).parent))
from text_mask import load_variants  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EN = ROOT / "work" / "graphics_en"
FD = "C:/Windows/Fonts/"


def column_clean(E, g, box, t=22, flat=False):
    """Снять тёмные буквы: у каждого столбца свой цвет бумаги, заливка — прямой по высоте.

    `flat` — заливка столбца одним цветом (медиана чистой бумаги): этикетка флакона
    `itm02_026` — цилиндр, цвет зависит только от столбца, а чистой бумаги над буквами
    два-три ряда, и прямая по ним уводит цвет (27 сентября 2026)."""
    x0, y0, x1, y1 = box
    sub = g[y0:y1, x0:x1]
    S = E[y0:y1, x0:x1].astype(float)
    bg = uniform_filter1d(np.percentile(sub, 85, axis=0), 5)
    ink = binary_dilation((bg[None, :] - sub) > t, iterations=2)
    paper = ~binary_dilation(ink, iterations=2)
    ys = np.arange(y1 - y0)
    fill = np.full(S.shape, np.nan)
    for x in range(x1 - x0):
        ok = paper[:, x]
        if flat and ok.sum() >= 2:
            fill[:, x, :] = np.median(S[ok, x], axis=0)
            continue
        if ok.sum() < 6:
            continue          # чистой бумаги в столбце нет — цвет возьмёт у соседей ниже
        for c in range(3):
            k, b = np.polyfit(ys[ok], S[ok, x, c], 1)
            fill[:, x, c] = k * ys + b
    good = ~np.isnan(fill[0, :, 0])
    if good.any() and not good.all():
        xs = np.arange(x1 - x0)
        for c in range(3):
            for y in range(y1 - y0):
                fill[y, ~good, c] = np.interp(xs[~good], xs[good], fill[y, good, c])
    S[ink] = fill[ink]
    E[y0:y1, x0:x1] = np.clip(S, 0, 255).astype(np.uint8)


def glow_corner(E, name, box):
    """Угол со свечением: самый светлый из латинских языков, остатки зелёного — по строке."""
    x0, y0, x1, y1 = box
    V = load_variants(name)
    cube = np.stack([np.asarray(V[k].convert("RGB"))[y0:y1, x0:x1] for k in ("eng", "ger", "fre")]).astype(int)
    idx = cube.mean(3).argmax(0)
    C = np.take_along_axis(cube, idx[None, ..., None].repeat(3, -1), 0)[0]
    green = binary_dilation((C[..., 1] - C[..., 0] > 25) & (C[..., 1] - C[..., 2] > 12), iterations=1)
    xs = np.arange(x1 - x0)
    for yy in range(y1 - y0):
        ok = ~green[yy]
        if green[yy].any() and ok.sum() > 2:
            for c in range(3):
                C[yy, green[yy], c] = np.interp(xs[green[yy]], xs[ok], C[yy, ok, c])
    E[y0:y1, x0:x1] = C.astype(np.uint8)


def ink_bbox(g, box, t=60):
    """Рамка английских чернил внутри рамки снятия — по ней мерятся кегль и сжатие."""
    x0, y0, x1, y1 = box
    sub = g[y0:y1, x0:x1]
    bg = uniform_filter1d(np.percentile(sub, 85, axis=0), 5)
    ys, xs = np.nonzero((bg[None, :] - sub) > t)
    return (x0 + xs.min(), y0 + ys.min(), x0 + xs.max() + 1, y0 + ys.max() + 1)


def render(text, font, size, q, bold=0):
    """Строка маской с опорой — левым краем базовой линии; набор ×4 и уменьшение."""
    F = ImageFont.truetype(FD + font + ".ttf", size * 4)
    w = int(F.getlength(text)) + size * 8
    im = Image.new("L", (w, size * 16), 0)
    ImageDraw.Draw(im).text((size * 4, size * 12), text, font=F, fill=255, anchor="ls",
                            stroke_width=bold, stroke_fill=255)
    im = im.resize((max(1, round(im.width * q / 4)), im.height // 4), Image.LANCZOS)
    return im, (round(size * 4 * q / 4), size * 3)


def fit(en_text, font, bb):
    """Кегль и сжатие, при которых английский текст нашим шрифтом встаёт в рамку его чернил."""
    H, W = bb[3] - bb[1], bb[2] - bb[0]
    for size in range(10, 400):
        b = render(en_text, font, size, 1.0)[0].getbbox()
        if b[3] - b[1] >= H:
            break
    b = render(en_text, font, size, 1.0)[0].getbbox()
    return size, W / (b[2] - b[0])


def place(out, lb, bb):
    font, en_text = lb["font"], lb["en"]
    size, q = fit(en_text, font, bb)
    em, eo = render(en_text, font, size, q)
    eb = em.getbbox()
    base_y = bb[1] - eb[1] + eo[1]
    size2 = round(size * lb.get("scale", 1.0))
    bold = lb.get("bold", 0)
    m, o = render(lb["ru"], font, size2, q, bold)
    b = m.getbbox()
    maxw = lb.get("maxw")
    if maxw and b[2] - b[0] > maxw:
        q = q * maxw / (b[2] - b[0])
        m, o = render(lb["ru"], font, size2, q, bold)
        b = m.getbbox()
    if lb.get("align", "center") == "center":
        x = (bb[0] + bb[2]) / 2 - (b[2] - b[0]) / 2 - b[0]
    else:
        x = lb.get("left", bb[0]) - b[0]
    at = (round(x), round(base_y - o[1] + lb.get("dy", 0)))
    if lb.get("glow"):
        gm = m.filter(ImageFilter.GaussianBlur(lb["glow"])).point(lambda v: min(255, int(v * 2.2)))
        out.paste((255, 255, 255), at, gm)
    out.paste(tuple(lb["colour"]), at, m)
    return f"{lb['ru']}: {font} кегль {size2}, сжатие {q:.3f}"


def build(name, job, case):
    raw = Image.open(EN / case / f"{name}.png")
    alpha = raw.getchannel("A") if raw.mode == "RGBA" else None
    E0 = np.asarray(raw.convert("RGB"))
    g = E0.astype(float).mean(2)
    E = E0.copy()
    bbs = []
    for lb in job["labels"]:
        bbs.append(ink_bbox(g, lb["box"]))
        if lb.get("угол"):
            glow_corner(E, name, lb["угол"])
        else:
            column_clean(E, g, lb["box"], flat=lb.get("flat", False))
    out = Image.fromarray(E)
    report = [place(out, lb, bb) for lb, bb in zip(job["labels"], bbs)]
    if alpha is not None:
        out = out.convert("RGBA")
        out.putalpha(alpha)
    return out, report


def small_copy(name, job, case, folder):
    """Мелкая копия картинки: в зонах надписей — уменьшенная русская большая, вне их — оригинал.

    `копия` — имя большой (набирается раньше, в том же задании), `k` — масштаб,
    `зоны` — рамки в координатах большой. Так сделана `logic02_023_s` — это
    `itm02_026_00_l`, уменьшенная ровно в 158/300 (27 сентября 2026)."""
    raw = Image.open(EN / case / f"{name}.png")
    out = raw.convert("RGBA")
    big_path = folder / f"{job['копия']}.png"
    if not big_path.exists():
        # большая ещё не принята и лежит в `drafts/hold/` — берём её оттуда
        held = sorted((ROOT / "work" / "graphics_masks" / "drafts" / "hold").rglob(f"{job['копия']}.png"))
        big_path = held[0] if held else big_path
    big = Image.open(big_path).convert("RGBA")
    # «перспектива» — [рамка в большой]: мелкая — та же вещь под углом (билет-улика
    # `itm03_004` — билет `cut03_001` в перспективе, 30 сентября 2026). Гомография
    # «большая → мелкая» считается по точкам SIFT между английскими вариантами, по ней
    # в мелкую ложатся только пиксели, где русская большая отличается от английской.
    if "перспектива" in job:
        import cv2
        from scipy.ndimage import binary_dilation
        x0, y0, x1, y1 = job["перспектива"]
        en_big = np.asarray(Image.open(EN / case / f"{job['копия']}.png").convert("RGB").crop((x0, y0, x1, y1)))
        ru_big = np.asarray(big.convert("RGB").crop((x0, y0, x1, y1)))
        small_en = np.asarray(raw.convert("RGB"))
        sift = cv2.SIFT_create()
        g1 = cv2.cvtColor(en_big, cv2.COLOR_RGB2GRAY)
        g2 = cv2.cvtColor(small_en, cv2.COLOR_RGB2GRAY)
        # «контраст» — мелкая затемнена (фон чтения улики `Sousa_TextCutBG_*`, яркость
        # до 60 из 255): SIFT на ней не находит ни одной точки, обе картинки
        # выравниваются гистограммой только для поиска точек
        if job.get("контраст"):
            g1, g2 = cv2.equalizeHist(g1), cv2.equalizeHist(g2)
        # большая уменьшается до размера мелкой, иначе SIFT не сводит масштабы
        k = job.get("k", g2.shape[1] / g1.shape[1])
        g1s = cv2.resize(g1, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        k1, d1 = sift.detectAndCompute(g1s, None)
        k2, d2 = sift.detectAndCompute(g2, None)
        pairs = cv2.BFMatcher().knnMatch(d1, d2, k=2)
        good = [m for m, n in pairs if m.distance < 0.75 * n.distance]
        src = np.float32([k1[m.queryIdx].pt for m in good])
        dst = np.float32([k2[m.trainIdx].pt for m in good])
        H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 2.0)
        # «тождество» — мелкая тот же кадр, что большая (×k): совмещение без поиска.
        # На затемнённом кадре `cut02_031` SIFT находил мусор и клал ленту наискось.
        if job.get("тождество"):
            H = np.array([[1.0, 0, x0 * k], [0, 1.0, y0 * k], [0, 0, 1]])
            inl = np.ones(1)
        size = (small_en.shape[1], small_en.shape[0])
        # переносится уже уменьшенная ×k большая — без уменьшения точечная печать
        # при линейной выборке рябит
        ru_s = cv2.resize(ru_big, (g1s.shape[1], g1s.shape[0]), interpolation=cv2.INTER_AREA)
        warped = cv2.warpPerspective(ru_s, H, size, flags=cv2.INTER_LINEAR)
        diff = (np.abs(ru_big.astype(int) - en_big.astype(int)).max(2) > 24).astype(np.float32)
        diff = cv2.resize(diff, (g1s.shape[1], g1s.shape[0]), interpolation=cv2.INTER_AREA)
        m = cv2.warpPerspective(diff, H, size, flags=cv2.INTER_LINEAR) > 0.08
        m = binary_dilation(m, iterations=job.get("запас", 1))
        # «свет» — мелкая освещена иначе (затемнённый кадр сцены `cut02_031` против
        # `cut02_032`): русская умножается на отношение «мелкая / большая» по каналам,
        # медиана по английским пикселям зоны. «видно» — допуск: пиксель переносится,
        # только если английская мелкая там та же, что английская большая (при этом
        # свете), — людей и предметы перед вывеской `cut02_001` русская не перекрывает.
        if job.get("свет") or job.get("видно"):
            en_s = cv2.resize(en_big, (g1s.shape[1], g1s.shape[0]), interpolation=cv2.INTER_AREA)
            w_en = cv2.warpPerspective(en_s, H, size, flags=cv2.INTER_LINEAR).astype(float)
            gain = np.ones(3)
            if job.get("свет"):
                ok = m & (w_en.min(2) > 20)
                gain = np.median(small_en[ok].astype(float) / w_en[ok], axis=0)
                warped = np.clip(warped.astype(float) * gain, 0, 255).astype(np.uint8)
            if job.get("видно"):
                m &= np.abs(small_en.astype(float) - w_en * gain).max(2) <= job["видно"]
        O = np.asarray(out).copy()
        O[m, :3] = warped[m]
        res_im = Image.fromarray(O)
        if raw.mode != "RGBA":
            res_im = res_im.convert(raw.mode)
        return res_im, [f"перспектива {job['копия']}: точек {len(good)}, опорных {int(inl.sum())}, пикс. {int(m.sum())}"]
    # «куски» — [[рамка в большой], [рамка в мелкой]]: мелкая нарисована не ровным
    # уменьшением, а своей раскладкой (улика `itm01_01d` — тот же щиток с рубильниками,
    # таблички на других местах). Каждая табличка переносится своей рамкой.
    if "куски" in job:
        for src, dst in job["куски"]:
            w, h = dst[2] - dst[0], dst[3] - dst[1]
            piece = big.crop(tuple(src)).resize((w, h), Image.LANCZOS)
            out.paste(piece, (dst[0], dst[1]))
        if raw.mode != "RGBA":
            out = out.convert(raw.mode)
        return out, [f"копия {job['копия']}: кусков {len(job['куски'])}"]
    # «найти» — [рамки в большой]: каждая рамка ищется в мелкой сама (английская большая,
    # уменьшенная ×k, против английской мелкой, cv2.matchTemplate), и туда ложатся только
    # пиксели, где русская большая отличается от английской (с запасом 2 px). Мелкая
    # нарисована своей раскладкой: улика `itm01_00b` повёрнута иначе, чем `cut01_027`,
    # и общий сдвиг давал двойные линии доски (27 сентября 2026).
    if "найти" in job:
        import cv2
        from scipy.ndimage import binary_dilation
        k = job["k"]
        en_big = Image.open(EN / case / f"{job['копия']}.png").convert("RGB")
        small_en = np.asarray(raw.convert("RGB")).astype(np.float32)
        O = np.asarray(out).copy()
        report = []
        for x0, y0, x1, y1 in job["найти"]:
            w, h = round((x1 - x0) * k), round((y1 - y0) * k)
            e = np.asarray(en_big.crop((x0, y0, x1, y1)).resize((w, h), Image.LANCZOS)).astype(np.float32)
            r = np.asarray(big.convert("RGB").crop((x0, y0, x1, y1)).resize((w, h), Image.LANCZOS))
            # поиск — в «окне» вокруг места по общему «сдвигу»: одинаковые буквы
            # (две ладьи, три пешки) иначе находят друг друга
            ox, oy = job.get("сдвиг", (0, 0))
            win = job.get("окно", 16)
            ex, ey = round(x0 * k) + ox, round(y0 * k) + oy
            sx0, sy0 = max(0, ex - win), max(0, ey - win)
            area = small_en[sy0:ey + h + win, sx0:ex + w + win]
            res = cv2.matchTemplate(area, e, cv2.TM_CCOEFF_NORMED)
            _, score, _, (px, py) = cv2.minMaxLoc(res)
            px, py = px + sx0, py + sy0
            diff = np.abs(np.asarray(big.convert("RGB").crop((x0, y0, x1, y1))).astype(int)
                          - np.asarray(en_big.crop((x0, y0, x1, y1))).astype(int)).max(2) > 24
            m = np.asarray(Image.fromarray((diff * 255).astype("uint8")).resize((w, h), Image.BILINEAR)) > 20
            m = binary_dilation(m, iterations=2)
            sub = O[py:py + h, px:px + w]
            sub[m, :3] = r[m]
            report.append(f"рамка {x0},{y0}: совпадение {score:.2f} в ({px},{py})")
        res_im = Image.fromarray(O)
        if raw.mode != "RGBA":
            res_im = res_im.convert(raw.mode)
        return res_im, report
    k = job["k"]
    # «сдвиг» — мелкая лежит не от угла большой (улика `itm01_00b` — шахматная диаграмма
    # `cut01_027`, уменьшенная ×0,208 и сдвинутая, замер cv2.matchTemplate 0,84)
    ox, oy = job.get("сдвиг", (0, 0))
    small = big.resize((round(big.width * k), round(big.height * k)), Image.LANCZOS)
    for x0, y0, x1, y1 in job["зоны"]:
        box = (round(x0 * k), round(y0 * k), round(x1 * k), round(y1 * k))
        out.paste(small.crop(box), (box[0] + ox, box[1] + oy))
    if raw.mode != "RGBA":
        out = out.convert(raw.mode)
    return out, [f"копия {job['копия']} ×{k}: зон {len(job['зоны'])}"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--only")
    args = ap.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    case = args.spec.parent.name
    for name, job in spec.items():
        if name.startswith("_") or (args.only and name != args.only):
            continue
        if "копия" in job:
            out, report = small_copy(name, job, case, args.spec.parent)
        else:
            out, report = build(name, job, case)
        out.save(args.spec.parent / f"{name}.png")
        print(name)
        for r in report:
            print("  ", r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
