"""LS-1: единый строитель wa.me-ссылок (WhatsApp — 94 % DACH).

v1 видео-консультаций и LS-2 «Jetzt erreichbar»: мы только открываем чат по
клику — ничего не звоним и НЕ записываем (§201 StGB). До этого wa.me жил одним
inline-шаблоном (share в promotion_detail) — новые места используют хелпер.
"""

from urllib.parse import quote


def wa_link(number: str, text: str = "") -> str:
    """https://wa.me/<digits>?text=… или "" без номера.

    Номер нормализуется в digits (wa.me принимает только цифры с кодом страны):
    «+49 171 123-45» → «4917112345»; ведущие нули НЕ трогаем (владелец вводит
    международный формат — подсказка в форме настроек).
    """
    digits = "".join(ch for ch in str(number or "") if ch.isdigit())
    if not digits:
        return ""
    url = f"https://wa.me/{digits}"
    if text:
        url += f"?text={quote(str(text))}"
    return url
