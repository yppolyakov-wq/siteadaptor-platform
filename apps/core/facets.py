"""UB2-1: протокол `FacetProvider` — единый интерфейс фасетов листингов витрины.

Провайдер per-kind ДЕЛЕГИРУЕТ существующей доменной логике приложений (обобщение
`_event_facets`/catalog-in-view без изменения выдачи); резолвер импортирует
провайдеры лениво — `apps.core` не тянет каталог/события/stays на загрузке.

Контракт:
  selected(params) -> dict        — распарсенные/провалидированные значения фасетов
                                    из request.GET-подобного маппинга;
  apply(items, params) -> items   — отфильтровать QuerySet/список (keyset-safe:
                                    фильтры каталога — нативные поля БД);
  present(items, params) -> dict  — доступные значения фасетов для рендера
                                    (считаются из items ДО фасет-фильтров);
  search(items, q) -> items       — UB2-2: поиск `?q=` (icontains v1, решение C-3;
                                    i18n: базовые поля + все локали *_i18n);
  sort(items, key) -> items       — UB2-2: user-facing сортировка; ""/неизвестный
                                    ключ = порядок вьюхи без пересортировки;
  sort_keys()/sort_options()      — реестр сортировок (паттерн _LISTING_SORTS
                                    агрегатора: ключ → (поле|callable, desc)).

Листинги без фасетов получают `NullFacets`. Фасеты цена/наличие/происхождение/
рейтинг — UB2-3.
"""


def i18n_icontains_q(q: str, flat_fields=(), json_fields=()):
    """Q-условие «q встречается в любом из полей на любой локали».

    `flat_fields` — обычные Char/TextField; `json_fields` — JSON-словари i18n
    ({"de": …, "en": …}): KeyTransform per локаль из settings.LANGUAGES →
    text-icontains (Postgres), keyset-safe (обычный WHERE)."""
    from django.conf import settings
    from django.db.models import Q

    cond = Q()
    for f in flat_fields:
        cond |= Q(**{f + "__icontains": q})
    for f in json_fields:
        for code, _label in settings.LANGUAGES:
            cond |= Q(**{f + "__" + code + "__icontains": q})
    return cond


def collection_chips(relation: str, items) -> list:
    """UB3-2: чипы подборок для листинга — только активные коллекции, в которых
    есть сущности из ПЕРЕДАННОГО QuerySet (present-values фасета).

    `relation` — related_name M2M на Collection ("services" | "stay_units").
    Возвращает [{"slug", "label"}] на текущей локали, в порядке sort_order/name."""
    from django.utils.translation import get_language

    from apps.collections.models import Collection

    locale = get_language()
    chips = Collection.objects.filter(is_active=True, **{relation + "__in": items}).distinct()
    return [{"slug": c.slug, "label": c.name_localized(locale)} for c in chips]


class FacetProvider:
    """База/No-op: листинг без фасетов."""

    kind = ""
    default_sort = ""  # "" = порядок вьюхи/Meta без пересортировки

    def selected(self, params) -> dict:
        return {}

    def apply(self, items, params):
        return items

    def present(self, items, params) -> dict:
        return {}

    def search(self, items, q):
        return items

    def sort_keys(self) -> dict:
        return {}

    def sort_options(self) -> list:
        return []

    def sort(self, items, key):
        spec = self.sort_keys().get(key or self.default_sort)
        if spec is None:
            return items
        field, desc = spec
        if callable(field):
            return sorted(items, key=field, reverse=desc)
        return items.order_by(("-" if desc else "") + field)


class NullFacets(FacetProvider):
    pass


def provider_for(kind: str) -> FacetProvider:
    """Провайдер фасетов по kind сущности (`apps.core.sellable.SELLABLE_KINDS`).

    Ленивые импорты: доменные модули грузятся только при обращении."""
    if kind == "event":
        from apps.events.facets import EventFacets

        return EventFacets()
    if kind == "product":
        from apps.catalog.facets import CatalogFacets

        return CatalogFacets()
    if kind == "stay":
        from apps.stays.facets import StayDateFacets

        return StayDateFacets()
    if kind == "service":
        from apps.booking.facets import ServiceFacets

        return ServiceFacets()
    return NullFacets()
