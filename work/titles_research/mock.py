import sys, pickle, numpy as np
S = sys.argv[1]; sys.path.insert(0, S)
import typo
from typo import *
from PIL import Image, ImageDraw, ImageFont
lab = ImageFont.truetype(FONTS + "segoeuib.ttf", 30)
BG = (40, 40, 48, 255)
L = pickle.load(open(f"{S}/layers.pkl", "rb"))
C = Image.frombytes("RGBA", (1920, 1080), L["SousaPart_Title_Start_R_ger"][1])
cm = np.asarray(C.getchannel("A")) > 128
base1 = int(np.nonzero(cm[:, 508:600].any(axis=1))[0].max())   # низ «E»
base2 = int(np.nonzero(cm[330:700].any(axis=1))[0].max()) + 330  # низ «starten»
print("базовые линии", base1, base2)
line1 = C.getchannel("A").crop((0, 0, 1920, 320)); ref = line1.crop(line1.getbbox())
def setline(canvas, text, font, sh, size, sx, base, cx=960, out=OUT, colour_=None, dw=0):
    m, b = render(text, font, size, sh); m = weight(m, dw)
    # базовая линия в обрезанной маске: верх рамки = верх букв; ищем через «Е»-подобную опору — проще: рендер «Н» той же высоты
    full, fb = render(text + "Н", font, size, sh)
    m = m.resize((round(m.width * sx), m.height), Image.LANCZOS)
    # низ буквы без выносных: берём по символу «Н»
    hm, _ = render("Н", font, size, sh)
    top_to_base = hm.height                                        # высота прописной
    capm, _ = render("НН" + text, font, size, sh)
    off_top = capm.height - hm.height                              # выносной вверх над прописной (й, б)
    im = colour(m, out)
    pad = out + 4
    y = base - top_to_base - pad - (0 if not any(c in text for c in "бдйЙ") else 0)
    # верх маски — самая высокая точка текста; у прописной/«б» верх выше прописной: выравниваем по низу «Н»
    t_m, _ = render(text, font, size, sh); h_noDesc = render(text.translate(str.maketrans("дрфуДЦЩщц", "оооооНННН")), font, size, sh)[0].height
    y = base - h_noDesc - pad
    canvas.alpha_composite(im, (round(cx - im.width / 2), round(y)))
    return m.width
font, sh, DW = "seguibl.ttf", SHEAR, -2.5
size, sx, _ = calibrate(font, ref, "Ermittlung", sh)
variants = {
  "V1": ("Расследование", "открыто", "Рассле | дование / отк | рыто", "как у немцев: 2+2, «Расследование» общее с «завершено», ссылки на спрайты не трогать"),
  "V2": ("Начать", "расследование", "Начать (1 кусок, слот L01 скрыт) / рассле | дование", "«дование» общий со строкой 1 «завершено»; 3 ссылки Image в префабе Start переставить"),
  "V3": ("Начало", "расследования", "Начало (1 кусок) / рассле | дования", "ничего не делится; «завершено» в End одним куском; ссылки Image переставить в обоих префабах"),
  "End": ("Расследование", "завершено", "Рассле | дование / завер | шено", "строка 1 — те же спрайты, что у Start V1"),
}
frames = []
for key, (a, b, cut, note) in variants.items():
    fr = Image.new("RGBA", (1920, 1080), BG)
    w1 = setline(fr, a, font, sh, size, sx, base1, dw=DW); w2 = setline(fr, b, font, sh, size, sx, base2, dw=DW)
    d = ImageDraw.Draw(fr)
    d.text((40, 900), f"{key}: «{a} {b}» — Segoe UI Black + наклон 0.16, штрих −2.5px, кегль {size}, сжатие {sx:.2f}, обводка {OUT}px", font=lab, fill=(255, 215, 80))
    d.text((40, 945), f"куски: {cut}; ширина строк {w1}/{w2}px (нем. Ermittlung 902, abgeschlossen 1289)", font=lab, fill=(200, 200, 200))
    d.text((40, 990), note, font=lab, fill=(200, 200, 200))
    fr.convert("RGB").save(f"{S}/start_{key}.png"); frames.append(fr)
    print(key, w1, w2)
# сводный лист: немецкие Start/End + 4 русских, по 50 %
ger = [Image.open(f"{S}/SousaPart_Title_Start_R_ger.png").convert("RGBA"), Image.open(f"{S}/SousaPart_Title_End_R_ger.png").convert("RGBA")]
tiles = ger + frames
sheet = Image.new("RGB", (1920, 3 * 540 + 3 * 10), (20, 20, 20))
for i, t in enumerate(tiles):
    sheet.paste(t.resize((960, 540), Image.LANCZOS).convert("RGB"), ((i % 2) * 960, (i // 2) * 550))
sheet.save(f"{S}/sted_overview.png")
# --- LogicChess ---
CL = pickle.load(open(f"{S}/chess_layers.pkl", "rb"))
Wc = Image.frombytes("RGBA", (1920, 1080), CL["LogicChess_Title_Success_R_ger"][0]); Cc = Image.frombytes("RGBA", (1920, 1080), CL["LogicChess_Title_Success_R_ger"][1])
comp = Image.alpha_composite(Wc, Cc); a = np.asarray(comp).astype(int)
blue = (a[..., 2] > 150) & (a[..., 0] < 80) & (a[..., 3] > 200)
print("синий (медиана):", np.median(a[blue][:, :3], axis=0))
from scipy import ndimage
solid = a[..., 3] > 128
d = ndimage.distance_transform_edt(~blue)[solid & ~ndimage.binary_erosion(solid)]
print("кайма LogicChess px: медиана %.1f p10 %.1f p90 %.1f" % (np.median(d), np.percentile(d, 10), np.percentile(d, 90)))
bm = Image.fromarray((blue[380:620] * 255).astype("uint8")); bm = bm.crop(bm.getbbox())
print("Mentalschach рамка", bm.size, "штрих %.1f наклон %.3f" % (stroke(bm), slant(bm)))
BLUE = tuple(int(v) for v in np.median(a[blue][:, :3], axis=0))
typo.CRIMSON = BLUE
bl1 = int(np.nonzero(blue[380:620, 560:700].any(axis=1))[0].max()) + 380     # низ «M»
bl2 = int(np.nonzero(blue[620:900].any(axis=1))[0].max()) + 620
out_c = int(round(np.median(d)))
rows = []
for cf, csh in (("ariblk.ttf", 0.17), ("seguibl.ttf", 0.175)):
    sz, csx, _ = calibrate(cf, bm, "Mentalschach", csh)
    fr = Image.new("RGBA", (1920, 1080), BG)
    w = render("Ментальные шахматы", cf, sz, csh)[0].width * csx
    k = min(1.0, 1720 / w)
    w1 = setline(fr, "Ментальные шахматы", cf, csh, round(sz * k), csx, bl1 - (1 - k) * 60, out=out_c)
    w2 = setline(fr, "Шах и мат", cf, csh, sz, csx, bl2, out=out_c)
    fr2 = Image.new("RGBA", (1920, 1080), BG)
    setline(fr2, "Ментальные шахматы", cf, csh, round(sz * k), csx, bl1 - (1 - k) * 60, out=out_c)
    setline(fr2, "Начали!", cf, csh, sz, csx, bl2, out=out_c)
    for f_, txt in ((fr, "Success"), (fr2, "Start")):
        ImageDraw.Draw(f_).text((40, 960), f"{cf}{' + наклон %.2f' % csh if csh else ''}: кегль {sz}, слово сжато до {k:.2f} ({w1}px), сжатие {csx:.2f}, кайма {out_c}px — {txt}", font=lab, fill=(255, 215, 80))
    rows += [fr, fr2]; print(cf, sz, round(csx, 2), "k", round(k, 2), w1, w2)
gers = [Image.open(f"{S}/LogicChess_Title_Success_R_ger.png").convert("RGBA"), Image.open(f"{S}/LogicChess_Title_Start_R_ger.png").convert("RGBA")]
tiles = gers + rows
sheet = Image.new("RGB", (1920, 3 * 550), (20, 20, 20))
for i, t in enumerate(tiles):
    sheet.paste(t.resize((960, 540), Image.LANCZOS).convert("RGB"), ((i % 2) * 960, (i // 2) * 550))
sheet.save(f"{S}/chess_overview.png")
