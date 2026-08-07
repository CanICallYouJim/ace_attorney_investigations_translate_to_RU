"""Собрать диагностический билд: показать в игре тестовые строки вместо реплик.

Нужен, когда часть букв рисуется чужими глифами: по скриншоту видно, какие именно
коды подменяются, и можно строить выводы вместо догадок.

Подменяет реплики сцены в комнате свиданий (sce1_c0_01, блок 01000080) на тестовые
строки. Не портит work/case2.json — пишет отдельный бандл в work/build/.

Наборов два.

  basic  Четыре строки: алфавит целиком, прописные и строчные, похожие пары,
         цифры и знаки. Им была снята первая диагностика — подмена глифов.

  split  Двенадцать строк, каждая отвечает на свой вопрос. Нужен после того, как
         увеличение страницы атласа до 4096 не помогло: набор разделяет причины,
         которые «basic» смешивает в одну картинку. Строки пронумерованы (#1..#12),
         номера латиницей и цифрами — они читаются всегда, даже если кириллица поплыла.
         Отснят, результат — в docs/font-atlas.md.

  carriers  Проверка обходного пути: сломанные буквы, записанные кодами-носителями
         из разных участков (см. tools/carriers.py). Годится тот участок, где строка
         читается обычными русскими буквами. Первая строка каждой половины —
         контрольная, своими кодами, она обязана сломаться.
         Требует заранее: python tools/patch_font_cmap.py --install

Что с чем сравнивать в наборе «split»:

  #1 против #3      одна буква против семнадцати. Если ломается уже одна буква,
                    переполнение страницы атласа ни при чём: одному глифу места хватит
                    в любом атласе.
  #2 против #12     одинаковые четыре буквы в начале и в самом конце показа. Разница
                    означает накопление: атлас забивается по мере показа реплик.
  #3 против #5      одна и та же строка два раза подряд. Разница означает, что причина
                    в рантайм-состоянии (упаковка глифов), а не в таблице соответствий.
  #4                одна буква восемь раз в одной строке. Если часть копий целая,
                    а часть нет — портится не буква, а конкретный знакоместо.
  #6, #7            латиница отдельно и вперемешку с кириллицей: контроль.
  #11               французские диакритики. Игра рисует их штатно во французской
                    локализации. Если они ломаются тоже — дело не в кириллице.

    python tools/alphabet_probe.py                   # собрать набор split
    python tools/alphabet_probe.py --set basic
    python tools/alphabet_probe.py --install
"""
from __future__ import annotations

import argparse
import shutil
import sys

from bundle_io import write_text_assets
from common import HOST_SCENARIO_DIR, HOST_SCRIPT, WORK, bundle, game_is_running, read_scripts
import carriers as C
import segments as S
import tps as T

FILE = "sce1_c0_01.bytes"
BLOCK = 0x01000080
STAGE = WORK / "build"


def carriers_set() -> dict[int, str]:
    """Набор «carriers»: сломанные буквы через каждый участок-кандидат.

    Первая строка каждой половины — контрольная, буквы своими кодами: она обязана
    сломаться, иначе проба недействительна. Дальше те же буквы через носители.
    Годится тот участок, где строка читается как обычные русские буквы.

    Требует, чтобы шрифты были пропатчены: python tools/patch_font_cmap.py --install
    """
    probes: dict[int, str] = {}
    idx = 3
    n = 1
    for letters in (C.BROKEN_UPPER, C.BROKEN_LOWER):
        probes[idx] = f"#{n} native {letters}"
        idx, n = idx + 1, n + 1
        for name, base in C.CANDIDATES.items():
            mapping = C.carrier_map(base, C.BROKEN)
            probes[idx] = f"#{n} {name} " + C.encode(letters, mapping)
            idx, n = idx + 1, n + 1
    return probes

# индекс сегмента в блоке -> что показать вместо реплики
PROBE_SETS: dict[str, dict[int, str]] = {
    "basic": {
        3: "АБВГДЕЁЖЗИЙКЛМНОП\nРСТУФХЦЧШЩЪЫЬЭЮЯ",
        4: "абвгдеёжзийклмноп\nрстуфхцчшщъыьэюя",
        5: "аaеeоoрpсcхxуy АAВBЕEКKМMНHОOРPСCТT",
        6: "0123456789 .,!?-:()\nАБВ абв ЁёЗЗз ГгЕе",
    },
    "split": {
        3: "#1 Ж",
        4: "#2 ЖЗЙК",
        5: "#3 АБВГДЕЁЖЗИЙКЛМНОП",
        6: "#4 ЖЖЖЖЖЖЖЖ",
        7: "#5 АБВГДЕЁЖЗИЙКЛМНОП",
        8: "#6 ABCDEFGHIJKLMNOP",
        9: "#7 AaБбBbВвCcГгDdДд",
        10: "#8 РСТУФХЦЧШЩЪЫЬЭЮЯ",
        11: "#9 абвгдеёжзийклмноп",
        12: "#10 рстуфхцчшщъыьэюя",
        13: "#11 ÀÂÇÈÉÊËÎÏÔÙÛÜŸÆŒ",
        14: "#12 ЖЗЙК",
    },
}

PROBE_SETS["carriers"] = carriers_set()

# Пара к tools/font_ident_probe.py: там А Б В Г Д переклеены на знак-опознаватель,
# свой у каждой гарнитуры. Здесь эти буквы просто показываются.
PROBE_SETS["ident"] = {
    3: "#1 АБВГД",
    4: "#2 АБВГДЕЁЖЗИЙКЛМНОП",
    5: "#3 control ABCDE 12345",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", dest="probe_set", choices=sorted(PROBE_SETS), default="split",
                    help="какой набор строк показать (по умолчанию split)")
    ap.add_argument("--install", action="store_true", help="установить в игру")
    args = ap.parse_args()

    probes = PROBE_SETS[args.probe_set]
    eng = read_scripts("script_eng")
    parsed = T.parse(eng[FILE])

    patched = 0
    for block in parsed.blocks:
        if block.label_id != BLOCK:
            continue
        segs = S.split(block.text)
        for idx, text in probes.items():
            if idx >= len(segs):
                print(f"нет сегмента {idx}", file=sys.stderr)
                continue
            head, _core, tail = segs[idx].core()
            segs[idx].body = head + [text] + tail
            patched += 1
        block.text = S.join(segs)

    if not patched:
        print(f"блок {BLOCK:08X} не найден в {FILE}", file=sys.stderr)
        return 1

    src = bundle(HOST_SCRIPT)
    out = STAGE / src.name
    write_text_assets(src, {HOST_SCENARIO_DIR + FILE: T.build(parsed)}, out)
    print(f"набор «{args.probe_set}» собран, реплик подменено: {patched}")
    print(f"-> {out}")

    if args.install:
        if game_is_running():
            print("\nGK12.exe запущен — закрой игру.", file=sys.stderr)
            return 1
        shutil.copy2(out, src)
        print("\nустановлено. В игре: Options -> Language -> Deutsch,")
        print(f"затем дело 2 с начала — {patched} реплик подряд в комнате свиданий.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
