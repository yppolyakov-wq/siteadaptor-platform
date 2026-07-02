"""UB2-1: провайдер фасетов листинга событий (обёртка таксономии R2).

Делегирует `_event_facets`/`_event_matches` из `public_views` (канон там —
без изменения выдачи); ленивые импорты рвут цикл модулей."""

from apps.core.facets import FacetProvider

_KEYS = ("cat", "level", "lang", "city", "dur", "month", "teacher")


class EventFacets(FacetProvider):
    kind = "event"

    def selected(self, params) -> dict:
        return {k: (params.get(k) or "").strip() for k in _KEYS}

    def apply(self, items, params):
        from apps.events.public_views import _event_matches

        selected = self.selected(params)
        return [e for e in items if _event_matches(e, selected)]

    def present(self, items, params) -> dict:
        from apps.events.public_views import _event_facets

        return _event_facets(items)
