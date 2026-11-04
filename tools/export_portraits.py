"""Выгрузить миниатюры картинок органайзера (профили персонажей) для карточек решений.

Пользователь решает спорное ты/вы и тон глазами: ему нужно видеть, **кто** с **кем**
говорит, какого они возраста, — как в игре. Сайты со спрайтами из облака закрыты,
поэтому лица берутся из самой игры: профили в органайзере лежат в `gk2_idcom`
(+`_trial`) рядом с картинками улик. Что из этого профиль, а что улика, по имени
текстуры заранее неизвестно — выгружается всё, мелкой миниатюрой, а разбирает
главная ветка по картинке.

    work/review/portraits/<бандл>/<имя>.jpg   миниатюра, длинная сторона ≤ 192 px
    work/review/portraits/index.json         имя, бандл, исходный размер

Это пиксели игры, поэтому в dev им не место (`work/review/` в .gitignore), а пушатся
они в ветку `review-pack`, только с явным `--push` — вместе со всем пакетом вычитки
через `export_review_pack.push_pack` (временный индекс, рабочее дерево не трогается).

    python tools/export_portraits.py           # только выгрузить в work/review/portraits
    python tools/export_portraits.py --push    # выгрузить и запушить пакет в review-pack
"""
from __future__ import annotations

import argparse
import datetime as dt
import io

from common import BUNDLES, save_json
from export_review_pack import OUT, push_pack

THUMB = 192
DEST = OUT / "portraits"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--push", action="store_true", help="запушить пакет в ветку review-pack")
    ap.add_argument("--glob", default="gk2_idcom*.bundle",
                    help="какие бандлы читать (по умолчанию gk2_idcom*)")
    args = ap.parse_args()

    import UnityPy
    from PIL import Image

    paths = sorted(BUNDLES.glob(args.glob))
    if not paths:
        print(f"! нет бандлов {args.glob} в {BUNDLES}")
        return 1

    index = []
    for path in paths:
        short = path.name.split("_assets_")[0]
        env = UnityPy.load(str(path))
        n = 0
        for obj in env.objects:
            if obj.type.name != "Texture2D":
                continue
            data = obj.read()
            name = getattr(data, "m_Name", None) or getattr(data, "name", "") or f"obj{obj.path_id}"
            try:
                img = data.image
            except Exception as exc:  # noqa: BLE001 — битая текстура не повод ронять выгрузку
                print(f"  ! {short}/{name}: {exc}")
                continue
            if img is None or img.width < 16 or img.height < 16:
                continue
            w, h = img.size
            thumb = img.convert("RGBA")
            thumb.thumbnail((THUMB, THUMB))
            canvas = Image.new("RGB", thumb.size, (255, 255, 255))
            canvas.paste(thumb, mask=thumb.split()[3])
            out = DEST / short / f"{name}.jpg"
            out.parent.mkdir(parents=True, exist_ok=True)
            buf = io.BytesIO()
            canvas.save(buf, "JPEG", quality=82)
            out.write_bytes(buf.getvalue())
            index.append({"bundle": short, "name": name, "w": w, "h": h,
                          "file": out.relative_to(OUT).as_posix()})
            n += 1
        print(f"{short}: {n} картинок")

    save_json(DEST / "index.json", {
        "exported": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(index), "items": index,
    })
    print(f"готово: {len(index)} миниатюр в {DEST}")
    if args.push:
        return push_pack(f"миниатюры органайзера, {len(index)} шт., {dt.date.today().isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
