"""Найти установленную игру на чужой машине.

Сначала проверяет папку патчера, текущую папку и библиотеки Steam, затем
ищет на подключённых локальных дисках. Папка распознаётся по файлу GK12.exe
и каталогу GK12_Data. Явный --game-path имеет приоритет над поиском.

Отдельный модуль без зависимостей от UnityPy: его можно гонять и проверять
раньше, чем собран весь патчер.
"""
from __future__ import annotations

import os
import re
import stat
import sys
import time
from pathlib import Path
from typing import Callable

MARKER = "GK12.exe"
APPID = 2401970
FOLDER = "Ace Attorney Investigations Collection"

# Ключи реестра, где Steam хранит путь к себе. HKCU первым: если клиентов два,
# запускается тот, что прописан у пользователя.
REGISTRY_KEYS = (
    ("HKCU", r"Software\Valve\Steam", "SteamPath"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
    ("HKLM", r"SOFTWARE\Valve\Steam", "InstallPath"),
)


def _registry_values() -> list[Path]:
    try:
        import winreg
    except ImportError:  # не Windows — тогда и Steam искать негде
        return []

    roots = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
    out: list[Path] = []
    for root, path, name in REGISTRY_KEYS:
        try:
            with winreg.OpenKey(roots[root], path) as key:
                value, _ = winreg.QueryValueEx(key, name)
        except OSError:
            continue
        if value:
            out.append(Path(str(value).replace("/", "\\")))
    return out


def steam_roots() -> list[Path]:
    """Корни клиента Steam: из реестра плюс обычные места, без дублей."""
    guesses = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Steam",
    ]
    seen: dict[str, Path] = {}
    for path in _registry_values() + guesses:
        if path.exists():
            seen.setdefault(str(path).lower(), path)
    return list(seen.values())


def steam_libraries() -> list[Path]:
    """Все библиотеки Steam. Игра может лежать на любом диске, путь берём из vdf.

    Формат там свой, но нужная строка всегда выглядит как  "path"  "D:\\\\SteamLibrary" —
    парсить весь vdf ради одного ключа незачем.
    """
    seen: dict[str, Path] = {}
    for root in steam_roots():
        seen.setdefault(str(root).lower(), root)
        for vdf in (root / "steamapps" / "libraryfolders.vdf",
                    root / "config" / "libraryfolders.vdf"):
            if not vdf.exists():
                continue
            try:
                text = vdf.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in re.finditer(r'"path"\s*"([^"]+)"', text):
                path = Path(match.group(1).replace("\\\\", "\\"))
                if path.exists():
                    seen.setdefault(str(path).lower(), path)
    return list(seen.values())


def is_game_dir(path: Path) -> bool:
    try:
        return (path / MARKER).is_file() and (path / "GK12_Data").is_dir()
    except OSError:
        return False


def nearby_candidates() -> list[Path]:
    """У собранного EXE __file__ лежит в распаковке, поэтому нужен sys.executable."""
    home = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    out = [home]
    try:
        out.append(Path.cwd())
    except OSError:
        pass
    return out


def local_drives() -> list[Path]:
    """Доступные локальные тома Windows, включая USB; сетевые диски не обходятся."""
    if os.name != "nt":
        return []
    import ctypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetLogicalDrives.restype = ctypes.c_uint32
    kernel.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
    kernel.GetDriveTypeW.restype = ctypes.c_uint
    mask = kernel.GetLogicalDrives()
    out = []
    for index in range(26):
        if not mask & (1 << index):
            continue
        root = Path(f"{chr(ord('A') + index)}:/")
        # DRIVE_REMOVABLE, DRIVE_FIXED, DRIVE_RAMDISK.
        try:
            if kernel.GetDriveTypeW(str(root)) in (2, 3, 6) and root.is_dir():
                out.append(root)
        except OSError:
            continue
    return out


def _is_reparse_dir(path: Path) -> bool:
    """Не входить в junction/symlink: они могут зациклить обход или увести в сеть."""
    try:
        info = path.stat(follow_symlinks=False)
    except OSError:
        return True
    return (stat.S_ISLNK(info.st_mode)
            or bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT))


def search_drive(root: Path, progress: Callable[[str], None] | None = None) -> Path | None:
    """Обход без ограничения глубины; недоступные каталоги os.walk пропускает."""
    last_report = time.monotonic()
    checked = 0
    preferred = {"games", "game", "игры", "gog games", "steamapps", "common"}
    for folder, dirs, files in os.walk(root, followlinks=False):
        here = Path(folder)
        dirs[:] = sorted(
            (name for name in dirs
             if name.casefold() not in {"$recycle.bin", "system volume information"}
             and not _is_reparse_dir(here / name)),
            key=lambda name: (name.casefold() not in preferred, name.casefold()),
        )
        checked += 1
        if any(name.casefold() == MARKER.casefold() for name in files) and is_game_dir(here):
            return here.resolve()
        if progress and time.monotonic() - last_report >= 10:
            progress(f"  Поиск на {root}: проверено папок {checked:,}".replace(",", " "))
            last_report = time.monotonic()
    return None


def candidates() -> list[Path]:
    """Все места, где игра могла бы стоять, — в порядке правдоподобия."""
    out: list[Path] = []
    for library in steam_libraries():
        out.append(library / "steamapps" / "common" / FOLDER)
    return out


def find_game(explicit: str | os.PathLike | None = None,
              progress: Callable[[str], None] | None = None) -> Path | None:
    """Папка игры или None. Явно указанная проверяется на маркер и не угадывается."""
    if explicit:
        path = Path(explicit).expanduser()
        return path.resolve() if is_game_dir(path) else None
    for path in nearby_candidates() + candidates():
        if is_game_dir(path):
            return path.resolve()
    for root in local_drives():
        if progress:
            progress(f"  Ищу {MARKER} на {root} ...")
        found = search_drive(root, progress)
        if found:
            return found
    return None


def explain_failure() -> str:
    """Что показать человеку, когда игра не нашлась: где именно смотрели."""
    return ("Не удалось найти игру автоматически.\n"
            "Проверены папка патчера, текущая папка, библиотеки Steam "
            "и доступные локальные диски.\n\n"
            "Укажите папку игры вручную: --game-path \"D:\\Games\\папка игры\"\n"
            "В ней должны лежать " + MARKER + " и папка GK12_Data.")


if __name__ == "__main__":
    game = find_game(sys.argv[1] if len(sys.argv) > 1 else None, progress=print)
    if game:
        print(f"игра: {game}")
        sys.exit(0)
    print(explain_failure(), file=sys.stderr)
    sys.exit(1)
