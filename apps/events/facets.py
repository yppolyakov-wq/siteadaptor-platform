"""UB2-1/2-2: провайдер листинга событий — фасеты таксономии R2 + поиск/сортировка.

Делегирует `_event_facets`/`_event_matches` из `public_views` (канон там —
без изменения выдачи); ленивые импорты рвут цикл модулей. События фильтруются
in-memory (вьюха работает со list) — search/sort тоже in-memory. Дефолт
сортировки "" = порядок вьюхи (starts_at, «по дате»)."""

from django.utils.translation import gettext_lazy as _

from apps.core.facets import FacetProvider

_KEYS = ("cat", "level", "lang", "city", "dur", "month", "teacher")


def _price_key(e):
    """Эффективная цена для сортировки: минимальный тир (has_tiers) либо базовая."""
    value = e.from_price_eur if e.has_tiers else e.price_eur
    return float(value or 0)


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

    def search(self, items, q):
        q = (q or "").strip().lower()
        if not q:
            return items

        def _hit(e):
            vals = [e.title, e.description]
            vals += list((e.title_i18n or {}).values())
            vals += list((e.description_i18n or {}).values())
            return any(q in (v or "").lower() for v in vals)

        return [e for e in items if _hit(e)]

    def sort_keys(self) -> dict:
        return {
            "price_asc": (_price_key, False),
            "price_desc": (_price_key, True),
        }

    def sort_options(self) -> list:
        return [
            ("", _("Date")),
            ("price_asc", _("Price: low to high")),
            ("price_desc", _("Price: high to low")),
        ]
