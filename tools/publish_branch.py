"""Перенести собранную витрину в ветку `main` и отправить на GitHub.

Ветка `main` — это дерево, которое собрал `publish_release.py`, и ничего кроме:
её содержимое каждый раз заменяется целиком. Руками там править нечего, а если
кто-то поправил — правка потеряется, и это правильно. Иначе витрина разойдётся
с кодом, из которого собрана.

Работа идёт во **временном worktree**, поэтому рабочее дерево `dev` не трогается
вовсе: можно публиковать, не прерывая перевод и не пряча незакоммиченное.

    python tools/publish_branch.py            подготовить коммит, не отправлять
    python tools/publish_branch.py --push     отправить на GitHub
    python tools/publish_branch.py -m "..."   своё сообщение коммита
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from common import PROJECT, load_json

TREE = PROJECT / "dist" / "release"
BRANCH = "main"

# .exe в ветку не кладётся: git не забывает блобы, и каждая пересборка добавляла бы
# 23 МБ в историю навсегда (к 17 августа 2026 их там уже два, 46 МБ из 81 МБ .git).
# Решение пользователя от 17 августа: файл раздаётся через GitHub Releases, а в витрине
# остаётся ссылка на `/releases/latest/download/AAI2-RU.exe` — она всегда ведёт
# на свежий выпуск и не зависит от номера версии.
ASSETS = ("AAI2-RU.exe",)

# Метка в сообщении коммита: по ней видно, что коммит сделан отсюда, а не руками.
# Нужна ровно для одного — не затереть молча правку, внесённую через веб-интерфейс
# GitHub. Такое уже случалось: витрину правили прямо в ветке, а ветка генерируется.
MARKER = "[собрано tools/publish_branch.py]"


def git(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd or PROJECT), check=check,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def default_message() -> str:
    """Сообщение со счётчиками: по коммиту в main видно, что в нём за версия."""
    stats = load_json(TREE / "patcher" / "data" / "version.json", default={}) or {}
    head = f"Витрина и патчер: сборка от {stats.get('built', 'сегодня')}"
    if not stats:
        return head
    return (f"{head}\n\n"
            f"Реплик переведено {stats['segments_done']} из {stats['segments_total']}, "
            f"записей строковых таблиц {stats['strings_done']} из {stats['strings_total']}.\n\n"
            f"Ветка собрана tools/publish_release.py и перенесена tools/publish_branch.py;\n"
            f"руками её править нельзя — разойдётся с кодом. {MARKER}\n\n"
            f"Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>")


def ref_exists(ref: str) -> bool:
    return bool(git("rev-parse", "--verify", "--quiet", ref, check=False).stdout.strip())


def hand_edits(ref: str) -> list[str]:
    """Коммиты ветки, сделанные не отсюда, — начиная с верхушки.

    Смотрим подряд с верхушки вниз до первого нашего: всё, что выше него,
    правка руками, и её вот-вот заменят сгенерированным деревом.
    """
    log = git("log", "--format=%h%x1f%s%x1f%b%x1e", "-20", ref, check=False).stdout
    out = []
    for record in log.split("\x1e"):
        if not record.strip():
            continue
        short, subject, body = (record.strip().split("\x1f") + ["", ""])[:3]
        if MARKER in body or MARKER in subject:
            break
        out.append(f"{short} {subject}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--push", action="store_true", help="отправить ветку на GitHub")
    ap.add_argument("-m", "--message", help="сообщение коммита")
    ap.add_argument("--force", action="store_true",
                    help="публиковать поверх правок, сделанных в ветке руками")
    args = ap.parse_args()

    if not (TREE / "README.md").exists():
        print(f"нет собранной витрины в {TREE} — сначала make release", file=sys.stderr)
        return 1
    if not (TREE / "AAI2-RU.exe").exists():
        print("в дереве нет AAI2-RU.exe — собери с ключом --exe", file=sys.stderr)
        return 1

    git("fetch", "--quiet", "origin", check=False)
    remote = f"origin/{BRANCH}"
    upstream = remote if ref_exists(remote) else (BRANCH if ref_exists(BRANCH) else None)

    if upstream and not args.force:
        stray = hand_edits(upstream)
        if stray:
            print(f"в ветке {upstream} есть правки, сделанные не отсюда:", file=sys.stderr)
            for line in stray:
                print(f"   {line}", file=sys.stderr)
            print("\nЭта ветка генерируется целиком, и публикация их сотрёт.\n"
                  "Перенеси правку в исходник — release/README.md, release/LICENSE —\n"
                  "пересобери (make release) и запусти снова. Если правка уже перенесена\n"
                  "или не нужна: тот же вызов с --force.", file=sys.stderr)
            return 1

    work = Path(tempfile.mkdtemp(prefix="aai2-main-")).resolve()
    # All recursive cleanup below must stay in this newly created temp checkout.
    if work.parent != Path(tempfile.gettempdir()).resolve() or not work.name.startswith("aai2-main-"):
        raise RuntimeError(f"unexpected publication worktree path: {work}")
    shutil.rmtree(work)                      # git worktree хочет несуществующий путь
    try:
        if ref_exists(BRANCH):
            git("worktree", "add", "-f", str(work), BRANCH)
        elif ref_exists(remote):
            git("worktree", "add", "-f", "-b", BRANCH, str(work), remote)
        else:
            git("worktree", "add", "-f", "--detach", str(work))
            git("checkout", "--orphan", BRANCH, cwd=work)
        # Ветку могли править на GitHub: встаём на удалённую верхушку, иначе push
        # упрётся в несовпадение, а правка потеряется вместе с историей.
        if ref_exists(remote):
            git("reset", "--hard", "--quiet", remote, cwd=work)
        # содержимое заменяется целиком: ветка — снимок дерева, а не его история
        git("rm", "-rf", "--quiet", ".", cwd=work, check=False)
        shutil.copytree(TREE, work, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(*ASSETS))
        git("add", "-A", cwd=work)

        if not git("status", "--porcelain", cwd=work).stdout.strip():
            print("в ветке уже ровно это — публиковать нечего")
            return 0

        message = args.message or default_message()
        note = work / ".commit-message"
        note.write_text(message, encoding="utf-8", newline="\n")
        git("commit", "--quiet", "-F", str(note), cwd=work)
        note.unlink(missing_ok=True)

        head = git("log", "-1", "--oneline", cwd=work).stdout.strip()
        print(f"{BRANCH}: {head}")
        for line in git("show", "--stat", "--oneline", "HEAD", cwd=work).stdout.splitlines()[-6:]:
            print("   " + line)

        if args.push:
            git("push", "--quiet", "-u", "origin", BRANCH, cwd=work)
            print(f"отправлено: origin/{BRANCH}")
        else:
            print("\n(коммит готов, но не отправлен; для отправки запусти с --push)")

        remaining = [name for name in ASSETS if (TREE / name).exists()]
        if remaining:
            stats = load_json(TREE / "patcher" / "data" / "version.json", default={}) or {}
            tag = f"v{stats.get('built', 'YYYY-MM-DD')}"
            print("\nВ ветку НЕ положено (раздаётся через GitHub Releases):")
            for name in remaining:
                size = (TREE / name).stat().st_size / 2**20
                print(f"   {name}  {size:.0f} МБ  ->  {TREE / name}")
            print(f"\nВыложить выпуск (нужен gh, иначе руками через веб-интерфейс):"
                  f"\n   gh release create {tag} \"{TREE / ASSETS[0]}\" "
                  f"--title {tag} --notes \"Сборка от {stats.get('built', '')}\"")
            print("Ссылка в витрине ведёт на /releases/latest/download/ — она заработает,\n"
                  "только когда выпуск с этим файлом существует.")
        return 0
    finally:
        git("worktree", "remove", "--force", str(work), check=False)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
