"""Прогнать все проверки разом и вернуть один код возврата.

Проверок в проекте много, и запускаются они по одной руками — а значит, часть
из них не запускается вовсе. Это не гипотеза: три дыры, найденные 12 августа 2026,
жили в игре месяц, и каждая была бы видна тому, кто прогнал `audit_text.py`.
Инструмент нужен ровно затем, чтобы прогон стоил одну команду, а не семь.

    python tools/check_all.py           # быстро: только work/*.json, секунды
    python tools/check_all.py --full    # + разбор всех бандлов игры, минуты
    python tools/check_all.py --build   # + собранный бандл (после build.py)
    python tools/check_all.py --all     # всё сразу

Быстрый набор гоняется **на каждой итерации перевода**, до записи в git.
Полный — перед сборкой в игру, вместе с `--build`.

Выходной код ненулевой, если провалилась хоть одна проверка: инструмент годится
как хук и как последний шаг скилла, а не только для чтения глазами.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
# Код возврата 2 у проверки означает «сверять было нечего» — не провал, но и не
# «OK»: молчаливый зелёный на пустом прогоне и есть тот баг, из-за которого
# проверка печатных надписей «проходила», падая на пути к заданию
# (разбор 20 сентября 2026).
NOTHING = 2
# Проверки запускаются из tools/ (см. `run`), поэтому путь к заданию — от корня,
# а не относительный: с относительным проверка печатных надписей падала
# FileNotFoundError и «проходила» ни разу не отработав (найдено 20 сентября 2026).
LABELS1 = str(TOOLS.parent / "work" / "graphics_ru" / "case1" / "labels.json")

# (набор, что проверяем, команда). Порядок — от дешёвого к дорогому: смысла
# читать бандлы нет, если перевод не сходится сам с собой.
CHECKS = [
    ("fast", "реплики: длины, число строк, сохранность кодов", ["check_len.py"]),
    ("fast", "таблицы: длины, теги шрифта, подстановки", ["check_strings.py"]),
    ("fast", "таблицы: строка влезает в окно по ширине букв", ["check_width.py"]),
    ("fast", "кальки с идиом", ["find_idioms.py", "--calques", "--case", "all"]),
    ("fast", "короткий отклик не скопирован на чужую реплику", ["check_echo.py"]),
    ("fast", "род обращения сходится с полом собеседника", ["check_gender.py"]),
    ("fast", "сторож рода сам не ослеп", ["test_check_gender.py"]),
    ("fast", "два хранилища: подписи дела не отстают от реплик", ["check_pipelines.py"]),
    ("fast", "покрытие таблиц: английского по недосмотру нет", ["check_coverage.py"]),
    ("fast", "принятые решения применены везде", ["check_decisions.py"]),
    ("fast", "повторы напарника и служебные реплики одинаковы", ["check_repeats.py"]),
    ("fast", "улику и человека реплика зовёт как таблица", ["check_terms.py"]),
    ("full", "формат .bytes: round-trip по всем бандлам", ["test_tps.py"]),
    ("full", "токенизатор: параметры не текут в текст", ["test_tokens.py"]),
    ("full", "нарезка блоков на сегменты", ["test_segments.py"]),
    ("full", "индекс локализаций", ["test_polyglot_index.py"]),
    ("full", "сторож имён сам не ослеп", ["check_terms.py", "--selftest"]),
    ("full", "проверка картинок сама ловит порчу", ["check_pictures.py", "--selftest"]),
    ("full", "английский эталон совпадает с нетронутым бандлом", ["check_etalon.py"]),
    ("full", "сторож эталона сам не ослеп", ["check_etalon.py", "--selftest"]),
    ("full", "плашки ситуации: набор по заданию, края и обводка", ["plates.py", "--check"]),
    ("full", "заставка «Возражение»: набор и куски атласа по заданию", ["splash.py", "--check"]),
    ("full", "планы дела 1: печатные надписи по замеру английских",
     ["prints.py", LABELS1, "--check"]),
    ("full", "планы дела 1: рукописные пометки по заданию", ["notes.py", "--case", "case1", "--check"]),
    ("full", "вывеска шоу: английское снято целиком, за след не вышли",
     ["sign.py", "--case", "case3", "--check"]),
    ("build", "собранный бандл перед установкой", ["verify_build.py"]),
]


def run(cmd: list[str]) -> tuple[int, str, float]:
    """Запустить проверку тем же питоном, что и мы. Кириллица не должна ломаться."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    started = time.monotonic()
    proc = subprocess.run([sys.executable, str(TOOLS / cmd[0]), *cmd[1:]],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, cwd=TOOLS)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or ""), time.monotonic() - started


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--full", action="store_true", help="+ разбор всех бандлов игры")
    ap.add_argument("--build", action="store_true", help="+ проверка собранного бандла")
    ap.add_argument("--all", action="store_true", help="всё сразу")
    ap.add_argument("--quiet", action="store_true", help="вывод только упавших проверок")
    args = ap.parse_args()

    sets = {"fast"}
    if args.full or args.all:
        sets.add("full")
    if args.build or args.all:
        sets.add("build")

    todo = [(what, cmd) for group, what, cmd in CHECKS if group in sets]
    results: list[tuple[str, int, float, str]] = []

    for what, cmd in todo:
        print(f"… {what}", flush=True)
        code, out, secs = run(cmd)
        results.append((what, code, secs, out))
        if not args.quiet and code in (0, NOTHING):
            # Последняя строка проверки — её собственный вердикт, он информативнее галочки.
            tail = [ln for ln in out.strip().splitlines() if ln.strip()]
            if tail:
                print(f"   {tail[-1][:100]}")

    print(f"\n{'проверка':48} {'итог':>6} {'секунд':>8}")
    failed, skipped = [], []
    for what, code, secs, out in results:
        mark = "OK" if code == 0 else ("ПУСТО" if code == NOTHING else "ПРОВАЛ")
        print(f"{what:48} {mark:>6} {secs:8.1f}")
        if code == NOTHING:
            skipped.append((what, out))
        elif code != 0:
            failed.append((what, out))

    if failed:
        for what, out in failed:
            print(f"\n────── {what}")
            lines = [ln for ln in out.strip().splitlines() if ln.strip()]
            for line in lines[-25:]:
                print("  ", line)
        print(f"\nпровалено проверок: {len(failed)} из {len(results)}")
        return 1

    print(f"\nOK — все {len(results)} проверок зелёные.")
    if "full" not in sets:
        print("(быстрый набор: бандлы игры не читались, перед сборкой гнать --full)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
