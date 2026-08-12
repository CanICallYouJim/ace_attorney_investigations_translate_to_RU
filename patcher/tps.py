"""Парсер и сборщик формата ` TPS` — скриптовых файлов .bytes из AAI Collection.

Структура (little-endian):

    0   char[4]  magic = b" TPS"
    4   u16      version = 0x0100
    6   u16      block_count
    8   u16      max_block_len — длина самого длинного блока в словах
                 (проверено: совпадает на всех 394 корректных файлах GK2)
    10  u16      xor_key = 0x55AA
    12  block_count записей таблицы блоков:
            u16/u32  offset    абсолютное смещение блока в файле
            u16      length    длина блока в 16-битных словах, без терминатора
            u32      label_id  идентификатор блока, одинаковый во всех языках
    ...  данные: 16-битные слова, каждое ^ xor_key.
         Каждый блок — length слов + одно слово-терминатор (0x0000).

Ширина поля offset (2 или 4 байта, т.е. запись 8 или 10 байт) в заголовке не указана,
поэтому определяется перебором: подходит тот вариант, при котором таблица вплотную
упирается в первый блок, а блоки без зазоров укладываются до конца файла.
Критерий приёмки — побайтовый round-trip, см. tools/test_tps.py.

Расшифрованные слова — это UTF-16-подобный поток: обычные символы плюс управляющие
коды в Private Use Area (U+E000..U+F8FF). Перенос строки внутри окна — обычный "\\n".
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

MAGIC = b" TPS"
# Всё от U+E000 и выше — управляющий код: латиница, кириллица и основной CJK лежат ниже.
OPCODE_MIN = 0xE000
# Исключение: китайские локализации пишут полноширинными формами (U+FF01..U+FF60),
# японская — полушириной каной (U+FF61..U+FF9F). Это текст, а не коды.
# Настоящие коды в этом блоке начинаются выше, от U+FFC4.
FULLWIDTH_TEXT = range(0xFF01, 0xFFA0)


def is_opcode(code: int) -> bool:
    return code >= OPCODE_MIN and code not in FULLWIDTH_TEXT
HEADER_SIZE = 12
# (размер записи, формат struct для offset+length): узкий вариант и широкий
RECORD_LAYOUTS = ((8, "<HHI"), (10, "<IHI"))


class TpsError(ValueError):
    pass


@dataclass
class Block:
    label_id: int
    text: str  # каждый символ = одно 16-битное слово исходника


@dataclass
class Tps:
    version: int
    xor_key: int
    record_size: int
    blocks: list[Block]

    def max_block_len(self) -> int:
        return max((len(b.text) for b in self.blocks), default=0)


def _decode_words(raw: bytes, key: int) -> str:
    words = struct.unpack(f"<{len(raw)//2}H", raw)
    return "".join(chr(w ^ key) for w in words)


def _encode_words(text: str, key: int) -> bytes:
    return struct.pack(f"<{len(text)}H", *(ord(c) ^ key for c in text))


def _try_layout(raw: bytes, count: int, key: int, rec_size: int, fmt: str) -> list[Block] | None:
    """Разобрать таблицу заданной ширины. None, если раскладка не сходится."""
    table_end = HEADER_SIZE + count * rec_size
    if table_end > len(raw):
        return None

    records = []
    for i in range(count):
        try:
            offset, length, label_id = struct.unpack_from(fmt, raw, HEADER_SIZE + i * rec_size)
        except struct.error:
            return None
        records.append((offset, length, label_id))

    # Блоки идут подряд от конца таблицы, каждый + слово-терминатор, без зазоров.
    cursor = table_end
    for offset, length, _ in records:
        if offset != cursor:
            return None
        cursor = offset + length * 2 + 2
    if cursor != len(raw):
        return None

    return [Block(label, _decode_words(raw[off:off + length * 2], key))
            for off, length, label in records]


def parse(raw: bytes) -> Tps:
    if raw[:4] != MAGIC:
        raise TpsError(f"не TPS-файл: magic={raw[:4]!r}")
    version, count, _max_len, key = struct.unpack_from("<4H", raw, 4)

    for rec_size, fmt in RECORD_LAYOUTS:
        blocks = _try_layout(raw, count, key, rec_size, fmt)
        if blocks is not None:
            return Tps(version=version, xor_key=key, record_size=rec_size, blocks=blocks)

    raise TpsError(f"таблица из {count} блоков не сходится ни при 8-, ни при 10-байтовой записи")


def build(tps: Tps) -> bytes:
    """Собрать файл обратно. Для неизменённого Tps даёт байт-в-байт исходник."""
    count = len(tps.blocks)
    rec_size = tps.record_size
    fmt = dict(RECORD_LAYOUTS)[rec_size]
    data_start = HEADER_SIZE + count * rec_size

    table = bytearray()
    data = bytearray()
    for block in tps.blocks:
        offset = data_start + len(data)
        if rec_size == 8 and offset > 0xFFFF:
            raise TpsError("блоки переросли 16-битные смещения — нужна 10-байтовая запись")
        table += struct.pack(fmt, offset, len(block.text), block.label_id)
        data += _encode_words(block.text, tps.xor_key)
        data += struct.pack("<H", 0 ^ tps.xor_key)  # терминатор блока

    header = struct.pack("<4sHHHH", MAGIC, tps.version, count, tps.max_block_len(), tps.xor_key)
    return bytes(header + table + data)


# --------------------------------------------------------------------------------------
# Разбор блока на текст и управляющие последовательности
# --------------------------------------------------------------------------------------

@lru_cache(maxsize=1)
def opcode_table() -> dict[int, int]:
    """Код -> число слов-параметров. Строится tools/derive_opcodes.py.

    Ищется в двух местах: рядом с модулем и в docs/ репозитория. Рядом — потому
    что этот же модуль уезжает в патчер, где никакого docs/ нет, а таблица
    обязана уехать вместе с ним: без неё не разобрать ни одной реплики.
    """
    here = Path(__file__).resolve().parent
    for path in (here / "opcodes.json", here.parent / "docs" / "opcodes.json"):
        if path.exists():
            return {int(k, 16): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}
    raise FileNotFoundError(f"нет opcodes.json ни в {here}, ни в {here.parent / 'docs'}")


@dataclass
class Op:
    """Управляющий код с параметрами — при переводе переносится без изменений."""
    code: int
    params: str


def tokenize(text: str) -> list[str | Op]:
    """Разбить блок на чередование текстовых кусков (str) и управляющих кодов (Op)."""
    table = opcode_table()
    tokens: list[str | Op] = []
    buf: list[str] = []
    i = 0
    while i < len(text):
        code = ord(text[i])
        if not is_opcode(code):
            buf.append(text[i])
            i += 1
            continue
        if buf:
            tokens.append("".join(buf))
            buf = []
        nparams = table.get(code, 0)
        params = text[i + 1: i + 1 + nparams]
        tokens.append(Op(code, params))
        i += 1 + len(params)
    if buf:
        tokens.append("".join(buf))
    return tokens


def detokenize(tokens: list[str | Op]) -> str:
    return "".join(t if isinstance(t, str) else chr(t.code) + t.params for t in tokens)


# --------------------------------------------------------------------------------------
# Разметка для перевода: коды показываем метками {E108:0008}, текст оставляем как есть
# --------------------------------------------------------------------------------------

_MARKUP = __import__("re").compile(r"\{([0-9A-F]{4})(?::((?:[0-9A-F]{4})+))?\}")


def to_markup(tokens: list[str | Op]) -> str:
    """Превратить токены в строку, пригодную для правки человеком."""
    out: list[str] = []
    for tok in tokens:
        if isinstance(tok, str):
            # экранируем фигурную скобку, чтобы её нельзя было спутать с меткой
            out.append(tok.replace("{", "{{"))
        else:
            params = "".join(f"{ord(c):04X}" for c in tok.params)
            out.append(f"{{{tok.code:04X}:{params}}}" if params else f"{{{tok.code:04X}}}")
    return "".join(out)


def from_markup(text: str) -> list[str | Op]:
    """Разобрать размеченную строку обратно в токены."""
    tokens: list[str | Op] = []
    buf: list[str] = []
    i = 0
    while i < len(text):
        if text.startswith("{{", i):
            buf.append("{")
            i += 2
            continue
        match = _MARKUP.match(text, i)
        if match:
            if buf:
                tokens.append("".join(buf))
                buf = []
            params = match.group(2) or ""
            tokens.append(Op(int(match.group(1), 16),
                             "".join(chr(int(params[k:k + 4], 16)) for k in range(0, len(params), 4))))
            i = match.end()
            continue
        buf.append(text[i])
        i += 1
    if buf:
        tokens.append("".join(buf))
    return tokens
