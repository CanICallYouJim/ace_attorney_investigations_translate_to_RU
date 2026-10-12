import UnityPy, sys, json
path, *prefabs = sys.argv[1:]
env = UnityPy.load(path)
objs = {o.path_id: o for o in env.objects}
def name(o):
    try: return o.peek_name() or ""
    except Exception: return ""
sprites = {o.path_id: name(o) for o in env.objects if o.type.name == "Sprite"}
# atlas maps
amap = {}
for o in env.objects:
    if o.type.name == "SpriteAtlas":
        t = o.read_typetree()
        for (k, rd) in t["m_RenderDataMap"]:
            first = k[0] if not isinstance(k, dict) else k
            kk = tuple(first.values()) if isinstance(first, dict) else tuple(first)
            amap[(kk, k[1])] = (name(o), rd)
def sprite_info(pid):
    o = objs.get(pid)
    if o is None: return None
    t = o.read_typetree()
    k = t["m_RenderDataKey"]; f = k[0] if not isinstance(k, dict) else k
    kk = (tuple(f.values()) if isinstance(f, dict) else tuple(f), k[1])
    at, rd = amap.get(kk, ("?", None))
    r = rd["textureRect"] if rd else {}
    off = rd["textureRectOffset"] if rd else {}
    return f'{t["m_Name"]} rect {t["m_Rect"]["width"]:.0f}x{t["m_Rect"]["height"]:.0f} piv({t["m_Pivot"]["x"]:.2f},{t["m_Pivot"]["y"]:.2f}) atlas {at} tex[{r.get("x",0):.0f},{r.get("y",0):.0f} {r.get("width",0):.0f}x{r.get("height",0):.0f}] off({off.get("x",0):.0f},{off.get("y",0):.0f})'
for pf in prefabs:
    roots = [o for o in env.objects if o.type.name == "GameObject" and name(o) == pf]
    print("#####", pf, [r.path_id for r in roots])
    for root in roots[:1]:
        def walk(go_obj, depth):
            g = go_obj.read_typetree()
            comps = [objs[c["component"]["m_PathID"]] for c in g["m_Component"] if c["component"]["m_PathID"] in objs]
            rt = next((c for c in comps if c.type.name in ("RectTransform", "Transform")), None)
            line = "  " * depth + g["m_Name"] + ("" if g["m_IsActive"] else " [off]")
            tt = rt.read_typetree()
            if rt.type.name == "RectTransform":
                p, s = tt["m_AnchoredPosition"], tt["m_SizeDelta"]
                line += f'  pos({p["x"]:.0f},{p["y"]:.0f}) size({s["x"]:.0f}x{s["y"]:.0f})'
                a0, a1 = tt["m_AnchorMin"], tt["m_AnchorMax"]
                if (a0["x"], a0["y"], a1["x"], a1["y"]) != (0.5, 0.5, 0.5, 0.5):
                    line += f' anch({a0["x"]},{a0["y"]}-{a1["x"]},{a1["y"]})'
                pv = tt["m_Pivot"]
                if (pv["x"], pv["y"]) != (0.5, 0.5): line += f' pivot({pv["x"]},{pv["y"]})'
            sc = tt["m_LocalScale"]
            if (sc["x"], sc["y"]) != (1, 1): line += f' scale({sc["x"]:.2f},{sc["y"]:.2f})'
            q = tt["m_LocalRotation"]
            if abs(q["z"]) > 1e-4: line += f' rotz q={q["z"]:.3f}'
            extra = []
            for c in comps:
                if c.type.name == "MonoBehaviour":
                    try: m = c.read_typetree()
                    except Exception as e: extra.append("MB?"); continue
                    if "m_Sprite" in m:
                        si = sprite_info(m["m_Sprite"]["m_PathID"])
                        col = m.get("m_Color", {})
                        extra.append(f'IMG[{si}] type{m.get("m_Type")} pa{m.get("m_PreserveAspect")} col({col.get("r",1):.2f},{col.get("g",1):.2f},{col.get("b",1):.2f},{col.get("a",1):.2f})')
                    else:
                        ks = [k for k in m.keys() if not k.startswith("m_") ][:6]
                        script = objs.get(m.get("m_Script",{}).get("m_PathID"))
                        extra.append("MB " + (name(script) if script else "?") + " " + ",".join(ks))
                elif c.type.name not in ("RectTransform", "Transform", "CanvasRenderer"):
                    extra.append(c.type.name)
            print(line + ("  || " + " | ".join(extra) if extra else ""))
            for ch in tt.get("m_Children", []):
                cht = objs[ch["m_PathID"]].read_typetree()
                walk(objs[cht["m_GameObject"]["m_PathID"]], depth + 1)
        walk(root, 0)
