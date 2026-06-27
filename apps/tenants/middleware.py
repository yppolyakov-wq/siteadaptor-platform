"""Middleware автоподключения кастомных доменов — ДО TenantMainMiddleware.

Если входящий хост есть в таблице `Domain` (поддомен бизнеса или подтверждённый
кастомный домен), но его нет в статическом `ALLOWED_HOSTS`, — дописываем его в
`settings.ALLOWED_HOSTS` на лету. Так django-tenants не отвергнет хост как
недоверенный (`DisallowedHost` → 404), и домен начинает обслуживаться сразу после
подтверждения в кабинете, без ручной правки env. Неизвестные хосты не трогаем —
поведение (404 по таблице Domain) сохраняется.
"""

from django.conf import settings

from .hosts import known_hosts


class CustomDomainHostMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        allowed = settings.ALLOWED_HOSTS
        if "*" not in allowed:
            # _get_raw_host() не валидирует ALLOWED_HOSTS (в отличие от get_host()).
            host = request._get_raw_host().split(":")[0].lower()
            if host and host not in allowed and host in known_hosts():
                # Переприсваиваем новый список (атомарно), не мутируя текущий.
                settings.ALLOWED_HOSTS = [*allowed, host]
        return self.get_response(request)
