"""Бренд городского портала «<Город>Markt» (план портала PH-1, решение владельца 2026-11-05).

Заголовок не переводится (одно имя во всех локалях — иначе на en `title_text` ушёл бы в
фолбэк). Сидер переименовывает только портал со СТАРЫМИ сидерными значениями — правки
оператора в админке не трогаются."""

from __future__ import annotations

BRAND_COLOR = "#C2410C"  # оранжевый акцент (белый текст 5,2 : 1 — AA)
LEGACY_COLOR = "#111827"
LOCALES = ("de", "en", "ru", "uk", "tr")

#: Подзаголовок по городу; прочие — общий.
_TAGLINES = {
    "Solingen": {
        "de": "Alles aus der Klingenstadt",
        "en": "Everything from the City of Blades",
        "ru": "Всё из города клинков",
        "uk": "Усе з міста клинків",
        "tr": "Bıçaklar şehrinden her şey",
    },
}


def brand_name(city: str) -> str:
    return f"{(city or '').replace(' ', '')}Markt"


def city_brand(city: str) -> dict:
    name = brand_name(city)
    tagline = _TAGLINES.get(city) or {
        "de": f"Läden, Angebote und Termine aus {city}",
        "en": f"Shops, offers and appointments from {city}",
        "ru": f"Магазины, предложения и записи — {city}",
        "uk": f"Крамниці, пропозиції та записи — {city}",
        "tr": f"{city} dükkânları, teklifler ve randevular",
    }
    return {"title": dict.fromkeys(LOCALES, name), "tagline": tagline, "color": BRAND_COLOR}


def legacy_title_de(city: str) -> str:
    return f"Angebote in {city}"


def refresh_city_brand(portal) -> bool:
    """Переименовать портал со старым сидерным заголовком в «<Город>Markt». True — изменён."""
    title = portal.title if isinstance(portal.title, dict) else {}
    if title.get("de") != legacy_title_de(portal.city) or portal.primary_color != LEGACY_COLOR:
        return False
    brand = city_brand(portal.city)
    portal.title = brand["title"]
    portal.tagline = brand["tagline"]
    portal.primary_color = brand["color"]
    portal.save(update_fields=["title", "tagline", "primary_color"])
    return True


def wordmark(title: str, city: str) -> tuple[str, str]:
    """(тёмная часть, акцентная часть): «SolingenMarkt» → («Solingen», «Markt»)."""
    title = title or ""
    key = (city or "").replace(" ", "")
    if key and title.startswith(key) and len(title) > len(key):
        return key, title[len(key) :]
    return "", title
