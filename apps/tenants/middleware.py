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


# T-8.25: пути, которые никогда не уводим со своего поддомена — вход/кабинет/служебное.
_NO_REDIRECT_PREFIXES = (
    "/accounts/",
    "/start/",
    "/anmelden/",
    "/static/",
    "/media/",
    "/webhooks/",
    "/api/",
    "/healthz",
    "/admin/",
    "/rosetta/",
    "/__debug__/",
)


class PrimaryDomainRedirectMiddleware:
    """T-8.25: свой домен бизнеса — основной адрес; поддомен 301 на него (решение
    владельца 2026-10-11 — один адрес для поисковиков).

    Только анонимные GET/HEAD витрины (посетители и роботы). Вошедший владелец, Studio
    и превью (`preview` в query), вход и кабинет остаются на поддомене: сессия
    привязана к хосту, канва редактора — same-origin.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        target = self._target(request)
        if target:
            from django.http import HttpResponsePermanentRedirect

            return HttpResponsePermanentRedirect(target)
        return self.get_response(request)

    @staticmethod
    def _target(request) -> str:
        if request.method not in ("GET", "HEAD"):
            return ""
        tenant = getattr(request, "tenant", None)
        if tenant is None or getattr(tenant, "schema_name", "public") == "public":
            return ""
        if getattr(getattr(request, "user", None), "is_authenticated", False):
            return ""
        path = request.path
        from apps.core.i18n_cabinet import CABINET_PREFIXES

        if path.startswith(CABINET_PREFIXES) or path.startswith(_NO_REDIRECT_PREFIXES):
            return ""
        if "preview" in request.GET:
            return ""
        base = getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de").split(":")[0]
        host = request._get_raw_host().split(":")[0].lower()
        if not host.endswith("." + base):
            return ""  # уже на своём домене (или не на поддомене платформы)
        from .hosts import public_base_url

        primary = public_base_url(tenant)
        if primary.split("://", 1)[-1] == host:
            return ""  # своего домена нет — основной адрес и есть поддомен
        return primary + request.get_full_path()
