"""Найти установленную игру на чужой машине.

Порт логики из tools/installer/install.ps1, проверенной на своей: реестр Steam
даёт корень клиента, `libraryfolders.vdf` — остальные библиотеки (они живут
не только на системном диске), а опознаётся папка по маркеру `GK12.exe`.

Отдельный модуль без зависимостей от UnityPy: его можно гонять и проверять
раньше, чем собран весь патчер.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

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
    return (path / MARKER).exists() and (path / "GK12_Data").is_dir()


def candidates() -> list[Path]:
    """Все места, где игра могла бы стоять, — в порядке правдоподобия."""
    out: list[Path] = []
    for library in steam_libraries():
        out.append(library / "steamapps" / "common" / FOLDER)
    return out


def find_game(explicit: str | os.PathLike | None = None) -> Path | None:
    """Папка игры или None. Явно указанная проверяется на маркер и не угадывается."""
    if explicit:
        path = Path(explicit).expanduser()
        return path.resolve() if is_game_dir(path) else None
    for path in candidates():
        if is_game_dir(path):
            return path.resolve()
    return None


def explain_failure() -> str:
    """Что показать человеку, когда игра не нашлась: где именно смотрели."""
    libraries = steam_libraries()
    if not libraries:
        return ("Steam не найден: ни в реестре, ни в Program Files.\n"
                "Укажите папку игры вручную — ту, в которой лежит " + MARKER + ".")
    lines = ["Steam найден, но игры в его библиотеках нет. Смотрели здесь:"]
    lines += [f"  {path}" for path in candidates()]
    lines.append("")
    lines.append("Если игра стоит в другом месте, укажите папку вручную — ту, "
                 "в которой лежит " + MARKER + ".")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    game = find_game(sys.argv[1] if len(sys.argv) > 1 else None)
    if game:
        print(f"игра: {game}")
        sys.exit(0)
    print(explain_failure(), file=sys.stderr)
    sys.exit(1)
