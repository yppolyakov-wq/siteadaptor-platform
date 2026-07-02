"""UB2-2/3-2: провайдер листинга услуг — фасет коллекций + поиск/сортировка.

Дефолт сортировки "" = Meta ordering ["name"] без пересортировки."""

from django.utils.translation import gettext_lazy as _

from apps.core.facets import FacetProvider, collection_chips, i18n_icontains_q


class ServiceFacets(FacetProvider):
    kind = "service"

    def selected(self, params) -> dict:
        """Валидные значения фасетов из GET: пока только slug подборки (UB3-2)."""
        return {"kollektion": (params.get("kollektion") or "").strip()}

    def apply(self, items, params):
        """Отфильтровать услуги по выбранной подборке (?kollektion=<slug>).

        M2M-JOIN по slug активной коллекции; distinct — услуга может входить в
        несколько подборок. Обычный WHERE → composable с поиском/сортировкой."""
        sel = self.selected(params)
        if sel["kollektion"]:
            items = items.filter(
                collections__slug=sel["kollektion"], collections__is_active=True
            ).distinct()
        return items

    def present(self, items, params) -> dict:
        """Чипы подборок для листинга услуг: только коллекции, где есть услуги
        из ПЕРЕДАННОГО набора (снимок до фасет-фильтров)."""
        return {"collection_chips": collection_chips("services", items)}

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
