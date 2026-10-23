"""KA-12 E7.10: телефоны демо — только «Drama Numbers» Bundesnetzagentur.

Mitteilung 148/2021 (Amtsblatt 07/21 vom 14.04.2021): номера, «die dauerhaft keinem
Teilnehmer zugeteilt sind» — их можно показывать в медиа без разрешения. Демо-витрины
публичны; номер из «555»-серии (американская традиция) в Германии может принадлежать
живому человеку, поэтому в демо — только эти диапазоны.
"""

import re

# (префикс в цифрах без нуля/+49, суффикс-диапазон) — все номера из Mitteilung 148/2021.
_LANDLINE = (
    ("3023125", 3),  # Berlin (0)30 23125 000–999
    ("6990009", 3),  # Frankfurt am Main (0)69 90009 000–999
    ("4066969", 3),  # Hamburg (0)40 66969 000–999
    ("2214710", 3),  # Köln (0)221 4710 000–999
    ("8999998", 3),  # München (0)89 99998 000–999
)
_MOBILE_BLOCKS = (
    ("17139200", 2),  # (0)171 39200 00–99
    ("176040690", 2),  # (0)176 040690 00–99
)
_MOBILE_SINGLE = frozenset(
    {
        "15228817386",
        "15228895456",
        "15254599371",
        "1729925904",
        "1729968532",
        "1729973185",
        "1729973186",
        "1729980752",
        "1749091317",
        "1749464308",
    }
)


def _national_digits(number: str) -> str:
    """«+49 221 4710100» / «0221 4710100» / «+492214710100» → «2214710100»."""
    digits = re.sub(r"\D", "", number or "")
    if digits.startswith("49"):
        return digits[2:]
    if digits.startswith("0"):
        return digits[1:]
    return ""


def is_reserved(number: str) -> bool:
    d = _national_digits(number)
    if not d:
        return False
    if d in _MOBILE_SINGLE:
        return True
    for prefix, tail in (*_LANDLINE, *_MOBILE_BLOCKS):
        if d.startswith(prefix) and len(d) == len(prefix) + tail:
            return True
    return False


def landline(n: int, *, international: bool = True) -> str:
    """n-й номер (0–999) диапазона Köln (0)221 4710 000–999."""
    if not 0 <= n <= 999:
        raise ValueError(n)
    return f"+49 221 4710{n:03d}" if international else f"0221 4710{n:03d}"


def mobile(n: int, *, international: bool = True) -> str:
    """n-й номер (0–99) блока (0)171 39200 00–99."""
    if not 0 <= n <= 99:
        raise ValueError(n)
    return f"+49 171 39200{n:02d}" if international else f"0171 39200{n:02d}"
