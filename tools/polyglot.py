"""Показать один и тот же сегмент во всех семи локализациях игры.

Первое, что делать с непонятным словом, каламбуром или выдуманным названием:
посмотреть, как с ним поступили официальные переводчики. У игры семь локализаций
(англ., фр., нем., яп., кор., кит. упр. и трад.), и все они лежат рядом в бандлах
`gk2_scriptmessage_<lang>`. Немцы и французы решали ровно ту же задачу, что и мы,
и их решение — готовая подсказка: перевели буквально, придумали своё или оставили
как есть.

    python tools/polyglot.py sce1_c2_08.bytes'|'010021E6'|'18   # один сегмент
    python tools/polyglot.py --find "Li'l Vee"                  # найти по тексту
    python tools/polyglot.py --block sce1_c2_08.bytes 010021E6   # блок целиком

Блоки во всех локализациях одни и те же (адресуются `label_id`), а вот разбивка
на сегменты внутри блока может разойтись: где англичане уместили фразу в одну
реплику, немцы могли разбить на две. Поэтому при расхождении числа сегментов
скрипт печатает предупреждение и показывает блок целиком — сверять глазами.
"""
from __future__ import annotations

import argparse
import re

from common import BACKUP, HOST, SCRIPT_LANGS, load_json, read_scripts
import segments as S
import tps as T

LANG_NAMES = {
    "eng": "английский", "fre": "французский", "ger": "немецкий",
    "jpn": "японский", "kor": "корейский",
    "sim": "китайский упр.", "tra": "китайский трад.",
}


def read_bundle_scripts(path) -> dict[str, bytes]:
    """То же, что common.read_scripts, но от произвольного файла бандла."""
    import UnityPy

    env = UnityPy.load(str(path))
    out: dict[str, bytes] = {}
    for name, obj in env.container.items():
        script = obj.read().m_Script
        raw = script.encode("utf-8", "surrogateescape") if isinstance(script, str) else bytes(script)
        out[name.split("/")[-1].lower()] = raw
    return out


def load_all() -> dict[str, dict[str, bytes]]:
    """Скрипты всех семи языков.

    Слот-носитель (`common.HOST`, сейчас немецкий) в живой игре уже занят нашим
    переводом, а непереведённое в нём — английское. Как подсказка он бесполезен,
    поэтому читается из `backup/` — там лежит нетронутый оригинал.
    """
    out = {}
    for lang in SCRIPT_LANGS:
        if lang == HOST:
            entry = (load_json(BACKUP / "manifest.json", default={}) or {}).get(f"script_{lang}")
            saved = BACKUP / entry["file"] if entry else None
            if saved and saved.exists():
                out[lang] = read_bundle_scripts(saved)
                continue
            print(f"! оригинал {lang} не найден в backup/ — колонка будет нашим переводом")
        out[lang] = read_scripts(f"script_{lang}")
    return out


def block_segments(raw: bytes, label_hex: str) -> list[str] | None:
    """Тексты сегментов блока с данным label_id, или None если блока нет.

    `label_id` в файле **не уникален**: у одной метки бывает до четырёх блоков,
    и лишние — склейка сцены из чистых кодов, без единой реплики. Берём первый
    блок, в котором текст действительно есть; разбор — в docs/bytes-format.md.
    """
    want = int(label_hex, 16)
    found = False
    for block in T.parse(raw).blocks:
        if block.label_id != want:
            continue
        found = True
        out = []
        for seg in S.split(block.text):
            if not seg.has_text():
                continue
            _head, core, _tail = seg.core()
            out.append(T.to_markup(core))
        if out:
            return out
    return [] if found else None


def strip_codes(text: str) -> str:
    return re.sub(r"\{[0-9A-F]{4}(?::[0-9A-F]+)?\}", "", text)


def show(scripts: dict[str, dict[str, bytes]], name: str, label: str,
         index: int | None, raw_codes: bool) -> int:
    name = name.lower()
    lengths = {}
    for lang in SCRIPT_LANGS:
        segs = block_segments(scripts[lang].get(name, b""), label) if name in scripts[lang] else None
        lengths[lang] = None if segs is None else len(segs)

    counts = {n for n in lengths.values() if n is not None}
    if index is not None and len(counts) > 1:
        print(f"! разбивка блока разошлась по языкам: {lengths}")
        print("! показываю блок целиком — сверяйте глазами\n")
        index = None

    for lang in SCRIPT_LANGS:
        segs = block_segments(scripts[lang].get(name, b""), label) if name in scripts[lang] else None
        head = f"--- {LANG_NAMES[lang]} ({lang})"
        if segs is None:
            print(f"{head}: блока нет")
            continue
        print(head)
        chosen = segs if index is None else segs[index:index + 1]
        for text in chosen:
            print("   " + (text if raw_codes else strip_codes(text)).replace("\n", "\n   "))
        print()
    return 0


def find(scripts: dict[str, dict[str, bytes]], needle: str, lang: str) -> int:
    low = needle.lower()
    hits = 0
    for name, raw in sorted(scripts[lang].items()):
        try:
            parsed = T.parse(raw)
        except Exception:
            continue
        for block in parsed.blocks:
            for idx, seg in enumerate(S.split(block.text)):
                if not seg.has_text():
                    continue
                _h, core, _t = seg.core()
                text = T.to_markup(core)
                if low in strip_codes(text).lower():
                    print(f"{name}|{block.label_id:08X}|{idx}")
                    print("   " + strip_codes(text).replace("\n", "\n   "))
                    hits += 1
    print(f"\nнайдено: {hits}")
    return 0 if hits else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("segment", nargs="?", help="адрес вида файл|БЛОК|индекс")
    ap.add_argument("--block", nargs=2, metavar=("ФАЙЛ", "БЛОК"), help="блок целиком")
    ap.add_argument("--find", metavar="ТЕКСТ", help="искать по тексту")
    ap.add_argument("--lang", default="eng", help="язык поиска для --find")
    ap.add_argument("--codes", action="store_true", help="не прятать управляющие коды")
    args = ap.parse_args()

    scripts = load_all()

    if args.find:
        return find(scripts, args.find, args.lang)
    if args.block:
        return show(scripts, args.block[0], args.block[1], None, args.codes)
    if args.segment:
        parts = args.segment.split("|")
        if len(parts) != 3:
            ap.error("адрес сегмента: файл|БЛОК|индекс")
        return show(scripts, parts[0], parts[1], int(parts[2]), args.codes)
    ap.error("нужен адрес сегмента, --block или --find")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
