"""Read-only loading-screen assets from the player's own installed game.

No game images are shipped. ``output`` must be a caller-owned temporary directory.
Scene labels come from the existing translation table; the allow-list covers only
the opening of GK2 episode one, so an installer cannot reveal later chapter names.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path


SCENE_KEYS = (
    "36231574053650538",  # Opening
    "36231574053650539",  # Edgeworth's Arrival
    "36231574053650542",  # The Investigation Begins
)


def check_chapters(data: Path, report) -> None:
    """Validate the five shipped chapter datasets before enabling installation."""
    for chapter in range(1, 6):
        source = data / f"case{chapter}.json"
        payload = json.loads(source.read_text(encoding="utf-8"))
        rows = payload.get("entries")
        if payload.get("case") != chapter or not isinstance(rows, list) or not rows:
            raise ValueError(f"Глава {chapter}: неверные или пустые данные перевода.")
        for row in rows:
            if not isinstance(row, dict) or not all(isinstance(row.get(key), str) and row[key]
                                                  for key in ("file", "block", "ru")):
                raise ValueError(f"Глава {chapter}: повреждённая или незаполненная запись.")
            if not isinstance(row.get("index"), int) or row["index"] < 0:
                raise ValueError(f"Глава {chapter}: неверный номер записи.")
        report({"kind": "chapter", "chapter": chapter, "count": len(rows)})


def scene_names() -> list[str]:
    """Read current agreed translations, including a frozen release's data."""
    here = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates = []
    if os.environ.get("AAI2_WORK"):
        candidates.append(Path(os.environ["AAI2_WORK"]) / "strings.json")
    candidates.extend((here / "data" / "strings.json",
                       Path(__file__).resolve().parent.parent / "work" / "strings.json"))
    for source in candidates:
        try:
            rows = json.loads(source.read_text(encoding="utf-8"))["tables"]["gk_common_title"]
            names = []
            for key in SCENE_KEYS:
                row = rows.get(key, {})
                name = row.get("ru") or row.get("en")
                if name and name not in names:
                    names.append(name)
            if names:
                return names
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return []


def prepare(game: Path, output: Path) -> dict:
    """Extract the opening map; never save or modify a game bundle.

    Missing/updated game resources are nonfatal: the UI can keep its plain
    background and the installation proceeds normally.
    """
    result = {"background": None, "scenes": scene_names(), "source": None}
    folder = Path(game) / "GK12_Data" / "StreamingAssets" / "aa" / "StandaloneWindows64"
    source = next(folder.glob("gk2_mapbg_trial_assets_all_*.bundle"), None)
    if source is None:
        return result
    try:
        import UnityPy
        from PIL import Image, ImageEnhance, ImageOps

        env = UnityPy.load(str(source))
        # Language-neutral original. Map00 is the opening Gourd Lake map,
        # without characters or later-story content.
        for obj in env.objects:
            if obj.type.name == "Texture2D" and obj.peek_name() == "map00":
                image = obj.read().image.convert("RGB")
                image = ImageOps.fit(image, (1100, 700), method=Image.Resampling.LANCZOS)
                image = ImageEnhance.Color(image).enhance(0.65)
                image = ImageEnhance.Brightness(image).enhance(0.48)
                output = Path(output)
                output.mkdir(parents=True, exist_ok=True)
                target = output / "loading-background.png"
                image.save(target)
                result.update(background=target, source=f"{source.name}:map00")
                break
    except Exception as exc:
        result["warning"] = "Фон недоступен:\n" + traceback.format_exc()
    return result
