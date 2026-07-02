"""UB2-2: провайдер листинга услуг — поиск/сортировка (фасетов у услуг нет).

Дефолт сортировки "" = Meta ordering ["name"] без пересортировки."""

from django.utils.translation import gettext_lazy as _

from apps.core.facets import FacetProvider, i18n_icontains_q


class ServiceFacets(FacetProvider):
    kind = "service"

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
            "newest": ("created_at", True),
        }

    def sort_options(self) -> list:
        return [
            ("", _("Standard")),
            ("price_asc", _("Price: low to high")),
            ("price_desc", _("Price: high to low")),
            ("newest", _("Newest")),
        ]
