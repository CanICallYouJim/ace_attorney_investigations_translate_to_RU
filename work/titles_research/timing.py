import UnityPy, sys, struct, zlib, collections
bpath, clipname, prefab = sys.argv[1:4]
env = UnityPy.load(bpath); objs = {o.path_id: o for o in env.objects}
def nm(o):
    try: return o.peek_name() or ""
    except Exception: return ""
paths = {0: "<root>"}
root = next(o for o in env.objects if o.type.name == "GameObject" and nm(o) == prefab)
def walk(tr, parts):
    tt = tr.read_typetree(); go = objs[tt["m_GameObject"]["m_PathID"]].read_typetree(); p = parts + [go["m_Name"]]
    paths[zlib.crc32("/".join(p[2:]).encode())] = "/".join(p[2:])
    for ch in tt["m_Children"]: walk(objs[ch["m_PathID"]], p)
g = root.read_typetree(); walk(next(objs[c["component"]["m_PathID"]] for c in g["m_Component"] if objs[c["component"]["m_PathID"]].type.name == "RectTransform"), [])
clip = next(o for o in env.objects if o.type.name == "AnimationClip" and nm(o) == clipname).read_typetree()
mc = clip["m_MuscleClip"]["m_Clip"]["data"]
sc = mc["m_StreamedClip"]; dc = mc["m_DenseClip"]; cc = mc["m_ConstantClip"]
B = clip["m_ClipBindingConstant"]["genericBindings"]
# число кривых на привязку: позиция/масштаб 3, вращение 4, euler 3, прочее 1
def width(b):
    if b["typeID"] == 4 and b["attribute"] in (1, 3, 4): return 3
    if b["typeID"] == 4 and b["attribute"] == 2: return 4
    return 1
curve_owner = []
for b in B:
    for k in range(width(b)): curve_owner.append((paths.get(b["path"], hex(b["path"])), b["typeID"], b["attribute"], k))
data = struct.pack(f"<{len(sc['data'])}I", *sc["data"])
pos = 0; keys = collections.defaultdict(list)
while pos < len(data):
    t, n = struct.unpack_from("<fI", data, pos); pos += 8
    for _ in range(n):
        idx, a, b2, c, d = struct.unpack_from("<I4f", data, pos); pos += 20
        keys[idx].append((t, d))
print("кривых streamed", sc["curveCount"], "dense", dc["m_CurveCount"], "const", len(cc["data"]), "всего по привязкам", len(curve_owner))
for idx in sorted(keys):
    own = curve_owner[idx] if idx < len(curve_owner) else ("?",)
    if own[1] == 1 or own[1] == 114 or (own[1] == 4 and own[3] == 0):
        ks = [(round(t, 3), round(v, 2)) for t, v in keys[idx] if t > -1e30 and abs(t) < 1e6]
        print(own[0], own[1], own[2], ks[:8])
