"""Демо-контент витрины (M20 — кнопки «Demo-Inhalte laden» / «Demo löschen»).

Чтобы после выбора шаблона витрина сразу выглядела живой, а не пустой. Создаёт
показательный каталог (категория + товары) и одну активную акцию в схеме
тенанта. Идемпотентно и обратимо: id созданных объектов хранятся в
``Tenant.site_config["demo"]`` (переживает normalize, см. siteconfig), «Demo
löschen» удаляет ровно их (hard-delete) и зачищает листинг агрегатора. Без
новых моделей/миграций.

Решения владельца (2026-06-15): отдельные кнопки загрузки/удаления (не авто
при шаблоне); демо нельзя оставлять в проде → удаление обязательно и точное.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from . import siteconfig

# Наборы товаров по типу бизнеса: (name_de, price_eur, description_de).
# Подобраны узнаваемо под вертикаль; для незнакомого типа — общий fallback.
_PRODUCTS = {
    "bakery": [
        ("Roggenbrot", "3.20", "Kräftiges Roggenbrot aus dem Steinofen."),
        ("Butter-Croissant", "1.80", "Frisch gebacken, jeden Morgen."),
        ("Käsebrötchen", "1.50", "Knusprig mit Gouda überbacken."),
        ("Apfeltasche", "2.40", "Mit fruchtiger Apfelfüllung."),
    ],
    "butcher": [
        ("Rinderhackfleisch", "9.90", "Frisch gewolft, 100 % Rind."),
        ("Bratwurst (4 St.)", "5.50", "Hausgemacht nach altem Rezept."),
        ("Schweineschnitzel", "12.90", "Aus der Oberschale, paniert oder natur."),
    ],
    "grocery": [
        ("Bio-Eier (6 St.)", "2.80", "Aus regionaler Freilandhaltung."),
        ("Bergkäse 200 g", "4.20", "Würzig gereift."),
        ("Honig 250 g", "5.90", "Vom Imker aus der Region."),
    ],
    "cafe": [
        ("Cappuccino", "3.20", "Mit cremigem Milchschaum."),
        ("Käsekuchen", "3.80", "Hausgemacht, Stück."),
        ("Frühstücksteller", "8.50", "Mit Ei, Käse und frischem Brot."),
    ],
    "restaurant": [
        ("Tagesgericht", "11.90", "Wechselnd – fragen Sie unser Team."),
        ("Hausburger", "13.50", "Mit Pommes und Salat."),
        ("Tiramisu", "5.50", "Nach Familienrezept."),
    ],
    "clothing": [
        ("Basic T-Shirt", "19.90", "Weiche Bio-Baumwolle."),
        ("Strickpullover", "49.90", "Warm für die kalte Jahreszeit."),
        ("Leinenhemd", "39.90", "Leicht und luftig."),
    ],
    "retail": [
        ("Geschenkset", "24.90", "Schön verpackt – ideal zum Verschenken."),
        ("Duftkerze", "12.90", "Handgegossen, lange Brenndauer."),
        ("Notizbuch A5", "9.90", "Mit festem Einband."),
    ],
    "hotel": [
        ("Frühstück für Gäste", "14.00", "Reichhaltiges Buffet, pro Person."),
        ("Late Check-out", "20.00", "Bis 14 Uhr, je nach Verfügbarkeit."),
    ],
}
_PRODUCTS_FALLBACK = [
    ("Beispiel-Produkt 1", "9.90", "Ersetzen Sie diesen Text durch Ihre Beschreibung."),
    ("Beispiel-Produkt 2", "14.90", "Ein zweites Beispiel für Ihr Sortiment."),
    ("Beispiel-Produkt 3", "19.90", "Demo-Inhalt — jederzeit löschbar."),
]

_CATEGORY_NAME = {"de": "Beliebt"}
_DEMO_DISCOUNT = 20  # % скидки демо-акции


def has_demo(tenant) -> bool:
    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    demo = cfg.get("demo") or {}
    return bool(demo.get("products") or demo.get("promotions") or demo.get("category"))


def _products_for(business_type) -> list:
    return _PRODUCTS.get(business_type, _PRODUCTS_FALLBACK)


def load_demo(tenant) -> bool:
    """Создать демо-каталог + акцию в текущей (tenant) схеме. False — уже есть.

    Вызывать в контексте схемы тенанта (как и весь кабинет). Хук post_save
    Promotion сам материализует листинг в агрегатор (active → upsert).
    """
    if has_demo(tenant):
        return False

    from apps.catalog.models import Category, Product
    from apps.promotions.models import Promotion

    category = Category.objects.create(name=_CATEGORY_NAME, slug="demo-beliebt", is_active=True)
    product_ids = []
    first_product = None
    for i, (name, price, desc) in enumerate(_products_for(tenant.business_type)):
        product = Product.objects.create(
            name={"de": name},
            description={"de": desc},
            base_price=Decimal(price),
            category=category,
            is_active=True,
            is_featured=(i == 0),
            metadata={"demo": True},
        )
        product_ids.append(str(product.pk))
        if first_product is None:
            first_product = product

    # Одна активная демо-акция (скидка на первый товар) — наполняет секцию
    # «Aktuelle Angebote» и попадает в агрегатор как настоящая.
    now = timezone.now()
    promo = Promotion.objects.create(
        title={"de": f"{first_product.name['de']} –{_DEMO_DISCOUNT} %"},
        description={"de": "Demo-Angebot — zum Ausprobieren."},
        product=first_product,
        promo_type=Promotion.DISCOUNT,
        discount_percent=_DEMO_DISCOUNT,
        status="active",
        starts_at=now,
        ends_at=now + timedelta(days=14),
        metadata={"demo": True},
    )

    cfg = siteconfig.normalize(tenant.site_config)
    cfg["demo"] = {
        "category": str(category.pk),
        "products": product_ids,
        "promotions": [str(promo.pk)],
    }
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config", "updated_at"])
    return True


def clear_demo(tenant) -> bool:
    """Удалить ровно демо-объекты (hard-delete) + зачистить листинг агрегатора.

    False — демо не было. Промо/товары/категория — SoftDelete, поэтому
    hard_delete через all_objects, чтобы реально убрать (демо не должно остаться).
    """
    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    demo = cfg.get("demo") or {}
    if not has_demo(tenant):
        return False

    from django.db import connection

    from apps.aggregator.tasks import sync_listing
    from apps.catalog.models import Category, Product
    from apps.promotions.models import Promotion

    promo_ids = list(demo.get("promotions") or [])
    Promotion.all_objects.filter(pk__in=promo_ids).hard_delete()
    # Акция удалена → убрать её листинг из агрегатора (sync видит отсутствие).
    for pid in promo_ids:
        sync_listing(connection.schema_name, pid)

    Product.all_objects.filter(pk__in=demo.get("products") or []).hard_delete()
    if demo.get("category"):
        Category.all_objects.filter(pk=demo["category"]).hard_delete()

    cfg = siteconfig.normalize(tenant.site_config)
    cfg.pop("demo", None)
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config", "updated_at"])
    return True
