"""build_ru.py <папка> <ролик> X0 Y0 Y1 — немецкие кадры DXT1, блоки 4×4 в полосе [X0..ширина) × [Y0..Y1) — из японских (снять «Uhr»)"""
import sys, struct, io
from pathlib import Path
import numpy as np
from PIL import Image
d = Path(sys.argv[1]); base = sys.argv[2]; X0, Y0, Y1 = map(int, sys.argv[3:6])
g = bytearray((d / f"{base}.mods_ger").read_bytes()); j = (d / f"{base}.mods").read_bytes()
off = 0; n = 0
while off < len(g):
    assert g[off:off+4] == b"DDS " and j[off:off+4] == b"DDS "
    h, w = struct.unpack_from("<II", g, off+12); bw = (w + 3) // 4
    size = 128 + bw * ((h + 3) // 4) * 8
    for by in range(Y0 // 4, (Y1 + 3) // 4):
        for bx in range(X0 // 4, bw):
            p = off + 128 + (by * bw + bx) * 8
            g[p:p+8] = j[p:p+8]
    off += size; n += 1
(d / f"{base}.mods_rus").write_bytes(bytes(g))
print(base, "кадров", n, "размер", len(g))
