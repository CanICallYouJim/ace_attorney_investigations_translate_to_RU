"""Установщик русской локализации Ace Attorney Investigations 2.

Ставит перевод на уже установленную игру. Готовых игровых файлов с собой не несёт:
берёт английское содержимое из самой игры, кладёт поверх русский текст и собирает
бандлы на месте. Поэтому патч переживает обновления игры — бандлы ищутся
по префиксу имени, а не по хешу сборки в нём.

    aai2ru.exe                     поставить
    aai2ru.exe --check             только показать, что будет сделано
    aai2ru.exe --uninstall         вернуть оригиналы
    aai2ru.exe --no-graphics       только текст, немецкие надписи оставить
    aai2ru.exe --game-path "D:\\..."  если игру не удалось найти самому

Оригиналы сохраняются в папку `_backup_ru` внутри игры — до первой записи.
Аварийный люк, если и это не поможет: Steam -> свойства игры -> Установленные
файлы -> Проверить целостность файлов игры.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
BACKUP_DIR = "_backup_ru"
STAGING = ".staging"


# --- консоль ------------------------------------------------------------------

def setup_console() -> None:
    """Чтобы кириллица не падала на английской Windows с кодовой страницей 437."""
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


def say(text: str = "") -> None:
    print(text, flush=True)


def fail(text: str) -> int:
    say()
    say("ОШИБКА: " + text)
    return 1


# --- пути ---------------------------------------------------------------------

def data_dir(explicit: str | None) -> Path:
    """Где лежат данные перевода. Рядом с патчером — у собранного, work/ — в репозитории."""
    if explicit:
        return Path(explicit)
    packed = HERE / "data"
    if (packed / "strings.json").exists():
        return packed
    repo = Path(__file__).resolve().parent.parent / "work"
    if (repo / "strings.json").exists():
        return repo
    return packed


def setup_env(game: Path, data: Path, backup: Path) -> None:
    """Нацелить модули tools/ на чужую игру.

    Пути там читаются на импорте (`from common import GAME`), поэтому переменные
    надо выставить до первого импорта — отсюда импорты внутри функций ниже.
    """
    os.environ["AAI2_GAME"] = str(game)
    os.environ["AAI2_WORK"] = str(data)
    os.environ["AAI2_BACKUP"] = str(backup)
    tools = Path(__file__).resolve().parent.parent / "tools"
    if tools.is_dir() and str(tools) not in sys.path:
        sys.path.insert(0, str(tools))       # работа из репозитория
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))        # собранный комплект, всё в одной папке


# --- бэкап и запись -----------------------------------------------------------

def load_manifest(backup: Path) -> dict:
    path = backup / "manifest.json"
    if not path.exists():
        return {"files": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"files": {}}


def save_manifest(backup: Path, manifest: dict) -> None:
    backup.mkdir(parents=True, exist_ok=True)
    (backup / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def replace(staged: Path, target: Path) -> None:
    """Заменить файл игры собранным. Windows отдаёт WinError 5, пока файл открыт.

    Открытым его держит UnityPy: исходный бандл он читает с диска и не закрывает,
    пока его внутренние объекты не соберёт сборщик мусора — они сидят в циклах
    ссылок, и подсчёт ссылок их не освобождает. Отсюда `gc.collect()` перед
    заменой; повторы — на случай антивируса или индексатора, схватившего файл
    на секунду.
    """
    import gc

    gc.collect()
    for attempt in range(6):
        try:
            os.replace(staged, target)
            return
        except PermissionError:
            if attempt == 5:
                raise
            gc.collect()
            time.sleep(0.3 * (attempt + 1))


def install_change(change, game: Path, backup: Path, manifest: dict,
                   keep_original: bool = True) -> str:
    """Сохранить оригинал, положить замену. Возвращает строку отчёта."""
    from common import sha256

    rel = change.target.relative_to(game).as_posix()
    saved = backup / rel

    # Бэкапим только один раз и только то, что лежало до нас: на повторном
    # прогоне в игре уже наш файл, и перезапись бэкапа стёрла бы оригинал.
    if keep_original and (rel not in manifest["files"] or not saved.exists()):
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(change.target, saved)
        manifest["files"][rel] = {"key": change.key, "sha_original": sha256(saved)}

    digest = sha256(change.staged)
    if digest == sha256(change.target):
        change.staged.unlink(missing_ok=True)
        return "уже стоит"

    # staged лежит на том же томе, что и игра, поэтому замена атомарная:
    # оборванный на середине патчер не оставит наполовину записанный бандл.
    replace(change.staged, change.target)
    if rel in manifest["files"]:
        manifest["files"][rel]["sha_patched"] = digest
    return change.note


def uninstall(game: Path, backup: Path) -> int:
    from common import sha256

    manifest = load_manifest(backup)
    if not manifest["files"]:
        return fail(
            "бэкапа нет — возвращать нечем.\n\n"
            "Оригиналы вернёт сама Steam: свойства игры -> Установленные файлы ->\n"
            "Проверить целостность файлов игры.")

    back = broken = 0
    for rel, rec in sorted(manifest["files"].items()):
        saved, target = backup / rel, game / rel
        if not saved.exists():
            say(f"  - нет в бэкапе: {rel}")
            continue
        if sha256(saved) != rec["sha_original"]:
            say(f"  X бэкап испорчен: {rel}")
            broken += 1
            continue
        if target.exists() and sha256(target) == rec["sha_original"]:
            continue
        shutil.copy2(saved, target)
        back += 1
        say(f"  < вернул {rel}")

    say()
    say(f"  Возвращено файлов: {back}" + (f", испорчено в бэкапе: {broken}" if broken else ""))
    say(f"  Бэкап оставлен на месте: {backup}")
    return 1 if broken else 0


# --- проверки перед записью ---------------------------------------------------

def preflight(game: Path, need_bytes: int) -> str | None:
    """Причина, по которой ставить нельзя, или None."""
    from common import game_is_running

    if game_is_running():
        return "игра запущена. Закройте её — Unity держит файлы бандлов открытыми."

    probe = game / f".write-probe-{os.getpid()}"
    try:
        probe.write_bytes(b"x")
        probe.unlink()
    except OSError:
        return ("нет прав на запись в папку игры.\n\n"
                "Игра стоит в защищённой папке. Запустите патчер от имени администратора:\n"
                "правой кнопкой по файлу -> «Запуск от имени администратора».")

    free = shutil.disk_usage(game).free
    if free < need_bytes:
        return (f"на диске мало места: нужно примерно {need_bytes / 2**20:,.0f} МБ "
                f"(файлы плюс бэкап), свободно {free / 2**20:,.0f} МБ.")
    return None


# --- сценарий -----------------------------------------------------------------

def run(args) -> int:
    import locate

    game = locate.find_game(args.game_path)
    if not game:
        if args.game_path:
            return fail(f"в папке «{args.game_path}» нет {locate.MARKER} — это не папка игры.")
        return fail(locate.explain_failure())
    say(f"  Игра найдена: {game}")

    data = data_dir(args.data)
    if not (data / "strings.json").exists():
        return fail(f"рядом с патчером нет данных перевода (искал в {data}).")

    backup = game / BACKUP_DIR
    setup_env(game, data, backup)

    if args.uninstall:
        return uninstall(game, backup)

    import steps

    # --build-only собирает всё в указанную папку и не трогает игру вовсе.
    # Нужен для проверки: собранное можно сличить с тем, что даёт репозиторий.
    stage = Path(args.build_only) if args.build_only else backup / STAGING
    if not args.build_only:
        shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True, exist_ok=True)

    if not args.build_only:
        # Место: самый крупный файл — data.unity3d, и его надо уместить и в бэкапе,
        # и во временной папке. Графика идёт по одному бандлу, но бэкап копит все.
        # Текст: оригинал data.unity3d в бэкапе плюс он же во временной папке.
        # Графика: одновременно лежит только один бандл, но с --backup-graphics
        # к нему добавляются копии всех 2,9 ГБ.
        need = (game / "GK12_Data" / "data.unity3d").stat().st_size * 2
        if not args.no_graphics:
            need += 700 * 2**20 + (3 * 2**30 if args.backup_graphics else 0)
            if args.gk1_graphics:
                need += 2500 * 2**20 if args.backup_graphics else 0
        problem = preflight(game, need)
        if problem:
            return fail(problem)

    manifest = load_manifest(backup)
    manifest.setdefault("files", {})
    manifest["game"] = "Ace Attorney Investigations Collection"
    manifest["installed"] = time.strftime("%Y-%m-%d %H:%M")

    def apply(change, keep_original: bool = True) -> str:
        if args.build_only:
            from common import sha256
            return f"собран, {change.staged.stat().st_size:,} байт, sha {sha256(change.staged)[:12]}"
        return install_change(change, game, backup, manifest, keep_original)

    started = time.time()
    done = 0
    spent: dict[str, float] = {}

    def phase(title: str) -> float:
        say(f"  {title}")
        return time.time()

    try:
        say()
        mark = phase("Собираю реплики...")
        for change in steps.scripts(stage):
            say(f"    {change.key}: {apply(change)}")
            done += 1
        spent["реплики"] = time.time() - mark

        mark = phase("Собираю строковые таблицы...")
        for change in steps.strings(stage):
            say(f"    {change.key}: {apply(change)}")
            done += 1
        spent["таблицы"] = time.time() - mark

        # Первая игра не переводится, но немецкий из неё убрать надо: игрок
        # выбрал «Русский» и не должен упираться в чужой язык.
        mark = phase("Убираю немецкий из первой игры...")
        for change in steps.gk1_scripts(stage):
            say(f"    {change.key}: {apply(change)}")
            done += 1
        spent["первая игра"] = time.time() - mark

        mark = phase("Правлю гарнитуры — самый долгий шаг, файл на 113 МБ...")
        changes = steps.fonts(stage)
        if not changes:
            say("    менять нечего — гарнитуры уже пропатчены")
        for change in changes:
            say(f"    {change.note}")
            say(f"    data.unity3d: {apply(change)}")
            done += 1
        spent["гарнитуры"] = time.time() - mark

        if not args.no_graphics:
            mark = phase("Меняю немецкие надписи, ролики и выкрики на английские.")
            say(f"    Это {'5,2 ГБ и минут двенадцать' if args.gk1_graphics else '2,9 ГБ и минут семь'}:"
                " файлы игры переписываются целиком.")
            if not args.backup_graphics:
                say("    Оригиналы графики не бэкапятся — это ещё 2,9 ГБ на диске."
                    " Вернуть их\n    можно через Steam: Проверить целостность файлов."
                    " Нужен бэкап — ключ --backup-graphics.")
            for i, change in enumerate(steps.graphics(stage, args.gk1_graphics), 1):
                say(f"    [{i}] {change.key}: {apply(change, args.backup_graphics)}")
                done += 1
            spent["графика"] = time.time() - mark
    finally:
        if not args.build_only:
            save_manifest(backup, manifest)
            shutil.rmtree(stage, ignore_errors=True)

    say()
    say(f"  Готово: изменено файлов {done}, за {time.time() - started:.0f} с.")
    say("  " + ", ".join(f"{name} {sec:.0f} с" for name, sec in spent.items()))
    say()
    say("  Запустите игру и выберите в настройках язык «Русский».")
    say(f"  Откат: тот же файл с ключом --uninstall. Оригиналы в {BACKUP_DIR}.")
    return 0


def check(args) -> int:
    """Ничего не менять, показать план."""
    import locate

    game = locate.find_game(args.game_path)
    if not game:
        return fail(locate.explain_failure() if not args.game_path else
                    f"в папке «{args.game_path}» нет {locate.MARKER}.")
    say(f"  Игра найдена: {game}")

    data = data_dir(args.data)
    say(f"  Данные перевода: {data}")
    setup_env(game, data, game / BACKUP_DIR)

    from common import BUNDLES, SCRIPT_PAIR, bundle, load_entries, load_json

    # В комплекте лежат только переведённые сегменты — непереведённые патчеру
    # не нужны. Поэтому общее число берём из version.json, а не из длины списка:
    # иначе счётчик всегда показывал бы честные, но бессмысленные 100%.
    entries = load_entries()
    ru = sum(1 for e in entries if e.get("ru"))
    stats = load_json(data / "version.json", default={}) or {}
    total = stats.get("segments_total", len(entries))
    say()
    say(f"  Реплик переведено: {ru} из {total} ({100 * ru / max(total, 1):.0f}%)")
    if stats.get("strings_total"):
        say(f"  Записей таблиц:    {stats['strings_done']} из {stats['strings_total']}")
    if stats.get("built"):
        say(f"  Перевод собран:    {stats['built']}")
    say("  Будет заменено:")
    for host_key, _ in SCRIPT_PAIR:
        path = bundle(host_key)
        say(f"    {path.name[:70]}  {path.stat().st_size / 2**20:.1f} МБ")
    for key in ("strings_ger", "strings_ger_main"):
        path = bundle(key)
        say(f"    {path.name[:70]}  {path.stat().st_size / 2**20:.1f} МБ")
    main_data = game / "GK12_Data" / "data.unity3d"
    say(f"    {main_data.name}  {main_data.stat().st_size / 2**20:.1f} МБ")

    if not args.no_graphics:
        from swap_localized import category_of
        from steps import CATEGORIES

        total = size = 0
        for path in sorted(BUNDLES.glob("*.bundle")):
            if any(bad in path.name for bad in ("scriptmessage", "string-tables")):
                continue
            if category_of(path.name) in CATEGORIES:
                total += 1
                size += path.stat().st_size
        say(f"    плюс графика: до {total} бандлов, {size / 2**30:.1f} ГБ"
            f" (меняются те, где есть немецкие адреса)")

    say()
    say("  Это была проверка, ничего не изменено.")
    return 0


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        prog="aai2ru", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="только показать, что будет сделано")
    ap.add_argument("--uninstall", action="store_true", help="вернуть оригиналы из бэкапа")
    ap.add_argument("--no-graphics", action="store_true",
                    help="только текст: немецкие надписи и выкрики оставить как есть")
    ap.add_argument("--backup-graphics", action="store_true",
                    help="бэкапить и графику тоже (+2,9 ГБ на диске)")
    ap.add_argument("--gk1-graphics", action="store_true",
                    help="заодно поправить надписи на картинках первой игры (+2,3 ГБ, +5 минут)")
    ap.add_argument("--game-path", help="папка игры, если найти её не удалось")
    ap.add_argument("--data", help="папка с данными перевода (по умолчанию рядом)")
    ap.add_argument("--build-only", metavar="ПАПКА",
                    help="собрать всё в папку и не трогать игру — для проверки")
    ap.add_argument("--no-pause", action="store_true", help="не ждать Enter в конце")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    setup_console()
    args = parse_args(argv)

    say()
    say("  Русская локализация Ace Attorney Investigations 2")
    say("  " + "-" * 48)
    say()

    try:
        code = check(args) if args.check else run(args)
    except KeyboardInterrupt:
        code = fail("прервано с клавиатуры. Уже записанное можно откатить: --uninstall")
    except Exception as exc:
        code = fail(f"{type(exc).__name__}: {exc}")

    if not args.no_pause and sys.stdin and sys.stdin.isatty():
        say()
        say("Нажмите Enter, чтобы закрыть окно.")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
    return code


if __name__ == "__main__":
    raise SystemExit(main())
