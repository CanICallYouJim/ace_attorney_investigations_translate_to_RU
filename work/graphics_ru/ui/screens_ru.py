"""screens_ru.py <имя> <куда.png> — экран запуска по заданию screens.json: строки по центру, база как у английской."""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

spec = json.loads(Path(__file__).with_name("screens.json").read_text(encoding="utf-8"))[sys.argv[1]]
W, H = spec["size"]
SS = 2
im = Image.new("RGB", (W * SS, H * SS), tuple(spec["фон"]))
d = ImageDraw.Draw(im)
for row in spec["строки"]:
    f = ImageFont.truetype(f"C:/Windows/Fonts/{row['шрифт']}", row["кегль"] * SS)
    col = tuple(row.get("цвет", spec["цвет"]))
    w = d.textlength(row["текст"], font=f)
    d.text(((W * SS - w) / 2, row["база"] * SS), row["текст"], font=f, fill=col, anchor="ls")
im = im.resize((W, H), Image.LANCZOS).convert("RGBA")
im.save(sys.argv[2])
print(sys.argv[1], "→", sys.argv[2])
