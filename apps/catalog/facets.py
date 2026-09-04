"""UB2-1/2-2/2-3: провайдер каталога — фасеты категория/диета/цена/наличие/
происхождение/рейтинг/размер/цвет/подборка/скидка + поиск/сортировка.

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


def _multi(params, name) -> list:
    """Значения мультивыбора: `?groesse=S&groesse=M` → ["S", "M"].

    `params` бывает и обычным dict (path-режим страницы категории собирает его
    сам), поэтому `getlist` — не гарантия; из простого dict читаем одно значение.
    Порядок сохраняем, дубли и пустое отбрасываем — иначе повтор параметра
    удлинял бы IN-список без смысла."""
    getlist = getattr(params, "getlist", None)
    raw = getlist(name) if callable(getlist) else [params.get(name, "")]
    out = []
    for value in raw:
        value = (value or "").strip()
        if value and value not in out:
            out.append(value)
    return out


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
            # M2 Boutique: фасет размера (ось `size`, иначе легаси-label) —
            # мультивыбор: покупатель почти всегда носит два соседних размера.
            "groesse": _multi(params, "groesse"),
            # 2026-09-03: цвет. Ось `ProductVariant.color` и свотчи на детали
            # были с M4-A, а фильтра на листинге не существовало вовсе.
            "farbe": _multi(params, "farbe"),
            # O-2 (Outlet): состояние товара и марка — своя ось у B-Ware. Здесь
            # мультивыбора нет намеренно: «Neu ohne OVP» и «Retoure» покупатель
            # выбирает по одному, а марок в аутлете десятки (список, не чипы).
            "zustand": (params.get("zustand") or "").strip(),
            "marke": (params.get("marke") or "").strip(),
            # M4-B Lookbook: подборка товаров владельца (M2M Collection).
            "kollektion": (params.get("kollektion") or "").strip(),
            "bewertung": bewertung if bewertung in RATING_THRESHOLDS else 0,
            # 2026-09-03: «Nur reduzierte» — товары с действующей акцией. Считаем
            # тем же резолвером, что рисует промо-цену на карточке (иначе фильтр
            # и витрина разошлись бы).
            "sale": params.get("sale") == "1",
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
        if sel["groesse"] or sel["farbe"]:
            from django.db.models import Q

            # M4-A: размер = ось `size`, а где её нет — легаси-label (смешанный
            # каталог: часть товаров заведена осями, часть — одним label).
            # pk__in по вариантам вместо джойна: доступность (NULL-остаток =
            # безлимит) считается на варианте, дублей товара не даёт.
            from apps.catalog.models import ProductVariant

            available = ProductVariant.objects.filter(product__in=items, is_active=True).filter(
                Q(stock_quantity__isnull=True) | Q(stock_quantity__gt=0)
            )
            matched = _with_size_axis(available)
            # Обе оси сужают ОДИН вариант: «M» + «Sand» = есть песочный в размере M,
            # а не «есть какой-то M и где-то песочный» (иначе выдача обманывает).
            if sel["groesse"]:
                matched = matched.filter(size_axis__in=sel["groesse"])
            if sel["farbe"]:
                matched = matched.filter(color__in=sel["farbe"])
            items = items.filter(pk__in=matched.values("product_id"))
        if sel["zustand"]:
            items = items.filter(condition=sel["zustand"])
        if sel["marke"]:
            items = items.filter(brand=sel["marke"])
        if sel["kollektion"]:
            # M2M-JOIN по slug активной подборки; distinct — товар может входить
            # в несколько (тот же приём, что у услуг/номеров UB3-2).
            items = items.filter(
                collections__slug=sel["kollektion"], collections__is_active=True
            ).distinct()
        if sel["bewertung"]:
            items = items.filter(pk__in=self._rated_ids(items, sel["bewertung"]))
        if sel["sale"]:
            items = items.filter(pk__in=self._discounted_ids(items))
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
        """pk товаров текущего набора с действующей скидкой — тот же резолвер,
        что навешивает промо-цену на карточку (`price_layer.product_promo_map`),
        поэтому «Nur reduzierte» показывает ровно те карточки, где виден бейдж.

        Намеренно НЕ считаем сюда «UVP выше цены»: UVP — сравнение с чужой
        рекомендацией производителя и в аутлете стоит у всей витрины, поэтому
        такой фильтр показывал бы «всё» и был бы чипом-обманкой."""
        from apps.promotions.price_layer import product_promo_map

        return list(product_promo_map(items.values_list("pk", flat=True)).keys())

    @staticmethod
    def _rated_ids(items, min_rating):
        """pk товаров текущего набора со средним ≥ min_rating — один bulk-агрегат."""
        from apps.reviews import services as review_services

        summary = review_services.bulk_summary("product", items.values_list("pk", flat=True))
        return [pk for pk, row in summary.items() if row["avg"] and row["avg"] >= min_rating]

    def present(self, items, params) -> dict:
        from django.db.models import Max, Min

        from apps.catalog import food
        from apps.catalog.models import ProductVariant
        from apps.reviews import services as review_services

        # Диет-чипы считаем по ПЕРЕДАННОМУ срезу, а не по всему каталогу: на
        # странице категории общий список предлагал диету, дающую ноль товаров
        # (разведка 2026-09-03). `Product` остаётся в импортах — нужен для бейджей.
        diet_counts: dict[str, int] = {}
        for vals in items.values_list("diets", flat=True):
            for v in vals or []:
                if v in food.VALID_DIETS:
                    diet_counts[v] = diet_counts.get(v, 0) + 1
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
                {"code": c, "label": label, "icon": icon, "count": diet_counts[c]}
                for c, label, icon in food.DIETS
                if c in diet_counts
            ],
            "price_lo": price_lo,
            "price_hi": price_hi,
            "show_price_filter": price_lo is not None
            and price_hi is not None
            and price_lo != price_hi,
            "show_stock_filter": show_stock,
            # UB2-3: Bio/Regional-Herkunft — только реально указанные значения.
            "origin_chips": self._origin_chips(items),
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
            # 2026-09-03: цвет — свотчи из явного реестра option_styles.COLOR_HEX.
            "color_chips": self._color_chips(items),
            # O-2 (Outlet): состояние и марка — те же правила, что у размера:
            # ось показываем, только когда в наборе БОЛЬШЕ ОДНОГО значения.
            "condition_chips": self._condition_chips(items),
            "brand_chips": self._brand_chips(items),
            # 2026-09-03: «Nur reduzierte» показываем, лишь когда скидки есть.
            "sale_count": len(self._discounted_ids(items)),
        }

    @staticmethod
    def _origin_chips(items) -> list:
        """Значения Herkunft среза со счётчиком товаров."""
        from django.db.models import Count

        rows = (
            items.exclude(origin="")
            .values("origin")
            .annotate(n=Count("id", distinct=True))
            .order_by("origin")
        )
        return [{"value": r["origin"], "count": r["n"]} for r in rows]

    @staticmethod
    def _color_chips(items) -> list:
        """Цвета среза: значение, счётчик товаров и hex из явного реестра.

        Порядок — по первому появлению в вариантах (владелец расставил цвета
        осмысленно), а не по алфавиту. Один цвет на весь срез = шум, прячем."""
        from django.db.models import Count, Min

        from apps.catalog.models import ProductVariant
        from apps.catalog.option_styles import COLOR_HEX

        rows = (
            ProductVariant.objects.filter(product__in=items, is_active=True)
            .exclude(color="")
            .values("color")
            .annotate(n=Count("product_id", distinct=True), o=Min("sort_order"))
            .order_by("o", "color")
        )
        chips = [
            {"value": r["color"], "count": r["n"], "hex": COLOR_HEX.get(r["color"].lower(), "")}
            for r in rows
        ]
        return chips if len(chips) > 1 else []

    @staticmethod
    def _condition_chips(items) -> list:
        """O-2 (Outlet): состояния, реально встречающиеся в наборе — в порядке
        реестра (от нового к подержанному), а не по алфавиту: это шкала."""
        from django.db.models import Count

        from apps.catalog.models import Product

        counts = {
            r["condition"]: r["n"]
            for r in items.exclude(condition="")
            .values("condition")
            .annotate(n=Count("id", distinct=True))
        }
        chips = [
            {"value": code, "label": label, "count": counts[code]}
            for code, label in Product.CONDITION_CHOICES
            if code and code in counts
        ]
        return chips if len(chips) > 1 else []

    @staticmethod
    def _brand_chips(items) -> list:
        """O-2 (Outlet): марки набора со счётчиком — по алфавиту (шкалы нет)."""
        from django.db.models import Count

        rows = (
            items.exclude(brand="")
            .values("brand")
            .annotate(n=Count("id", distinct=True))
            .order_by("brand")
        )
        chips = [{"value": r["brand"], "count": r["n"]} for r in rows]
        return chips if len(chips) > 1 else []

    @staticmethod
    def _size_chips(items) -> list:
        """Чипы размера. M4-A: ось `size`, а где её нет — label (тот же резолвер,
        что у фильтра — иначе клик по чипу ничего не нашёл бы).

        Без оси у товара с цветами чипы были бы декартовым произведением
        («S · Blau», «S · Rot», «M · Blau»…) и фильтр стал бы бессмысленным."""
        from django.db.models import Count, Min

        from apps.catalog.models import ProductVariant

        active = ProductVariant.objects.filter(product__in=items, is_active=True)
        rows = (
            _with_size_axis(active)
            .exclude(size_axis="")
            .values("size_axis")
            .annotate(o=Min("sort_order"), n=Count("product_id", distinct=True))
            .order_by("o", "size_axis")
        )
        sizes = [{"value": r["size_axis"], "count": r["n"]} for r in rows]
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
