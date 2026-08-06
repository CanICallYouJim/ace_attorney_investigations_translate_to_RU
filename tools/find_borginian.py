"""Сколько борджинийского текста в скриптах GK1 — то есть что ломает освобождение кодов.

Письменность Борджинии сидит на 16 кодах кириллицы (разбор — docs/font-atlas.md).
Вопрос был в том, пишет ли игра этими кодами настоящий текст. В GK2 — нет, в GK1 —
да, 2049 вхождений на 7 локализаций: реплики, которые персонаж говорит по-борджинийски,
а другой следом переводит.

Формат скриптов GK1 отличается от GK2: текст лежит кодовыми точками по 4 байта
(UTF-32LE), разделители вида ff ff ff 00, в шапке таблица записей по 16 байт.
Прошлая проверка дала ложный ноль, потому что искала в UTF-8 и UTF-16.

Контроль метода печатается вместе с результатом: слово Edgeworth в UTF-32LE обязано
находиться в eng и ger (во французской его нет — там Benjamin Hunter).

    python tools/find_borginian.py
"""
from __future__ import annotations

import struct
import sys

sys.path.insert(0, r"C:\Users\Илья\Desktop\Code\Ace Attorney Translating\tools")
from common import SCRIPT_LANGS, read_scripts

MOVED = [0x414, 0x416, 0x417, 0x419, 0x41A, 0x424, 0x428, 0x42E,
         0x430, 0x431, 0x432, 0x433, 0x435, 0x43B, 0x43F, 0x451]
HIRA_WI = 0x3090


def u32s(raw: bytes) -> list[int]:
    n = len(raw) // 4
    return list(struct.unpack(f"<{n}I", raw[:n * 4]))


def main() -> None:
    control = "Edgeworth".encode("utf-32-le")
    grand = {c: 0 for c in MOVED + [HIRA_WI]}
    for lang in SCRIPT_LANGS:
        try:
            files = read_scripts(f"gk1_script_{lang}")
        except Exception as e:
            print(f"{lang}: не прочитан ({e})")
            continue
        ctrl = sum(b.count(control) for b in files.values())
        chars = 0
        per = {c: 0 for c in grand}
        examples = []
        for fn, blob in files.items():
            words = u32s(blob)
            # «текстовые» слова: печатные коды. Считаем объём текста грубо.
            chars += sum(1 for w in words if 0x20 <= w <= 0x2FFFF)
            for i, w in enumerate(words):
                if w in per:
                    per[w] += 1
                    if len(examples) < 12:
                        ctx = "".join(chr(x) if 0x20 <= x <= 0x2FFFF else "·"
                                      for x in words[max(0, i - 20):i + 20])
                        examples.append((fn, i, hex(w), ctx))
        for c in per:
            grand[c] += per[c]
        total = sum(per.values())
        print(f"{lang}: файлов {len(files):>4}  текстовых кодов ~{chars:>9,}  "
              f"контроль 'Edgeworth' {ctrl:>5}  наших кодов {total}")
        for fn, i, w, ctx in examples:
            print(f"      {fn} @{i} {w}  …{ctx}…")

    print("\nсводно по 16 освобождённым кодам + ゐ:")
    for c, n in grand.items():
        if n:
            print(f"  U+{c:04X} {chr(c)!r}: {n}")
    print(f"  всего вхождений: {sum(grand.values())}")


if __name__ == "__main__":
    main()
