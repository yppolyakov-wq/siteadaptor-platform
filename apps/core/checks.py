"""Security-check: инварианты изоляции сессий между схемами тенантов (HIGH-10)."""

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security)
def session_cookie_domain_not_set(app_configs, **kwargs):
    """SESSION_COOKIE_DOMAIN должен оставаться пустым.

    Общий cookie-domain между субдоменами (`.siteadaptor.de`) ломает изоляцию:
    `_auth_user_id` из одной схемы совпал бы с чужим владельцем в другой
    (pk-коллизия auth_user). Fail-closed: `manage.py check` падает, если задан.
    """
    if getattr(settings, "SESSION_COOKIE_DOMAIN", None):
        return [
            Error(
                "SESSION_COOKIE_DOMAIN задан — ломает изоляцию сессий между схемами "
                "тенантов (pk-коллизия auth_user → кросс-тенант вход).",
                hint="Оставьте SESSION_COOKIE_DOMAIN пустым (host-only cookie). Сессии "
                "привязаны к схеме логина (apps.core.session_schema), но общий "
                "cookie-domain открыл бы окно между логином и первым запросом.",
                id="core.E001",
            )
        ]
    return []
