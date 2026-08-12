"""Проверка сегментации: склейка сегментов обязана давать исходный блок байт-в-байт,
и ни один кусок текста с буквами не должен оказаться вне тела сегмента.

Второе важнее первого: если текст попал в преамбулу, он не будет извлечён на перевод
и молча останется английским в игре.

    python tools/test_segments.py
"""
from __future__ import annotations

import collections
import sys

from common import SCRIPT_LANGS, in_case_scope, read_scripts_all
import segments as S
import tps as T


def main() -> int:
    rejoin_fail = []
    stranded: collections.Counter[str] = collections.Counter()
    total_segments = with_text = 0

    for lang in SCRIPT_LANGS:
        for name, raw in sorted(read_scripts_all(lang).items()):
            for block in T.parse(raw).blocks:
                segs = S.split(block.text)
                if S.join(segs) != block.text:
                    rejoin_fail.append(f"{lang}/{name} блок {block.label_id:08X}")
                total_segments += len(segs)
                for seg in segs:
                    if seg.has_text():
                        with_text += 1
                    if lang == "eng" and in_case_scope(name):
                        for tok in seg.prefix:
                            if isinstance(tok, str) and any(c.isalpha() for c in tok):
                                stranded[name] += 1
        print(f"  gk2/{lang}: готово")

    print(f"\nсегментов всего:       {total_segments}")
    print(f"из них с текстом:      {with_text}")
    print(f"склейка не совпала:    {len(rejoin_fail)}")
    for line in rejoin_fail[:10]:
        print("   ", line)

    if stranded:
        print(f"\nтекст застрял в преамбуле ({sum(stranded.values())} кусков) — не переведётся:")
        for name, n in stranded.most_common(10):
            print(f"   {n:4d}  {name}")
        return 1

    if rejoin_fail:
        return 1
    print("\nOK — сегменты покрывают блоки полностью, текст весь в теле.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
