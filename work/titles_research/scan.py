import UnityPy, sys, glob
for p in glob.glob("backup/gk_common_ingameui*.bundle"):
    env = UnityPy.load(p)
    print("==", p.split("/")[-1])
    ab = next(o for o in env.objects if o.type.name == "AssetBundle")
    for k, v in ab.read_typetree()["m_Container"]:
        if any(s in k for s in ("SousaPart_Title_St", "SousaPart_Title_End", "LogicChess", "SousaPart_Title_StEd")):
            print("  C", k, v["asset"]["m_PathID"])
    for o in env.objects:
        if o.type.name in ("SpriteAtlas", "Texture2D", "AnimationClip", "AnimatorController"):
            n = o.peek_name() or ""
            if any(s in n for s in ("StEd", "LogicChess", "Title_Start", "Title_End")):
                print("  ", o.type.name, n, o.path_id)
