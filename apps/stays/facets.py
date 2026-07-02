"""UB2-1/2-2/3-2: провайдер листинга номеров — «фасет дат» + коллекции + поиск/сортировка.

Разбор/валидация date-search параметров — здесь; сам движок наличия/квотирования
(`_quote`/availability) НЕ трогаем (вне единого слоя, решение U-B). Фильтр по
датам — построчный расчёт движка во вьюхе; `apply` фильтрует только подборку
(?kollektion=, UB3-2). Дефолт сортировки "" = Meta ordering ["name"]."""

from django.utils.translation import gettext_lazy as _

from apps.core.facets import FacetProvider, collection_chips, i18n_icontains_q


class StayDateFacets(FacetProvider):
    kind = "stay"

    def selected(self, params) -> dict:
        """Валидные параметры листинга: даты/гости date-search + slug подборки."""
        from apps.stays.public_views import _parse_date, _parse_guests

        adults, children = _parse_guests(params)
        return {
            "von": _parse_date(params.get("von")),
            "bis": _parse_date(params.get("bis")),
            "adults": adults,
            "children": children,
            "kollektion": (params.get("kollektion") or "").strip(),
        }

    def apply(self, items, params):
        """Отфильтровать номера по выбранной подборке (?kollektion=<slug>);
        M2M-JOIN + distinct (номер может входить в несколько подборок)."""
        sel = self.selected(params)
        if sel["kollektion"]:
            items = items.filter(
                collections__slug=sel["kollektion"], collections__is_active=True
            ).distinct()
        return items

    def present(self, items, params) -> dict:
        """Чипы подборок для листинга номеров (из переданного снимка QuerySet)."""
        return {"collection_chips": collection_chips("stay_units", items)}

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
