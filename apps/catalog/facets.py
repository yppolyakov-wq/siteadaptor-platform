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

from apps.core.facets import FacetProvider, collection_chips, i18n_icontains_q

# Пороги фасета рейтинга (минимум звёзд) — те же значения, что _RATING_THRESHOLDS
# агрегатора (A8); только их принимаем из GET.
RATING_THRESHOLDS = (3, 4, 5)


def _with_size_axis(variants):
    """M4-A: аннотация `size_axis` = ось `size`, а если она пуста — легаси-label.

    Чипы и фильтр обязаны смотреть на ОДНО значение, иначе в смешанном каталоге
    (часть товаров с осями, часть — со старым label) клик по чипу ничего не найдёт.

    O-9: легаси-фолбэк действует ТОЛЬКО у варианта без цвета. У цветового варианта
    (`color` задан, `size` пуст) label и есть название цвета — без этой оговорки
    «Anthrazit» и «Silber» вставали в список размеров рядом с «36» и «S»."""
    from django.db.models import Case, F, Value, When
    from django.db.models.functions import Coalesce, NullIf

    legacy = Case(When(color="", then=F("label")), default=Value(""))
    return variants.annotate(size_axis=Coalesce(NullIf(F("size"), Value("")), legacy))


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
            # M2 Boutique: фасет размера (по variant.label, только доступные).
            "groesse": (params.get("groesse") or "").strip(),
            # O-2: цвет — ось `ProductVariant.color` (M4-A завела ось, фасета не было).
            "farbe": (params.get("farbe") or "").strip(),
            # O-2 (Outlet): состояние товара и марка — своя ось у B-Ware.
            "zustand": (params.get("zustand") or "").strip(),
            "marke": (params.get("marke") or "").strip(),
            # O-2: «nur reduzierte Artikel» — товары с действующей акцией.
            "nur_angebote": params.get("nur_angebote") == "1",
            # M4-B Lookbook: подборка товаров владельца (M2M Collection).
            "kollektion": (params.get("kollektion") or "").strip(),
            "bewertung": bewertung if bewertung in RATING_THRESHOLDS else 0,
        }

    def apply(self, items, params):
        sel = self.selected(params)
        if sel["kategorie"]:
            from django.db.models import Q

            # KAT-1: категория-контейнер включает товары ПРЯМЫХ детей — иначе
            # страница /sortiment/<slug>/ родителя без собственных товаров была
            # бы пустой сеткой под шапкой (осознанная смена семантики фасета).
            items = items.filter(
                Q(category__slug=sel["kategorie"])
                | Q(category__parent__slug=sel["kategorie"], category__parent__is_active=True),
                category__is_active=True,
            )
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
        if sel["groesse"]:
            from django.db.models import Q

            # M4-A: размер = ось `size`, а где её нет — легаси-label (смешанный
            # каталог: часть товаров заведена осями, часть — одним label).
            # pk__in по вариантам вместо джойна: доступность (NULL-остаток =
            # безлимит) считается на варианте, дублей товара не даёт.
            from apps.catalog.models import ProductVariant

            available = ProductVariant.objects.filter(product__in=items, is_active=True).filter(
                Q(stock_quantity__isnull=True) | Q(stock_quantity__gt=0)
            )
            matched = _with_size_axis(available).filter(size_axis=sel["groesse"])
            items = items.filter(pk__in=matched.values("product_id"))
        if sel["farbe"]:
            # O-2: тот же приём, что у размера — pk__in по ДОСТУПНЫМ вариантам
            # (NULL-остаток = безлимит), поэтому распроданный цвет не всплывает.
            from django.db.models import Q

            from apps.catalog.models import ProductVariant

            matched = ProductVariant.objects.filter(
                product__in=items, is_active=True, color=sel["farbe"]
            ).filter(Q(stock_quantity__isnull=True) | Q(stock_quantity__gt=0))
            items = items.filter(pk__in=matched.values("product_id"))
        if sel["zustand"]:
            items = items.filter(condition=sel["zustand"])
        if sel["marke"]:
            items = items.filter(brand=sel["marke"])
        if sel["nur_angebote"]:
            items = items.filter(pk__in=self._discounted_ids(items))
        if sel["kollektion"]:
            # M2M-JOIN по slug активной подборки; distinct — товар может входить
            # в несколько (тот же приём, что у услуг/номеров UB3-2).
            items = items.filter(
                collections__slug=sel["kollektion"], collections__is_active=True
            ).distinct()
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
    def _discounted_ids(items):
        """O-2: pk товаров с ДЕЙСТВУЮЩЕЙ акцией (bulk-карта, без N+1).

        Намеренно НЕ считаем сюда «UVP выше цены»: UVP — сравнение с чужой
        рекомендацией производителя и в аутлете стоит у всей витрины, поэтому
        такой фильтр показывал бы «всё» и был бы чипом-обманкой. «Reduziert» =
        дешевле, чем этот товар стоит здесь обычно, а это ровно акция."""
        from apps.promotions.price_layer import product_promo_map

        return set(product_promo_map(items.values_list("pk", flat=True)).keys())

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
            # M4-B: чипы подборок — только те, где есть товары ЭТОГО набора.
            "collection_chips": collection_chips("products", items),
            # UB2-3: рейтинг-фасет показываем, лишь когда есть отзывы (bulk, без N+1).
            "show_rating_filter": bool(
                review_services.bulk_summary("product", items.values_list("pk", flat=True))
            ),
            "rating_thresholds": RATING_THRESHOLDS,
            # M2 Boutique: чипы размеров (порядок — по sort_order вариантов);
            # один размер на весь каталог = шум, чипы прячем.
            "size_chips": self._size_chips(items),
            # O-2: цвет/состояние/марка — те же правила, что у размера: показываем
            # ось, только когда в наборе БОЛЬШЕ ОДНОГО значения (одно = не фильтр).
            "color_chips": self._color_chips(items),
            "condition_chips": self._condition_chips(items),
            "brand_chips": self._brand_chips(items),
            # O-2: тумблер «только со скидкой» показываем, лишь когда он реально
            # СУЖАЕТ выдачу. В аутлете UVP стоит у всех позиций, и фильтр «всё»
            # был бы чипом-обманкой: покупатель жмёт и ничего не меняется.
            "show_deal_filter": 0 < len(self._discounted_ids(items)) < items.count(),
        }

    @staticmethod
    def _color_chips(items) -> list:
        """O-2: цвета набора — {code, label}. Код и подпись совпадают (цвет ведёт
        владелец свободным текстом), но форма dict оставляет место свотчу."""
        from apps.catalog.models import ProductVariant

        rows = (
            ProductVariant.objects.filter(product__in=items, is_active=True)
            .exclude(color="")
            .values_list("color", flat=True)
            .distinct()
        )
        colors = sorted(set(rows))
        return [{"code": c, "label": c} for c in colors] if len(colors) > 1 else []

    @staticmethod
    def _condition_chips(items) -> list:
        """O-2: состояния, реально встречающиеся в наборе — в порядке реестра
        (от нового к подержанному), а не по алфавиту: это шкала, не список."""
        from apps.catalog.models import Product

        present = set(items.exclude(condition="").values_list("condition", flat=True))
        chips = [
            {"code": code, "label": label}
            for code, label in Product.CONDITION_CHOICES
            if code and code in present
        ]
        return chips if len(chips) > 1 else []

    @staticmethod
    def _brand_chips(items) -> list:
        brands = sorted(set(items.exclude(brand="").values_list("brand", flat=True)))
        return brands if len(brands) > 1 else []

    @staticmethod
    def _size_chips(items) -> list:
        """Чипы размера. M4-A: ось `size`, а где её нет — label (тот же резолвер,
        что у фильтра — иначе клик по чипу ничего не нашёл бы).

        Без оси у товара с цветами чипы были бы декартовым произведением
        («S · Blau», «S · Rot», «M · Blau»…) и фильтр стал бы бессмысленным."""
        from django.db.models import Min

        from apps.catalog.models import ProductVariant

        active = ProductVariant.objects.filter(product__in=items, is_active=True)
        rows = (
            _with_size_axis(active)
            .exclude(size_axis="")
            .values("size_axis")
            .annotate(o=Min("sort_order"))
            .order_by("o", "size_axis")
        )
        sizes = [r["size_axis"] for r in rows]
        return sizes if len(sizes) > 1 else []

    def search(self, items, q):
        q = (q or "").strip()
        if not q:
            return items
        # name/description — JSON i18n {"de","en"}: ищем по всем локалям реестра.
        # O-2: + марка и артикул — в аутлете ищут «Nordvolt» и «OUT-014», а не
        # только слово из названия (тот же приём, что у поиска сделок VS-3).
        from django.db.models import Q

        return items.filter(
            i18n_icontains_q(q, json_fields=("name", "description"))
            | Q(brand__icontains=q)
            | Q(sku__icontains=q)
        )

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
