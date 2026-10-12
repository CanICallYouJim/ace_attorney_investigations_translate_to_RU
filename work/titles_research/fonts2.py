import sys, pickle, numpy as np
S = sys.argv[1]; sys.path.insert(0, S)
from typo import *
from PIL import Image, ImageDraw, ImageFont
L = pickle.load(open(f"{S}/layers.pkl", "rb"))["SousaPart_Title_Start_R_ger"]
C = Image.frombytes("RGBA", (1920, 1080), L[1]); W = Image.frombytes("RGBA", (1920, 1080), L[0])
line1 = C.getchannel("A").crop((0, 0, 1920, 320)); ref = line1.crop(line1.getbbox())
orig = Image.new("RGBA", (1920, 1080), (40, 40, 48, 255)); orig.alpha_composite(W); orig.alpha_composite(C)
refW = orig.crop((470, 60, 1450, 330))
gs = stroke(ref)
cands = [("seguibl.ttf", "Segoe UI Black, прямой + наклон 0.16", SHEAR, 0), ("seguibl.ttf", "Segoe UI Black + наклон, штрих −2.5px", SHEAR, -2.5),
         ("segoeuib.ttf", "Segoe UI Bold + наклон, штрих +1.5px", SHEAR, 1.5), ("ariblk.ttf", "Arial Black + наклон (как «Возражение»)", SHEAR, 0),
         ("Inter-Bold-slnt=0.ttf", "Inter Bold + наклон, штрих +2px", SHEAR, 2), ("seguibli.ttf", "Segoe UI Black Italic — курсивные т/д/и (для сравнения)", 0.0, 0)]
lab = ImageFont.truetype(FONTS + "segoeuib.ttf", 28)
rows = []
for font, title, sh, dw in cands:
    size, sx, _ = calibrate(font, ref, "Ermittlung", sh)
    out = []
    for t in ("Ermittlung", "Расследование завершено"):
        m, _ = render(t, font, size, sh); m = weight(m, dw); m = m.resize((round(m.width * sx), m.height), Image.LANCZOS); out.append(m)
    note = f"{title}: кегль {size}, сжатие {sx:.2f}, штрих {stroke(out[0]):.0f} (нем. {gs:.0f}), наклон {slant(out[0]):.2f} (нем. 0.16)"
    print(note); rows.append((note, colour(out[0]), colour(out[1])))
H = 270; Wd = 980 + max(r[2].width for r in rows) + 20
sheet = Image.new("RGB", (Wd, 60 + (len(rows) + 1) * (H + 44)), (40, 40, 48)); d = ImageDraw.Draw(sheet)
d.text((10, 10), "Сверху — немецкий оригинал из атласа. Ниже: кандидат «Ermittlung» (сверка формы) | «Расследование завершено» (одной строкой — только для глаза), 1:1 к экрану", font=lab, fill=(255, 215, 80))
sheet.paste(refW.convert("RGB"), (0, 54)); y = 54 + H + 44
for note, de, ru in rows:
    d.text((10, y - 36), note, font=lab, fill=(255, 215, 80)); sheet.paste(de, (0, y), de); sheet.paste(ru, (980, y), ru); y += H + 44
sheet.save(f"{S}/fonts.png"); print(sheet.size)
