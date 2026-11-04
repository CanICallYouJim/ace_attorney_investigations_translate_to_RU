"""Проверить патч вычитки ДО применения: ключи, коды, окно, «ты/вы» по говорящему.

Редактор сплошной вычитки (ноябрь 2026) сдаёт патч в формате `apply.py`. Всё,
что `check_len.py` поймает только после записи, здесь ловится заранее — тем же
кодом (`check_len.windows`, `check_len.opcodes_of`), чтобы правило было одно:

  * ключ есть в work/case*.json и записан полностью, с `.bytes`;
  * набор кодов совпадает с английским (порядок можно менять);
  * в каждом окне ≤ 2 строк, строка ≤ 53 (узкое окно ≤ 24); длиннее 50 — предупреждение;
  * в реплике есть кириллица, нет латиницы-забытого английского длиннее одного слова;
  * правка не пустая (новый текст отличается от нынешнего).

Плюс сводка по сценам: у кого из говорящих в патче появилось или пропало «ты»/«вы» —
это не ошибка, а список на глаз главной ветке.

    python tools/proof_check.py work/proofread-2026-11/c4/sce3_c0_01.patch.json
    python tools/proof_check.py work/proofread-2026-11/c4/*.patch.json   # пачкой
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from check_len import (LINE_HARD, LINE_SOFT, MAX_LINES, NARROW_LIMIT, NARROW_MODE,
                       opcodes_of, plain_text, windows)
from common import load_entries, load_json
import tps as T

TY = re.compile(r"\b(ты|тебя|тебе|тобой|тобою|твой|твоя|твоё|твое|твои|твоего|твоей|твоих|твоим|твоими|твоему|твою)\b", re.I)
VY = re.compile(r"\b(вы|вас|вам|вами|ваш|ваша|ваше|ваши|вашего|вашей|ваших|вашим|вашими|вашему|вашу)\b", re.I)
LATIN = re.compile(r"[A-Za-z]{2,}(?:\s+[A-Za-z]{2,})+")


def check(patch_path: Path, entries: dict, speakers: dict) -> tuple[list[str], list[str]]:
    errors, warns = [], []
    patch = load_json(patch_path)
    if not isinstance(patch, dict):
        return [f"{patch_path}: патч не словарь id -> текст"], []
    for key, new in patch.items():
        e = entries.get(key)
        if e is None:
            hint = " (нет .bytes в имени файла?)" if ".bytes|" not in key else ""
            errors.append(f"{key}: нет такого id{hint}")
            continue
        if not isinstance(new, str) or not new.strip():
            errors.append(f"{key}: пустой текст")
            continue
        if new == e["ru"]:
            warns.append(f"{key}: текст не изменился")
        try:
            T.from_markup(new)
        except Exception as exc:  # noqa: BLE001 — сообщаем любую поломку разметки
            errors.append(f"{key}: разметка не разобралась — {exc}")
            continue
        lost = opcodes_of(e["en"]) - opcodes_of(new)
        added = opcodes_of(new) - opcodes_of(e["en"])
        if lost or added:
            errors.append(f"{key}: коды не совпали с английским — потеряны "
                          f"{[f'{c:04X}' for c, _ in lost]}, лишние {[f'{c:04X}' for c, _ in added]}")
        text = plain_text(new)
        if not re.search("[а-яё]", text, re.I):
            errors.append(f"{key}: нет кириллицы")
        if LATIN.search(text):
            warns.append(f"{key}: латиница в реплике — {LATIN.search(text).group(0)!r}")
        for n, win in enumerate(windows(new, e.get("mode")), 1):
            if len(win) > MAX_LINES:
                errors.append(f"{key}: окно {n} — {len(win)} строк, влезает {MAX_LINES}")
            for line, mode in win:
                limit = NARROW_LIMIT if mode == NARROW_MODE else LINE_HARD
                if len(line) > limit:
                    errors.append(f"{key}: строка {len(line)} > {limit} — {line!r}")
                elif mode != NARROW_MODE and len(line) > LINE_SOFT:
                    warns.append(f"{key}: строка {len(line)} > {LINE_SOFT} (рабочий лимит) — {line!r}")
        was_ty, now_ty = bool(TY.search(plain_text(e["ru"]))), bool(TY.search(text))
        was_vy, now_vy = bool(VY.search(plain_text(e["ru"]))), bool(VY.search(text))
        if (was_ty, was_vy) != (now_ty, now_vy):
            who = speakers.get(key) or "?"
            warns.append(f"{key}: [{who}] форма обращения сменилась: "
                         f"{'ты' if was_ty else ''}{'вы' if was_vy else ''} → "
                         f"{'ты' if now_ty else ''}{'вы' if now_vy else ''}")
    return errors, warns


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("patches", nargs="+", type=Path)
    args = ap.parse_args()
    entries = {e["id"]: e for e in load_entries()}
    from scene_dump import PACK
    speakers = load_json(PACK / "speakers.json", default={}) or {}
    total_err = 0
    for path in args.patches:
        errors, warns = check(path, entries, speakers)
        n = len(load_json(path) or {})
        print(f"{path.name}: правок {n}, ошибок {len(errors)}, предупреждений {len(warns)}")
        for line in errors:
            print("  ✗", line)
        for line in warns:
            print("  ·", line)
        total_err += len(errors)
    return 1 if total_err else 0


if __name__ == "__main__":
    sys.exit(main())
