# -*- coding: utf-8 -*-
"""Одна английская строка — два разных русских перевода. Сводка на разбор.

Не проверка: часть расхождений законна (короткий отклик по правилу №9 обязан
звучать по-разному в разных сценах). Ловится здесь другое — повторяющаяся
служебная реплика игры, переведённая в разных делах по-разному.
"""
import collections
import json
import re

FILES = ["work/case1.json", "work/case2.json", "work/case3.json",
         "work/case4.json", "work/common.json"]
MIN_VISIBLE = 25  # короче — почти наверняка отклик, ему разнобой положен

groups = collections.defaultdict(collections.Counter)
where = collections.defaultdict(lambda: collections.defaultdict(list))


def visible(m):
    return re.sub(r"\{[^}]*\}", "", m)


for f in FILES:
    for x in json.load(open(f, encoding="utf-8"))["entries"]:
        if not x["ru"].strip():
            continue
        en = x["en"].strip()
        if len(visible(en)) < MIN_VISIBLE:
            continue
        groups[en][x["ru"]] += 1
        where[en][x["ru"]].append((f.split("/")[-1][:-5], x["id"]))

div = [(en, c) for en, c in groups.items() if len(c) > 1]
div.sort(key=lambda p: -sum(p[1].values()))

out = ["# Одна английская строка — разные русские переводы",
       "",
       "Сводка от 2 сентября 2026, найдена по ходу перевода `sce3_c4_05`:",
       "служебная реплика «(Judge Gavèlle is a tougher nut to crack...)» в делах 2",
       "и 3 переведена одним способом, а в деле 4 — другим. Прогон по всем пяти",
       "файлам показал, что случай не единичный.",
       "",
       f"**Английских строк с двумя и более переводами: {len(div)}.**",
       "Считаны только строки длиннее 25 видимых знаков: короткий отклик обязан",
       "звучать по-разному в разных сценах (правило №9, `check_echo.py`), и в этот",
       "список он попадать не должен.",
       "",
       "Разбирать глазами: часть расхождений законна (разный говорящий, разная",
       "сцена), часть — настоящий разнобой в повторяющемся служебном тексте.",
       "",
       "---",
       ""]

for en, c in div:
    out.append("### `" + visible(en).replace("\n", " / ").strip()[:110] + "`")
    out.append("")
    for ru, n in c.most_common():
        loc = where[en][ru][0]
        out.append(f"- **×{n}** «{visible(ru).replace(chr(10), ' / ').strip()}» "
                   f"— `{loc[0]}` `{loc[1]}`")
    out.append("")

path = "work/repeats-2026-09-02.md"
with open(path, "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("расхождений:", len(div), "->", path)
