"""screens_ru.py <имя> <куда.png> — экран запуска по заданию screens.json: строки по центру, база как у английской."""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

spec = json.loads(Path(__file__).with_name("screens.json").read_text(encoding="utf-8"))[sys.argv[1]]
W, H = spec["size"]
SS = spec.get("сглаживание", 2)
im = Image.new("RGB", (W * SS, H * SS), tuple(spec["фон"]))
d = ImageDraw.Draw(im)
for row in spec["строки"]:
    f = ImageFont.truetype(f"C:/Windows/Fonts/{row['шрифт']}", row["кегль"] * SS)
    col = tuple(row.get("цвет", spec["цвет"]))
    k = row.get("ширина", 1.0)   # растяжка по ширине: у англичан широкий гротеск, такого с кириллицей нет
    w = d.textlength(row["текст"], font=f)
    sw = row.get("обводка", 0)  # добрать жирность: штрих в пикселях сглаживания с каждой стороны
    if k == 1.0:
        d.text(((W * SS - w) / 2, row["база"] * SS), row["текст"], font=f, fill=col, anchor="ls",
               stroke_width=sw, stroke_fill=col)
        continue
    pad = row["кегль"] * SS
    m = Image.new("L", (int(w) + 2 * pad, 3 * pad), 0)
    ImageDraw.Draw(m).text((pad, 2 * pad), row["текст"], font=f, fill=255, anchor="ls")
    m = m.resize((round(m.width * k), m.height), Image.LANCZOS)
    x = round((W * SS - w * k) / 2 - pad * k)
    im.paste(Image.new("RGB", m.size, col), (x, row["база"] * SS - 2 * pad), m)
im = im.resize((W, H), Image.LANCZOS).convert("RGBA")
im.save(sys.argv[2])
print(sys.argv[1], "→", sys.argv[2])
