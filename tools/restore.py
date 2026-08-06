"""Откат игры к оригинальным файлам из backup/.

Нужен после апдейта Steam, после «Проверить целостность файлов игры»,
или просто чтобы вернуть английскую версию.

    python tools/restore.py           # вернуть оригиналы
    python tools/restore.py --check   # показать, какие игровые файлы сейчас изменены
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from common import BACKUP, CATALOG, MODIFIED, bundle, game_is_running, load_json, sha256

MANIFEST = BACKUP / "manifest.json"


def current_path(name: str) -> Path:
    return CATALOG if name == "catalog" else bundle(name)


def do_check(manifest: dict) -> int:
    modified = 0
    for name, rec in manifest.items():
        live = current_path(name)
        state = "оригинал" if sha256(live) == rec["sha256"] else "ИЗМЕНЁН"
        if state == "ИЗМЕНЁН":
            modified += 1
        print(f"  {state:9s} {name:12s} {live.name}")
    print(f"\nИзменённых файлов: {modified}")
    return 0


def do_restore(manifest: dict) -> int:
    if game_is_running():
        print("GK12.exe запущен — закрой игру, иначе файлы заблокированы.", file=sys.stderr)
        return 1

    restored = 0
    for name, rec in manifest.items():
        src = BACKUP / rec["file"]
        if sha256(src) != rec["sha256"]:
            print(f"  X {name:12s} бэкап не совпадает с манифестом, пропускаю", file=sys.stderr)
            continue
        live = current_path(name)
        if sha256(live) == rec["sha256"]:
            print(f"  = {name:12s} уже оригинал")
            continue
        shutil.copy2(src, live)
        print(f"  < {name:12s} восстановлен")
        restored += 1

    print(f"\nВосстановлено файлов: {restored}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="только показать статус, ничего не менять")
    args = ap.parse_args()

    data = load_json(MANIFEST)
    if not data:
        print("Бэкапа нет — сначала tools/backup.py", file=sys.stderr)
        sys.exit(1)
    sys.exit(do_check(data) if args.check else do_restore(data))
