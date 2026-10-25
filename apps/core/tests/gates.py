"""KA-12 E6.7c-4: тестовые помощники доступа «как браузер».

Права экранов живут на МАРШРУТАХ (``view_perms`` в ``process_view``), а не в префиксах
пути. Поэтому проверка «закрыто ли для сотрудника» = правило маршрута, а прогон запроса
= пол (``__call__``) → resolve → ``process_view`` → вьюха (или заглушка).
"""

from django.http import HttpResponse, HttpResponseNotFound
from django.urls import Resolver404, resolve

from apps.core import permissions, view_perms
from apps.core.middleware import CabinetOwnerAccessMiddleware

URLCONF = "config.urls_tenant"


def rule(path):
    return view_perms.rule_for(resolve(path.split("?")[0], urlconf=URLCONF).view_name)


def _keys(r):
    return {r.read, r.write}


def owner_only(path) -> bool:
    """Ни admin, ни staff по умолчанию сюда не пускаются (пол или ключ вне пресета admin)."""
    r = rule(path)
    admin = permissions.PRESETS["admin"]
    return all(k == view_perms.FLOOR or (k != view_perms.OPEN and k not in admin) for k in _keys(r))


def floor(path) -> bool:
    """Inhaber-Vorbehalt: не выдаётся никому."""
    return _keys(rule(path)) == {view_perms.FLOOR}


def finance_export(path) -> bool:
    """owner + admin (бухгалтер), не staff."""
    r = rule(path)
    keys = _keys(r)
    return keys <= permissions.PRESETS["admin"] and not keys & permissions.PRESETS["staff"]


def open_as(request, view=None):
    """Прогнать запрос через весь гейт. ``view`` — заглушка вместо настоящей вьюхи."""
    middleware = CabinetOwnerAccessMiddleware(None)

    def get_response(req):
        try:
            match = resolve(req.path, urlconf=URLCONF)
        except Resolver404:
            return HttpResponseNotFound()
        req.resolver_match = match
        denied = middleware.process_view(req, match.func, match.args, match.kwargs)
        if denied is not None:
            return denied
        if view is not None:
            return view(req)
        return match.func(req, *match.args, **match.kwargs)

    middleware.get_response = get_response
    return middleware(request)


def ok(_request):
    return HttpResponse("ok")
