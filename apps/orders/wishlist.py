"""M4-C «Merkzettel» (план m4-boutique-plan-2026-07-30 §C): список отложенного.

v1 — СЕССИЯ, по образцу корзины: 0 миграций, без аккаунта, DSGVO-чисто (ничего
не пишем в БД о неавторизованном посетителе). Персист на `promotions.Customer`
с merge при magic-link входе — v2 по спросу.

Хранение: `session["wish"] = [<uuid-товара>, …]`, порядок = порядок добавления
(новое в начало — как «последнее отложенное сверху»). Кап на длину, чтобы кука
сессии не росла бесконечно.
"""

WISH_SESSION_KEY = "wish"
WISH_MAX = 60


def _raw(request) -> list:
    value = request.session.get(WISH_SESSION_KEY)
    return [str(x) for x in value] if isinstance(value, list) else []


def ids(request) -> list[str]:
    """Отложенные pk в порядке показа (новое первым)."""
    return _raw(request)


def count(request) -> int:
    return len(_raw(request))


def has(request, pk) -> bool:
    return str(pk) in _raw(request)


def toggle(request, pk) -> bool:
    """Переключить товар. Возвращает новое состояние (True = в списке)."""
    pk = str(pk)
    current = _raw(request)
    if pk in current:
        current.remove(pk)
        state = False
    else:
        current.insert(0, pk)
        del current[WISH_MAX:]
        state = True
    request.session[WISH_SESSION_KEY] = current
    request.session.modified = True
    return state


def remove(request, pk) -> None:
    pk = str(pk)
    current = _raw(request)
    if pk in current:
        current.remove(pk)
        request.session[WISH_SESSION_KEY] = current
        request.session.modified = True


def products(request):
    """Активные товары списка в порядке отложения (мёртвые pk молча выпадают —
    товар мог быть удалён/скрыт после добавления)."""
    from apps.catalog.models import Product

    order = _raw(request)
    if not order:
        return []
    found = {str(p.pk): p for p in Product.objects.filter(pk__in=order, is_active=True)}
    return [found[pk] for pk in order if pk in found]


def enabled(tenant) -> bool:
    """Опция витрины: список отложенного нужен там, где выбирают ВЕЩИ (бутик,
    ритейл, шоп). Гастро/услуги его не показывают — там задача другая.
    Ключ `wishlist` в site_config (presence-minimal); дефолт — по архетипу."""
    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    if "wishlist" in cfg:
        return bool(cfg["wishlist"])
    return getattr(tenant, "business_type", "") in ("clothing", "retail", "online_shop")
