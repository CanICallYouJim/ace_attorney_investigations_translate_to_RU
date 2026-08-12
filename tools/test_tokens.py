"""Проверка токенизатора: параметры опкодов не должны утекать в переводимый текст.

Главный критерий — в текстовых кусках не встречается управляющих символов (< 0x20),
кроме перевода строки. Если таблица параметров где-то занижена, «лишний» параметр
сразу вылезет мусорным байтом внутри реплики.

Тест валит сборку только при утечке в языках конвейера (латиница: eng — источник,
fre/ger — контроль той же скриптовой структуры) и только в файлах дела 2. Находки в
CJK-локализациях и вне дела 2 печатаются как информация: мы эти файлы не читаем и не
пишем, а формат там местами расходится (например, у китайского после паузы идёт лишний
параметр перед многоточием).

    python tools/test_tokens.py
"""
from __future__ import annotations

import collections
import sys

from common import BINARY_ONLY_FILES, SCRIPT_LANGS, in_case_scope, read_scripts_all
import tps as T

ALLOWED_LOW = {"\n"}
# Языки, на которых реально работает конвейер перевода: из eng читаем, в слот fre пишем.
PIPELINE_LANGS = ("eng", "fre", "ger")


def main() -> int:
    unknown: collections.Counter[int] = collections.Counter()
    in_scope: list[str] = []
    elsewhere: collections.Counter[str] = collections.Counter()
    rt_fail = 0
    blocks = chars = 0
    table = T.opcode_table()

    for lang in SCRIPT_LANGS:
        for name, raw in sorted(read_scripts_all(lang).items()):
            for block in T.parse(raw).blocks:
                blocks += 1
                tokens = T.tokenize(block.text)
                if T.detokenize(tokens) != block.text:
                    rt_fail += 1
                for tok in tokens:
                    if isinstance(tok, T.Op):
                        if tok.code not in table:
                            unknown[tok.code] += 1
                        continue
                    chars += len(tok)
                    bad = {c for c in tok if ord(c) < 0x20 and c not in ALLOWED_LOW}
                    if not bad:
                        continue
                    codes = " ".join(f"{ord(c):#04x}" for c in sorted(bad))
                    if in_case_scope(name) and lang in PIPELINE_LANGS:
                        in_scope.append(f"{lang}/{name}: {codes} в {tok[:70]!r}")
                    elif name not in BINARY_ONLY_FILES:
                        elsewhere[f"{lang}/{name}"] += 1
        print(f"  gk2/{lang}: готово")

    print(f"\nблоков:                {blocks}")
    print(f"текстовых символов:    {chars:,}")
    print(f"round-trip токенов:    {'OK' if rt_fail == 0 else f'{rt_fail} ошибок'}")
    print(f"неизвестных кодов:     {len(unknown)}")
    if unknown:
        print("   " + ", ".join(f"U+{c:04X}×{n}" for c, n in unknown.most_common(10)))

    if elsewhere:
        print(f"\nвне конвейера — служебные байты в тексте ({len(elsewhere)} файлов):")
        for where, n in elsewhere.most_common(10):
            print(f"   {where} ×{n}")
        print("   (эти файлы не читаются и не пишутся, на дело 2 не влияет)")

    if in_scope:
        print("\nВ ОБЛАСТИ ПЕРЕВОДА параметры утекают в текст — таблица занижена:")
        for line in in_scope[:15]:
            print("  ", line)
        return 1

    print(f"\nOK — в файлах дела 2 ({'/'.join(PIPELINE_LANGS)}) текст чистый, параметры не утекают.")
    return 0 if rt_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
