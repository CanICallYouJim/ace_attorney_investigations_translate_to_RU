"""Паспорт надписи и сверка русской надписи с английской — один инструмент на все картинки.

Курс от 1 октября 2026 (правило №13, разбор — `work/graphics-review-2026-10-01.md`):
геометрию против оригинала проверяет машина, лист пользователю идёт только после
зелёной сверки и независимого просмотра, принимает глаз пользователя. Около 4/5
замечаний пользователя по наложению за 23.09–01.10 — меряемые отклонения: место
и центр блока, размер и сжатие, наклон и форма строки, штрих, кайма, налезание
на стены; ещё часть — порча рисунка при снятии английского. Их и меряет этот файл.

Английская и русская надписи меряются **одинаково**: по цвету букв из задания
(«чернила», «fill», «stroke»), в выпрямленных координатах надписи («наклон»,
«центр»). Внутренние маски набора не используются — иначе сверка наследует
слепые пятна той же работы (урок 20 сентября, `docs/graphics-workflow.md`).
Исключение одно: если рядом с русской картинкой лежит свежий `<имя>_ink.png`
(что именно нарисовал набор), русские буквы берутся из него — так точнее
и так считаются остатки английского. Если английские буквы цветом задания
не находятся (задание врёт про цвет — «Cells» на `cut01_008`), цвет берётся
с самих букв и об этом пишется предупреждение.

По каждой надписи:
  * **место** — у подписи в блоке (комната, круг, клетка — стены найдены лучами
    от середины английской надписи: скачок цвета, а не порог от фона, иначе мягкий
    край комнаты не виден) середина против середины блока и поля до стен; у строки
    без блока — опорный край по «по» (лево/право/центр), ширина и базовая линия;
  * **размер** — строчные против строчных, если обе строки со строчными, иначе
    прописные; у подписи в блоке мельче — только «посмотреть»: длинное слово
    набирается мельче, а не уже (решение пользователя 30.09); сжатие — ширина русской
    строки против той же строки гарнитурой задания без сжатия;
  * **угол** — остаток наклона после выпрямления по заданию: у английской он значит,
    что «наклон» в задании неверен; **форма строки** — дуга верха высоких букв;
  * **начертание** — штрих по карте расстояний (край буквы делится между цветом
    буквы и цветом каймы или фона — иначе мелкие буквы выходят тоньше на ровном
    месте), кайма — площадь каймы на длину края; цвет букв;
  * **рисунок** — линии рисунка у надписи, которые были у английской картинки
    и пропали у русской (замазанные стены, размытая крыша), и новые края (пятна,
    швы, ореолы); **остатки** английских букв — только при `_ink.png`.

Допуски — одна таблица `TOL` ниже, на все картинки. Править её только отдельным
коммитом с «да» пользователя: проверку, подогнанную под картинку, курс 23 сентября
запретил, и правильно. Сознательное отступление — в паспорт дела
(`work/graphics_ru/<дело>/passport.json`, `<картинка>.задано.<англ>.исключения`:
`{"пункт": "причина"}`): ✗ становится ≈ и печатается с причиной.

    .venv\\Scripts\\python.exe tools\\passport.py cut01_008
    .venv\\Scripts\\python.exe tools\\passport.py cut00_01e --ru work/graphics_masks/drafts/hold/case1/cut00_01e.png
    .venv\\Scripts\\python.exe tools\\passport.py cut01_008 --measure      паспорт английской, записать в passport.json

Лист сверки — `work/graphics_masks/checks/<имя>_сверка.png`: сверху весь кадр
с картой линий (жёлтое — пропало, голубое — новое), ниже по каждой надписи
английская | русская | наложение (красное — английские буквы, синее — русские,
лиловое — совпало; зелёное — стены блока). Отчёт числами — `<имя>_сверка.json`.
Код выхода 1, если есть ✗.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
EN_DIR = WORK / "graphics_en"
RU_DIR = WORK / "graphics_ru"
CHECKS = WORK / "graphics_masks" / "checks"
FONT_DIR = Path("C:/Windows/Fonts")

# Допуски — одни на все картинки (курс 1 октября 2026). Не подгонять под картинку.
TOL = {
    "цвет": 60,          # уровней на канал: пиксель буквы против цвета из задания
    "центр": 4,          # px — середина против английской (строка без блока)
    "центр_блока": 2,    # px — середина против середины блока: у принятых кружков 0,5–1 px,
    "центр_доля": 0.025, # ... у забракованных 3,5–6 px на круге в 90 px; или эта доля ширины блока
    "центр_англ": 0.04,  # английская в пределах этой доли блока от середины — «по центру блока»
    "край": 6,           # px — опорный край строки против английского
    "база": 3,           # px — базовая линия
    "высота": 0.10,      # доля — строчные (или прописные) против английских
    "сжатие": 0.85,      # уже этого — «сплющено» (решение пользователя 30.09)
    "растяжка": 1.15,    # шире этого — растянуто
    "ширина": (0.85, 1.15),  # строка без блока: доля английской ширины
    "угол": 0.6,         # градусов — остаток наклона после выпрямления
    "дуга": 0.12,        # доля высоты — прогиб верха высоких букв
    "штрих": 0.20,       # доля — штрих против английского (с поправкой на кегль)
    "кайма": 1.5,        # px — ширина каймы против английской
    "цвет_букв": 40,     # уровней — цвет русских букв против английских (посмотреть)
    "поле": 0.5,         # доля английского поля до стены — меньше, значит «впритык»
    "стена": 50,         # уровней от фона блока — стена наверняка
    "скачок": 22,        # уровней против соседних пикселей луча — край стены
    "край_сильный": 60,  # градиент: линия рисунка
    "край_слабый": 20,   # градиент: линии нет
    "линия_px": 12,      # кусок пропавшей/новой линии короче — шум
    "пропало_px": 40,    # пропало линий у надписи больше — ✗
    "новое_px": 80,      # новых краёв больше — ~ (посмотреть)
    "остатки_px": 25,    # остатков английских букв больше — ✗
}

OK, BAD, WARN, DECL = "✓", "✗", "~", "≈"


# ---------------------------------------------------------------- задание

def find_png(folder: Path, name: str) -> Path | None:
    hits = sorted(folder.glob(f"*/{name}.png"))
    return hits[0] if hits else None


def newspaper_labels(job: dict) -> tuple[dict, list[dict]]:
    """`newspaper.json` (газеты дела 1) в словаре `labels.json`."""
    labels = []
    for lb in job.get("labels", []):
        col = lb.get("colour", [40, 40, 40])
        labels.append({"box": lb["box"], "англ": lb.get("en", ""), "text": lb.get("ru", ""),
                       "чернила": [col], "fill": col, "шрифт": lb.get("font"),
                       "по": {"left": "лево", "right": "право"}.get(lb.get("align", ""), "центр")})
    return {"stroke": []}, labels


def find_task(name: str, case: str | None) -> tuple[str, dict, list[dict], str]:
    cases = [case] if case else sorted(p.name for p in RU_DIR.iterdir() if p.is_dir())
    for c in cases:
        p = RU_DIR / c / "labels.json"
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            if name in d:
                return c, d[name], d[name].get("labels", []), "labels.json"
        p = RU_DIR / c / "newspaper.json"
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            if name in d:
                cfg, labels = newspaper_labels(d[name])
                return c, cfg, labels, "newspaper.json"
    sys.exit(f"{name}: нет задания ни в labels.json, ни в newspaper.json"
             + (f" дела {case}" if case else ""))


def centre(lb: dict) -> tuple[float, float]:
    """Точка поворота надписи с «наклоном» — как в `prints.py`."""
    if "центр" in lb:
        return tuple(lb["центр"])
    x0, y0, x1, y1 = lb["box"]
    return ((x0 + x1) / 2, (y0 + y1) / 2)


def straight_pt(lb: dict, x: float, y: float) -> tuple[float, float]:
    """Точка картинки в выпрямленных координатах надписи — как `Image.rotate(-наклон)`."""
    a = math.radians(-lb.get("наклон", 0))
    cx, cy = centre(lb)
    dx, dy = x - cx, y - cy
    return (cx + dx * math.cos(a) + dy * math.sin(a), cy - dx * math.sin(a) + dy * math.cos(a))


def colours(cfg: dict, lb: dict) -> dict:
    """Цвета букв: английские — «чернила» задания, русские — «fill»/«stroke»."""
    ink = lb.get("чернила") or []
    fill = lb.get("fill") or cfg.get("fill") or (ink[0] if ink else [30, 30, 30])
    stroke = lb.get("stroke", cfg.get("stroke")) or []
    rim_w = lb.get("кант", cfg.get("кант", cfg.get("stroke_width", 2)))
    has_rim = bool(stroke) and rim_w not in (0, None) and cfg.get("stroke_width", 2) != 0
    en_body = list(ink[0]) if ink else list(fill)
    en_rim = list(ink[1]) if len(ink) > 1 else (list(stroke) if has_rim else None)
    # «чернила» назвали одну краску, и это краска каймы, а не букв: у «Viewing Platform»
    # на разрезах (cut03_006/027/028, cut04_03a/046) снятие идёт по белой кайме — тёмные
    # буквы там цвета линий крыши, — и по той же белой сверка меряла английскую: «буквы»
    # 9 px штриха и 52 px роста против 5 и 42 у русской. Английские буквы тогда — той же
    # краской, что русские («fill»), и только внутри своей каймы (см. `run`)
    rim_only = (len(ink) == 1 and en_rim is not None
                and max(abs(a - b) for a, b in zip(en_body, en_rim)) <= 10
                and max(abs(a - b) for a, b in zip(fill, en_body)) > TOL["цвет"])
    if rim_only:
        en_body = list(fill)
    return {"en_body": en_body, "en_rim": en_rim, "ru_body": list(fill),
            "ru_rim": list(stroke) if has_rim else None, "rim_w": int(math.ceil(rim_w or 0)) if has_rim else 0,
            "tol": int(lb.get("чернила_допуск", TOL["цвет"])), "по_кайме": rim_only}


def letters_case(s: str) -> str:
    """«caps» — все буквы прописные, «mixed» — есть строчные."""
    ls = [c for c in s if c.isalpha()]
    return "caps" if ls and all(c == c.upper() for c in ls) else "mixed"


# ---------------------------------------------------------------- маски и повороты

def near(img: np.ndarray, colour, tol: int) -> np.ndarray:
    c = np.array(colour[:3], dtype=np.int16)
    return np.abs(img.astype(np.int16) - c).max(axis=2) <= tol


def disk(r: int) -> np.ndarray:
    r = max(1, int(r))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def grow(m: np.ndarray, r: int) -> np.ndarray:
    return cv2.dilate(m.astype(np.uint8), disk(r)) > 0 if r > 0 else m.astype(bool)


def text_masks(img: np.ndarray, body_col, rim_col, rim_w: int, tol: int):
    body = near(img, body_col, tol)
    rim = np.zeros_like(body)
    if rim_col is not None:
        rim = near(img, rim_col, tol) & grow(body, rim_w + 2) & ~body
    return body, rim


def coverage(img: np.ndarray, body_col, other_col, around: np.ndarray) -> np.ndarray:
    """Доля буквы в пикселе (0…1): проекция цвета на отрезок «цвет буквы — цвет каймы
    или фона». Сглаженный край идёт в счёт долей, а не целиком или никак — от этого
    штрих мелких и крупных букв мерится одинаково."""
    p = img.astype(np.float32)
    b = np.array(body_col[:3], np.float32)
    o = np.array(other_col[:3], np.float32)
    v = o - b
    n = float((v * v).sum())
    if n < 1:
        return around.astype(np.float32)
    t = ((p - b) * v).sum(-1) / n
    return np.where(around, 1 - np.clip(t, 0, 1), 0).astype(np.float32)


def stroke_of(cov: np.ndarray) -> float | None:
    """Штрих = 2 · площадь букв / длина их контура: у длинного штриха ширины w это w,
    без ступенек целых пикселей, на которых карта расстояний давала 2 вместо 2,9."""
    m = (cov >= 0.5).astype(np.uint8)
    if m.sum() < 12:
        return None
    cs, _ = cv2.findContours(m, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    per = sum(cv2.arcLength(c, True) for c in cs)
    return float(2 * cov.sum() / per) if per > 0 else None


def rot_rgb(img: np.ndarray, lb: dict) -> tuple[np.ndarray, np.ndarray]:
    """Картинка в выпрямленных координатах надписи и маска «пиксель из кадра»."""
    a = lb.get("наклон", 0)
    if not a:
        return img, np.ones(img.shape[:2], bool)
    c = centre(lb)
    im = Image.fromarray(img).rotate(-a, resample=Image.BICUBIC, center=c, fillcolor=(0, 0, 0))
    ok = Image.new("L", (img.shape[1], img.shape[0]), 255).rotate(-a, resample=Image.NEAREST,
                                                                   center=c, fillcolor=0)
    return np.asarray(im), np.asarray(ok) > 0


def rot_cov(c: np.ndarray, lb: dict) -> np.ndarray:
    a = lb.get("наклон", 0)
    if not a:
        return c
    im = Image.fromarray(c.astype(np.float32), mode="F")
    return np.asarray(im.rotate(-a, resample=Image.BILINEAR, center=centre(lb)))


def rot_mask(m: np.ndarray, lb: dict, back: bool = False) -> np.ndarray:
    a = lb.get("наклон", 0)
    if not a:
        return m
    im = Image.fromarray((m * 255).astype(np.uint8))
    return np.asarray(im.rotate(a if back else -a, resample=Image.NEAREST, center=centre(lb))) > 0


def box_poly(lb: dict, pad: float = 0.0) -> np.ndarray:
    """Рамка надписи (в выпрямленных координатах) — многоугольником на картинке."""
    x0, y0, x1, y1 = lb["box"]
    pts = [(x0 - pad, y0 - pad), (x1 + pad, y0 - pad), (x1 + pad, y1 + pad), (x0 - pad, y1 + pad)]
    a = math.radians(lb.get("наклон", 0))
    cx, cy = centre(lb)
    out = []
    for x, y in pts:
        dx, dy = x - cx, y - cy
        out.append((cx + dx * math.cos(a) + dy * math.sin(a), cy - dx * math.sin(a) + dy * math.cos(a)))
    return np.array(out, dtype=np.float32)


def poly_mask(shape, lb: dict, pad: float) -> np.ndarray:
    m = np.zeros(shape[:2], np.uint8)
    cv2.fillPoly(m, [box_poly(lb, pad).astype(np.int32)], 1)
    return m.astype(bool)


def inside(lb: dict, x: float, y: float, pad: float = 0.0) -> bool:
    sx, sy = straight_pt(lb, x, y)
    x0, y0, x1, y1 = lb["box"]
    return x0 - pad <= sx <= x1 + pad and y0 - pad <= sy <= y1 + pad


def dist_to_box(lb: dict, x: float, y: float) -> float:
    sx, sy = straight_pt(lb, x, y)
    x0, y0, x1, y1 = lb["box"]
    return math.hypot(max(x0 - sx, 0, sx - x1), max(y0 - sy, 0, sy - y1))


def strip_lines(m: np.ndarray, line_h: float) -> np.ndarray:
    """Убрать из маски букв длинные прямые того же цвета — стены плана, линейки газеты.
    Штрих буквы короче высоты строки, стена длиннее: открытие длинным отрезком оставляет
    только стену. Стенка плана `cut01_008` цвета букв срасталась с заголовком в один кусок
    и шла в «остатки английского» (1 октября 2026)."""
    u = m.astype(np.uint8)
    kv = cv2.getStructuringElement(cv2.MORPH_RECT, (1, int(max(15, 1.6 * line_h))))
    kh = cv2.getStructuringElement(cv2.MORPH_RECT, (int(max(25, 2.2 * line_h)), 1))
    lines = cv2.morphologyEx(u, cv2.MORPH_OPEN, kv) | cv2.morphologyEx(u, cv2.MORPH_OPEN, kh)
    if not lines.any():
        return m
    return m & ~(cv2.dilate(lines, np.ones((3, 3), np.uint8)) > 0)


def components(m: np.ndarray, min_area: int = 3):
    n, lab, st, cen = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    return lab, [(k, st[k], cen[k]) for k in range(1, n) if st[k][4] >= min_area]


def pick(mask: np.ndarray, labels: list[dict], i: int, window: float, line_h: float) -> np.ndarray:
    """Куски маски, принадлежащие надписи i: центр куска в её рамке (с запасом `window`),
    а не в рамке соседней; линии рисунка (длинные и тонкие) — не буквы."""
    lb = labels[i]
    lab, comps = components(mask)
    keep = np.zeros(mask.shape, bool)
    for k, st, (cx, cy) in comps:
        x, y, w, h, area = st
        if not inside(lb, cx, cy, window):
            continue
        if not inside(lb, cx, cy, 4):
            if any(j != i and inside(labels[j], cx, cy, 4) for j in range(len(labels))):
                continue
            d = dist_to_box(lb, cx, cy)
            if any(j != i and dist_to_box(labels[j], cx, cy) < d for j in range(len(labels))):
                continue
        if (w >= 5 * line_h and h <= 0.25 * line_h) or (h >= 2.5 * line_h and w <= 0.25 * line_h):
            continue
        keep |= lab == k
    return keep


def ring_colour(img: np.ndarray, lb: dict, text: np.ndarray) -> list[int]:
    """Фон у надписи: медиана кольца вокруг рамки без букв."""
    ring = poly_mask(img.shape, lb, 14) & ~poly_mask(img.shape, lb, 3) & ~grow(text, 3)
    if ring.sum() < 20:
        ring = poly_mask(img.shape, lb, 14) & ~grow(text, 3)
    px = img[ring] if ring.any() else img.reshape(-1, 3)
    return [int(v) for v in np.median(px, axis=0)] if len(px) else [128, 128, 128]


def guess_colour(img: np.ndarray, lb: dict, bg, rim_col) -> list[int] | None:
    """Цвет английских букв с самих букв — когда задание назвало не тот."""
    m = poly_mask(img.shape, lb, 0)
    d = np.abs(img.astype(np.int16) - np.array(bg, np.int16)).max(axis=2)
    cand = m & (d > 45)
    if rim_col is not None:
        cand &= ~near(img, rim_col, 50)
    if cand.sum() < 30:
        return None
    return [int(v) for v in np.median(img[cand], axis=0)]


# ---------------------------------------------------------------- замер одной надписи

def baseline(bottoms: np.ndarray, href: float) -> float:
    """База — самое людное значение нижних краёв букв: буквы на строке сидят на ней
    с разбросом в пиксель-два, хвосты (у «Двор» — у двух букв из четырёх) в стороне.
    Медиана тут врёт, профиль строки тоже: у прописных круглых букв («СИЗО») пиксели
    вверху и внизу, а не посередине."""
    tol = max(1.5, 0.06 * href)
    best = max(bottoms, key=lambda b: ((np.abs(bottoms - b) <= tol).sum(), -b))
    return float(np.median(bottoms[np.abs(bottoms - best) <= tol]))


def measure(body: np.ndarray, rim: np.ndarray, cov: np.ndarray | None, cov_rim: np.ndarray | None,
            n_lines: int, text: str = "", base_frac: float | None = None) -> tuple[dict | None, np.ndarray]:
    """Геометрия надписи по маскам в выпрямленных координатах и маска того, что сочтено
    буквами.

    Буквы — куски в полосе строки (от линии прописных до хвостов); что торчит выше
    или ниже полосы — рисунок того же цвета: стены плана `cut01_008` между камерами
    и у «Тюрьмы» шли в «буквы» и сдвигали край, базу и высоты (1 октября 2026).
    Прописные — по первым буквам слов, которые в тексте с прописной (верх самой
    высокой буквы у «Office» — выносная «f», а она выше прописных); строчные — только
    у текста со строчными. `base_frac` — доля роста строки над базой по гарнитуре
    (`baseline_frac`), нужна, когда на базе сидит меньше двух букв."""
    src = body if body.sum() >= 12 else (body | rim)
    lab, comps = components(src)
    if not comps:
        return None, np.zeros_like(body)
    areas = [st[4] for _, st, _ in comps]
    med = statistics.median(areas)
    keep_ids = [k for k, st, _ in comps if st[4] >= 0.1 * med]
    r = {}
    if n_lines == 1:
        big = [(k, st, c) for k, st, c in comps if st[4] >= 0.25 * med]
        bottoms = np.array([st[1] + st[3] - 1 for _, st, _ in big], float)
        href0 = float(np.median([st[3] for _, st, _ in big]))
        base = baseline(bottoms, href0)
        on_line = [st[3] for _, st, _ in big if abs(st[1] + st[3] - 1 - base) <= max(2, 0.08 * href0)]
        href = float(np.median(on_line)) if on_line else href0
        lo, hi = base - 1.6 * href, base + 0.6 * href
        keep_ids = [k for k, st, _ in comps
                    if st[4] >= 0.1 * med and st[1] >= lo and st[1] + st[3] - 1 <= hi]
        # У строки с высокой начальной прописной медианная полоса строчных
        # может отрезать F/S/G целиком. Буква на той же базе не становится
        # рисунком из-за высоты: сохраняем первую прописную вместе со строкой.
        # Условие базы то же, что ниже при отборе upright; допуски не меняются.
        initial = next((c for c in text if c.isalpha()), "")
        if initial.isupper():
            capitals = [(k, st) for k, st, _ in big
                        if st[3] >= href
                        and abs(st[1] + st[3] - 1 - base) <= max(2, 0.15 * href)]
            if capitals:
                first, _ = min(capitals, key=lambda item: item[1][0])
                if first not in keep_ids:
                    keep_ids.append(first)
    keep = np.isin(lab, keep_ids) if keep_ids else np.zeros_like(src)
    if keep.sum() < 12:
        return None, keep
    rim_k = rim & grow(keep, 8)
    m = keep | rim_k
    ys, xs = np.nonzero(m)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    bys, bxs = np.nonzero(keep)
    w = x1 - x0 + 1
    r.update({"x0": x0, "x1": x1, "y0": y0, "y1": y1, "ширина": w, "cx": (x0 + x1) / 2,
              "тело": [int(bxs.min()), int(bys.min()), int(bxs.max()), int(bys.max())],
              "cy_чернил": (bys.min() + bys.max()) / 2})
    if n_lines == 1:
        big = [(st, c) for k, st, c in comps if k in keep_ids and st[4] >= 0.25 * med]
        if big:
            bottoms = np.array([st[1] + st[3] - 1 for st, _ in big], float)
            href = float(np.median([st[3] for st, _ in big]))
            base = baseline(bottoms, href)
            tol = max(1.5, 0.06 * href)
            # одиночная буква: людного низа нет, и у «Д» базой становился низ её засечек —
            # прописная 65 px вместо 53 («B» → «Д», cutObj04_045). Когда гарнитура известна,
            # место базы в росте буквы берётся из неё самой. Только для одной буквы одним
            # куском: у строки замеренный рост не обязан совпадать с ростом по гарнитуре
            # (контурные «Камеры» на cut01_008 — хвост «р» в маску не попал)
            if base_frac is not None and len(big) == 1:
                st0 = big[0][0]
                base = st0[1] + base_frac * st0[3] - 1
            upright = [(st, c) for st, c in big if st[1] + st[3] - 1 <= base + max(2, 0.15 * href)]
            top = min(st[1] for st, _ in upright) if upright else min(st[1] for st, _ in big)
            r.update({"база": int(round(base)), "верх": int(top)})
            if letters_case(text) == "mixed" and upright:
                hs = sorted(base - st[1] + 1 for st, _ in upright)
                short = [h for h in hs if h <= 0.8 * hs[-1]]
                if short:
                    r["строчные"] = int(round(statistics.median(short)))
            # слова — по промежуткам шире 0,45 высоты буквы (между буквами у кириллицы
            # бывает 0,3: «Тюрьма» рвалась надвое); прописная с хвостом («Д») — тоже прописная
            # цифры — тоже слова: у даты «April 4» / «4 апреля» (cut03_026, cut03_00a) «4» стояла
            # своей группой, в список слов не попадала, и прописные не считались вовсе —
            # сравнение уходило в строчные, а их доля у гарнитур разная
            words = [w_ for w_ in text.replace("|", " ").split() if any(ch.isalnum() for ch in w_)]
            order = sorted(big, key=lambda sc: sc[0][0])
            groups, cur = [], []
            for st, c in order:
                if cur and st[0] - max(q[0][0] + q[0][2] for q in cur) > 0.45 * href:
                    groups.append(cur)
                    cur = []
                cur.append((st, c))
            if cur:
                groups.append(cur)
            if words and len(groups) == len(words):
                caps = []
                for wd, grp in zip(words, groups):
                    first = next((ch for ch in wd if ch.isalnum()), "")
                    if wd.isupper() or all(ch.isdigit() for ch in wd if ch.isalnum()):
                        # слово из прописных или цифр — все его буквы (цифры ростом с прописные)
                        caps += [base - st[1] + 1 for st, _ in grp]
                    elif first.isupper():
                        # первая буква слова с прописной — первый кусок ростом не ниже 0,8 самого
                        # высокого в слове (выносная «l» выше прописной на 3–5 %), а не просто
                        # первый слева: «Восход» начинался с ёлочки (два куска, верх на 0,63 роста
                        # прописной — выше строчных), и «прописная» выходила 20 вместо 33 px
                        # («Sunrise Hall», cut04_03e/010)
                        hmax = max(base - st[1] + 1 for st, _ in grp)
                        tall = [st for st, _ in grp if base - st[1] + 1 >= 0.8 * hmax]
                        caps.append(base - tall[0][1] + 1)
                if caps:
                    r["прописные"] = int(round(statistics.median(caps)))
            # угол — по буквам, сидящим на базе; наклон медианой попарных наклонов
            pts = [(c[0], st[1] + st[3] - 1) for st, c in big if abs(st[1] + st[3] - 1 - base) <= tol]
            if len(pts) >= 3:
                px = np.array([q[0] for q in pts], float)
                py = np.array([q[1] for q in pts], float)
                if px.max() - px.min() >= 0.4 * w:
                    sl = [(py[j] - py[i]) / (px[j] - px[i]) for i in range(len(px)) for j in range(i + 1, len(px))
                          if abs(px[j] - px[i]) >= 0.2 * w]
                    if sl:
                        r["угол"] = math.degrees(math.atan(float(np.median(sl))))
                        r["угол_точность"] = math.degrees(math.atan(3 / max(1, px.max() - px.min())))
            # форма строки — у строки из прописных: верх букв дугой или прямой
            if upright and letters_case(text) == "caps":
                hmax = max(base - st[1] + 1 for st, _ in upright)
                tall = [(c[0], st[1]) for st, c in upright if base - st[1] + 1 >= 0.85 * hmax]
                if len(tall) >= 4:
                    tx = np.array([(q[0] - r["cx"]) / (w / 2) for q in tall])
                    ty = np.array([q[1] for q in tall], float)
                    if tx.max() - tx.min() >= 1.0:
                        c2 = np.polyfit(tx, ty, 2)[0]
                        r["дуга"] = float(-c2 / max(1, base - top + 1))
    c = (cov * grow(keep, 2)) if cov is not None and cov.sum() >= 12 else keep.astype(np.float32)
    st_ = stroke_of(c)
    if st_:
        r["штрих"] = st_
    if cov_rim is not None and cov_rim.sum() >= 12:
        m_ = (c >= 0.5).astype(np.uint8)
        cs, _ = cv2.findContours(m_, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        per = sum(cv2.arcLength(x, True) for x in cs)
        if per > 0:
            r["кайма"] = float((cov_rim * grow(keep, 8)).sum() / per)
    return r, keep | rim_k


def block(img: np.ndarray, valid: np.ndarray, text: np.ndarray, g: dict, line_h: float) -> dict:
    """Стены вокруг надписи: лучи от середины английской надписи до первого пикселя,
    который не буква и резко отличается от пикселей луча перед ним (мягкий край
    комнаты — перепад 30 уровней, «Prison» на `cut01_008`) или от фона вообще.
    Медиана по 7 лучам — дверной проём сбивает один-два луча, а не все."""
    H, W = text.shape
    x0, x1 = g["x0"], g["x1"]
    top, bot = g["тело"][1], g["тело"][3]
    ring = grow(text, 14) & ~grow(text, 3) & valid
    ry0, ry1 = max(0, top - 20), min(H, bot + 21)
    rx0, rx1 = max(0, x0 - 20), min(W, x1 + 21)
    sub = ring[ry0:ry1, rx0:rx1]
    if sub.sum() < 20:
        return {}
    bg = np.median(img[ry0:ry1, rx0:rx1][sub].astype(np.int16), axis=0)
    passable = grow(text, 3)
    w = x1 - x0 + 1
    lim_x = int(1.2 * w + 4 * line_h + 60)
    lim_y = int(4 * line_h + 80)
    cx, cy = int(round((x0 + x1) / 2)), int(round((top + bot) / 2))

    def ray(x, y, dx, dy, lim):
        hist = []
        for t in range(1, lim):
            xx, yy = x + dx * t, y + dy * t
            if not (0 <= xx < W and 0 <= yy < H) or not valid[yy, xx]:
                return None
            if passable[yy, xx]:
                continue
            p = img[yy, xx].astype(np.int16)
            hit = np.abs(p - bg).max() > TOL["стена"]
            if not hit and len(hist) >= 3:
                ref = np.median(np.array(hist[-4:]), axis=0)
                hit = np.abs(p - ref).max() > TOL["скачок"]
            if hit:
                return xx if dx else yy
            hist.append(p)
        return None

    out = {"фон": [int(v) for v in bg]}
    rows = [int(round(top + k * (bot - top) / 6)) for k in range(7)]
    cols = [int(round(x0 + w * (0.1 + 0.8 * k / 6))) for k in range(7)]
    for key, hits in (("лево", [ray(cx, y, -1, 0, lim_x) for y in rows]),
                      ("право", [ray(cx, y, 1, 0, lim_x) for y in rows]),
                      ("верх", [ray(x, cy, 0, -1, lim_y) for x in cols]),
                      ("низ", [ray(x, cy, 0, 1, lim_y) for x in cols])):
        found = [h for h in hits if h is not None]
        if len(found) >= 4:
            out[key] = float(statistics.median(found))
    # стена нашлась внутри самой английской строки — надпись лежит на линиях рисунка
    # («Cells» поверх стенок камер, `cut01_008`): своего блока у неё нет
    if ("лево" in out and out["лево"] > x0 + 2) or ("право" in out and out["право"] < x1 - 2):
        out.pop("лево", None)
        out.pop("право", None)
        out["на_рисунке"] = True
    if ("верх" in out and out["верх"] > top + 2) or ("низ" in out and out["низ"] < bot - 2):
        out.pop("верх", None)
        out.pop("низ", None)
    return out


def font_path(font_name: str | None) -> Path | None:
    """Файл гарнитуры задания (`seguisb`, `arial@…`, `GOTHIC^12`) в папке шрифтов Windows."""
    if not font_name:
        return None
    base = font_name.split("@")[0].split("^")[0]
    return next((FONT_DIR / f"{base}{e}" for e in (".ttf", ".TTF", ".otf") if (FONT_DIR / f"{base}{e}").exists()), None)


def natural_width(text: str, font_name: str | None, height: float) -> float | None:
    """Ширина строки гарнитурой задания без сжатия при той же высоте букв."""
    path = font_path(font_name)
    if path is None or not text:
        return None
    f = ImageFont.truetype(str(path), 200)
    bb = f.getbbox(text)
    h = bb[3] - bb[1]
    return (bb[2] - bb[0]) * height / h if h > 0 else None


def baseline_frac(text: str, font_name: str | None) -> float | None:
    """Где в росте строки лежит база по самой гарнитуре: доля роста над базой (0…1).
    None — гарнитура неизвестна или строка ниже базы не опускается (хвостов меньше 3 %
    роста): тогда база ищется, как всегда, по людному низу букв."""
    path = font_path(font_name)
    if path is None or not text.strip():
        return None
    f = ImageFont.truetype(str(path), 200)
    bb = f.getbbox(text.replace("|", " "), anchor="ls")
    h = bb[3] - bb[1]
    if h <= 0 or bb[3] < 0.03 * h:
        return None
    return -bb[1] / h


# ---------------------------------------------------------------- сверка

def verdicts(lb: dict, en: dict, ru: dict | None, blk: dict, cfg: dict, decl: dict) -> list[tuple]:
    """Список (пункт, знак, текст). Знак ✗ валит сверку, ~ — посмотреть, ≈ — объявлено."""
    out = []

    def add(key, sign, text):
        if sign == BAD and key in decl:
            out.append((key, DECL, f"{text} — объявлено: {decl[key]}"))
        else:
            out.append((key, sign, text))

    if ru is None:
        add("место", BAD, "русская строка не найдена у английской")
        return out
    n_lines = len(lb.get("text", "").split("|"))
    en_lines = len(lb.get("англ", "").split("|"))
    has_h = "лево" in blk and "право" in blk
    has_v = "верх" in blk and "низ" in blk
    bw = (blk["право"] - blk["лево"]) if has_h else None
    bh = (blk["низ"] - blk["верх"]) if has_v else None
    # английская по центру блока — и с заметными полями: строка во всю ширину карточки
    # (заголовок улики `itm01_02f`, поля 10/9 px) «по центру» и «от левого края» сразу,
    # и выравнивание тогда — по «по» задания
    en_in_block = (has_h and not blk.get("на_рисунке")
                   and abs(en["cx"] - (blk["лево"] + blk["право"]) / 2) <= max(TOL["центр"], TOL["центр_англ"] * bw)
                   and min(en["x0"] - blk["лево"], blk["право"] - en["x1"]) >= 0.12 * bw)
    mode = decl.get("выравнивание")
    if not mode:
        if en_in_block:
            mode = "блок"
        elif "ось" in lb:
            mode = "ось"
        else:
            mode = {"лево": "лево", "право": "право"}.get(lb.get("по", "центр"), "центр")
    # ---- место по горизонтали
    if mode == "блок" and has_h:
        bc = (blk["лево"] + blk["право"]) / 2
        off = ru["cx"] - bc
        lim = max(TOL["центр_блока"], TOL["центр_доля"] * bw)
        # английская сама стоит не точно посередине — русская там же тоже годится
        # («Rosie» на письме `itm03_003`: −2 px у обеих)
        en_off = en["cx"] - bc
        add("центр", OK if abs(off) <= lim or abs(off - en_off) <= TOL["центр_блока"] else BAD,
            f"середина против блока {off:+.0f} px (английская {en['cx'] - bc:+.0f}, блок {bw:.0f} px)")
        lm, rm = ru["x0"] - blk["лево"], blk["право"] - ru["x1"]
        elm, erm = en["x0"] - blk["лево"], blk["право"] - en["x1"]
        need = max(3, 0.12 * en.get("прописные", en["y1"] - en["y0"]))
        if min(lm, rm) < 0:
            add("стены", BAD, f"за стеной блока: поля {lm:.0f} / {rm:.0f} px")
        elif min(lm, rm) < min(need, max(0, min(elm, erm))):
            add("стены", BAD, f"впритык к стене: поля {lm:.0f} / {rm:.0f} px (у английской {elm:.0f} / {erm:.0f})")
        else:
            add("стены", OK, f"поля {lm:.0f} / {rm:.0f} px (у английской {elm:.0f} / {erm:.0f})")
    elif mode in ("блок", "ось"):
        axis = lb.get("ось")
        if axis is None:
            add("центр", WARN, "выравнивание «блок», но стен у надписи не найдено")
        else:
            off = ru["cx"] - axis
            note = ("стены не найдены — середина из задания" if not has_h else
                    "английская не по центру найденного блока — середина из задания")
            add("центр", OK if abs(off) <= TOL["центр"] else WARN, f"середина против «ось» задания {off:+.0f} px")
            out.append(("центр_блока", WARN, note))
    else:
        if mode == "лево":
            d = ru["x0"] - en["x0"]
            add("край", OK if abs(d) <= TOL["край"] else BAD, f"левый край {d:+d} px")
        elif mode == "право":
            d = ru["x1"] - en["x1"]
            add("край", OK if abs(d) <= TOL["край"] else BAD, f"правый край {d:+d} px")
        else:
            d = ru["cx"] - en["cx"]
            add("центр", OK if abs(d) <= TOL["центр"] else BAD, f"середина {d:+.0f} px против английской")
        k = ru["ширина"] / max(1, en["ширина"])
        lo, hi = TOL["ширина"]
        # ширина — только «посмотреть»: короткое русское слово уже английского по праву
        # (растягивать короткую строку по ширине английской пользователь запретил 30.09),
        # а сплющенность и мелкий кегль ловят «сжатие» и «высота»
        add("ширина", OK if lo <= k <= hi else WARN,
            f"ширина {k:.2f} английской ({ru['ширина']} против {en['ширина']} px)")
    if lb.get("только_по"):
        out[:] = [(k, WARN if (s == BAD and k in ("край", "центр", "ширина")) else s, t_) for k, s, t_ in out]
    # ---- налезает на стену с любой стороны, где она найдена («Двор» на стенке двора)
    for side in ("верх", "низ") + (() if mode == "блок" else ("лево", "право")):
        if side in blk:
            over = {"лево": blk.get("лево", 0) - ru["x0"], "право": ru["x1"] - blk.get("право", 0),
                    "верх": blk.get("верх", 0) - ru["y0"], "низ": ru["y1"] - blk.get("низ", 0)}[side]
            if over > 1:
                add("стены", BAD, f"налезает на стену ({side}) на {over:.0f} px")
    # ---- по вертикали
    if mode in ("блок", "ось") and has_v and abs(en["cy_чернил"] - (blk["верх"] + blk["низ"]) / 2) <= max(TOL["центр"], TOL["центр_англ"] * bh):
        bc = (blk["верх"] + blk["низ"]) / 2
        off = ru["cy_чернил"] - bc
        add("по_вертикали", OK if abs(off) <= max(TOL["центр"], 0.06 * bh) else BAD,
            f"по вертикали против блока {off:+.0f} px (английская {en['cy_чернил'] - bc:+.0f}, блок {bh:.0f} px)")
    elif mode in ("блок", "ось"):
        d = ru["cy_чернил"] - en["cy_чернил"]
        big = max(8, 0.35 * en.get("прописные", en["y1"] - en["y0"]))
        add("по_вертикали", OK if abs(d) <= 2 * TOL["база"] else (BAD if abs(d) > big else WARN),
            f"середина по вертикали {d:+.0f} px против английской")
    elif n_lines == 1 and en_lines == 1 and "база" in en and "база" in ru:
        d = ru["база"] - en["база"]
        add("база", OK if abs(d) <= TOL["база"] else BAD, f"базовая линия {d:+d} px")
    else:
        d = ru["cy_чернил"] - en["cy_чернил"]
        add("база", OK if abs(d) <= 2 * TOL["база"] else WARN, f"середина по вертикали {d:+.0f} px")
    # ---- размер
    size_k = None
    key = ("прописные" if "прописные" in en and "прописные" in ru else
           "строчные" if "строчные" in en and "строчные" in ru else None)
    if n_lines == 1 and en_lines == 1 and key:
        ce, cr = letters_case(lb.get("англ", "")), letters_case(lb.get("text", ""))
        # прописные — как их выравнивает набор («прописные как у англичан»); строчные —
        # только если прописных нет ни у одной: у гарнитур разная доля строчных
        size_k = ru[key] / max(1, en[key])
        sign = OK if abs(ru[key] - en[key]) <= max(TOL["высота"] * en[key], 1.5) else BAD
        if sign == BAD and (key == "строчные" and ce != cr or 0.7 <= size_k < 1):
            sign = WARN       # мельче, а не уже — решение 30.09; регистр разный — сравнение грубое
        add("высота", sign, f"{key} {ru[key]} против {en[key]} px ({size_k:.2f})")
    elif n_lines > 1 or en_lines > 1:
        size_k = ((ru["y1"] - ru["y0"] + 1) / n_lines) / max(1, (en["y1"] - en["y0"] + 1) / en_lines)
        if abs(size_k - 1) > 0.15:
            out.append(("высота", WARN, f"высота строки {size_k:.2f} английской"))
    # ---- сжатие
    font = lb.get("шрифт", cfg.get("font"))
    squeeze_est = None
    clipped = bool(lb.get("только_по"))
    if clipped:
        out.append(("сжатие", WARN, "строка уходит под предмет (`только_по`) — сжатие и край по видимой части не меряются"))
    if n_lines == 1 and not lb.get("верх_по") and not clipped:
        t = ru["тело"]
        letters = sum(ch.isalpha() for ch in lb.get("text", ""))
        # замер сжатия у одной-двух букв и у мелкого текста (ниже 16 px) — шум
        nat = (natural_width(lb.get("text", ""), font, t[3] - t[1] + 1)
               if letters >= 3 and t[3] - t[1] + 1 >= 16 else None)
        if nat:
            s = (t[2] - t[0] + 1) / nat
            squeeze_est = s
            if TOL["сжатие"] <= s <= TOL["растяжка"]:
                sign = OK
            elif TOL["сжатие"] - 0.05 <= s <= TOL["растяжка"] + 0.05:
                sign = WARN       # замер сжатия врёт на ±0,03
            else:
                sign = BAD
            add("сжатие", sign, f"сжатие ≈{s:.2f} (гарнитура {font})")
    # ---- угол и форма
    a_tol = max(TOL["угол"], en.get("угол_точность", 0), ru.get("угол_точность", 0))
    if "угол" in en and abs(en["угол"]) > a_tol:
        add("угол_задания", BAD, f"английская строка после выпрямления наклонена ещё на {en['угол']:+.1f}° — «наклон» в задании неверен")
    if "угол" in en and "угол" in ru:
        d = ru["угол"] - en["угол"]
        add("угол", OK if abs(d) <= a_tol else BAD, f"наклон против английской {d:+.1f}°")
    if "дуга" in en and abs(en["дуга"]) >= TOL["дуга"]:
        rd = ru.get("дуга", 0.0)
        ok = rd * en["дуга"] > 0 and abs(rd - en["дуга"]) <= 0.5 * abs(en["дуга"])
        add("форма", OK if ok else BAD, f"верх строки дугой: {rd:+.2f} против {en['дуга']:+.2f} у английской")
    # ---- штрих, кайма, цвет
    if "штрих" in en and "штрих" in ru:
        # штрих растёт с кеглем; сжатие утончает вертикальные штрихи, а горизонтальные
        # нет — средний штрих тоньше примерно на половину сжатия
        scale = size_k if size_k else 1.0
        if squeeze_est:
            scale *= (1 + min(1.0, squeeze_est)) / 2
        k = ru["штрих"] / max(0.1, en["штрих"] * scale)
        diff = ru["штрих"] - en["штрих"] * scale
        ok = (1 - TOL["штрих"] <= k <= 1 + 1.25 * TOL["штрих"]) or abs(diff) <= 0.5
        add("штрих", OK if ok else BAD,
            f"штрих {ru['штрих']:.1f} против {en['штрих']:.1f} px"
            + (f" (с поправкой на кегль и сжатие {k:.2f})" if scale < 1 else f" ({k:.2f})"))
    if "кайма" in en and en["кайма"] >= 1.0:
        if "кайма" not in ru or ru["кайма"] < 0.5:
            add("кайма", BAD, f"у английской кайма {en['кайма']:.1f} px, у русской нет")
        else:
            d = ru["кайма"] - en["кайма"]
            add("кайма", OK if abs(d) <= TOL["кайма"] else BAD, f"кайма {ru['кайма']:.1f} против {en['кайма']:.1f} px")
    return out


def edge_map(img: np.ndarray) -> np.ndarray:
    f = cv2.GaussianBlur(img, (3, 3), 0).astype(np.float32)
    g = np.zeros(img.shape[:2], np.float32)
    for c in range(3):
        gx = cv2.Sobel(f[:, :, c], cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(f[:, :, c], cv2.CV_32F, 0, 1, ksize=3)
        g = np.maximum(g, np.sqrt(gx * gx + gy * gy) / 4)
    return g


def clean(m: np.ndarray, min_px: int) -> np.ndarray:
    lab, comps = components(m, min_px)
    out = np.zeros(m.shape, bool)
    for k, _, _ in comps:
        out |= lab == k
    return out


# ---------------------------------------------------------------- лист

def font(size: int, names=("arial.ttf", "segoeui.ttf")):
    for f in names:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def overlay(en_img, en_m, ru_m, box, blk, en, ru) -> Image.Image:
    x0, y0, x1, y1 = box
    g = cv2.cvtColor(en_img, cv2.COLOR_RGB2GRAY).astype(np.float32)
    base = np.stack([g * 0.3 + 170] * 3, axis=-1)
    base[en_m] = (225, 40, 40)
    base[ru_m] = (40, 80, 230)
    base[en_m & ru_m] = (150, 40, 170)
    im = Image.fromarray(base.clip(0, 255).astype(np.uint8)[y0:y1, x0:x1])
    d = ImageDraw.Draw(im)
    for key in ("лево", "право"):
        if key in blk:
            x = blk[key] - x0
            d.line([(x, 0), (x, im.height)], fill=(0, 170, 0), width=2)
    for key in ("верх", "низ"):
        if key in blk:
            y = blk[key] - y0
            d.line([(0, y), (im.width, y)], fill=(0, 170, 0), width=2)
    for m, col in ((en, (225, 40, 40)), (ru, (40, 80, 230))):
        if m and "база" in m:
            y = m["база"] - y0
            for x in range(0, im.width, 12):
                d.line([(x, y), (x + 6, y)], fill=col, width=1)
    return im


def sheet(name: str, ru_img, rows: list, lost, added, polys, out_dir: Path) -> Path:
    W = 1800
    k = W / ru_img.shape[1]
    top = ru_img.astype(np.float32) * 0.55 + 100
    top[lost] = (255, 220, 0)
    top[added] = (0, 210, 255)
    top_im = Image.fromarray(top.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(top_im)
    for i, poly in enumerate(polys, 1):
        d.polygon([tuple(p) for p in poly], outline=(0, 160, 0))
        d.text(tuple(poly[0] + np.array([2, -26])), str(i), fill=(0, 120, 0), font=font(24))
    top_im = top_im.resize((W, max(1, round(top_im.height * k))), Image.LANCZOS)
    f, fs, sym = font(26), font(19), font(19, ("seguisym.ttf", "segoeui.ttf"))
    pieces = []
    for title, lines, a, b, c in rows:
        kk = min(2.0, (W / 3 - 20) / max(1, a.width))
        size = (max(1, round(a.width * kk)), max(1, round(a.height * kk)))
        pieces.append((title, lines, a.resize(size, Image.NEAREST),
                       b.resize(size, Image.NEAREST), c.resize(size, Image.NEAREST)))
    H = 50 + top_im.height + 30 + sum(p[2].height + 40 + 24 * len(p[1]) + 20 for p in pieces)
    out = Image.new("RGB", (W + 20, H), (38, 38, 38))
    d = ImageDraw.Draw(out)
    d.text((10, 10), f"{name}: сверка с английской — жёлтое: линии рисунка пропали, голубое: новые края",
           fill="white", font=f)
    out.paste(top_im, (10, 50))
    y = 50 + top_im.height + 30
    for title, lines, a, b, c in pieces:
        d.text((10, y), title + "   (английская | русская | наложение: красное — англ., синее — рус., зелёное — стены)",
               fill="white", font=fs)
        y += 30
        out.paste(a, (10, y))
        out.paste(b, (20 + a.width, y))
        out.paste(c, (30 + 2 * a.width, y))
        y += a.height + 8
        for ln in lines:
            col = (255, 110, 110) if ln.startswith(BAD) else (255, 220, 120) if ln.startswith(WARN) else (200, 230, 200)
            # ✓ и ✗ в Arial нет — значок гарнитурой символов, текст Arial
            d.text((14, y), ln[:1], fill=col, font=sym)
            d.text((40, y), ln[1:].lstrip(), fill=col, font=fs)
            y += 24
        y += 16
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}_сверка.png"
    out.save(path)
    return path


# ---------------------------------------------------------------- главное

def load_rgb(p: Path) -> np.ndarray:
    return np.asarray(Image.open(p).convert("RGB"))


def passport_file(case: str) -> Path:
    return RU_DIR / case / "passport.json"


def declared(case: str, name: str) -> dict:
    p = passport_file(case)
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    return d.get(name, {}).get("задано", {})


def fresh_ink(R: np.ndarray, ink_path: Path, cfg: dict, labels: list[dict]) -> np.ndarray | None:
    """Маска набора годится, если под её ядром в картинке цвет букв из задания."""
    if not ink_path.exists():
        return None
    ink = np.asarray(Image.open(ink_path).convert("L")) > 0
    if ink.shape != R.shape[:2]:
        return None
    core = cv2.erode(ink.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    hit = np.zeros(core.shape, bool)
    for lb in labels:
        col = colours(cfg, lb)
        hit |= near(R, col["ru_body"], 70)
        if col["ru_rim"]:
            hit |= near(R, col["ru_rim"], 70)
    share = (hit & core).sum() / max(1, core.sum())
    if core.sum() < 50 or share < 0.85:
        print(f"  {ink_path.name}: не совпадает с картинкой ({share:.0%}) — русские буквы по цвету")
        return None
    return ink


def run(name: str, case: str | None, ru_path: Path | None, ink_path: Path | None,
        only_measure: bool, save: bool, out_dir: Path = CHECKS, no_ink: bool = False) -> int:
    case, cfg, labels, src = find_task(name, case)
    en_path = find_png(EN_DIR, name)
    if not en_path:
        sys.exit(f"{name}: нет английского оригинала в {EN_DIR}")
    E = load_rgb(en_path)
    labels = [lb for lb in labels if lb.get("box") and lb.get("англ")]
    decl_all = declared(case, name)

    R = ink = None
    if not only_measure:
        ru_path = ru_path or RU_DIR / case / f"{name}.png"
        if not ru_path.exists():
            sys.exit(f"{name}: нет русской картинки {ru_path}")
        R = load_rgb(ru_path)
        if R.shape != E.shape:
            sys.exit(f"{name}: размеры разные {R.shape} против {E.shape}")
        if ink_path is None:
            ink_path = ru_path.with_name(f"{name}_ink.png")
            if not ink_path.exists() and ru_path.name == f"{name}.png":
                ink_path = RU_DIR / case / f"{name}_ink.png"
        ink = None if no_ink else fresh_ink(R, ink_path, cfg, labels)

    changed = (np.abs(R.astype(np.int16) - E.astype(np.int16)).max(axis=2) > 30) if R is not None else None
    # куски чужого языка («основа» картинки): там сверять с английским нечего
    foreign = np.zeros(E.shape[:2], bool)
    for b_ in cfg.get("основа", []) or []:
        if isinstance(b_, dict) and b_.get("рамка"):
            fx0, fy0, fx1, fy1 = b_["рамка"]
            foreign[max(0, fy0):fy1, max(0, fx0):fx1] = True
    report, rows, polys = [], [], []
    en_text_all = np.zeros(E.shape[:2], bool)
    ru_text_all = np.zeros(E.shape[:2], bool)
    measured = {}
    slots = {}          # надпись → (строка листа, запись отчёта)
    unsure = set()      # надписи с ненадёжным замером: английские буквы не все в маске
    bad = 0
    for i, lb in enumerate(labels):
        col = colours(cfg, lb)
        n_lines = len(lb.get("text", "").split("|"))
        en_lines = len(lb["англ"].split("|"))
        x0, y0, x1, y1 = lb["box"]
        line_h = (y1 - y0) / max(1, en_lines)
        polys.append(box_poly(lb))
        title = f"{i + 1}. «{lb['англ'].replace('|', ' / ')}» → «{lb.get('text', '').replace('|', ' / ')}»"
        notes = []
        if foreign[poly_mask(E.shape, lb, 0)].mean() > 0.5 if poly_mask(E.shape, lb, 0).any() else False:
            print(f"{title}\n     ~ в куске чужого языка («основа») — с английским не сверяется, только глазом")
            report.append({"англ": lb["англ"], "пропуск": "основа"})
            continue
        # ---- английская
        if col["по_кайме"]:
            # задание назвало только кайму («Viewing Platform», «Clothes Box»): английские
            # буквы — краска «fill» внутри того, что кайма замыкает; линии крыши той же
            # краски снаружи каймы в буквы не идут
            rim0 = pick(strip_lines(near(E, col["en_rim"], col["tol"]), line_h), labels, i, 4, line_h)
            flood = rim0.astype(np.uint8) * 255
            cv2.floodFill(flood, np.zeros((flood.shape[0] + 2, flood.shape[1] + 2), np.uint8), (0, 0), 255)
            inner = (flood == 0) & poly_mask(E.shape, lb, 4)
            eb = near(E, col["en_body"], col["tol"]) & inner
            er = rim0 & grow(eb, col["rim_w"] + 2) & ~eb
        else:
            eb, er = text_masks(E, col["en_body"], col["en_rim"], col["rim_w"], col["tol"])
        eb = pick(strip_lines(eb, line_h), labels, i, 4, line_h)
        outline_only = False
        if eb.sum() < 30 and col["en_rim"] is not None:
            # буквы — одна кайма с прозрачной серединой («Cells» на `cut01_008`):
            # текст — кайма вместе с тем, что она замыкает
            rim0 = pick(strip_lines(near(E, col["en_rim"], col["tol"]), line_h), labels, i, 4, line_h)
            flood = rim0.astype(np.uint8) * 255
            cv2.floodFill(flood, np.zeros((flood.shape[0] + 2, flood.shape[1] + 2), np.uint8), (0, 0), 255)
            inner = (flood == 0) & poly_mask(E.shape, lb, 4)
            if inner.sum() > 30:
                eb, er = inner, rim0
                outline_only = True
                notes.append((WARN, "английские буквы контурные (кайма без заливки) — штрих и кайма не сравниваются"))
        if eb.sum() < 30 and not outline_only:
            bg0 = ring_colour(E, lb, eb)
            guess = guess_colour(E, lb, bg0, col["en_rim"])
            if guess:
                eb2, er = text_masks(E, guess, col["en_rim"], col["rim_w"], 45)
                eb = pick(strip_lines(eb2, line_h), labels, i, 4, line_h)
                notes.append((WARN, f"цвет английских букв не тот, что в задании: {tuple(guess)} против {tuple(col['en_body'])}"))
                col = dict(col, en_body=guess)
        er = er & grow(eb, col["rim_w"] + 2)
        bg_en = ring_colour(E, lb, eb | er)
        around = grow(eb | er, 2)
        ec = coverage(E, col["en_body"], col["en_rim"] or bg_en, around)
        ecr = (coverage(E, col["en_rim"], bg_en, around & ~(ec >= 0.5))
               if col["en_rim"] and not outline_only else None)
        Es, valid = rot_rgb(E, lb)
        sb, sr = rot_mask(eb, lb), rot_mask(er, lb)
        if lb.get("наклон"):
            sb = strip_lines(sb, line_h)          # линейки газеты идут вдоль строки
        if outline_only:
            # контурные буквы: мерить кайму вместе с тем, что она замыкает, — и у русской так же
            en, en_keep = measure(sb | sr, np.zeros_like(sb), None, None, en_lines, lb["англ"])
        else:
            en, en_keep = measure(sb, sr, rot_cov(ec, lb), rot_cov(ecr, lb) if ecr is not None else None,
                                  en_lines, lb["англ"])
        sb, sr = sb & en_keep, sr & en_keep
        en_text_all |= rot_mask(en_keep, lb, back=True)
        if en is not None and outline_only:
            en.pop("штрих", None)
            en.pop("кайма", None)
        if en is None:
            # в задании надпись есть, а на картинке английской нет (частичный план
            # `cut01_037` с заданием целого) — пропуск, но на виду
            report.append({"англ": lb["англ"], "пропуск": "английская не найдена"})
            print(f"{title}\n     ~ английские буквы не найдены ни цветом задания, ни по самим буквам — "
                  f"надписи нет на этой картинке? сверить глазом")
            continue
        blk = block(Es, valid, sb | sr, en, line_h)
        measured[lb["англ"]] = {"рамка": [en["x0"], en["y0"], en["x1"], en["y1"]],
                                **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in en.items()
                                   if k in ("база", "прописные", "строчные", "угол", "дуга", "штрих", "кайма")},
                                "цвет_букв": col["en_body"], "кайма_цвет": col["en_rim"],
                                "блок": blk, "наклон_задания": lb.get("наклон", 0)}
        if only_measure:
            continue
        # ---- русская
        if ink is not None:
            rb_all = ink & near(R, col["ru_body"], col["tol"])
            rr_all = ink & ~rb_all
        else:
            # без маски набора: буква — пиксель цвета букв, который изменился против
            # английской картинки или был английской буквой; кайма кружка и стены
            # не меняются и в «буквы» не идут
            rb_all, rr_all = text_masks(R, col["ru_body"], col["ru_rim"], col["rim_w"], col["tol"])
            fresh = changed | grow(eb | er, 1)
            rb_all, rr_all = rb_all & fresh, rr_all & fresh
        window = max(0.6 * line_h, 0.25 * (x1 - x0)) + 20
        rb = pick(strip_lines(rb_all, line_h), labels, i, window, line_h)
        rr = rr_all & grow(rb, col["rim_w"] + 2)
        bg_ru = ring_colour(R, lb, rb | rr)
        around_r = grow(rb | rr, 2)
        rc = coverage(R, col["ru_body"], col["ru_rim"] or bg_ru, around_r)
        rcr = coverage(R, col["ru_rim"], bg_ru, around_r & ~(rc >= 0.5)) if col["ru_rim"] else None
        rsb, rsr = rot_mask(rb, lb), rot_mask(rr, lb)
        if lb.get("наклон"):
            rsb = strip_lines(rsb, line_h)
        # база одиночной буквы — по гарнитуре набора (у английской гарнитура неизвестна,
        # и её база — по людному низу, как прежде)
        ru_text = lb.get("text", "")
        frac_ru = (baseline_frac(ru_text, lb.get("шрифт", cfg.get("font")))
                   if n_lines == 1 and sum(ch.isalnum() for ch in ru_text) == 1 else None)
        if outline_only:
            ru, ru_keep = measure(rsb | rsr, np.zeros_like(rsb), None, None, n_lines, lb.get("text", ""), frac_ru)
        else:
            ru, ru_keep = measure(rsb, rsr, rot_cov(rc, lb), rot_cov(rcr, lb) if rcr is not None else None,
                                  n_lines, lb.get("text", ""), frac_ru)
        rsb, rsr = rsb & ru_keep, rsr & ru_keep
        ru_text_all |= rot_mask(ru_keep, lb, back=True)
        decl = dict(decl_all.get(lb["англ"], {}))
        decl.update(decl.pop("исключения", {}) or {})
        vs = verdicts(lb, en, ru, blk, cfg, decl) + [("цвет", s, t) for s, t in notes]
        # замер ненадёжен: английская нашлась обрывками (буквы на сетке с обводкой —
        # шахматы `cut01_027`: цвет задания ловит обводку и линии доски) или русская
        # и английская несопоставимы по размеру — тогда сверка не судит, а зовёт глаз
        why = []
        if en_lines == 1 and (en["y1"] - en["y0"] + 1) < 0.35 * (y1 - y0):
            why.append(f"английская найдена обрывками ({en['y1'] - en['y0'] + 1} px при рамке {y1 - y0})")
        # мелкий текст: при буквах ниже 12 px (визитка `itm01_017`, строчные 4–5 px)
        # пиксель — это 10–20 % штриха и высоты, замер штриха, сжатия и стен — шум
        h_en = en.get("прописные") or (en["y1"] - en["y0"] + 1)
        small = h_en < 12 or en.get("строчные", 99) <= 8
        if small:
            why.append(f"мелкий текст ({en.get('строчные') or h_en} px)")
        if ru is not None:
            hk = (ru["y1"] - ru["y0"] + 1) / max(1, en["y1"] - en["y0"] + 1)
            if not 0.55 <= hk <= 1.8:
                why.append(f"высота русской {hk:.2f} английской")
        if why:
            unsure.add(i)
            # у мелкого текста сжатие и наклон меряются по всей строке и держатся:
            # сплющенный в 0,55 заголовок улики `itm01_02f` (строчные 6 px) пользователь
            # забраковал 28.09 — их не глушить
            keep = ("сжатие", "угол") if small and len(why) == 1 else ()
            vs = [(k, WARN if s == BAD and k not in keep else s, t) for k, s, t in vs]
            vs.insert(0, ("замер", WARN, "замер ненадёжен: " + "; ".join(why) + " — сверить глазом"))
        if ru is not None and rb.any() and eb.any():
            ke = cv2.erode(eb.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            kr = cv2.erode(rb.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            ce = np.median(E[ke], axis=0) if ke.sum() > 10 else None
            cr = np.median(R[kr], axis=0) if kr.sum() > 10 else None
            if ce is not None and cr is not None:
                dc = int(np.abs(ce - cr).max())
                vs.append(("цвет_букв", OK if dc <= TOL["цвет_букв"] else WARN,
                           f"цвет букв {tuple(int(v) for v in cr)} против английских {tuple(int(v) for v in ce)}"))
        # остатки английского — только по маске набора
        if ink is not None:
            core_en = cv2.erode(eb.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            same = near(R, col["en_body"], col["tol"])
            ink_zone = grow(ink, 2)
            if col["по_кайме"]:
                # буквы цвета рисунка: остаток английской буквы — тёмное с собственной белой
                # каймой рядом, а не балка крыши в просвете между русскими словами (49 px
                # на cut03_006); под русской каймой остатка не видно
                same &= grow(near(R, col["en_rim"], col["tol"]), col["rim_w"] + 1)
                ink_zone = grow(ink, col["rim_w"] + 2)
            zone = poly_mask(E.shape, lb, 0.35 * line_h)
            lab_, comps_ = components(same, 1)
            outside = np.zeros(same.shape, bool)
            for k_, st_, _ in comps_:
                piece = lab_ == k_
                if (piece & ~zone).any():
                    outside |= piece            # тянется за рамку надписи — рисунок, не буква
            left = clean(core_en & same & ~outside & ~ink_zone, 6)
            n_left = int(left.sum())
            vs.append(("остатки", OK if n_left <= TOL["остатки_px"] else BAD, f"остатки английских букв {n_left} px"))
        bad += [s for _, s, _ in vs].count(BAD)
        # ---- кадр для листа
        pad = int(max(30, 0.7 * line_h))
        bx0 = max(0, min(x0, ru["x0"] if ru else x0) - pad)
        bx1 = min(E.shape[1], max(x1, ru["x1"] if ru else x1) + pad)
        by0 = max(0, min(y0, ru["y0"] if ru else y0) - pad)
        by1 = min(E.shape[0], max(y1, ru["y1"] if ru else y1) + pad)
        Rs, _ = rot_rgb(R, lb)
        crop = (bx0, by0, bx1, by1)
        a = Image.fromarray(Es[by0:by1, bx0:bx1])
        b = Image.fromarray(Rs[by0:by1, bx0:bx1])
        c = overlay(Es, sb | sr, rsb | rsr, crop, blk, en, ru)
        lines = [f"{s} {t}" for _, s, t in vs]
        slots[i] = (len(rows), len(report))
        rows.append((title, lines, a, b, c))
        report.append({"англ": lb["англ"], "текст": lb.get("text"), "английская": en, "русская": ru,
                       "блок": blk, "пункты": [{"что": k, "знак": s, "как": t} for k, s, t in vs]})
        print(title)
        for ln in lines:
            print(f"     {ln}")

    if save or only_measure:
        p = passport_file(case)
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        entry = d.setdefault(name, {})
        entry["замер"] = measured
        entry.setdefault("задано", {})
        p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"паспорт — {p.relative_to(ROOT)} («{name}»: замер {len(measured)} надписей)")
    if only_measure:
        for eng, m in measured.items():
            walls = ", ".join(f"{k} {v:.0f}" for k, v in m["блок"].items() if k != "фон") or "стен нет"
            print(f"«{eng}»: рамка {m['рамка']}, база {m.get('база')}, прописные {m.get('прописные')}, "
                  f"строчные {m.get('строчные')}, остаток наклона {m.get('угол', 0):+.1f}°, "
                  f"дуга {m.get('дуга', 0):+.2f}, штрих {m.get('штрих', 0):.1f}, "
                  f"кайма {m.get('кайма', 0):.1f}, цвет {tuple(m['цвет_букв'])}; блок: {walls}")
        return 0

    # ---- линии рисунка у надписей
    region = np.zeros(E.shape[:2], bool)
    zones = []
    for lb in labels:
        x0, y0, x1, y1 = lb["box"]
        z = poly_mask(E.shape, lb, max(16, 0.6 * (y1 - y0)))
        zones.append(z)
        region |= z
    gE, gR = edge_map(E), edge_map(R)
    # контур английских букв с толстой каймой (шахматы `cut01_027`, кайма 6 px) — не линия
    # рисунка: зона исключения шире на кайму
    rim_max = max([colours(cfg, lb)["rim_w"] for lb in labels] or [0])
    excl = grow(en_text_all, 4 + rim_max) | grow(ru_text_all, 4 + rim_max) | foreign
    lost = clean(region & ~excl & (gE >= TOL["край_сильный"]) & (gR <= TOL["край_слабый"]), TOL["линия_px"])
    added = clean(region & ~excl & (gR >= TOL["край_сильный"]) & (gE <= TOL["край_слабый"]), TOL["линия_px"])
    for i, (ri, rj) in slots.items():
        nl, na = int((lost & zones[i]).sum()), int((added & zones[i]).sum())
        sign_l = OK if nl <= TOL["пропало_px"] else (WARN if i in unsure else BAD)
        d_ = decl_all.get(labels[i]["англ"], {}).get("исключения", {}) or {}
        why_l = f" — объявлено: {d_['линии']}" if sign_l == BAD and "линии" in d_ else ""
        if why_l:
            sign_l = DECL
        sign_a = OK if na <= TOL["новое_px"] else WARN
        rows[ri][1].append(f"{sign_l} линии рисунка: пропало {nl} px{why_l}")
        rows[ri][1].append(f"{sign_a} новые края у надписи: {na} px")
        bad += sign_l == BAD
        report[rj]["пункты"] += [{"что": "линии", "знак": sign_l, "как": f"пропало {nl} px"},
                                 {"что": "новые_края", "знак": sign_a, "как": f"{na} px"}]
        print(f"{i + 1}. линии рисунка: {sign_l} пропало {nl} px, {sign_a} новых краёв {na} px")

    path = sheet(name, R, rows, lost, added, polys, out_dir)
    jpath = out_dir / f"{name}_сверка.json"
    jpath.write_text(json.dumps({"картинка": name, "задание": f"{case}/{src}", "русская": str(ru_path),
                                 "маска_букв": str(ink_path) if ink is not None else None,
                                 "надписи": report}, ensure_ascii=False, indent=1, default=float),
                     encoding="utf-8")
    n_warn = sum(ln.startswith(WARN) for _, lines, *_ in rows for ln in lines)
    print(f"\n{name}: {'✗ ' + str(bad) if bad else '✓ сверка чистая'}"
          f"{f', ~ {n_warn} посмотреть' if n_warn else ''}; лист {path}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="+", help="имена картинок, например cut01_008")
    ap.add_argument("--case", help="дело (case1…case5), если имя есть в нескольких")
    ap.add_argument("--ru", type=Path, help="русская картинка (по умолчанию work/graphics_ru/<дело>/<имя>.png)")
    ap.add_argument("--ink", type=Path, help="маска русских букв (по умолчанию <русская>_ink.png)")
    ap.add_argument("--measure", action="store_true", help="только паспорт английской — и записать в passport.json")
    ap.add_argument("--save", action="store_true", help="записать замер английской в passport.json и при сверке")
    ap.add_argument("--out", type=Path, default=CHECKS, help="куда писать лист и отчёт (по умолчанию checks)")
    ap.add_argument("--no-ink", action="store_true", help="русские буквы только по цвету, без маски набора")
    args = ap.parse_args()
    if args.ru and len(args.names) > 1:
        sys.exit("--ru — для одной картинки")
    code = 0
    for n in args.names:
        code |= run(n, args.case, args.ru, args.ink, args.measure, args.save, args.out, args.no_ink)
    return code


if __name__ == "__main__":
    sys.exit(main())
