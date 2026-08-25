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

from PIL import Image, ImageFilter

from relabel import strip_text

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
        src = src_dir / f"{name}.png"
        if not src.exists():
            print(f"  {name}: нет исходника {src}")
            continue
        im = Image.open(src).convert("RGBA")
        alpha = im.getchannel("A")          # альфа оригинала: у cut* она 254..255
        flat = im.convert("RGB")

        for cut in job.get("снять", []):
            strip_text(flat, cut["box"], tuple(cut["fill"]), tuple(cut["stroke"]),
                       cut.get("pad", 6))
        im = flat.convert("RGBA")
        im.putalpha(alpha)

        for glue in job.get("вклеить", []):
            art_path = (spec_path.parent / glue["art"]).resolve()
            art = key_out(
                Image.open(art_path),
                key=tuple(glue.get("key", MAGENTA)),
                tol=glue.get("key_tol", 90),
                despill=glue.get("despill", True),
                shrink=glue.get("shrink", 2),
            )
            art, at = fit(art, glue["box"])
            if glue.get("opacity", 1.0) != 1.0:
                a = art.getchannel("A").point(lambda v: int(v * glue["opacity"]))
                art.putalpha(a)
            im.alpha_composite(art, at)

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
