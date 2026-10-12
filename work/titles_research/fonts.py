import sys, pickle, numpy as np
sys.path.insert(0, sys.argv[1]); S = sys.argv[1]
from typo import *
from PIL import Image, ImageDraw, ImageFont
L = pickle.load(open(f"{S}/layers.pkl", "rb"))["SousaPart_Title_Start_R_ger"]
C = Image.frombytes("RGBA", (1920, 1080), L[1]); W = Image.frombytes("RGBA", (1920, 1080), L[0])
line1 = C.getchannel("A").crop((0, 0, 1920, 320)); ref = line1.crop(line1.getbbox())
refW = Image.alpha_composite(W, C).crop((470, 60, 1450, 330))
gs, gsl = stroke(ref), slant(ref)
print(f"немецкий Ermittlung: рамка {ref.size}, штрих {gs:.1f}px, наклон {gsl:.3f}")
cands = [("ariblk.ttf", "Arial Black + наклон", SHEAR, None), ("arialbd.ttf", "Arial Bold + наклон", SHEAR, None),
         ("seguibli.ttf", "Segoe UI Black Italic", 0.0, None), ("segoeuiz.ttf", "Segoe UI Bold Italic", 0.0, None),
         ("NotoSans-BoldItalic.ttf", "Noto Sans Bold Italic", 0.0, None), ("Inter-Bold-slnt=0.ttf", "Inter Bold + наклон", SHEAR, None),
         ("verdanaz.ttf", "Verdana Bold Italic", 0.0, None), ("bahnschrift.ttf", "Bahnschrift Bold + наклон", SHEAR, 700)]
lab = ImageFont.truetype(FONTS + "segoeuib.ttf", 26)
rows = []
for font, title, sh, wg in cands:
    try:
        size, sx, p = calibrate(font, ref, "Ermittlung", sh, wg)
    except OSError as e:
        print(font, "нет", e); continue
    de, _ = render("Ermittlung", font, size, sh, wght=wg); de = de.resize((round(de.width * sx), de.height), Image.LANCZOS)
    ru, _ = render("Расследование", font, size, sh, wght=wg); ru = ru.resize((round(ru.width * sx), ru.height), Image.LANCZOS)
    st, sl = stroke(de), slant(de)
    note = f"{title}: кегль {size}, сжатие {sx:.2f}, штрих {st:.1f} (нем. {gs:.1f}), наклон {sl:.2f} (нем. {gsl:.2f}), «Расследование» {ru.width}px (нем. Ermittlung {ref.width})"
    print(note); rows.append((note, colour(de), colour(ru)))
H = 270; Wd = 980 + 1350
sheet = Image.new("RGB", (Wd, 60 + (len(rows) + 1) * (H + 40)), (40, 40, 48)); d = ImageDraw.Draw(sheet)
d.text((10, 10), "Оригинал (немецкий, из атласа) — слева; кандидаты: тот же шрифт «Ermittlung» | «Расследование», масштаб игры 1:1", font=lab, fill=(255, 215, 80))
sheet.paste(refW.convert("RGB"), (0, 50))
y = 50 + H + 40
for note, de, ru in rows:
    d.text((10, y - 34), note, font=lab, fill=(255, 215, 80))
    sheet.paste(de, (0, y), de); sheet.paste(ru, (980, y), ru); y += H + 40
sheet.save(f"{S}/fonts.png"); print("ok", sheet.size)
