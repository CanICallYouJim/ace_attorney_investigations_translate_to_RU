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
            patch = big.crop(tuple(there)).resize(
                (here[2] - here[0], here[3] - here[1]), Image.LANCZOS)
            im.paste(patch, (here[0], here[1]))

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
