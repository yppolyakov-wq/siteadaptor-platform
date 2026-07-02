"""UB2-1: провайдер фасетов каталога — категория (slug) + диета (A4).

Обобщает in-view логику `product_list` без изменения выдачи: apply — нативные
поля БД (composable с keyset-пагинацией); present — диет-чипы только реально
встречающихся диет (по ВСЕМ активным товарам, не по выбранной категории — как
было во вьюхе). Цена/бейдж/наличие переезжают сюда в UB2-3."""

from apps.core.facets import FacetProvider


class CatalogFacets(FacetProvider):
    kind = "product"

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
