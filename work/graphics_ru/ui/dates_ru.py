"""dates_ru.py <папка> — русские плашки даты: немецкие без «Uhr» (тело букв справа от цифр снято, контур цифр достроен по профилю)"""
import sys
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
d = Path(sys.argv[1])
GREEN = np.array([0, 139, 78])
for i in range(4):
    for j in range(2):
        src = d / f"Date_{i}_{j}_ger.png"
        a = np.asarray(Image.open(src).convert("RGBA"), float)
        A = a[..., 3]; rgb = a[..., :3]
        green = (np.abs(rgb - GREEN).max(-1) < 60) & (A > 128)
        body = (A > 200) & ~green & (rgb.max(-1) > 150)
        lab, n = ndimage.label(body)
        objs = ndimage.find_objects(lab)
        # «Uhr» — три последние тела, верх ниже цифр (надстрочные), справа
        tops = [(sl[1].start, sl[0].start, k + 1) for k, sl in enumerate(objs)]
        digit_top = min(t for _, t, _ in tops)
        right = sorted(tops)[-3:]
        uhr = {k for x, t, k in right if t > digit_top + 8}
        assert len(uhr) == 3, (src.name, right)
        x_cut = min(x for x, t, k in right if k in uhr)
        keep = np.isin(lab, [k for k in range(1, n + 1) if k not in uhr])
        dk = ndimage.distance_transform_edt(~keep)
        # профиль альфы по расстоянию от тела — по левой части (до x_cut-20)
        L = np.zeros_like(A, bool); L[:, : x_cut - 20] = True
        prof = {}
        for r in np.arange(0, 20, 0.5):
            sel = L & (dk >= r) & (dk < r + 0.5)
            if sel.sum() > 20: prof[r] = np.median(A[sel])
        rs = np.array(sorted(prof)); vs = np.array([prof[r] for r in rs])
        Z = np.zeros_like(A, bool); Z[:, x_cut - 12:] = True
        out = a.copy()
        newA = np.interp(dk, rs + 0.25, vs, right=0)
        out[..., 3][Z] = newA[Z]
        uhr_m = ndimage.binary_dilation(np.isin(lab, list(uhr)), iterations=3)
        recolor = Z & uhr_m & (newA > 0)
        out[..., :3][recolor] = GREEN
        out[..., 3][Z & (newA <= 0)] = 0
        Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA").save(d / f"Date_{i}_{j}.png")
        print(src.name, "Uhr с x", x_cut, "профиль до", rs.max())
