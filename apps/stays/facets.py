"""UB2-1: провайдер «фасета дат» листинга номеров (date-search von/bis/erw/kinder).

Разбор/валидация параметров поиска — здесь; сам движок наличия/квотирования
(`_quote`/availability) НЕ трогаем (вне единого слоя, решение U-B). `apply` —
identity: фильтрация по датам — построчный расчёт движка во вьюхе."""

from apps.core.facets import FacetProvider


class StayDateFacets(FacetProvider):
    kind = "stay"

    def selected(self, params) -> dict:
        from apps.stays.public_views import _parse_date, _parse_guests

        adults, children = _parse_guests(params)
        return {
            "von": _parse_date(params.get("von")),
            "bis": _parse_date(params.get("bis")),
            "adults": adults,
            "children": children,
        }
