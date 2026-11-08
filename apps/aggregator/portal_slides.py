"""PH-11d1 (макет K1): слайды баннера главной городского портала.

Слайд без данных не рендерится. Каждый слайд ведёт на ленту, в которой есть то, что он
обещает (число слайда ⊆ ленты). Платное сюда не попадает (UWG §5a): «Deal» — органический
`deal_of_day`. Без пользовательских данных — страница кэшируется (P0-1).
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.utils.translation import gettext_lazy as _

# Фото города для бизнес-слайда. Лицензия CC BY-SA — подпись и ссылка видны на слайде.
CITY_PHOTOS: dict[str, dict] = {
    "solingen": {
        "src": "portal/muengstener-bruecke.webp",
        "alt": _("Müngstener Brücke bei Solingen"),
        "credit": "InterCityImpress",
        "license": "CC BY-SA 2.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/2.0/",
        "source_url": (
            "https://commons.wikimedia.org/wiki/"
            "File:Solingen_--_M%C3%BCngstener_Br%C3%BCcke_(10403938084).jpg"
        ),
    },
}


def city_photo(city: str) -> dict | None:
    return CITY_PHOTOS.get((city or "").strip().lower())


def _feed(path: str, **params) -> str:
    return f"{path}?{urlencode(params)}"


def slides(portal, *, deal, stats: dict, newbiz: dict | None, path: str) -> list[dict]:
    """Слайды по порядку макета: бизнес-CTA · Deal · Wochenende · Neu · Region."""
    from .platform_links import platform_url

    out: list[dict] = [
        {
            "key": "business",
            "photo": city_photo(getattr(portal, "city", "")),
            "start_url": platform_url("quick-start"),
        }
    ]
    if deal is not None:
        out.append({"key": "deal", "deal": deal})
    if stats.get("weekend"):
        out.append(
            {
                "key": "weekend",
                "count": stats["weekend"],
                "url": _feed(path, kind="event", datum="wochenende"),
            }
        )
    if newbiz and newbiz.get("items"):
        out.append(
            {
                "key": "newbiz",
                "item": newbiz["items"][0],
                "count": len(newbiz["items"]),
                "url": newbiz["more_url"],
            }
        )
    if stats.get("regional"):
        out.append(
            {
                "key": "regional",
                "count": stats["regional"],
                "url": _feed(path, kind="alle", merkmal="regional"),
            }
        )
    return out
