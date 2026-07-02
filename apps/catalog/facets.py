"""UB2-1/2-2/2-3: провайдер каталога — фасеты категория/диета/цена/наличие/
происхождение/рейтинг + поиск/сортировка.

Обобщает in-view логику `product_list` без изменения выдачи: apply — нативные
поля БД / `pk__in` (composable с keyset-пагинацией); present — доступные значения
из ПЕРЕДАННОГО QuerySet (снимок категории до фасет-фильтров), кроме диет-чипов —
они по ВСЕМ активным товарам (как было во вьюхе). Рейтинг-фасет читает
`reviews.services.bulk_summary` (один агрегат-запрос, без N+1); сортировки =
прежний _CATALOG_SORTS (keyset-поля; paginate навешивает order_by сам)."""

from decimal import Decimal, InvalidOperation

from django.utils.translation import gettext_lazy as _

from apps.core.facets import FacetProvider, i18n_icontains_q

# Пороги фасета рейтинга (минимум звёзд) — те же значения, что _RATING_THRESHOLDS
# агрегатора (A8); только их принимаем из GET.
RATING_THRESHOLDS = (3, 4, 5)


def _money(raw):
    """Decimal из пользовательского ввода цены («12,50» тоже); мусор/минус → None."""
    try:
        value = Decimal(str(raw).replace(",", ".").strip())
    except (InvalidOperation, AttributeError):
        return None
    return value if value >= 0 else None


class CatalogFacets(FacetProvider):
    kind = "product"
    default_sort = "newest"

    def selected(self, params) -> dict:
        from apps.catalog import food

        diet = params.get("diet", "")
        try:
            bewertung = int(params.get("bewertung", ""))
        except (TypeError, ValueError):
            bewertung = 0
        return {
            "kategorie": (params.get("kategorie") or "").strip(),
            "diet": diet if diet in food.VALID_DIETS else "",
            "preis_von": _money(params.get("preis_von")),
            "preis_bis": _money(params.get("preis_bis")),
            "nur_verfuegbar": params.get("nur_verfuegbar") == "1",
            "herkunft": (params.get("herkunft") or "").strip(),
            "bewertung": bewertung if bewertung in RATING_THRESHOLDS else 0,
        }

    def apply(self, items, params):
        sel = self.selected(params)
        if sel["kategorie"]:
            items = items.filter(category__slug=sel["kategorie"], category__is_active=True)
        if sel["diet"]:
            items = items.filter(diets__contains=[sel["diet"]])
        if sel["preis_von"] is not None:
            items = items.filter(base_price__gte=sel["preis_von"])
        if sel["preis_bis"] is not None:
            items = items.filter(base_price__lte=sel["preis_bis"])
        if sel["nur_verfuegbar"]:
            items = self._only_available(items)
        if sel["herkunft"]:
            items = items.filter(origin=sel["herkunft"])
        if sel["bewertung"]:
            items = items.filter(pk__in=self._rated_ids(items, sel["bewertung"]))
        return items

    @staticmethod
    def _only_available(items):
        """«Nur verfügbare»: наличие с учётом вариантов (зеркало Product.in_stock)."""
        from django.db.models import Exists, OuterRef, Q

        from apps.catalog.models import ProductVariant

        active_var = ProductVariant.objects.filter(product=OuterRef("pk"), is_active=True)
        in_stock_var = active_var.filter(Q(stock_quantity__isnull=True) | Q(stock_quantity__gt=0))
        return items.annotate(
            _has_var=Exists(active_var),
            _has_stock_var=Exists(in_stock_var),
        ).filter(
            Q(_has_var=True, _has_stock_var=True)
            | (Q(_has_var=False) & (Q(stock_quantity__isnull=True) | Q(stock_quantity__gt=0)))
        )

    @staticmethod
    def _rated_ids(items, min_rating):
        """pk товаров текущего набора со средним ≥ min_rating — один bulk-агрегат."""
        from apps.reviews import services as review_services

        summary = review_services.bulk_summary("product", items.values_list("pk", flat=True))
        return [pk for pk, row in summary.items() if row["avg"] and row["avg"] >= min_rating]

    def present(self, items, params) -> dict:
        from django.db.models import Max, Min

        from apps.catalog import food
        from apps.catalog.models import Product, ProductVariant
        from apps.reviews import services as review_services

        present_diets = set()
        for vals in Product.objects.filter(is_active=True).values_list("diets", flat=True):
            present_diets.update(v for v in (vals or []) if v in food.VALID_DIETS)
        bounds = items.aggregate(lo=Min("base_price"), hi=Max("base_price"))
        price_lo, price_hi = bounds["lo"], bounds["hi"]
        # Тумблер наличия — только если что-то реально распродано (иначе шум).
        show_stock = (
            items.filter(stock_quantity=0).exists()
            or ProductVariant.objects.filter(
                product__in=items, is_active=True, stock_quantity=0
            ).exists()
        )
        return {
            "diet_chips": [
                {"code": c, "label": label, "icon": icon}
                for c, label, icon in food.DIETS
                if c in present_diets
            ],
            "price_lo": price_lo,
            "price_hi": price_hi,
            "show_price_filter": price_lo is not None
            and price_hi is not None
            and price_lo != price_hi,
            "show_stock_filter": show_stock,
            # UB2-3: Bio/Regional-Herkunft — только реально указанные значения.
            "origin_chips": sorted(set(items.exclude(origin="").values_list("origin", flat=True))),
            # UB2-3: рейтинг-фасет показываем, лишь когда есть отзывы (bulk, без N+1).
            "show_rating_filter": bool(
                review_services.bulk_summary("product", items.values_list("pk", flat=True))
            ),
            "rating_thresholds": RATING_THRESHOLDS,
        }

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
