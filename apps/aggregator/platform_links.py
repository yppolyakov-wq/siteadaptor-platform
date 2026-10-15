"""T-8.8: абсолютные ссылки на страницы ПЛАТФОРМЫ (основной домен) с любого хоста.

Портал живёт на своём хосте с `config.urls_portal`, где нет ни Impressum, ни
Datenschutz, ни `/entdecken/`. Реверс по имени в urlconf публичного домена + база
`TENANT_DOMAIN_BASE` — одна точка для подвала портала, llms.txt и фида.
"""

from __future__ import annotations

from django.conf import settings
from django.urls import NoReverseMatch, reverse


def platform_base() -> str:
    scheme = "http" if getattr(settings, "DEBUG", False) else "https"
    return f"{scheme}://{settings.TENANT_DOMAIN_BASE}"


def platform_url(name: str, *args) -> str:
    """Абсолютный URL страницы публичного домена по имени роута ('' если роута нет)."""
    try:
        path = reverse(name, args=args or None, urlconf="config.urls_public")
    except NoReverseMatch:
        return ""
    return platform_base() + path


def legal_links() -> dict[str, str]:
    """Impressum/Datenschutz платформы — для подвала портала, llms.txt и шапки фида."""
    return {
        "impressum": platform_url("platform-impressum"),
        "datenschutz": platform_url("platform-datenschutz"),
    }
