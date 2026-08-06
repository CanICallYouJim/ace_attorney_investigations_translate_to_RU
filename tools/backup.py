"""Бэкап оригинальных игровых файлов перед модификацией.

Пишет копии в backup/ и manifest.json с SHA-256 — restore.py по нему проверяет,
что кладёт обратно именно оригинал, а не уже пропатченный файл.

    python tools/backup.py            # создать бэкап (не перезаписывает существующий)
    python tools/backup.py --verify   # проверить, что бэкап цел и совпадает с манифестом
"""
from __future__ import annotations

import argparse
import shutil
import sys

from common import BACKUP, CATALOG, MODIFIED, bundle, load_json, save_json, sha256

MANIFEST = BACKUP / "manifest.json"


def targets() -> dict[str, "object"]:
    items = {name: bundle(name) for name in MODIFIED}
    items["catalog"] = CATALOG
    return items


def do_backup() -> int:
    BACKUP.mkdir(parents=True, exist_ok=True)
    manifest = load_json(MANIFEST, default={}) or {}
    changed = False

    for name, src in targets().items():
        dst = BACKUP / src.name
        if dst.exists() and name in manifest:
            if sha256(dst) == manifest[name]["sha256"]:
                print(f"  = {name:12s} уже в бэкапе")
                continue
            print(f"  ! {name:12s} бэкап повреждён, перезаписываю", file=sys.stderr)

        digest = sha256(src)
        print(f"  + {name:12s} {src.name} ({src.stat().st_size:,} B)")
        shutil.copy2(src, dst)
        manifest[name] = {"file": src.name, "source": str(src), "sha256": digest}
        changed = True

    if changed:
        save_json(MANIFEST, manifest)
    print(f"\nБэкап: {BACKUP}")
    return 0


def do_verify() -> int:
    manifest = load_json(MANIFEST)
    if not manifest:
        print("Бэкапа нет — сначала запусти без --verify", file=sys.stderr)
        return 1

    bad = 0
    for name, rec in manifest.items():
        dst = BACKUP / rec["file"]
        if not dst.exists():
            print(f"  X {name:12s} файл бэкапа пропал: {dst.name}")
            bad += 1
            continue
        if sha256(dst) != rec["sha256"]:
            print(f"  X {name:12s} SHA-256 не совпадает")
            bad += 1
        else:
            print(f"  OK {name:12s} {rec['file']}")

    if bad:
        print(f"\n{bad} проблем(ы) в бэкапе", file=sys.stderr)
    else:
        print("\nБэкап цел.")
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", action="store_true", help="только проверить целостность бэкапа")
    args = ap.parse_args()
    sys.exit(do_verify() if args.verify else do_backup())
