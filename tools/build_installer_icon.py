"""Extract Edgeworth's original pixel sprite and build the installer icon.

No game bundles are changed. Generated PNG/ICO contain game pixels and stay
out of the development branch. The small icon is deliberately included in EXE.
"""
from pathlib import Path
import json
from PIL import Image
from common import BUNDLES

ASSETS = Path(__file__).resolve().parent.parent / "patcher" / "assets"
BUNDLE = "gk2_mapchar_trial"
TEXTURE = "chr000_000_TexIdxEx"
PALETTE = "chr000_000_ColorPlteEx"
# Three-quarter facing-left pose: hair, face, cravat and upper shoulders.
CROP = (201, 0, 249, 49)
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def build():
    import UnityPy
    source = next(BUNDLES.glob(BUNDLE + "_assets_all_*.bundle"))
    env = UnityPy.load(str(source))
    textures = {obj.peek_name(): obj for obj in env.objects if obj.type.name == "Texture2D"}
    index = textures[TEXTURE].read().image.convert("RGBA")
    palette = textures[PALETTE].read().image.convert("RGBA")
    colors = [palette.getpixel((n, 0)) for n in range(256)]
    rgba = Image.new("RGBA", index.size)
    # The game's indexed texture stores the palette index in alpha.
    rgba.putdata([colors[n] for n in index.getchannel("A").getdata()])
    rgba = rgba.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    face = rgba.crop(CROP)
    if not face.getbbox():
        raise ValueError("Edgeworth's sprite crop is empty")
    ASSETS.mkdir(parents=True, exist_ok=True)
    images = []
    for size in SIZES:
        canvas = Image.new("RGBA", (size, size))
        room = size - max(2, size // 16)
        scale = min(room / face.width, room / face.height)
        thumb = face.resize((round(face.width * scale), round(face.height * scale)), Image.Resampling.NEAREST)
        canvas.alpha_composite(thumb, ((size - thumb.width) // 2, (size - thumb.height) // 2))
        images.append(canvas)
    images[-1].save(ASSETS / "installer.png")
    images[-1].save(ASSETS / "installer.ico", sizes=[(n, n) for n in SIZES], append_images=images[:-1])
    recipe = {"bundle": BUNDLE, "texture": TEXTURE, "palette": PALETTE,
              "palette_channel": "A", "palette_row": 0, "flip_y": True,
              "crop": list(CROP), "resize": "NEAREST", "sizes": list(SIZES)}
    (ASSETS / "installer.json").write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8")
    print(ASSETS / "installer.ico")


if __name__ == "__main__":
    build()
