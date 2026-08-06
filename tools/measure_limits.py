"""Замерить, сколько символов реально помещается в строку окна реплики.

Лимит нигде не записан, поэтому выводим его из самих локализаций: берём все реплики
и смотрим, какой длины строки допускали переводчики. Немецкий тут главный ориентир —
он длиннее английского и ближе всего к русскому по среднему приросту.

Реплика — это участок между кодом «начало текста» (E107) и «конец текста» (E102).
Внутри неё строки разделяются обычным \\n; коды и их параметры при подсчёте выбрасываются,
иначе в длину попадает служебная начинка.

    python tools/measure_limits.py
"""
from __future__ import annotations

import collections
import statistics

from common import SCRIPT_LANGS, in_case_scope, read_scripts
import tps as T

TEXT_START = 0xE107
TEXT_END = 0xE102


def messages(text: str):
    """(param у E107, список строк) для каждой реплики блока."""
    tokens = T.tokenize(text)
    param = None
    buf: list[str] = []
    for tok in tokens:
        if isinstance(tok, T.Op):
            if tok.code == TEXT_START:
                param = ord(tok.params[0]) if tok.params else -1
                buf = []
            elif tok.code == TEXT_END and param is not None:
                yield param, "".join(buf).split("\n")
                param = None
            continue
        if param is not None:
            buf.append(tok)


def message_lines(text: str):
    for param, lines in messages(text):
        for line in lines:
            yield param, line


def pct(values: list[int], p: float) -> int:
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * p))]


def main() -> int:
    per_lang: dict[str, dict[int, list[int]]] = {}
    for lang in SCRIPT_LANGS:
        by_param: dict[int, list[int]] = collections.defaultdict(list)
        for name, raw in read_scripts(f"script_{lang}").items():
            if not in_case_scope(name):
                continue
            for block in T.parse(raw).blocks:
                for param, line in message_lines(block.text):
                    by_param[param].append(len(line))
        per_lang[lang] = by_param

    print("=== по режиму реплики (параметр E107) ===")
    print(f"{'режим':>6} {'язык':>5} {'строк':>7} {'медиана':>8} {'p95':>5} {'p99':>5} {'max':>5}")
    params = sorted(per_lang["eng"], key=lambda p: -len(per_lang["eng"][p]))
    for param in params:
        if len(per_lang["eng"][param]) < 50:
            continue
        for lang in ("eng", "fre", "ger"):
            xs = per_lang[lang].get(param, [])
            if not xs:
                continue
            print(f"{param:>6} {lang:>5} {len(xs):>7} {statistics.median(xs):>8.0f} "
                  f"{pct(xs, .95):>5} {pct(xs, .99):>5} {max(xs):>5}")
        print()

    print("=== все реплики дела 2 ===")
    limits = {}
    for lang in SCRIPT_LANGS:
        xs = [n for v in per_lang[lang].values() for n in v]
        if not xs:
            continue
        limits[lang] = max(xs)
        print(f"  {lang}: строк={len(xs):>6} медиана={statistics.median(xs):>4.0f} "
              f"p95={pct(xs, .95):>3} p99={pct(xs, .99):>3} max={max(xs):>3}")

    print("\n=== строк в одной реплике ===")
    for lang in ("eng", "fre", "ger", "jpn"):
        counts: collections.Counter[int] = collections.Counter()
        for name, raw in read_scripts(f"script_{lang}").items():
            if not in_case_scope(name):
                continue
            for block in T.parse(raw).blocks:
                for _param, lines in messages(block.text):
                    counts[len(lines)] += 1
        total = sum(counts.values())
        dist = "  ".join(f"{n} стр: {c * 100 / total:.1f}%" for n, c in sorted(counts.items())[:5])
        print(f"  {lang}: {dist}   максимум={max(counts)}")

    tight = max(pct([n for v in per_lang[l].values() for n in v], .99) for l in ("fre", "ger"))
    print(f"\nФранцузы и немцы — те же, у кого текст длиннее английского — удержались")
    print(f"в пределах {tight} символов на строку (p99). Это и есть рабочий лимит для русского.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
