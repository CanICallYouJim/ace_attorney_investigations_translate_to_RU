"""Коды-носители для кириллицы: обход подмены глифов в рантайме игры.

Зачем. Игра детерминированно подменяет 16 кириллических букв из 66 чужими глифами
(разбор — docs/font-atlas.md). Гарнитура, её cmap и FreeType проверены и невиновны:
подмена держится за **код символа**. Значит её можно обойти, не трогая отрисовку —
записать букву другим кодом, который игра не трогает, и научить сам шрифт отдавать
по этому коду нужный глиф.

Здесь только таблицы соответствий. Правку шрифта делает patch_font_cmap.py,
подстановку в текст при сборке — build.py.

Носители обязаны быть **ниже 0xE000**: с этого значения tps.is_opcode() считает
код управляющим, и весь диапазон частного использования занят игрой под свои коды.
Диапазон 0xFF01..0xFF9F (полноширинные формы) тоже годится — tps относит его к тексту.
"""
from __future__ import annotations

# Буквы, которые игра подменяет. Порядок фиксирован: по нему считаются носители.
BROKEN_UPPER = "ДЖЗЙКФШЮ"
BROKEN_LOWER = "абвгеёлп"
BROKEN = BROKEN_UPPER + BROKEN_LOWER

# Вся кириллица — на случай, если носители придётся раздать всем буквам,
# а не только сломанным.
ALPHABET_UPPER = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
ALPHABET_LOWER = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
ALPHABET = ALPHABET_UPPER + ALPHABET_LOWER

# Кандидаты в носители: начало непрерывного участка нужной длины.
# Проверяются в игре пробой alphabet_probe.py --set carriers: какой участок
# игра пропускает нетронутым, тот и берём в работу.
CANDIDATES: dict[str, int] = {
    "greek": 0x03B1,      # α.. — греческие строчные
    "latext": 0x0100,     # Ā.. — Latin Extended-A
    "armenian": 0x0531,   # Ա.. — армянские прописные
    "yi": 0xA000,         # ꀀ.. — слоговое письмо и
    "fullwidth": 0xFF21,  # Ａ.. — полноширинная латиница
}

# Выбранный участок. Заполняется после пробы; None — ещё не выбран.
CHOSEN: str | None = None


def carrier_map(base: int, letters: str = BROKEN) -> dict[str, int]:
    """Буква -> код-носителя для участка, начинающегося с base."""
    return {ch: base + i for i, ch in enumerate(letters)}


def all_candidate_maps(letters: str = BROKEN) -> dict[str, dict[str, int]]:
    """Все участки-кандидаты разом: имя участка -> {буква: код}."""
    return {name: carrier_map(base, letters) for name, base in CANDIDATES.items()}


def encode(text: str, mapping: dict[str, int]) -> str:
    """Заменить буквы на их коды-носители."""
    return "".join(chr(mapping[c]) if c in mapping else c for c in text)


def decode(text: str, mapping: dict[str, int]) -> str:
    """Обратная замена — чтобы проверки и диффы читались по-человечески."""
    back = {chr(v): k for k, v in mapping.items()}
    return "".join(back.get(c, c) for c in text)
