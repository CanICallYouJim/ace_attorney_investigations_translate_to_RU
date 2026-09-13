"""Заменить надпись на картинке, не тронув рисунок.

Для того пласта графики, где надпись — обычный шрифт, а не рисованный логотип:
планы этажей, таблички комнат, визитки, лицензии, подписи под работами. Такие
надписи набираются, и звать ради них нейросеть незачем — она перерисовывает
картинку целиком и портит рисунок (разбор в
[`docs/localized-assets.md`](../docs/localized-assets.md)).

Как устроено. Скрипт **не заливает прямоугольник** — он находит пиксели самих
букв и обводки по цвету, расширяет маску на пару пикселей и **затягивает дыру
соседними пикселями** (простой inpaint: несколько проходов усреднения по краю).
Поэтому надпись, лежащая поверх стены, границы или градиента, снимается
без следа: подложка восстанавливается той, что была вокруг, а не одним цветом.

Задание — JSON рядом с картинками:

    {
      "cut02_003": {
        "fill": [242, 234, 224],      # цвет букв в оригинале
        "stroke": [85, 85, 87],       # цвет обводки
        "stroke_width": 3,
        "font": "segoeuib",           # гарнитура из C:/Windows/Fonts
        "labels": [
          {"box": [513, 266, 763, 324], "text": "Комната Густо", "max_width": 400},
          {"box": [704, 816, 843, 911], "text": "Комната|охраны", "max_width": 175}
        ]
      }
    }

`box` — рамка старой надписи в пикселях исходной картинки, `|` в тексте делит
на строки. Кегль подбирается **общий на всю картинку** — самый крупный, при
котором каждая надпись влезает в свой `max_width`; иначе длинные подписи
съезжают на мелкий шрифт, а короткие остаются крупными, и картинка выглядит
собранной из кусков.

    python tools/relabel.py work/graphics_ru/case3/labels.json
    python tools/relabel.py work/graphics_ru/case3/labels.json --only cut02_003

Читает из `work/graphics_en/<дело>/`, пишет в папку, где лежит задание.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path("C:/Windows/Fonts")


def near(a, b, tol):
    return all(abs(p - q) <= tol for p, q in zip(a, b))


def inpaint(im: Image.Image, mask: Image.Image, box, passes: int = 24) -> None:
    """Затянуть закрашенные маской пиксели соседними. Маска — режим L, 255 = дыра."""
    x0, y0 = box[0], box[1]
    w, h = mask.size
    px = im.load()
    hole = {(x, y) for y in range(h) for x in range(w) if mask.getpixel((x, y))}
    for _ in range(passes):
        if not hole:
            break
        filled = []
        for (x, y) in hole:
            vals = []
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and (nx, ny) in hole:
                    continue
                ax, ay = x0 + nx, y0 + ny
                if 0 <= ax < im.width and 0 <= ay < im.height:
                    vals.append(px[ax, ay])
            if vals:
                n = len(vals)
                filled.append(((x, y), tuple(sum(c[i] for c in vals) // n for i in range(3))))
        if not filled:
            break
        for (x, y), c in filled:
            px[x0 + x, y0 + y] = c
            hole.discard((x, y))


def strip_text(im: Image.Image, box, fill, stroke, pad: int = 6,
               tol_fill: int = 45, tol_stroke: int = 25) -> None:
    """Снять старую надпись: маска по цвету букв и обводки, затем inpaint.

    Допуск вынесен в аргументы не для красоты. На мелких копиях той же картинки
    (карточка логики 158x158 против врезки 1920x1080) буква занимает три-четыре
    пикселя и почти вся состоит из сглаживания: её средний цвет уходит к бумаге,
    и маска с допуском 45 не берёт ничего. Проверено 25 августа 2026 —
    английская надпись осталась под русской, и на карточке они задвоились.
    """
    x0, y0, x1, y1 = box
    X0, Y0 = max(0, x0 - pad), max(0, y0 - pad)
    X1, Y1 = min(im.width, x1 + pad), min(im.height, y1 + pad)
    px = im.load()
    mask = Image.new("L", (X1 - X0, Y1 - Y0), 0)
    mp = mask.load()
    for y in range(Y0, Y1):
        for x in range(X0, X1):
            p = px[x, y]
            if near(p, fill, tol_fill) or near(p, stroke, tol_stroke):
                mp[x - X0, y - Y0] = 255
    mask = mask.filter(ImageFilter.MaxFilter(5))
    inpaint(im, mask, (X0, Y0))


def remap(job: dict, there, here) -> dict:
    """Пересчитать рамки задания под другой файл с той же картинкой.

    Дело 1 повторяется само в себе: план охраны лежит в трёх файлах, газета
    в пяти. Файлы **не одна картинка в разных размерах** — у карточки улики
    свой кадр, и врезка, вписанная в её рамку, расходится с ней на 24 из 255:
    мелкие копии игра рисует отдельно и резче. Уменьшать готовую врезку нельзя,
    собирать надо в родном масштабе.

    Зато рисунок один и тот же. Если указать в обоих файлах общий ориентир —
    у планов это лист бумаги, — рамки пересчитываются сами, и размечать руками
    надо только первый файл.

    `there` и `here` — рамка ориентира в исходном и в целевом файле.
    """
    sx = (here[2] - here[0]) / (there[2] - there[0])
    sy = (here[3] - here[1]) / (there[3] - there[1])

    def box(b):
        return [round(here[0] + (b[0] - there[0]) * sx),
                round(here[1] + (b[1] - there[1]) * sy),
                round(here[2] + (b[2] - there[2]) * sx),
                round(here[3] + (b[3] - there[3]) * sy)]

    out = {k: v for k, v in job.items() if k not in ("снять", "вернуть", "вклеить", "labels")}
    for key in ("снять", "вернуть", "вклеить"):
        if key in job:
            out[key] = [dict(it, box=box(it["box"])) for it in job[key]]
    if "labels" in job:
        out["labels"] = []
        for lb in job["labels"]:
            new = dict(lb, box=box(lb["box"]))
            if "max_width" in lb:
                new["max_width"] = max(1, round(lb["max_width"] * sx))
            if "size" in lb:
                new["size"] = max(6, round(lb["size"] * sy))
            out["labels"].append(new)
    return out


def pick_size(draw, labels, font_path, hi=64, lo=10):
    """Общий кегль: самый крупный, при котором каждая надпись влезает в свой max_width."""
    for size in range(hi, lo - 1, -1):
        f = ImageFont.truetype(str(font_path), size)
        if all(
            max(draw.textbbox((0, 0), t, font=f)[2] for t in lb["text"].split("|"))
            <= lb.get("max_width", lb["box"][2] - lb["box"][0])
            for lb in labels
        ):
            return size
    return lo


def run(spec_path: Path, only: str | None) -> int:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    src_dir = Path("work/graphics_en") / spec_path.parent.name
    out_dir = spec_path.parent
    done = 0
    for name, cfg in spec.items():
        if only and name != only:
            continue
        if "как" in cfg:
            own = {k: v for k, v in cfg.items()
                   if k not in ("как", "якорь_там", "якорь_тут")}
            cfg = {**remap(spec[cfg["как"]], cfg["якорь_там"], cfg["якорь_тут"]), **own}
        src = src_dir / f"{name}.png"
        if not src.exists():
            print(f"  ! нет исходника {src}")
            continue
        raw = Image.open(src)
        # Родная альфа: у кат-инов она 254..255. Без неё картинка сохранялась
        # с 255 везде, и сверка слоя (layer_localized.py) видела «правку»
        # на треть кадра там, где не менялся ни один цвет. Найдено 13 сентября 2026.
        alpha = raw.getchannel("A") if raw.mode == "RGBA" else None
        im = raw.convert("RGB")
        fill = tuple(cfg["fill"])
        stroke = tuple(cfg["stroke"])
        font_path = FONT_DIR / f"{cfg.get('font', 'segoeuib')}.ttf"
        labels = cfg["labels"]

        for lb in labels:
            strip_text(im, lb["box"], fill, stroke,
                       tol_fill=cfg.get("допуск", 45),
                       tol_stroke=cfg.get("допуск_обводки", 25))

        draw = ImageDraw.Draw(im)
        size = pick_size(draw, labels, font_path)
        sw = cfg.get("stroke_width", 3)
        for lb in labels:
            lines = lb["text"].split("|")
            # Общий кегль — правило, но бывают картинки с двумя настоящими
            # размерами шрифта: на плане охраны «Ладья» вдвое крупнее шапки
            # «План охраны президента». Тогда у надписи свой кегль, явно.
            if "size" in lb:
                s = lb["size"]
            else:
                s = size if len(lines) == 1 else max(10, size - 4)
            while s > 10:
                f = ImageFont.truetype(str(font_path), s)
                if max(draw.textbbox((0, 0), t, font=f)[2] for t in lines) <= lb.get(
                    "max_width", lb["box"][2] - lb["box"][0]
                ):
                    break
                s -= 1
            f = ImageFont.truetype(str(font_path), s)
            hs = [draw.textbbox((0, 0), t, font=f)[3] for t in lines]
            total = sum(hs) + 6 * (len(lines) - 1)
            x0, y0, x1, y1 = lb["box"]
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            yy = cy - total // 2
            for t, hh in zip(lines, hs):
                bb = draw.textbbox((0, 0), t, font=f)
                draw.text((cx - bb[2] // 2, yy), t, font=f, fill=tuple(lb.get("fill", fill)),
                          stroke_width=sw, stroke_fill=stroke)
                yy += hh + 6
        out = out_dir / f"{name}.png"
        if alpha is not None:
            im = im.convert("RGBA")
            im.putalpha(alpha)
        im.save(out)
        print(f"  {name}: надписей {len(labels)}, кегль {size} -> {out}")
        done += 1
    return 0 if done else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path, help="JSON с заданием")
    ap.add_argument("--only", help="сделать одну картинку")
    args = ap.parse_args()
    return run(args.spec, args.only)


if __name__ == "__main__":
    raise SystemExit(main())
