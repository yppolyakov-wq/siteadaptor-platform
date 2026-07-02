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
                                    (считаются из items ДО фасет-фильтров).

Листинги без фасетов (booking) получают `NullFacets`. Фасеты цена/наличие/
происхождение/рейтинг — UB2-3; поиск `?q=` и сорт — UB2-2.
"""


class FacetProvider:
    """База/No-op: листинг без фасетов."""

    kind = ""

    def selected(self, params) -> dict:
        return {}

    def apply(self, items, params):
        return items

    def present(self, items, params) -> dict:
        return {}


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
    return NullFacets()
