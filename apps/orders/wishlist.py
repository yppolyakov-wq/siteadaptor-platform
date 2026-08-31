"""M4-C «Merkzettel» (план m4-boutique-plan-2026-07-30 §C): список отложенного.

v1 — СЕССИЯ, по образцу корзины: 0 миграций, без аккаунта, DSGVO-чисто (ничего
не пишем в БД о неавторизованном посетителе). Персист на `promotions.Customer`
с merge при magic-link входе — v2 по спросу.

SF-4a: список стал generic — товары И акции (у магазина акций главный контент —
акции, а Merkzettel их не знал). Хранение по-прежнему в сессии, отдельными
ключами на kind (легаси-ключ `wish` товаров не мигрируем):
`session["wish"] = [<uuid-товара>, …]`, `session["wish_promo"] = [<uuid-акции>, …]`;
порядок = порядок добавления (новое в начало). Кап на длину каждого списка,
чтобы кука сессии не росла бесконечно. Закончившиеся позиции больше не выпадают
молча — помечаются «Beendet» (посетитель видит, ЧТО ушло, и может убрать сам).
"""

WISH_SESSION_KEY = "wish"
WISH_PROMO_SESSION_KEY = "wish_promo"
WISH_MAX = 60

_KEYS = {"product": WISH_SESSION_KEY, "promotion": WISH_PROMO_SESSION_KEY}


def _key(kind: str) -> str:
    return _KEYS.get(kind, WISH_SESSION_KEY)


def _raw(request, kind: str = "product") -> list:
    value = request.session.get(_key(kind))
    return [str(x) for x in value] if isinstance(value, list) else []


def ids(request, kind: str = "product") -> list[str]:
    """Отложенные pk в порядке показа (новое первым)."""
    return _raw(request, kind)


def count(request) -> int:
    """Общий счётчик бейджа шапки: товары + акции."""
    return len(_raw(request, "product")) + len(_raw(request, "promotion"))


def has(request, pk, kind: str = "product") -> bool:
    return str(pk) in _raw(request, kind)


def toggle(request, pk, kind: str = "product") -> bool:
    """Переключить позицию. Возвращает новое состояние (True = в списке)."""
    pk = str(pk)
    current = _raw(request, kind)
    if pk in current:
        current.remove(pk)
        state = False
    else:
        current.insert(0, pk)
        del current[WISH_MAX:]
        state = True
    request.session[_key(kind)] = current
    request.session.modified = True
    return state


def remove(request, pk, kind: str = "product") -> None:
    pk = str(pk)
    current = _raw(request, kind)
    if pk in current:
        current.remove(pk)
        request.session[_key(kind)] = current
        request.session.modified = True


def products(request):
    """Товары списка в порядке отложения. Мёртвые pk (товар удалён) выпадают;
    скрытый товар (is_active=False) остаётся с пометкой `wish_ended` — раньше
    выпадал молча, посетитель не понимал, куда делась позиция (SF-4a)."""
    from apps.catalog.models import Product

    order = _raw(request, "product")
    if not order:
        return []
    found = {str(p.pk): p for p in Product.objects.filter(pk__in=order)}
    out = []
    for pk in order:
        p = found.get(pk)
        if p is None:
            continue
        p.wish_ended = not p.is_active
        out.append(p)
    return out


def promotions(request):
    """Акции списка в порядке отложения (SF-4a). Публичными были только
    active/ended/paused/archived — draft/scheduled выпадают как мёртвые pk;
    не-active помечаются `wish_ended` («Beendet» + ссылка на актуальные)."""
    from apps.promotions.models import Promotion

    order = _raw(request, "promotion")
    if not order:
        return []
    qs = Promotion.objects.filter(
        pk__in=order, status__in=("active", "ended", "paused", "archived")
    ).select_related("product")
    found = {str(p.pk): p for p in qs}
    out = []
    for pk in order:
        p = found.get(pk)
        if p is None:
            continue
        p.wish_ended = p.status != "active"
        out.append(p)
    return out


def enabled(tenant) -> bool:
    """Опция витрины: список отложенного нужен там, где выбирают ВЕЩИ (бутик,
    ритейл, шоп). Гастро/услуги его не показывают — там задача другая.
    Ключ `wishlist` в site_config (presence-minimal); дефолт — по архетипу."""
    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    if "wishlist" in cfg:
        return bool(cfg["wishlist"])
    return getattr(tenant, "business_type", "") in ("clothing", "retail", "online_shop")
