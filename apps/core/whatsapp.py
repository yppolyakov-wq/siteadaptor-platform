"""LS-1: единый строитель wa.me-ссылок (WhatsApp — 94 % DACH).

v1 видео-консультаций и LS-2 «Jetzt erreichbar»: мы только открываем чат по
клику — ничего не звоним и НЕ записываем (§201 StGB). До этого wa.me жил одним
inline-шаблоном (share в promotion_detail) — новые места используют хелпер.
"""

import re
from urllib.parse import quote

# Печатная DACH-запись «+49 (0) 170 …»: «(0)» — национальный trunk-префикс,
# в международном номере его быть не должно (49 0 170… wa.me не откроет).
_PAREN_TRUNK = re.compile(r"\(\s*0\s*\)")


def wa_link(number: str, text: str = "") -> str:
    """https://wa.me/<digits>?text=… или "" без номера.

    Номер нормализуется в digits (wa.me принимает только цифры с кодом страны):
    «+49 171 123-45» → «4917112345». Дополнительно (ревью 2026-07-28) снимаем
    национальный trunk-ноль в скобках «+49 (0) 170 …» и префикс выхода на
    международку «0049 …» — иначе ссылка вела в никуда. Ведущий ноль БЕЗ кода
    страны («0170 …») не трогаем: подставить код неоткуда, подсказка — в форме.
    """
    digits = "".join(ch for ch in _PAREN_TRUNK.sub("", str(number or "")) if ch.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    if not digits:
        return ""
    url = f"https://wa.me/{digits}"
    if text:
        url += f"?text={quote(str(text))}"
    return url
