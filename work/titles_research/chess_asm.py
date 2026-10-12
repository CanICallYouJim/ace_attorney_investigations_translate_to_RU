"""Сборка немецких заставок LogicChess на экран: позиции — сумма anchoredPosition по цепочке."""
import UnityPy, sys, pickle, numpy as np
from PIL import Image
S = sys.argv[1]; sys.path.insert(0, S)
from typo import slant, stroke
from scipy import ndimage
env = UnityPy.load("backup/gk2_logicchess_trial_assets_all_928b642aa98c463dc645f349c82e07f5.bundle")
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
tc = {}
def piece(spid):
    t = objs[spid].read_typetree(); rd = amap[kk(t["m_RenderDataKey"])]; tid = rd["texture"]["m_PathID"]
    if tid not in tc: tc[tid] = objs[tid].read().image.convert("RGBA")
    tex = tc[tid]; r = rd["textureRect"]
    img = tex.crop((round(r["x"]), round(tex.height-r["y"]-r["height"]), round(r["x"]+r["width"]), round(tex.height-r["y"])))
    return img, rd["textureRectOffset"], t["m_Rect"], t["m_Name"]
out = {}
for pf in ("LogicChess_Title_ger", "LogicChess_Title_Start_R_ger", "LogicChess_Title_Success_R_ger", "LogicChess_Title_eng"):
    root = next(o for o in env.objects if o.type.name == "GameObject" and nm(o) == pf)
    lay = {"W": Image.new("RGBA", (1920, 1080)), "C": Image.new("RGBA", (1920, 1080))}; rows = []
    def walk(go_obj, cx, cy):
        g = go_obj.read_typetree(); cs = [objs[c["component"]["m_PathID"]] for c in g["m_Component"]]
        rt = next(c for c in cs if c.type.name == "RectTransform").read_typetree()
        stretch = rt["m_AnchorMin"]["x"] == 0.0 and rt["m_AnchorMax"]["x"] == 1.0
        if not stretch:
            cx += rt["m_AnchoredPosition"]["x"]; cy += rt["m_AnchoredPosition"]["y"]
        if g["m_Name"].startswith("Char_") and g["m_IsActive"]:
            s = rt["m_SizeDelta"]
            for c in cs:
                if c.type.name == "MonoBehaviour":
                    m = c.read_typetree()
                    if m.get("m_Sprite", {}).get("m_PathID"):
                        img, off, rect, sn = piece(m["m_Sprite"]["m_PathID"])
                        sx, sy = s["x"]/rect["width"], s["y"]/rect["height"]
                        im2 = img.resize((max(1, round(img.width*sx)), max(1, round(img.height*sy))), Image.LANCZOS)
                        x0, y0 = 960+cx-s["x"]/2, 540-cy-s["y"]/2
                        L = "W" if g["m_Name"].endswith("_W") else "C"
                        lay[L].alpha_composite(im2, (round(x0+off["x"]*sx), round(y0+s["y"]-off["y"]*sy-im2.height)))
                        if L == "C": rows.append((g["m_Name"], sn, round(cx), round(cy), round(s["x"]), round(s["y"])))
        for ch in rt["m_Children"]:
            walk(objs[objs[ch["m_PathID"]].read_typetree()["m_GameObject"]["m_PathID"]], cx, cy)
    walk(root, 0, 0)
    bg = Image.new("RGBA", (1920, 1080), (40, 40, 48, 255)); bg.alpha_composite(lay["W"]); bg.alpha_composite(lay["C"])
    bg.convert("RGB").save(f"{S}/{pf}.png")
    out[pf] = (lay["W"].tobytes(), lay["C"].tobytes())
    print(pf, sorted(rows, key=lambda r: (r[3] < -100, r[2])))
pickle.dump(out, open(f"{S}/chess_layers.pkl", "wb"))
C = np.array(Image.frombytes("RGBA", (1920, 1080), out["LogicChess_Title_Success_R_ger"][1]))
W = np.array(Image.frombytes("RGBA", (1920, 1080), out["LogicChess_Title_Success_R_ger"][0]))
cm, wm = C[..., 3] > 128, W[..., 3] > 128
print("цвет букв", np.median(C[cm][:, :3], axis=0), "обводки", np.median(W[wm][:, :3], axis=0))
d = ndimage.distance_transform_edt(~cm)[wm & ~ndimage.binary_erosion(wm)]
print("обводка px: медиана %.1f p10 %.1f p90 %.1f" % (np.median(d), np.percentile(d, 10), np.percentile(d, 90)))
for nmz, (y0, y1) in (("буквы", (380, 620)), ("d-строка", (620, 820))):
    m = Image.fromarray((cm[y0:y1] * 255).astype("uint8")); m = m.crop(m.getbbox())
    print(nmz, "рамка", m.size, "наклон %.3f штрих %.1f" % (slant(m), stroke(m)))
