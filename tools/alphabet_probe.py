"""Собрать диагностический билд: показать в игре весь русский алфавит по порядку.

Нужен, когда часть букв рисуется чужими глифами: по скриншоту сразу видно, какие
именно коды подменяются, и можно построить точное соответствие вместо догадок.

Подменяет первые реплики сцены в комнате свиданий (sce1_c0_01) на тестовые строки.
Не портит work/case2.json — пишет отдельный бандл в work/build/.

    python tools/alphabet_probe.py --install
"""
from __future__ import annotations

import argparse
import shutil
import sys

from bundle_io import write_text_assets
from common import WORK, bundle, game_is_running, read_scripts
import segments as S
import tps as T

FILE = "sce1_c0_01.bytes"
BLOCK = 0x01000080

# что показать: (индекс сегмента, строка). Индексы — реплики в начале сцены.
PROBES = {
    3: "АБВГДЕЁЖЗИЙКЛМНОП\nРСТУФХЦЧШЩЪЫЬЭЮЯ",
    4: "абвгдеёжзийклмноп\nрстуфхцчшщъыьэюя",
    5: "аaеeоoрpсcхxуy АAВBЕEКKМMНHОOРPСCТT",
    6: "0123456789 .,!?-:()\nАБВ абв ЁёЗЗз ГгЕе",
}
STAGE = WORK / "build"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--install", action="store_true", help="установить в игру")
    args = ap.parse_args()

    eng = read_scripts("script_eng")
    parsed = T.parse(eng[FILE])

    patched = 0
    for block in parsed.blocks:
        if block.label_id != BLOCK:
            continue
        segs = S.split(block.text)
        for idx, text in PROBES.items():
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

    src = bundle("script_fre")
    out = STAGE / src.name
    write_text_assets(src, {f"Assets/GK2/Scenario/_fre/{FILE}": T.build(parsed)}, out)
    print(f"диагностический бандл собран, реплик подменено: {patched}")
    print(f"-> {out}")

    if args.install:
        if game_is_running():
            print("\nGK12.exe запущен — закрой игру.", file=sys.stderr)
            return 1
        shutil.copy2(out, src)
        print(f"\nустановлено. В игре: Options -> Language -> Français,")
        print("затем дело 2 с начала — первые четыре реплики в комнате свиданий.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
