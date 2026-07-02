"""UB2-1/2-2: провайдер каталога — фасеты категория/диета + поиск/сортировка.

Обобщает in-view логику `product_list` без изменения выдачи: apply — нативные
поля БД (composable с keyset-пагинацией); present — диет-чипы только реально
встречающихся диет (по ВСЕМ активным товарам, не по выбранной категории — как
было во вьюхе). Сортировки = прежний _CATALOG_SORTS (keyset-поля; paginate
навешивает order_by сам — вьюха берёт sort_keys()). Цена/бейдж/наличие — UB2-3."""

from django.utils.translation import gettext_lazy as _

from apps.core.facets import FacetProvider, i18n_icontains_q


class CatalogFacets(FacetProvider):
    kind = "product"
    default_sort = "newest"

    def search(self, items, q):
        q = (q or "").strip()
        if not q:
            return items
        # name/description — JSON i18n {"de","en"}: ищем по всем локалям реестра.
        return items.filter(i18n_icontains_q(q, json_fields=("name", "description")))

    def sort_keys(self) -> dict:
        return {
            "newest": ("created_at", True),
            "price_asc": ("base_price", False),
            "price_desc": ("base_price", True),
        }

    def sort_options(self) -> list:
        return [
            ("newest", _("Newest")),
            ("price_asc", _("Price: low to high")),
            ("price_desc", _("Price: high to low")),
        ]

    def selected(self, params) -> dict:
        from apps.catalog import food

        diet = params.get("diet", "")
        return {
            "kategorie": (params.get("kategorie") or "").strip(),
            "diet": diet if diet in food.VALID_DIETS else "",
        }

    def apply(self, items, params):
        sel = self.selected(params)
        if sel["kategorie"]:
            items = items.filter(category__slug=sel["kategorie"], category__is_active=True)
        if sel["diet"]:
            items = items.filter(diets__contains=[sel["diet"]])
        return items

    def present(self, items, params) -> dict:
        from apps.catalog import food
        from apps.catalog.models import Product

        present_diets = set()
        for vals in Product.objects.filter(is_active=True).values_list("diets", flat=True):
            present_diets.update(v for v in (vals or []) if v in food.VALID_DIETS)
        return {
            "diet_chips": [
                {"code": c, "label": label, "icon": icon}
                for c, label, icon in food.DIETS
                if c in present_diets
            ]
        }
