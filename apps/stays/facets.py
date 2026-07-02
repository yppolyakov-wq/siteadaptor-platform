"""UB2-1/2-2: провайдер листинга номеров — «фасет дат» + поиск/сортировка.

Разбор/валидация date-search параметров — здесь; сам движок наличия/квотирования
(`_quote`/availability) НЕ трогаем (вне единого слоя, решение U-B). `apply` —
identity: фильтрация по датам — построчный расчёт движка во вьюхе. Дефолт
сортировки "" = Meta ordering ["name"] без пересортировки."""

from django.utils.translation import gettext_lazy as _

from apps.core.facets import FacetProvider, i18n_icontains_q


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

    def search(self, items, q):
        q = (q or "").strip()
        if not q:
            return items
        return items.filter(
            i18n_icontains_q(
                q,
                flat_fields=("name", "description"),
                json_fields=("name_i18n", "description_i18n"),
            )
        )

    def sort_keys(self) -> dict:
        return {
            "price_asc": ("price_cents", False),
            "price_desc": ("price_cents", True),
        }

    def sort_options(self) -> list:
        return [
            ("", _("Standard")),
            ("price_asc", _("Price: low to high")),
            ("price_desc", _("Price: high to low")),
        ]
