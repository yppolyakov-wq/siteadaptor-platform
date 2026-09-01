"""DL-8e: смена шаблона НА ДЕМО-ВИТРИНЕ без входа в кабинет.

Фидбэк владельца 2026-09-01: посетитель демо (например, с /branchen/) должен
пощёлкать шаблоны прямо на сайте. Механика read-only: выбор живёт в СЕССИИ
посетителя, конфиг тенанта не пишется никогда; оверлей — тот же stateless-
механизм, что у превью `?preview=1&bundle=` (кожа Look'а + оси сборки).
Кнопка и роут существуют ТОЛЬКО на демо-тенантах (слаги демо-китов) —
у живого бизнеса посетитель ничего переключить не может.
"""

from functools import lru_cache

from django.http import Http404
from django.shortcuts import redirect

SESSION_KEY = "demo_design"


@lru_cache(maxsize=1)
def _demo_slugs() -> frozenset:
    from apps.tenants import demo_kits

    return frozenset((kit.subdomain or key) for key, kit in demo_kits.KITS.items())


def is_demo_tenant(tenant) -> bool:
    """Демо = тенант на слаге демо-кита (их создаёт только seed_demo_tenants)."""
    try:
        return getattr(tenant, "slug", "") in _demo_slugs()
    except Exception:  # noqa: BLE001 — сбой реестра не должен ронять витрину
        return False


def overlay_bundle_key(request) -> str:
    """Ключ сборки-оверлея для ЭТОГО рендера: явный `?preview=1&bundle=` глав-
    нее; иначе — выбор из демо-сессии (только на демо-тенанте). "" = нет."""
    if request.GET.get("preview") == "1":
        return request.GET.get("bundle", "")
    if not hasattr(request, "session"):
        return ""
    key = request.session.get(SESSION_KEY, "")
    if key and is_demo_tenant(getattr(request, "tenant", None)):
        return key
    return ""


def demo_design_switch(request):
    """GET ?tpl=<bundle|standard>&next=/pfad — записать выбор в сессию
    посетителя (прецедент set_language). 404 вне демо-тенанта."""
    from apps.tenants import sitetemplates

    if not is_demo_tenant(getattr(request, "tenant", None)):
        raise Http404
    tpl = request.GET.get("tpl", "")
    if tpl == "standard":
        request.session.pop(SESSION_KEY, None)
    elif sitetemplates.get_bundle(tpl) is not None:
        request.session[SESSION_KEY] = tpl
    nxt = request.GET.get("next", "/")
    # Только локальный путь (не //host — открытый редирект).
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = "/"
    return redirect(nxt)
