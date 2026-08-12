"""Вывести таблицу «сколько слов-параметров съедает управляющий код» и сохранить в docs/opcodes.json.

Используются два независимых признака.

1. Маска совпадений. Скриптовый скелет (коды и их параметры) одинаков во всех локализациях
   одного файла, а текст различается — особенно в японском и корейском, где другой алфавит.
   Выравниваем потоки и помечаем позиции, совпавшие во всех языках. После кода идут его
   параметры (совпадающие, не-код), затем либо следующий код, либо текст (несовпадающий).
   Слабое место: параметр, который переводчики меняли от языка к языку (длительность паузы
   у E108, режим у E107), маска засчитывает как текст и занижает число параметров.

2. Признак «параметр — не управляющий код». Позиция параметра никогда не занята кодом.
   Если слово №k после кода оказалось не-кодом во ВСЕХ вхождениях корпуса, это железно
   параметр, независимо от языка. Слабое место в обратную сторону: у кодов с переменным
   числом параметров цепочка обрывается рано.

Итог — максимум из двух оценок: признак 2 даёт достоверную нижнюю границу, признак 1
дотягивает её там, где параметры не отличить от текста по типу слова.

    python tools/derive_opcodes.py
"""
from __future__ import annotations

import collections
import difflib

from common import DOCS, read_scripts_all, save_json
import tps as T
from tps import is_opcode

# Языки для сравнения: латиница + японский и корейский, чтобы текст гарантированно расходился.
COMPARE = ("fre", "ger", "jpn", "kor")
MIN_OCCURRENCES = 4
MAX_PARAMS = 8

# Коды, где нижняя граница врёт, и почему. Признак 2 считает параметром всякое слово,
# которое ни разу не оказалось управляющим кодом, — а буквы кодами не бывают никогда.
# Поэтому у кода, за которым ВСЕГДА идёт текст, граница съедает начало реплики.
#
# Поймано 12 августа 2026 прогоном test_polyglot_index.py: после пересборки
# `exam.bytes|FFFFFFFF#13|0` отдавал ' have a record of your reporting!' вместо
# 'You must have a record of your reporting!' — ровно восемь букв, столько же,
# сколько параметров граница выдала коду E04D. Маска совпадений на обоих кодах
# говорила 0, и права была она: за ними идёт переводной текст, он в языках разный.
#
# Соседи по семейству (E040..E043) — парные коды подсветки с нулём параметров,
# см. docs/decisions.md о `{E041}…{E040}`. E04C и E04D устроены так же.
OVERRIDES = {
    0xE04C: 0,
    0xE04D: 0,
}

# Корпус — ОБА скриптовых бандла языка, через read_scripts_all.
#
# Так было не всегда, и это стоило бага. Скриптовых бандлов на язык два, и до
# 12 августа 2026 весь конвейер знал только главный. Таблица, выведенная по одному
# бандлу, не видела кодов второго: E2BF встретился ей 3 раза при пороге 4 и получил
# ноль параметров, хотя параметр у него есть — в game_over.bytes он идёт следом
# и уезжает прямо в текст реплики. Ещё 15 кодов второго бандла в таблицу
# не попали вовсе. Поймано прогоном test_tokens.py после того, как game_over.bytes
# вошёл в объём перевода вместе с псевдоделом 0.


def agreement_mask(texts: dict[str, str]) -> list[int]:
    """Для каждой позиции в eng — со сколькими другими языками совпало слово."""
    base = texts["eng"]
    mask = [0] * len(base)
    for lang, other in texts.items():
        if lang == "eng":
            continue
        matcher = difflib.SequenceMatcher(None, base, other, autojunk=False)
        for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
            if tag == "equal":
                for i in range(i1, i2):
                    mask[i] += 1
    return mask


def derive_by_mask():
    langs = {lang: read_scripts_all(lang) for lang in ("eng",) + COMPARE}
    names = [n for n in sorted(langs["eng"]) if all(n in langs[l] for l in langs)]
    print(f"файлов для анализа: {len(names)}")

    votes: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    for idx, name in enumerate(names):
        if idx % 50 == 0:
            print(f"  {idx}/{len(names)}")
        parsed = {lang: T.parse(files[name]) for lang, files in langs.items()}
        if len({len(p.blocks) for p in parsed.values()}) != 1:
            continue  # разное число блоков — выравнивание бессмысленно

        for bi in range(len(parsed["eng"].blocks)):
            texts = {lang: p.blocks[bi].text for lang, p in parsed.items()}
            mask = agreement_mask(texts)
            base = texts["eng"]
            full = len(COMPARE)
            for i, ch in enumerate(base):
                if not is_opcode(ord(ch)):
                    continue
                n = 0
                while (i + 1 + n < len(base)
                       and mask[i + 1 + n] == full
                       and not is_opcode(ord(base[i + 1 + n]))):
                    n += 1
                votes[ord(ch)][n] += 1

    table = {code: c.most_common(1)[0][0]
             for code, c in votes.items() if sum(c.values()) >= MIN_OCCURRENCES}
    return table, votes


def derive_lower_bound() -> dict[int, int]:
    """Сколько слов после кода гарантированно не являются кодом — по всему корпусу."""
    hits: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    for lang in ("eng",) + COMPARE:
        for raw in read_scripts_all(lang).values():
            for block in T.parse(raw).blocks:
                text = block.text
                for i, ch in enumerate(text):
                    code = ord(ch)
                    if not is_opcode(code):
                        continue
                    for k in range(1, MAX_PARAMS + 1):
                        if i + k >= len(text):
                            break
                        hits[code][("total", k)] += 1
                        if not is_opcode(ord(text[i + k])):
                            hits[code][k] += 1

    bounds: dict[int, int] = {}
    for code, counter in hits.items():
        n = 0
        for k in range(1, MAX_PARAMS + 1):
            total = counter[("total", k)]
            if total < MIN_OCCURRENCES or counter[k] != total:
                break
            n += 1
        bounds[code] = n
    return bounds


if __name__ == "__main__":
    mask_table, votes = derive_by_mask()
    print("\nсчитаю нижнюю границу по признаку «параметр — не код»...")
    bounds = derive_lower_bound()

    result: dict[str, int] = {}
    lifted = []
    for code in sorted(set(mask_table) | set(bounds)):
        mask_n = mask_table.get(code, 0)
        bound_n = bounds.get(code, 0)
        result[f"{code:04X}"] = OVERRIDES.get(code, max(mask_n, bound_n))
        if bound_n > mask_n and code not in OVERRIDES:
            lifted.append((sum(votes[code].values()), code, mask_n, bound_n))
    print(f"ручных поправок применено: {len(OVERRIDES)} "
          f"({', '.join(f'U+{c:04X}={n}' for c, n in sorted(OVERRIDES.items()))})")

    save_json(DOCS / "opcodes.json", result)
    print(f"\nкодов в таблице: {len(result)} -> {DOCS / 'opcodes.json'}")
    print("распределение числа параметров:",
          dict(sorted(collections.Counter(result.values()).items())))
    if lifted:
        print(f"\nподняты нижней границей (маска занижала): {len(lifted)}")
        for total, code, mask_n, bound_n in sorted(lifted, reverse=True)[:15]:
            print(f"   U+{code:04X}  маска={mask_n} -> {bound_n}  ({total} вхождений)")
