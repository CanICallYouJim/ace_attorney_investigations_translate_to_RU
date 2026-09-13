"""Собрать дерево ветки `main` — то, что видит и скачивает игрок.

Ветка `main` не пишется руками: она **генерируется** из этого репозитория, как
gh-pages. Иначе витрина неминуемо разойдётся с кодом — README будет обещать одно,
а патчер делать другое.

Что складывается:

    <out>/patcher/*.py        точка входа и модули tools/, от которых она зависит
    <out>/patcher/data/       данные перевода, урезанные до нужных полей
    <out>/patcher/data/graphics_layers/   слой русских надписей: только наши пиксели
    <out>/patcher/requirements.txt

Список модулей не выписан руками, а вычисляется: разбираем импорты `aai2ru.py`
и идём по ним вглубь. Забыть модуль поэтому нельзя, а лишний не попадёт.

Данные режутся до того, что читает сборка: непереведённые сегменты патчеру
не нужны вовсе (`build.py` смотрит только на заполненное `ru`), а служебные поля
не нужны тем более. 6,3 МБ превращаются примерно в 2,5.

    python tools/publish_release.py                  # собрать дерево
    python tools/publish_release.py --exe            # плюс собрать AAI2-RU.exe
    python tools/publish_release.py --out D:/release
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from common import CASES, DOCS, PROJECT, WORK, case_json, load_json, save_json

PATCHER = PROJECT / "patcher"
SHOWCASE = PROJECT / "release"     # исходник витрины: README, лицензия, кадры
TOOLS = PROJECT / "tools"
DEFAULT_OUT = PROJECT / "dist" / "release"
ENTRY = "aai2ru"
EXE_NAME = "AAI2-RU"

# Пакеты, без которых патчер не соберёт бандлы. Версии фиксируются те, на которых
# всё проверено: UnityPy меняет внутренности от версии к версии.
REQUIREMENTS = """\
# Зависимости патчера. Ставятся только тем, кто запускает его скриптом,
# а не .exe: в .exe они уже внутри.
#
#     pip install -r requirements.txt
#     python aai2ru.py
#
UnityPy=={unitypy}
fonttools=={fonttools}
"""


def module_closure(entry: str) -> list[Path]:
    """Все локальные модули, до которых дотягивается точка входа."""
    search = [PATCHER, TOOLS]
    found: dict[str, Path] = {}
    queue = [entry]
    while queue:
        name = queue.pop()
        if name in found:
            continue
        path = next((d / f"{name}.py" for d in search if (d / f"{name}.py").exists()), None)
        if path is None:
            continue                    # сторонний пакет — не наша забота
        found[name] = path
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                queue += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                queue.append(node.module.split(".")[0])
    return [found[k] for k in sorted(found)]


def slim_entries() -> tuple[dict, dict]:
    """Переводы реплик, урезанные до полей, которые читает сборка."""
    keep = ("file", "block", "index", "en", "ru")
    out: dict[int, list[dict]] = {}
    total = done = 0
    for case in CASES:
        data = load_json(case_json(case))
        if not data:
            continue
        total += len(data["entries"])
        rows = [{k: e[k] for k in keep} for e in data["entries"] if e.get("ru")]
        done += len(rows)
        out[case] = rows
    return out, {"segments_total": total, "segments_done": done}


def slim_strings() -> tuple[dict, dict]:
    """Переводы строковых таблиц — только записи с русским."""
    data = load_json(WORK / "strings.json")
    tables = {}
    total = done = 0
    for name, rows in data["tables"].items():
        total += len(rows)
        kept = {key: {"ru": row["ru"]} for key, row in rows.items() if row.get("ru")}
        done += len(kept)
        if kept:
            tables[name] = kept
    return {"source": data.get("source"), "tables": tables}, \
           {"strings_total": total, "strings_done": done}


def copy_layers(dest: Path) -> int:
    """Слой русских надписей — в данные патчера. Устаревший слой не везём.

    Готовых картинок в комплекте нет и быть не может: витрина обещает «ни одного
    файла игры». Едет только слой — наши пиксели и рецепты, — и склеивается
    у игрока из его же текстуры (`picture_layer.py`). Листы для показа
    остаются дома: это кадры игры.
    """
    from layer_localized import stale
    from picture_layer import FOLDER

    problems = stale()
    if problems:
        raise SystemExit("слой русских надписей в выпуск не годится:\n  " + "\n  ".join(problems))
    manifest = load_json(FOLDER / "manifest.json")
    if not manifest or not manifest["pictures"]:
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    save_json(dest / "manifest.json", manifest)
    for entry in manifest["pictures"]:
        for rel in (entry.get("layer"), entry.get("mask")):
            if rel:
                (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(FOLDER / rel, dest / rel)
    size = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
    print(f"слой русских надписей: картинок {len(manifest['pictures'])}, {size / 1024:.0f} КБ")
    return len(manifest["pictures"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="куда собирать")
    ap.add_argument("--exe", action="store_true", help="собрать ещё и .exe через PyInstaller")
    args = ap.parse_args()

    out = args.out
    patcher_out = out / "patcher"
    if patcher_out.exists():
        shutil.rmtree(patcher_out)
    data_out = patcher_out / "data"
    data_out.mkdir(parents=True)

    modules = module_closure(ENTRY)
    print(f"модулей: {len(modules)}")
    for path in modules:
        shutil.copy2(path, patcher_out / path.name)
        print(f"   {path.parent.name}/{path.name}")

    # Таблица опкодов — не документация, а данные разбора: без неё tps.py
    # не прочитает ни одной реплики. Ложится рядом с модулями, там её и ищет.
    shutil.copy2(DOCS / "opcodes.json", patcher_out / "opcodes.json")

    entries, stats = slim_entries()
    for case, rows in entries.items():
        name = "common.json" if case == 0 else f"case{case}.json"
        save_json(data_out / name, {"case": case, "entries": rows})
    strings, more = slim_strings()
    save_json(data_out / "strings.json", strings)
    stats |= more
    stats["pictures_done"] = copy_layers(data_out / "graphics_layers")

    stats |= {
        "built": time.strftime("%Y-%m-%d"),
        "unitypy": version_of("UnityPy"),
        "fonttools": version_of("fonttools"),
    }
    save_json(data_out / "version.json", stats)
    (patcher_out / "requirements.txt").write_text(
        REQUIREMENTS.format(unitypy=stats["unitypy"], fonttools=stats["fonttools"]),
        encoding="utf-8")

    write_showcase(out, stats)

    size = sum(p.stat().st_size for p in patcher_out.rglob("*") if p.is_file())
    print(f"\nреплик:  {stats['segments_done']} из {stats['segments_total']}")
    print(f"таблицы: {stats['strings_done']} из {stats['strings_total']}")
    print(f"дерево:  {out}  ({size / 2**20:.1f} МБ)")

    if args.exe:
        return build_exe(patcher_out, out)
    print("\n(.exe не собирался; для сборки запусти с --exe)")
    return 0


def write_showcase(out: Path, stats: dict) -> None:
    """README витрины, лицензия и кадры.

    Счётчики в README подставляются отсюда, а не пишутся руками: витрина, которая
    врёт о том, сколько переведено, хуже отсутствующей. Кадр вставляется только
    если файл есть — иначе на странице висела бы битая картинка.
    """
    press_src = SHOWCASE / "press"
    if press_src.is_dir():
        shutil.copytree(press_src, out / "press", dirs_exist_ok=True)

    def shot(match: re.Match) -> str:
        name, _, caption = match.group(1).partition("|")
        if not (press_src / name).exists():
            print(f"   кадра нет, пропускаю: {name}")
            return ""
        return f"![{caption}](press/{name})"

    text = (SHOWCASE / "README.md").read_text(encoding="utf-8")
    for key, value in stats.items():
        text = text.replace("{{" + key + "}}", f"{value:,}".replace(",", " ")
                            if isinstance(value, int) else str(value))
    text = re.sub(r"\{\{shot:([^}]+)\}\}", shot, text)

    # Ролик живёт на CDN гитхаба: файл в репозитории плеером не показывается.
    # Ссылку кладёт человек в release/press/video.txt — см. docs/press-kit.md.
    video = press_src / "video.txt"
    text = text.replace("{{video}}", video.read_text(encoding="utf-8").strip()
                        if video.exists() else "")
    text = re.sub(r"\n{3,}", "\n\n", text)

    exe = out / f"{EXE_NAME}.exe"
    if exe.exists():
        text = text.replace("{{exe_mb}}", f"{exe.stat().st_size / 2**20:.0f}")

    (out / "README.md").write_text(text, encoding="utf-8", newline="\n")
    shutil.copy2(SHOWCASE / "LICENSE", out / "LICENSE")
    # {{exe_mb}} закрывается позже, после сборки .exe — он тут не остаток.
    left = [m for m in re.findall(r"\{\{[^}]+\}\}", text) if m != "{{exe_mb}}"]
    if left:
        print(f"   ! в README остались незакрытые подстановки: {left}", file=sys.stderr)


def version_of(package: str) -> str:
    from importlib.metadata import version

    try:
        return version(package)
    except Exception:
        return "0"


def build_exe(patcher_out: Path, out: Path) -> int:
    """PyInstaller: один файл, данные внутри, консольное окно."""
    work = out / ".build"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--console", "--clean", "--noconfirm",
        "--name", EXE_NAME,
        "--distpath", str(out),
        "--workpath", str(work),
        "--specpath", str(work),
        "--add-data", f"{patcher_out / 'data'}{';'}data",
        # Внутри .exe у модулей __file__ указывает в распакованный _MEIPASS,
        # поэтому таблица опкодов должна лечь в его корень — рядом с ними.
        "--add-data", f"{patcher_out / 'opcodes.json'}{';'}.",
        # UnityPy тащит с собой ресурсы (описания типов) и грузит часть модулей
        # по имени в рантайме — анализатор PyInstaller их не видит, и собранный
        # .exe падает на первом же бандле: «No module named UnityPy.resources».
        "--collect-all", "UnityPy",
        "--collect-all", "fontTools",
        # etcpak UnityPy импортирует изнутри функции, в момент упаковки BC7.
        # Без явного имени анализатор может его пропустить, и русские картинки
        # у игрока лягут несжатыми — вчетверо тяжелее.
        "--hidden-import", "etcpak",
        "--paths", str(patcher_out),
        str(patcher_out / f"{ENTRY}.py"),
    ]
    print("\n" + " ".join(cmd[:8]) + " ...")
    result = subprocess.run(cmd)
    if result.returncode:
        print("PyInstaller не собрал .exe", file=sys.stderr)
        return result.returncode

    exe = out / f"{EXE_NAME}.exe"
    print(f"\n-> {exe}  ({exe.stat().st_size / 2**20:.1f} МБ)")
    shutil.rmtree(work, ignore_errors=True)

    # Размер .exe подставляется после сборки: в README он должен быть замером,
    # а не обещанием. Заодно это последняя незакрытая подстановка — проверка
    # на остатки в write_showcase про неё знает и ругаться перестанет.
    readme = out / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").replace(
        "{{exe_mb}}", f"{exe.stat().st_size / 2**20:.0f}"), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
