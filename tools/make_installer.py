"""Собрать переносимый комплект локализации для другого компьютера.

Требование пользователя от 7 августа 2026: в конце работы нужен комплект, который
на чужой машине ставит перевод сам — без этого репозитория, без venv, без ручного
указания путей. Игра там стоит из Steam, а вот Python может отсутствовать вовсе,
поэтому сам установщик написан на PowerShell (он есть в любой Windows) и лежит
рядом с файлами: `install.bat` -> `install.ps1`.

Ставятся **готовые файлы**, а не правки на месте. Причина: правку шрифтов и подмену
графики делает UnityPy, тащить его на чужую машину — значит тащить туда Python
с пакетами. Байтовой дельтой обойтись тоже нельзя: UnityPy пересобирает бандл
целиком, и размер файла меняется (data.unity3d худеет на 15 МБ, gk2_mapbg толстеет
на 1,2 МБ), так что «тот же файл со сдвигом в пару байт» — не наш случай.

Отсюда деление на две части:

* **текст** (~110 МБ) — шрифт `data.unity3d`, бандл реплик и две таблицы строк.
  Без этого перевода нет вообще: без шрифта кириллица не рисуется;
* **графика** (~2,9 ГБ, флаг `--graphics`) — 35 бандлов, где немецкие картинки,
  ролики и выкрики заменены английскими. Без неё игра читается по-русски, но
  «Einspruch!» и заставки остаются немецкими.

    python tools/make_installer.py                 # только текст
    python tools/make_installer.py --graphics      # плюс графика, 3 ГБ
    python tools/make_installer.py --out D:/AAI2   # куда складывать
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from common import BACKUP, GAME, PROJECT, bundle, load_json, sha256

MANIFEST = BACKUP / "manifest.json"
TEMPLATES = PROJECT / "tools" / "installer"
DEFAULT_OUT = PROJECT / "dist" / "AAI2-RU"

# Ключи манифеста, попадающие в текстовую часть. Остальные изменённые файлы —
# графика и звук, их заносит swap_localized.py под ключами asset_*/font_*.
TEXT_KEYS = ("font_data.unity3d", "script_ger", "strings_ger", "strings_ger_main")


def live_path(name: str, rec: dict) -> Path:
    """Где этот файл лежит в живой игре."""
    if name.startswith(("font_", "asset_")):
        return Path(rec["source"])
    return bundle(name)


def relative_to_game(path: Path) -> str:
    """Путь внутри папки игры — по нему установщик и разложит файлы обратно."""
    return path.relative_to(GAME).as_posix()


def collect(manifest: dict, with_graphics: bool) -> list[dict]:
    """Изменённые файлы игры -> записи комплекта, без дублей по пути."""
    seen: dict[str, dict] = {}
    for name, rec in sorted(manifest.items()):
        if name == "catalog":
            continue
        is_text = name in TEXT_KEYS
        if not is_text and not with_graphics:
            continue
        live = live_path(name, rec)
        if not live.exists():
            print(f"  ! {name}: файла нет в игре, пропускаю", file=sys.stderr)
            continue
        digest = sha256(live)
        if digest == rec["sha256"]:
            print(f"  = {name}: в игре оригинал, в комплект не идёт")
            continue
        rel = relative_to_game(live)
        # у gk_common_ingameui две записи в манифесте на один и тот же файл
        if rel in seen:
            continue
        seen[rel] = {
            "name": name,
            "path": rel,
            "part": "text" if is_text else "graphics",
            "size": live.stat().st_size,
            "sha_original": rec["sha256"],
            "sha_translated": digest,
        }
    return list(seen.values())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--graphics", action="store_true",
                    help="добавить 35 бандлов графики и звука (+2,9 ГБ)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="куда собрать комплект")
    ap.add_argument("--dry-run", action="store_true", help="только показать состав")
    args = ap.parse_args()

    manifest = load_json(MANIFEST)
    if not manifest:
        print("Бэкапа нет — сначала tools/backup.py", file=sys.stderr)
        return 1

    files = collect(manifest, args.graphics)
    if not files:
        print("В игре нет изменённых файлов — ставить нечего.", file=sys.stderr)
        return 1

    total = sum(f["size"] for f in files)
    text_n = sum(1 for f in files if f["part"] == "text")
    print(f"\nв комплекте: {len(files)} файлов, {total / 1073741824:.2f} ГБ"
          f"  (текст {text_n}, графика {len(files) - text_n})")
    for f in sorted(files, key=lambda x: -x["size"]):
        print(f"   {f['size'] / 1048576:9.1f} МБ  {f['part']:8}  {f['path']}")
    if args.dry_run:
        return 0

    out = args.out
    data = out / "data"
    if out.exists():
        shutil.rmtree(out)
    data.mkdir(parents=True)

    for i, f in enumerate(sorted(files, key=lambda x: x["path"]), 1):
        dst = data / f["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        print(f"  [{i}/{len(files)}] {f['path']}")
        shutil.copy2(GAME / f["path"], dst)

    (out / "files.json").write_text(json.dumps({
        "game": "Ace Attorney Investigations Collection",
        "appid": 2401970,
        "marker": "GK12.exe",
        "files": files,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    for tpl in ("install.bat", "install.ps1", "README.txt"):
        shutil.copy2(TEMPLATES / tpl, out / tpl)

    print(f"\n-> {out}")
    print("   Переносить папку целиком. На той машине — двойной клик по install.bat.")
    if not args.graphics:
        print("   Графика в комплект не вошла: немецкие картинки и выкрики останутся"
              " немецкими.\n   Нужна — пересобрать с --graphics (+2,9 ГБ).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
