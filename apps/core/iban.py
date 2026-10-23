"""KA-H2: проверка и маскирование IBAN (ISO 13616, контрольная сумма mod-97).

Без внешних зависимостей: длина проверяется точно для DACH-стран, для остальных —
только допустимый диапазон, контрольная сумма — для всех.
"""

import re

# Длины IBAN по стране — для рынка DACH (прочие страны проверяются диапазоном).
_LENGTHS = {"DE": 22, "AT": 20, "CH": 21, "LI": 21}
_SHAPE = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")  # только ASCII-цифры


def normalize_iban(raw: str) -> str:
    """Без пробелов любого вида (в т.ч. неразрывного из банковского PDF) и дефисов,
    в верхнем регистре. Длину не режем: слишком длинный IBAN отклонит проверка."""
    return re.sub(r"[\s\-]", "", raw or "").upper()


def is_valid_iban(value: str) -> bool:
    if not value or not _SHAPE.match(value):
        return False
    expected = _LENGTHS.get(value[:2])
    if expected is not None and len(value) != expected:
        return False
    rearranged = value[4:] + value[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


def mask_iban(value: str) -> str:
    """«DE•• … 3000» — для писем и экранов без права видеть счёт целиком."""
    if not value:
        return ""
    return f"{value[:2]}•• … {value[-4:]}"
