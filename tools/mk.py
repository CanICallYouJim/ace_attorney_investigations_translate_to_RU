"""Мелочи для Makefile, которые нельзя доверить шеллу.

На Windows make исполняет команды через `cmd`, если рядом не нашлось bash,
а `cmd` не умеет ни прямых слэшей в пути, ни UTF-8 в `echo` — кириллица
превращается в кракозябры. Поэтому всё, что сложнее вызова программы,
живёт здесь: и список целей, и уборка.

    python tools/mk.py            список целей из Makefile
    python tools/mk.py clean      убрать собранное
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent

# Что считается собранным и потому одноразовым. Данные перевода и бэкап
# игры сюда не входят никогда: их не пересоберёшь.
JUNK = ("work/build", "work/build_assets", "dist/release", "dist/.build")


def setup_console() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def show_help() -> int:
    """Список целей — прямо из Makefile, чтобы он не разошёлся с ним.

    Раздел объявляется строкой `##@ Название`, цель — комментарием `## что делает`
    в конце строки с двоеточием.
    """
    text = (PROJECT / "Makefile").read_text(encoding="utf-8")
    print("\n  Ace Attorney Investigations 2 — русская локализация\n")
    for line in text.splitlines():
        section = re.match(r"^##@\s+(.*)", line)
        if section:
            print(f"\n  {section.group(1)}")
            continue
        target = re.match(r"^([a-zA-Z0-9_.-]+):.*?##\s+(.*)", line)
        if target:
            print(f"    make {target.group(1):<14} {target.group(2)}")
    print("\n  Запускать из Git Bash. Игра должна быть закрыта для всего,")
    print("  что пишет в неё: install, graphics, patch, restore.\n")
    return 0


def clean() -> int:
    removed = []
    for rel in JUNK:
        path = PROJECT / rel
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            removed.append(rel)
    caches = [p for p in PROJECT.rglob("__pycache__") if ".venv" not in p.parts]
    for path in caches:
        shutil.rmtree(path, ignore_errors=True)
    print(f"убрано: {', '.join(removed) if removed else 'нечего'}"
          f"{f'; кешей {len(caches)}' if caches else ''}")
    return 0


def main() -> int:
    setup_console()
    command = sys.argv[1] if len(sys.argv) > 1 else "help"
    if command == "clean":
        return clean()
    return show_help()


if __name__ == "__main__":
    raise SystemExit(main())
