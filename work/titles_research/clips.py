import UnityPy, sys, zlib, collections
path = sys.argv[1]; ctrls = sys.argv[2].split(","); langs = sys.argv[3].split(","); base = sys.argv[4]
env = UnityPy.load(path)
objs = {o.path_id: o for o in env.objects}
def nm(o):
    try: return o.peek_name() or ""
    except Exception: return ""
# collect all paths under 'root' for prefabs of language variants
paths = {}
for lang in langs:
    pf = f"{base}_{lang}" if lang else base
    root = next((o for o in env.objects if o.type.name == "GameObject" and nm(o) == pf), None)
    if not root: continue
    def walk(tr, parts):
        tt = tr.read_typetree(); go = objs[tt["m_GameObject"]["m_PathID"]].read_typetree()
        p = parts + [go["m_Name"]]
        rel = "/".join(p[2:])  # relative to 'root' (Animator)
        paths[zlib.crc32(rel.encode())] = rel
        for ch in tt.get("m_Children", []): walk(objs[ch["m_PathID"]], p)
    g = root.read_typetree()
    walk(next(objs[c["component"]["m_PathID"]] for c in g["m_Component"] if objs[c["component"]["m_PathID"]].type.name=="RectTransform"), [])
paths[0] = "<root>"
for c in env.objects:
    if c.type.name == "AnimatorController" and nm(c) in ctrls:
        t = c.read_typetree()
        print("### controller", nm(c), [nm(objs[a["m_PathID"]]) for a in t["m_AnimationClips"] if a["m_PathID"] in objs])
        for a in t["m_AnimationClips"]:
            clip = objs.get(a["m_PathID"]); 
            if not clip: continue
            ct = clip.read_typetree()
            print("  clip", nm(clip), "len", round(ct["m_MuscleClipSize"] and ct["m_MuscleClip"]["m_StopTime"],3))
            b = ct["m_ClipBindingConstant"].get("m_GenericBindings") or ct["m_ClipBindingConstant"].get("genericBindings")
            per = collections.OrderedDict()
            for gb in b:
                p = paths.get(gb.get("path"), hex(gb["path"]))
                attr = gb["attribute"]
                per.setdefault(p, set()).add((gb.get("typeID", gb.get("classID")), attr))
            for p, s in per.items(): print("    ", p, sorted(s)[:6])
