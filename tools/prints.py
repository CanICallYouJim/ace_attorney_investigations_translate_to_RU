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
    return ImageFont.truetype(str(FONT_DIR / f"{name}.ttf"), size)


def render(text: str, font_name: str, size: int, sw: int, squeeze: float):
    """Строка маской, точка опоры в ней (левый край базовой линии) и рамка чернил от опоры."""
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
        votes = [sum(1 for x, y in comp if x0 <= x < x1 and y0 <= y < y1)
                 for x0, y0, x1, y1 in boxes]
        best = max(range(len(votes)), key=lambda k: votes[k])
        if 2 * votes[best] <= len(comp):
            continue                   # кусок больше снаружи рамки, чем внутри, — не эта надпись
        for p in comp:
            ops[best][p] = 255
    return out


def compose(name: str, cfg: dict, case: str):
    """Картинка с русскими печатными надписями, маска букв и отчёт."""
    raw = Image.open(EN / case / f"{name}.png")
    alpha = raw.getchannel("A") if raw.mode == "RGBA" else None
    E = raw.convert("RGB")
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
        bb = mask.getbbox()
        if bb is None:
            raise ValueError(f"{name}: у надписи «{lb['text']}» английских чернил в рамке не нашлось")
        gone = ImageChops.lighter(gone, mask)
        jobs.append((lb, mask, bb))

    out = Image.composite(C, E, gone.filter(ImageFilter.MaxFilter(2 * GROW + 1)))
    ink = Image.new("L", E.size, 0)
    # Область та же, какой её берёт судья (`check_pictures`: рамка русских чернил
    # на всей картинке), а не «рамка английских ±40»: от запаса поле надписи
    # замыкается шире, набор считал место свободным, а судья — занятым рисунком.
    area = (min(b[0] for _, _, b in jobs), min(b[1] for _, _, b in jobs),
            max(b[2] for _, _, b in jobs), max(b[3] for _, _, b in jobs))
    forbidden = cp.untouchable(C, m["paper"].convert("RGB"), eng, area)

    def geometry(lb: dict, mask: Image.Image, bb):
        """Что снимается с английской надписи: гарнитура, строки, кегль, сжатие, контур."""
        font_name = lb.get("шрифт", cfg.get("font", "segoeuib"))
        lines_en = lb["англ"].split("|")
        lines_ru = lb["text"].split("|")
        want_h = (bb[3] - bb[1] - LINE_GAP * (len(lines_en) - 1)) / len(lines_en)
        want_w = bb[2] - bb[0]
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
        en_stroke = cp.stroke(mask)
        sw = 0
        if cp.stroke(solid(render(lines_en[0], font_name, size, 0, squeeze)[0])) < THIN * en_stroke:
            sw = 1
            size = pick_size(lines_en[0], font_name, sw, squeeze, want_h)
        return font_name, lines_en, lines_ru, want_h, want_w, size, squeeze, sw, en_stroke

    # Кант подбирается **замером** и один на всю картинку: у англичан он один,
    # а русская строка сжата по ширине — её штрихи тоньше, и на «Лифт» и на
    # «Комната Густо» одна и та же толщина даёт разный штрих. Считаем, какой кант
    # нужен каждой надписи, чтобы догнать английский штрих, и берём медиану:
    # разнобой «1 и 4» на соседних комнатах виден глазом, а число из задания —
    # не замер (правило от 20 сентября 2026).
    edge_w = 0
    if cfg.get("stroke"):
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
        measured = statistics.median(seen) if seen else 0.0
        report.append(f"  кант снят с английских букв: "
                      + ", ".join(f"{v:.1f}" for v in seen)
                      + f" -> {edge_w} px на всю картинку")

    for lb, mask, bb in jobs:
        (font_name, lines_en, lines_ru, want_h, want_w,
         size, squeeze, sw, en_stroke) = geometry(lb, mask, bb)
        ru_stroke = cp.stroke(solid(render(lines_ru[0], font_name, size,
                                           sw + edge_w, squeeze)[0]))

        # Точка опоры — из замера: тот же английский текст нашей гарнитурой ложится
        # в рамку английских чернил, и его базовая линия становится нашей.
        _, _, en_bb = render(lines_en[0], font_name, size, sw, squeeze)
        bx, by = bb[0] - en_bb[0], bb[1] - en_bb[1]
        step = want_h + LINE_GAP
        colour = tuple(lb.get("fill", cfg["fill"]))
        # У английских надписей этого пласта буквы белые, а вокруг тёмный кант:
        # без него набор читается бледно, а замер штриха сравнивает наше «только
        # буквы» с английским «буквы вместе с кантом» и всегда кричит «тоньше».
        edge = tuple(cfg["stroke"]) if cfg.get("stroke") else None
        where = lb.get("по", "центр")
        pieces = []
        mine = Image.new("L", E.size, 0)
        for j, text in enumerate(lines_ru):
            ru_im, (ox, oy), ru_bb = render(text, font_name, size, sw, squeeze)
            dx = 0.0
            if where == "центр":
                dx = ((en_bb[2] - en_bb[0]) - (ru_bb[2] - ru_bb[0])) / 2
            elif where == "право":
                dx = (en_bb[2] - en_bb[0]) - (ru_bb[2] - ru_bb[0])
            at = (round(bx + dx - ox), round(by + j * step - oy))
            wide = render(text, font_name, size, sw + edge_w, squeeze)[0] if edge_w else None
            pieces.append((ru_im, wide, at))
            mine.paste(255, at, solid(wide if wide is not None else ru_im))
        # Русское слово короче или длиннее английского, и буква попадает туда, где у англичан
        # был пробел, — на точку или линию плана. Тогда надпись сдвигается на пару пикселей:
        # глазу это незаметно, а на рисунок она уже не ложится (20 сентября 2026).
        shift = (0, 0)
        if cp.count(ImageChops.multiply(mine, forbidden)):
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
        for ru_im, wide, at in pieces:
            place = (at[0] + shift[0], at[1] + shift[1])
            if wide is not None:
                out.paste(edge, place, wide)
                ink.paste(255, place, solid(wide))
            out.paste(colour, place, ru_im)
            ink.paste(255, place, solid(ru_im))
        report.append(f"  {lb['text'].replace('|', ' / ')}: кегль {size}, сжатие {squeeze:.3f}, контур {sw}; "
                      f"высота {want_h:.0f} px, ширина {want_w} px; штрих наш {ru_stroke:.1f} против "
                      f"английского {en_stroke:.1f}; кант {edge_w}"
                      + (f"; сдвиг {shift}" if shift != (0, 0) else ""))
    # Сравнение «штрих против штриха» по мерке `stroke` здесь не судья: она растёт,
    # когда соседние буквы слипаются кантом, и у длинного «Gusto's Room» показывает
    # 17,5 против 11,6 у «Elevator» при одном и том же канте. Судим по прямому
    # замеру кольца: наш кант не должен быть тоньше английского.
    if cfg.get("stroke") and edge_w < 0.85 * measured:
        problems.append(f"{name}: кант тоньше английского — {edge_w} px против "
                        f"{measured:.1f} px замеренных")
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
