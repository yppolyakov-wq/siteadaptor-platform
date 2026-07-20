"""FD-4: платформенный Finder агрегатора — «найди Angebot под задачу».

Public-схема, кросс-тенантно над денормализованными AggregatorListing —
тенантский apps/core/finder.py сюда НЕ переносится (display_fields/M2M живут в
схеме тенанта). Дерево — живые данные пула (вертикали/города), не конфиг:
у агрегатора нет site_config. UWG §5a: выдача ОРГАНИЧЕСКАЯ — featured не
переприоритизируется; в карточках платное несёт обычную метку «★ Anzeige»
(реюз _cards.html; замок в тестах).
"""

from apps.tenants.models import Tenant

from .models import AggregatorListing

_RESULTS = 3


def _active():
    return AggregatorListing.objects.filter(is_active=True)


def type_options():
    """Вертикали с живыми листингами: (business_type, DE-метка из choices)."""
    labels = dict(Tenant.BUSINESS_TYPES)
    types = _active().exclude(business_type="").values_list("business_type", flat=True)
    return [(t, str(labels.get(t, t))) for t in sorted(set(types))]


def city_options(business_type=""):
    """Города с листингами выбранной вертикали (или все)."""
    qs = _active()
    if business_type:
        qs = qs.filter(business_type=business_type)
    return sorted({c for c in qs.values_list("city", flat=True) if c})


def resolve_public(typ, stadt):
    """Состояние диалога: шаг 1 (вертикаль) → шаг 2 (город) → 3 Angebote.

    Порядок выдачи — дефолтный listings_for (органический; НЕ переставляем
    платные позиции — UWG §5a). Пусто → честный фолбэк «сейчас популярно»."""
    from . import recommendations
    from .views import listings_for

    types = type_options()
    if typ not in {t for t, _label in types}:
        return {"step": 1, "total": 2, "type_options": types}
    cities = city_options(typ)
    if stadt not in cities:
        return {"step": 2, "total": 2, "typ": typ, "city_options": cities}
    results = list(listings_for(city=stadt, business_type=typ)[:_RESULTS])
    fallback = False
    if not results:
        results = list(recommendations.ending_soon(limit=_RESULTS)) or list(_active()[:_RESULTS])
        fallback = True
    return {
        "step": 3,
        "total": 2,
        "typ": typ,
        "stadt": stadt,
        "results": results,
        "fallback": fallback,
    }
