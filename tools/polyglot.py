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
import collections
import re

from common import BACKUP, HOST, SCRIPT_LANGS, load_json, read_scripts_all
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
            # Бандла два, и оригинал каждого лежит в backup/ под своим ключом.
            files: dict[str, bytes] = {}
            manifest = load_json(BACKUP / "manifest.json", default={}) or {}
            missing = False
            for key in (f"script_{lang}", f"script_{lang}_trial"):
                entry = manifest.get(key)
                saved = BACKUP / entry["file"] if entry else None
                if saved and saved.exists():
                    files.update(read_bundle_scripts(saved))
                else:
                    missing = True
            if files and not missing:
                out[lang] = files
                continue
            print(f"! оригинал {lang} не найден в backup/ — колонка будет нашим переводом")
        out[lang] = read_scripts_all(lang)
    return out


def block_variants(raw: bytes, label_hex: str) -> list[list[str | None]]:
    """Все блоки с этой меткой, каждый — сегменты по их **сырым** индексам.

    Позиция сегмента без текста заполняется `None`, а не выбрасывается. Это
    обязательно: адрес сегмента в `work/caseN.json`, в `--find` и в `reread.py`
    берётся из `enumerate(S.split(...))` **вместе** с пустыми, и если их здесь
    отбросить, список схлопнется, а индекс уедет на число пустых перед ним.
    Так и было до 11 августа 2026: в `sce1_c2_06|01001FB0` запрос индекса 32
    молча показывал реплику 33, то есть сверка с чужими локализациями выдавала
    соседнюю строку.
    """
    want = int(label_hex, 16)
    out = []
    for block in T.parse(raw).blocks:
        if block.label_id != want:
            continue
        segs: list[str | None] = []
        for seg in S.split(block.text):
            if not seg.has_text():
                segs.append(None)
                continue
            _head, core, _tail = seg.core()
            segs.append(T.to_markup(core))
        out.append(segs)
    return out


def resolve(raw: bytes, label_spec: str, index: int | None) -> list[str | None] | None:
    """Сегменты блока по адресу вида `01001FB0` или `FFFFFFFF#2`, или None.

    `label_id` в файле **не уникален**: у одной метки бывает до дюжины блоков.
    `extract.py` различает их суффиксом `#N`, причём считает не блоки подряд,
    а те, у которых на этом же индексе есть текст (`extract.py:47`). Здесь
    та же арифметика — иначе `FFFFFFFF#2|0` показывал бы первый блок метки,
    как было до 11 августа 2026 во всём `sce2_opening.bytes`.

    Для чужих локализаций разбивка блока может не совпасть с английской;
    если точного попадания нет, отдаём N-й блок с текстом — приблизительно,
    зато не пусто. Проверка на будущее — `tools/test_polyglot_index.py`.
    """
    label, _, nth_text = label_spec.partition("#")
    nth = int(nth_text) if nth_text else 1
    variants = block_variants(raw, label)
    if not variants:
        return None

    if index is not None:
        seen = 0
        for segs in variants:
            if index < len(segs) and segs[index] is not None:
                seen += 1
                if seen == nth:
                    return segs

    with_text = [v for v in variants if any(t is not None for t in v)]
    return with_text[nth - 1] if len(with_text) >= nth else None


def strip_codes(text: str) -> str:
    return re.sub(r"\{[0-9A-F]{4}(?::[0-9A-F]+)?\}", "", text)


def show(scripts: dict[str, dict[str, bytes]], name: str, label: str,
         index: int | None, raw_codes: bool) -> int:
    name = name.lower()
    resolved = {
        lang: (resolve(scripts[lang][name], label, index) if name in scripts[lang] else None)
        for lang in SCRIPT_LANGS
    }
    # Сверяем именно число реплик: пустых позиций у языков законно разное
    # количество, и считать их значило бы ругаться на каждый второй блок.
    lengths = {lang: (None if segs is None else sum(1 for t in segs if t is not None))
               for lang, segs in resolved.items()}

    counts = {n for n in lengths.values() if n is not None}
    if index is not None and len(counts) > 1:
        print(f"! разбивка блока разошлась по языкам: {lengths}")
        print("! показываю блок целиком — сверяйте глазами\n")
        index = None

    for lang in SCRIPT_LANGS:
        segs = resolved[lang]
        head = f"--- {LANG_NAMES[lang]} ({lang})"
        if segs is None:
            print(f"{head}: блока нет")
            continue
        print(head)
        if index is None:
            chosen = [t for t in segs if t is not None]
        elif 0 <= index < len(segs) and segs[index] is not None:
            chosen = [segs[index]]
        else:
            chosen = []
            print("   (сегмента с таким индексом в этом языке нет)")
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
        # Нумерация повторов метки — ровно как в extract.py:47, иначе найденный
        # адрес нельзя скопировать ни в caseN.json, ни обратно в polyglot.
        seen: collections.Counter = collections.Counter()
        for block in parsed.blocks:
            for idx, seg in enumerate(S.split(block.text)):
                if not seg.has_text():
                    continue
                label = f"{block.label_id:08X}"
                seen[(label, idx)] += 1
                nth = seen[(label, idx)]
                _h, core, _t = seg.core()
                text = T.to_markup(core)
                if low in strip_codes(text).lower():
                    suffix = "" if nth == 1 else f"#{nth}"
                    print(f"{name}|{label}{suffix}|{idx}")
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
