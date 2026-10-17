"""Вклеить нарисованную надпись в игровую текстуру, не тронув рисунок.

Парный к `relabel.py`. Тот **набирает** надпись шрифтом — годится для планов
этажей, табличек и визиток. Этот берёт **нарисованную** надпись (логотип,
рукописную пометку, объёмные буквы) и ставит её на место английской.

Откуда берётся надпись. Нейросеть рисует **только слово на сплошном пурпурном
фоне `#FF00FF`**, игровую картинку видит лишь как образец стиля — порядок
описан в [`docs/graphics-workflow.md`](../docs/graphics-workflow.md), шаг 5.
Её картинка в игру **не идёт никогда**: отсюда берутся только буквы.

Три вещи, на которых это ломается, и что скрипт с ними делает.

1. **Фон не бывает ровно `#FF00FF`.** Генератор промахивается, а пересылка
   дожимает картинку в webp. Замеры по присланным шести файлам: чистого
   `#FF00FF` — 0,0%, реальный фон (247,4,239), (231,6,239), (237,6,246),
   (241,5,242). Поэтому ключ идёт **с допуском**, а не по точному совпадению.
2. **Вокруг букв остаётся пурпурная кайма** — сглаживание плюс потери сжатия.
   Лечится деспиллом: где `min(r,b)` выше `g`, разница вычитается из красного
   и синего. В логотипе своего пурпура нет, поэтому вычитается целиком.
   Плюс альфа сжимается на пару пикселей (`shrink`).
3. **Старую надпись мало закрыть — её надо снять.** Проверено на `cut00_002`:
   русское «СТАЛЬНОЙ» шире английского `STEEL`, но между букв у него дыры,
   и сквозь них старое слово видно. Снятие — тем же способом, что в `relabel.py`:
   маска по цвету букв и обводки, затем затягивание дыры соседними пикселями.

Задание — JSON рядом с картинками, имя ассета сверху (как в `relabel.py`):

    {
      "cut00_002": {
        "снять": [
          {"box": [1090, 640, 1805, 735], "fill": [205, 205, 210],
           "stroke": [35, 35, 40]}
        ],
        "вклеить": [
          {"art": "../../graphics_ai/case1/cut00_002_стальной_самурай.png",
           "box": [995, 628, 1875, 1041], "shrink": 2}
        ]
      }
    }

`box` во «вклеить» — куда лечь арту после ключа и обрезки по содержимому;
пропорции сохраняются, картинка вписывается в рамку. Путь `art` — относительно
файла задания. Необязательное: `key` (цвет фона, по умолчанию пурпур),
`key_tol` (допуск, 90), `despill` (по умолчанию да), `shrink` (сжать альфу,
2 пикселя), `opacity`.

Ключ `плашка` (8 октября 2026) — класс «без фона», курс 23 сентября: нейросеть
перерисовала **всю вырезку вместе с фоном** (`codex_image.py`), сюда идёт её
рисунок целиком. Совмещение по точкам вне зоны, подгонка цвета, вклейка
только в зону с мягким краем внутрь — подробно в `plate()`:

    "плашка": [{"art": "../../graphics_ai/case2/cut01_009_codex_1.png",
                "вырезка": [250, 0, 1920, 720],
                "зона": [[90, 60, 1670, 660]],
                "кроме": [], "по_разнице": 40, "запас": 8, "край": 6}]

`вырезка` — та же рамка, что `--box` у `codex_image.py`; `зона` и `кроме` —
в координатах вырезки, рамки и многоугольники.

    python tools/paste_art.py work/graphics_ru/case1/art.json
    python tools/paste_art.py work/graphics_ru/case1/art.json --only cut00_002

Читает фон из `work/graphics_en/<дело>/`, пишет в папку, где лежит задание.
Размер файла на выходе — как у оригинала: `inject_localized.py` приводит
картинку к размеру ассета сам, но менять его тут незачем и нельзя.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from picture_layer import shrink
from relabel import remap, strip_text

MAGENTA = (255, 0, 255)


def key_out(im: Image.Image, key=MAGENTA, tol: int = 90, despill: bool = True,
            shrink: int = 2) -> Image.Image:
    """Убрать фон по цвету, снять кайму, вернуть RGBA, обрезанный по содержимому."""
    im = im.convert("RGB")
    w, h = im.size
    px = im.load()
    out = Image.new("RGBA", (w, h))
    op = out.load()
    kr, kg, kb = key
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if abs(r - kr) < tol and abs(g - kg) < tol and abs(b - kb) < tol:
                op[x, y] = (0, 0, 0, 0)
                continue
            if despill:
                spill = min(r, b) - g
                if spill > 0:
                    r, b = max(0, r - spill), max(0, b - spill)
            op[x, y] = (r, g, b, 255)
    if shrink:
        size = shrink * 2 + 1
        out.putalpha(out.getchannel("A").filter(ImageFilter.MinFilter(size)))
    box = out.getbbox()
    return out.crop(box) if box else out


def keep_only(im: Image.Image, colour, tol_in: int = 45, tol_out: int = 110,
              recolour=None) -> Image.Image:
    """Оставить только пиксели около заданного цвета — остальное прозрачным.

    Нужно, когда нейросеть нарисовала не одно слово, а слово **на плашке**:
    плашку рисовал Capcom, её надо сохранить, а взять только буквы. Ключом
    по фону тут не обойтись — фонов два.

    Край букв сглажен и уезжает в цвет плашки, поэтому альфа не ступенькой,
    а полосой: до `tol_in` непрозрачно, после `tol_out` прозрачно, между —
    линейно. Иначе буквы приезжают с зубцами.

    `recolour` перекрашивает буквы в цвет оригинала: нейросеть рисует при
    своём освещении, а плашка в кадре бывает в тени (у `cut02_032` буквы
    оригинала (42,20,15), у нейросети (63,27,12) — заметно светлее).
    """
    im = im.convert("RGB")
    w, h = im.size
    px = im.load()
    out = Image.new("RGBA", (w, h))
    op = out.load()
    span = max(1, tol_out - tol_in)
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            d = max(abs(p[i] - colour[i]) for i in range(3))
            if d <= tol_in:
                a = 255
            elif d >= tol_out:
                op[x, y] = (0, 0, 0, 0)
                continue
            else:
                a = int(255 * (tol_out - d) / span)
            op[x, y] = (*(recolour or p), a)
    box = out.getbbox()
    return out.crop(box) if box else out


def _zone_mask(size, zones) -> "np.ndarray":
    """Маска зон: рамки [x0, y0, x1, y1] и многоугольники [[x, y], …] в координатах вырезки."""
    import numpy as np
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for z in zones:
        if isinstance(z[0], (int, float)):
            d.rectangle(tuple(z), fill=255)
        else:
            d.polygon([tuple(p) for p in z], fill=255)
    return np.array(m) > 0


def plate(base: Image.Image, glue: dict, spec_dir: Path) -> dict:
    """Плашка нейросети: вся зона надписи вместе с фоном (курс 23 сентября 2026).

    Нейросеть получила вырезку оригинала (`вырезка` — где она лежит в кадре)
    и вернула её же с русской надписью, но перерисованной целиком: размер
    другой, сдвиг на несколько пикселей, свет чуть иной. Поэтому:

    1. рисунок приводится к размеру вырезки и **совмещается** с оригиналом
       по точкам SIFT вне зоны надписи (подобие: масштаб, сдвиг, поворот);
    2. **цвет** подгоняется по тем же неизменённым местам — по каналу
       `оригинал ≈ a·нейросеть + b`;
    3. в кадр идёт только `зона` (рамки и многоугольники в координатах
       вырезки) минус `кроме`; с `по_разнице` — лишь там, где рисунок
       отличается от оригинала больше порога (буквы), с запасом `запас` px;
       край мягкий на `край` px **внутрь** зоны — снаружи оригинал до пикселя.

    Возвращает замеры для отчёта: сколько точек, масштаб, остаток вне зоны.
    """
    import cv2
    import numpy as np

    x0, y0, x1, y1 = glue["вырезка"]
    w, h = x1 - x0, y1 - y0
    # прозрачное — на сером, как вырезку видела нейросеть (codex_image.py)
    grey = Image.new("RGBA", base.size, (128, 128, 128, 255))
    grey.alpha_composite(base)
    orig = np.array(grey.convert("RGB").crop((x0, y0, x1, y1))).astype(np.float32)
    art = Image.open((spec_dir / glue["art"]).resolve()).convert("RGB")
    # Пропорции рисунка не трогать: генератор не рисует вытянутее 3:1 и
    # вырезку 4:1 рисует во всю ширину и добивает полями по высоте
    # (транспарант cut02_02d, 8 октября 2026). Масштаб — по большему,
    # поля срезаются по центру, остальное — совмещение по точкам.
    k = max(w / art.width, h / art.height)
    fitted = art.resize((max(1, round(art.width * k)), max(1, round(art.height * k))), Image.LANCZOS)
    canvas = Image.new("RGB", (w, h), (128, 128, 128))
    canvas.paste(fitted, ((w - fitted.width) // 2, (h - fitted.height) // 2))
    ai = np.array(canvas).astype(np.float32)

    zone = _zone_mask((w, h), glue["зона"])
    # прозрачное оригинала не в счёт: его не видно, а край предмета задаёт альфа
    seen = np.array(base.getchannel("A").crop((x0, y0, x1, y1))) > 0
    keep_out = (cv2.dilate(zone.astype(np.uint8), np.ones((31, 31), np.uint8)) == 0) & seen
    report = {"точек": 0, "масштаб": 1.0, "сдвиг": (0.0, 0.0)}

    g_o = cv2.cvtColor(orig.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    g_a = cv2.cvtColor(ai.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    sift = cv2.SIFT_create(4000)

    def match(where):
        ko, do = sift.detectAndCompute(g_o, where)
        ka, da = sift.detectAndCompute(g_a, where)
        if do is None or da is None or len(ko) <= 8 or len(ka) <= 8:
            return None, 0
        pairs = cv2.BFMatcher().knnMatch(da, do, k=2)
        good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < 0.75 * p[1].distance]
        if len(good) < 8:
            return None, 0
        src = np.float32([ka[m.queryIdx].pt for m in good])
        dst = np.float32([ko[m.trainIdx].pt for m in good])
        if glue.get("совмещение") == "перспектива":
            # плоский лист, который нейросеть повернула иначе (афиша-улика)
            M, inl = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
        else:
            M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                                 ransacReprojThreshold=3.0)
        return M, (int(inl.sum()) if M is not None else 0)

    cv2.setRNGSeed(0)          # RANSAC случайный: одна и та же вклейка — один результат
    M, n = match(keep_out.astype(np.uint8) * 255)
    if n < 50:
        # зона заняла почти всю вырезку — точки по всей: буквы изменены,
        # но рисунок вокруг (люди, здание) тот же, RANSAC отбросит буквы
        cv2.setRNGSeed(0)
        M2, n2 = match(None)
        if n2 > n:
            M, n = M2, n2
            report["точки_по_всей"] = True
    if M is not None:
        warp = cv2.warpPerspective if M.shape[0] == 3 else cv2.warpAffine
        ai = warp(ai, M, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)
        report.update(точек=n,
                      масштаб=round(float(np.hypot(M[0, 0], M[1, 0])), 4),
                      сдвиг=(round(float(M[0, 2]), 1), round(float(M[1, 2]), 1)))

    # неизменённые места; нет их — вся вырезка (буквы — малая доля)
    sel = keep_out if keep_out.sum() > 5000 else seen
    if glue.get("свет", True):
        # цвет по неизменённым местам; концы распределения отброшены — там
        # тени и блики, которые нейросеть рисует по-своему
        for c in range(3):
            a_, o_ = ai[..., c][sel], orig[..., c][sel]
            if a_.size > 1000 and a_.std() > 1:
                lo, hi = np.percentile(a_, [1, 99])
                ok = (a_ > lo) & (a_ < hi)
                k, b = np.polyfit(a_[ok], o_[ok], 1)
                ai[..., c] = ai[..., c] * k + b
    ai = np.clip(ai, 0, 255)
    resid = np.abs(ai - orig).max(axis=2)
    report["остаток_вне_зоны"] = round(float(np.median(resid[sel])), 1)

    # «альфа_по_фону» — {цвет, от, до}: у картинки своя прозрачность, и русская надпись
    # выходит за её контур (выкрики `efc_BigFont*`: буквы вылезают за звезду иначе, чем
    # английские). Нейросеть видела прозрачное серым — по отличию от серого строится
    # новая альфа зоны; без ключа прозрачное оригинала остаётся как было.
    by_bg = glue.get("альфа_по_фону")
    mask = zone if by_bg else zone & seen
    if "кроме" in glue:
        mask &= ~_zone_mask((w, h), glue["кроме"])
    if "по_разнице" in glue:
        diff = np.abs(ai - orig).max(axis=2) > glue["по_разнице"]
        # шум — только крошечные пятна; «открытие» 3×3 стирало тонкие штрихи
        # мелкого текста целиком, и английская строка оставалась (cut03_021)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(diff.astype(np.uint8), connectivity=8)
        diff = np.isin(lab, np.nonzero(stats[:, cv2.CC_STAT_AREA] >= 6)[0][1:]).astype(np.uint8)
        r = glue.get("запас", 6)
        diff = cv2.dilate(diff, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
        mask &= diff > 0
    edge = max(1, glue.get("край", 6))
    dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    alpha = np.clip(dist / edge, 0, 1)[..., None]
    out = orig * (1 - alpha) + ai * alpha
    patch = Image.fromarray(np.round(out).astype(np.uint8), "RGB")
    where = Image.fromarray(((alpha[..., 0] > 0) * 255).astype(np.uint8), "L")
    flat = base.convert("RGB")
    flat.paste(patch, (x0, y0), where)     # вне зоны — оригинал до пикселя
    a = base.getchannel("A")
    before = np.array(base.convert("RGB"))
    if by_bg:
        lo, hi = by_bg.get("от", 16), by_bg.get("до", 48)
        far = np.abs(ai - np.array(by_bg.get("цвет", [128, 128, 128]), np.float32)).max(axis=2)
        new_a = np.clip((far - lo) / max(1, hi - lo), 0, 1) * 255
        if by_bg.get("закрыть"):
            # проколы в 1 px по чёрному контуру и на стыке букв с белым: генератор местами
            # рисует контур тоном, близким к серому фону (выкрики, 9 октября 2026: 1350–1900
            # проколов на файл против 49 у оригинала) — морфологическое замыкание 3×3
            new_a = np.maximum(new_a, cv2.morphologyEx(new_a.astype(np.float32), cv2.MORPH_CLOSE,
                                                       np.ones((3, 3), np.uint8)))
        old_a = np.array(a.crop((x0, y0, x1, y1))).astype(np.float32)
        mixed = old_a * (1 - alpha[..., 0]) + new_a * alpha[..., 0]
        a = a.copy()
        a.paste(Image.fromarray(np.round(mixed).astype(np.uint8), "L"), (x0, y0))
    base.paste(flat)
    base.putalpha(a)
    if by_bg and by_bg.get("прозрачное") == "оригинал":
        # под прозрачным у нейросети серый фон вырезки; при сглаживании текстуры он даёт
        # серую бахрому — цвет полностью прозрачных пикселей берётся у оригинала
        arr = np.array(base)
        clear = arr[..., 3] == 0
        arr[clear, :3] = before[clear]
        base.paste(Image.fromarray(arr, "RGBA"))
    report["зона_px"] = int((alpha > 0).sum())
    return report


def fit(art: Image.Image, box) -> tuple[Image.Image, tuple[int, int]]:
    """Вписать арт в рамку, сохранив пропорции. Возвращает картинку и левый верх."""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    scale = min(bw / art.width, bh / art.height)
    w, h = max(1, round(art.width * scale)), max(1, round(art.height * scale))
    art = art.resize((w, h), Image.LANCZOS)
    return art, (x0 + (bw - w) // 2, y0 + (bh - h) // 2)


def run(spec_path: Path, only: str | None) -> int:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    src_dir = Path("work/graphics_en") / spec_path.parent.name
    out_dir = spec_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    done = 0
    for name, job in spec.items():
        if only and name != only:
            continue
        if "как" in job:
            own = {k: v for k, v in job.items()
                   if k not in ("как", "якорь_там", "якорь_тут")}
            job = {**remap(spec[job["как"]], job["якорь_там"], job["якорь_тут"]), **own}
        src = src_dir / f"{name}.png"
        if job.get("основа") == "готовое" and (out_dir / f"{name}.png").exists():
            # На картинке есть и набираемое, и рисованное: сперва по ней проходит
            # relabel.py, потом этот скрипт. Оба пишут в одну папку, поэтому
            # второй должен брать за основу результат первого, а не оригинал.
            src = out_dir / f"{name}.png"
        if not src.exists():
            print(f"  {name}: нет исходника {src}")
            continue
        im = Image.open(src).convert("RGBA")
        alpha = im.getchannel("A")          # альфа оригинала: у cut* она 254..255
        flat = im.convert("RGB")
        pristine = flat.copy()              # для «вернуть»: снятие уже не отменить

        for cut in job.get("снять", []):
            strip_text(flat, cut["box"], tuple(cut["fill"]), tuple(cut["stroke"]),
                       cut.get("pad", 6), tol_fill=cut.get("допуск", job.get("допуск", 45)),
                       tol_stroke=cut.get("допуск_обводки", job.get("допуск_обводки", 25)))
        im = flat.convert("RGBA")
        im.putalpha(alpha)

        if "уменьшить" in job:
            # Третий приём — для копий, где набирать уже нечего. На карточке
            # логики 158x158 лист занимает 141x97, и буква шапки выходит в три
            # пикселя: снятие мажет, а набранное превращается в кашу. Проверено
            # 25 августа 2026. Тогда готовая большая картинка ужимается в рамку
            # ориентира этой. Линии игра рисует резче, чем выходит уменьшением,
            # но ровное уменьшение верного кадра лучше сломанной сборки.
            u = job["уменьшить"]
            big = Image.open(out_dir / f'{u["из"]}.png').convert("RGBA")
            there, here = u["якорь_там"], u["якорь_тут"]
            # Ужимает тот же код, что склеивает картинку у игрока: иначе его копия
            # разойдётся с этой на единицу в половине пикселей (13 сентября 2026).
            patch = shrink(big, there, (here[2] - here[0], here[3] - here[1]))
            im.paste(patch, (here[0], here[1]))

        for glue in job.get("плашка", []):
            r = plate(im, glue, spec_path.parent)
            print(f"  {name}: плашка {glue['art']} — точек {r['точек']}, масштаб {r['масштаб']}, "
                  f"сдвиг {r['сдвиг']}, остаток вне зоны {r['остаток_вне_зоны']}, зона {r['зона_px']} px")

        for glue in job.get("вклеить", []):
            art_path = (spec_path.parent / glue["art"]).resolve()
            raw = Image.open(art_path)
            if "отрезать" in glue:
                # Строки на листе идут лесенкой и налезают друг на друга по
                # вертикали: прямоугольником одну от другой не отделить.
                # Режем прямой через две точки — «выше» или «ниже» неё стирается
                # фоном. Нужно, когда пометку надо разложить в одну строку,
                # а нейросеть нарисовала её в две.
                raw = raw.convert("RGB")
                bg = tuple(glue.get("key", MAGENTA))
                rp = raw.load()
                for cut_ in glue["отрезать"]:
                    side = "ниже" if "ниже" in cut_ else "выше"
                    (ax, ay), (bx, by) = cut_[side]
                    k = (by - ay) / (bx - ax)
                    for x in range(raw.width):
                        edge = ay + k * (x - ax)
                        rng = (range(max(0, int(edge)), raw.height) if side == "ниже"
                               else range(0, min(raw.height, int(edge) + 1)))
                        for y in rng:
                            rp[x, y] = bg
            if "из" in glue:
                # на одном листе нейросеть прислала несколько пометок сразу —
                # берём нужную. Просить по одной за запрос выходит дороже,
                # а лист режется рамкой без потерь.
                raw = raw.crop(tuple(glue["из"]))
            if "кроме" in glue:
                # пометки на листе стоят лесенкой, и прямоугольник вокруг одной
                # обязательно прихватывает угол соседней. Проверено: в первую
                # пометку плана 24 марта заехало «Ладья перестав» из второй.
                # Лишнее закрашивается фоном, а не вырезается рамкой, — иначе
                # придётся резать пометку на куски.
                raw = raw.convert("RGB")
                bg = tuple(glue.get("key", MAGENTA))
                d = ImageDraw.Draw(raw)
                for rect in glue["кроме"]:
                    d.rectangle(tuple(rect), fill=bg)
            if "взять" in glue:
                # арт лежит на плашке, а не на пурпуре: берём только буквы
                art = keep_only(
                    raw,
                    tuple(glue["взять"]),
                    tol_in=glue.get("tol_in", 45),
                    tol_out=glue.get("tol_out", 110),
                    recolour=tuple(glue["перекрасить"]) if "перекрасить" in glue else None,
                )
            else:
                art = key_out(
                    raw,
                    key=tuple(glue.get("key", MAGENTA)),
                    tol=glue.get("key_tol", 90),
                    despill=glue.get("despill", True),
                    shrink=glue.get("shrink", 2),
                )
            if glue.get("поворот"):
                # пометка от руки лежит на плане под углом; лист от нейросети
                # ровный. Поворот с expand, чтобы углы букв не срезало.
                art = art.rotate(glue["поворот"], Image.BICUBIC, expand=True)
                box = art.getbbox()
                if box:
                    art = art.crop(box)
            art, at = fit(art, glue["box"])
            if glue.get("opacity", 1.0) != 1.0:
                a = art.getchannel("A").point(lambda v: int(v * glue["opacity"]))
                art.putalpha(a)
            im.alpha_composite(art, at)

        for back in job.get("вернуть", []):
            # Стрелка от пометки к фигуре нарисована той же красной ручкой и
            # проходит сквозь буквы, поэтому снятие надписи откусывает ей хвост.
            # Здесь кусок стрелки возвращается из нетронутого оригинала: рамка
            # берётся такая, где из красного есть только стрелка.
            x0, y0, x1, y1 = back["box"]
            col = tuple(back["цвет"])
            tol = back.get("допуск", 60)
            sp, dp = pristine.load(), im.load()
            for y in range(y0, y1):
                for x in range(x0, x1):
                    q = sp[x, y]
                    if max(abs(q[i] - col[i]) for i in range(3)) <= tol:
                        dp[x, y] = (*q, 255)

        for dab in job.get("закрасить", []):
            # Просвет в пиксель-два между буквами, который нейросеть дважды не развела
            # (ножка «д» и дужка «й» на книге `itm02_023`, 9 октября 2026): рамка
            # заливается цветом фона, взятым с пикселя-образца рядом («цвет_из»).
            x0, y0, x1, y1 = dab["box"]
            sample = im.getpixel(tuple(dab["цвет_из"]))
            dp = im.load()
            for y in range(y0, y1):
                for x in range(x0, x1):
                    dp[x, y] = sample

        if job.get("сохранить_альфу"):
            im.putalpha(alpha)
        dest = out_dir / f"{name}.png"
        im.save(dest)
        print(f"  {name}: {im.size[0]}x{im.size[1]} -> {dest}")
        done += 1
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec", type=Path, help="JSON с заданием")
    ap.add_argument("--only", help="сделать одну картинку")
    args = ap.parse_args()
    n = run(args.spec, args.only)
    print(f"готово картинок: {n}")
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
