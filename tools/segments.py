"""Разбиение блока на сегменты — общая основа для извлечения и сборки.

Реплика обычно выглядит как `{E107:mode} ...текст... {E102}`, но не всегда:

  * внутри одной реплики E107 может встретиться повторно — так помечают смену интонации
    на полуфразе, закрывающий E102 у них общий;
  * открывать реплику может и другой код (встречались E12F и E281), а закрывать её
    всё равно будет E102;
  * отдельные надписи вида `{E042}Breakers data jotted down{E040}` обходятся вообще
    без пары E107/E102.

Поэтому сегментация не пытается угадать открывающий код: блок режется по надёжной
границе — коду E102 — а всё остальное попадает в сегмент как есть. Сегменты покрывают
блок целиком и без пересечений, так что склейка обязана давать исходный текст
байт-в-байт; это проверяет tools/test_segments.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import tps as T

TEXT_START = 0xE107
TEXT_END = 0xE102


@dataclass
class Segment:
    """Кусок блока: служебная преамбула, полезная нагрузка, закрывающий код."""
    prefix: list = field(default_factory=list)   # коды до начала текста
    body: list = field(default_factory=list)     # то, что переводится
    closer: T.Op | None = None                   # E102, если сегмент им закрыт
    mode: int | None = None                      # параметр открывающего E107

    def tokens(self) -> list:
        out = list(self.prefix) + list(self.body)
        if self.closer is not None:
            out.append(self.closer)
        return out

    def has_text(self) -> bool:
        return any(isinstance(t, str) and any(c.isalpha() for c in t) for t in self.body)

    def core(self) -> tuple[list, list, list]:
        """Разложить тело на (голова, ядро, хвост).

        Голова и хвост — сплошные управляющие коды до первого и после последнего
        текстового куска. Переводу подлежит только ядро: так переводчик не видит
        хвостовой мешанины из кодов анимаций и не может её случайно потерять.
        """
        first, last = None, None
        for i, tok in enumerate(self.body):
            if isinstance(tok, str):
                first = i if first is None else first
                last = i
        if first is None:
            return list(self.body), [], []
        return self.body[:first], self.body[first:last + 1], self.body[last + 1:]


def split(text: str) -> list[Segment]:
    """Разрезать блок на сегменты по закрывающему коду E102."""
    segments: list[Segment] = []
    current = Segment()
    started = False

    for tok in T.tokenize(text):
        if isinstance(tok, T.Op) and tok.code == TEXT_END:
            current.closer = tok
            segments.append(current)
            current, started = Segment(), False
            continue

        if not started and isinstance(tok, T.Op) and tok.code == TEXT_START:
            # первый E107 в сегменте — граница преамбулы и текста
            current.mode = ord(tok.params[0]) if tok.params else -1
            current.prefix.append(tok)
            started = True
            continue

        if started:
            current.body.append(tok)
        elif isinstance(tok, T.Op):
            current.prefix.append(tok)
        else:
            # текст без открывающего E107 — всё равно переводимая надпись
            current.body.append(tok)
            started = True

    if current.prefix or current.body:
        segments.append(current)
    return segments


def join(segments: list[Segment]) -> str:
    return T.detokenize([tok for seg in segments for tok in seg.tokens()])
