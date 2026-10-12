"""Сборка немецкой заставки StEd из кусков атласа на экран 1920x1080 + замеры."""
import UnityPy, sys, pickle
from PIL import Image, ImageChops, ImageFilter
import numpy as np
S = sys.argv[1]
env = UnityPy.load("backup/gk_common_ingameui_trial_assets_all_2909a51ea4d5a5dd0d5869b17fa2004a.bundle")
objs = {o.path_id: o for o in env.objects}
def nm(o):
    try: return o.peek_name() or ""
    except Exception: return ""
def kk(k):
    f = k[0]; return (tuple(f.values()) if isinstance(f, dict) else tuple(f), k[1])
amap = {}
for o in env.objects:
    if o.type.name == "SpriteAtlas":
        for k, rd in o.read_typetree()["m_RenderDataMap"]: amap[kk(k)] = rd
texcache = {}
def piece(spid):
    t = objs[spid].read_typetree(); rd = amap[kk(t["m_RenderDataKey"])]
    tid = rd["texture"]["m_PathID"]
    if tid not in texcache: texcache[tid] = objs[tid].read().image.convert("RGBA")
    tex = texcache[tid]; r = rd["textureRect"]
    img = tex.crop((round(r["x"]), round(tex.height - r["y"] - r["height"]), round(r["x"] + r["width"]), round(tex.height - r["y"])))
    return img, rd["textureRectOffset"], t["m_Rect"], t["m_Name"]
def build(pf):
    root = next(o for o in env.objects if o.type.name == "GameObject" and nm(o) == pf)
    layers = {"W": Image.new("RGBA", (1920, 1080)), "C": Image.new("RGBA", (1920, 1080))}
    info = []
    def comps(go): return [objs[c["component"]["m_PathID"]] for c in go["m_Component"]]
    def walk(go_obj, parent_box):
        g = go_obj.read_typetree(); cs = comps(g)
        rt = next(c for c in cs if c.type.name == "RectTransform").read_typetree()
        box = parent_box
        if g["m_Name"].startswith("Char_"):
            a0 = rt["m_AnchorMin"]
            if a0["x"] == 0.0 and rt["m_AnchorMax"]["x"] == 1.0: box = parent_box
            else:
                p, s = rt["m_AnchoredPosition"], rt["m_SizeDelta"]
                box = (960 + p["x"] - s["x"]/2, 540 - p["y"] - s["y"]/2, s["x"], s["y"])
            for c in cs:
                if c.type.name == "MonoBehaviour":
                    m = c.read_typetree()
                    if "m_Sprite" in m and m["m_Sprite"]["m_PathID"]:
                        img, off, rect, sname = piece(m["m_Sprite"]["m_PathID"])
                        sx, sy = box[2] / rect["width"], box[3] / rect["height"]
                        im2 = img.resize((max(1, round(img.width*sx)), max(1, round(img.height*sy))), Image.LANCZOS)
                        x = round(box[0] + off["x"]*sx); y = round(box[1] + box[3] - off["y"]*sy - im2.height)
                        L = "W" if g["m_Name"].endswith("_W") else "C"
                        layers[L].alpha_composite(im2, (x, y))
                        info.append((g["m_Name"], sname, [round(v) for v in box], (x, y, im2.width, im2.height)))
        for ch in rt["m_Children"]:
            walk(objs[objs[ch["m_PathID"]].read_typetree()["m_GameObject"]["m_PathID"]], box)
    walk(root, (0, 0, 1920, 1080))
    return layers, info
out = {}
for pf in ("SousaPart_Title_Start_R_ger", "SousaPart_Title_End_R_ger", "SousaPart_Title_Start_R_eng"):
    layers, info = build(pf)
    out[pf] = (layers["W"].tobytes(), layers["C"].tobytes(), info)
    bg = Image.new("RGBA", (1920, 1080), (40, 40, 48, 255))
    bg.alpha_composite(layers["W"]); bg.alpha_composite(layers["C"])
    bg.convert("RGB").save(f"{S}/{pf}.png")
    for i in info: print(pf, i)
pickle.dump(out, open(f"{S}/layers.pkl", "wb"))
# замеры по немецкому Start
W = np.array(Image.frombytes("RGBA", (1920,1080), out["SousaPart_Title_Start_R_ger"][0]))
C = np.array(Image.frombytes("RGBA", (1920,1080), out["SousaPart_Title_Start_R_ger"][1]))
cm = C[..., 3] > 128; wm = W[..., 3] > 128
print("цвет букв (медиана):", np.median(C[cm][:, :3], axis=0))
print("цвет обводки (медиана):", np.median(W[wm][:, :3], axis=0))
# обводка: расстояние от тела букв до края белого
from scipy import ndimage
dist = ndimage.distance_transform_edt(~cm)
edge = wm & ~ndimage.binary_erosion(wm)
d = dist[edge]
print("обводка: расстояние край белого -> тело букв, px: медиана %.1f, p10 %.1f, p90 %.1f" % (np.median(d), np.percentile(d,10), np.percentile(d,90)))
# наклон: максимум резкости проекции на ось x после разнаклонки, отдельно строка 1 и 2
for name, (y0, y1) in (("строка 1", (0, 330)), ("строка 2", (330, 700))):
    m = Image.fromarray((cm[y0:y1] * 255).astype("uint8"))
    best = None
    for s in np.arange(0.0, 0.40, 0.005):
        u = m.transform(m.size, Image.AFFINE, (1, -s, s * m.height / 2, 0, 1, 0), Image.BILINEAR)
        prof = np.asarray(u, dtype=float).sum(axis=0)
        score = (np.diff(prof) ** 2).sum()
        if best is None or score > best[0]: best = (score, s)
    ys, xs = np.nonzero(cm[y0:y1])
    print(f"{name}: наклон {best[1]:.3f} (≈{np.degrees(np.arctan(best[1])):.1f}°), рамка букв x {xs.min()}–{xs.max()} y {ys.min()+y0}–{ys.max()+y0}")
