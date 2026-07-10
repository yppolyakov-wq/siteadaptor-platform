"""Демо-контент витрины (M20 — кнопки «Demo-Inhalte laden» / «Demo löschen»).

Наполняет витрину как настоящий сайт под тип бизнеса: до ~10 товаров, несколько
акций, а также услуги (booking), номера (stays) и события (events) — там, где
соответствующий модуль активен. Идемпотентно и обратимо: id всех созданных
объектов хранятся в ``Tenant.site_config["demo"]`` (переживает normalize),
«Demo löschen» удаляет ровно их (hard-delete) и зачищает листинги агрегатора.
Без новых моделей/миграций.

Решения владельца: отдельные кнопки загрузки/удаления; демо нельзя оставлять в
проде → удаление точное; контент — реалистичный, по типу бизнеса (2026-06-15).
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from . import siteconfig

# --- Товары по типу бизнеса: (name_de, price_eur, description_de) --------------
_PRODUCTS = {
    "bakery": [
        ("Roggenbrot", "3.20", "Kräftiges Roggenbrot aus dem Steinofen."),
        ("Bauernbrot", "3.80", "Knusprige Kruste, saftige Krume."),
        ("Butter-Croissant", "1.80", "Frisch gebacken, jeden Morgen."),
        ("Schoko-Croissant", "2.00", "Mit zarter Schokoladenfüllung."),
        ("Käsebrötchen", "1.50", "Knusprig mit Gouda überbacken."),
        ("Laugenbrezel", "1.20", "Klassisch mit grobem Salz."),
        ("Apfeltasche", "2.40", "Mit fruchtiger Apfelfüllung."),
        ("Vollkornbrötchen", "0.60", "Mit Sonnenblumenkernen."),
        ("Nussschnecke", "2.20", "Saftig mit Haselnüssen."),
        ("Bienenstich", "2.80", "Mit Mandeln und Vanillecreme."),
    ],
    "butcher": [
        ("Rinderhackfleisch", "9.90", "Frisch gewolft, 100 % Rind (pro kg)."),
        ("Schweineschnitzel", "12.90", "Aus der Oberschale (pro kg)."),
        ("Bratwurst (4 St.)", "5.50", "Hausgemacht nach altem Rezept."),
        ("Rinderfilet", "29.90", "Zart und mager (pro kg)."),
        ("Hähnchenbrust", "11.50", "Ohne Haut, küchenfertig (pro kg)."),
        ("Leberkäse", "6.90", "Hausgemacht, am Stück (pro kg)."),
        ("Grillplatte", "18.90", "Bunte Auswahl für 2 Personen."),
        ("Wiener Würstchen (Paar)", "4.50", "Im Saitling, mild geräuchert."),
    ],
    "grocery": [
        ("Bio-Eier (6 St.)", "2.80", "Aus regionaler Freilandhaltung."),
        ("Bergkäse 200 g", "4.20", "Würzig gereift."),
        ("Imker-Honig 250 g", "5.90", "Aus der Region."),
        ("Vollmilch 1 L", "1.29", "Frische Weidemilch."),
        ("Bio-Äpfel 1 kg", "2.99", "Knackig und süß."),
        ("Kartoffeln 2 kg", "3.49", "Festkochend."),
        ("Tomaten 500 g", "2.49", "Sonnengereift."),
        ("Bauernbutter 250 g", "2.79", "Mild gesäuert."),
        ("Olivenöl 0,5 L", "8.90", "Nativ extra."),
        ("Vollkornnudeln 500 g", "1.99", "Aus Hartweizengrieß."),
    ],
    "cafe": [
        ("Cappuccino", "3.20", "Mit cremigem Milchschaum."),
        ("Latte Macchiato", "3.50", "In Schichten serviert."),
        ("Espresso", "2.20", "Kräftig und aromatisch."),
        ("Käsekuchen", "3.80", "Hausgemacht, Stück."),
        ("Apfelstrudel", "3.90", "Warm mit Vanillesauce."),
        ("Frühstücksteller", "8.50", "Mit Ei, Käse und frischem Brot."),
        ("Heiße Schokolade", "3.40", "Mit Sahnehaube."),
        ("Croissant", "1.80", "Buttrig und frisch."),
    ],
    "restaurant": [
        ("Tagesgericht", "11.90", "Wechselnd – fragen Sie unser Team."),
        ("Hausburger", "13.50", "Mit Pommes und Salat."),
        ("Schnitzel mit Pommes", "14.90", "Knusprig paniert."),
        ("Caesar Salad", "9.90", "Mit Hähnchen und Parmesan."),
        ("Pasta Bolognese", "11.50", "Nach Familienrezept."),
        ("Flammkuchen", "10.90", "Elsässer Art."),
        ("Rumpsteak", "22.90", "200 g, mit Kräuterbutter."),
        ("Tomatensuppe", "5.50", "Mit Basilikum."),
        ("Tiramisu", "5.50", "Hausgemacht."),
        ("Pizza Margherita", "9.50", "Mit Mozzarella und Basilikum."),
    ],
    "clothing": [
        ("Basic T-Shirt", "19.90", "Weiche Bio-Baumwolle."),
        ("Strickpullover", "49.90", "Warm für die kalte Jahreszeit."),
        ("Leinenhemd", "39.90", "Leicht und luftig."),
        ("Jeans Slim Fit", "59.90", "Stretch-Denim."),
        ("Sommerkleid", "45.00", "Leicht fallend."),
        ("Kapuzenpullover", "39.90", "Kuschelig weich."),
        ("Wollschal", "24.90", "Aus Merinowolle."),
        ("Sneaker", "69.90", "Bequem für jeden Tag."),
        ("Ledergürtel", "29.90", "Echtes Leder."),
        ("Strickmütze", "14.90", "Warm und weich."),
    ],
    "retail": [
        ("Geschenkset", "24.90", "Schön verpackt – ideal zum Verschenken."),
        ("Duftkerze", "12.90", "Handgegossen, lange Brenndauer."),
        ("Notizbuch A5", "9.90", "Mit festem Einband."),
        ("Keramiktasse", "11.90", "Handbemalt."),
        ("Wolldecke", "39.90", "Kuschelig warm."),
        ("Pflanzentopf", "8.90", "Aus Keramik."),
        ("Holzbrett", "19.90", "Aus heimischem Holz."),
        ("Seifenset", "16.90", "Natürliche Pflege."),
    ],
    "online_shop": [
        ("Bluetooth-Kopfhörer", "49.90", "Kabellos, 24 h Akku."),
        ("Handyhülle", "14.90", "Stoßfest, viele Modelle."),
        ("Edelstahl-Trinkflasche", "19.90", "0,75 L, isoliert."),
        ('Laptop-Tasche 15"', "29.90", "Wasserabweisend, gepolstert."),
        ("LED-Schreibtischlampe", "34.90", "Dimmbar, USB-C."),
        ("Yogamatte", "24.90", "Rutschfest, 6 mm."),
        ("Rucksack Daypack", "44.90", "20 L, Laptopfach."),
        ("Powerbank 10.000 mAh", "22.90", "2 Geräte gleichzeitig."),
    ],
    "hotel": [
        ("Frühstücksbuffet", "14.00", "Reichhaltig, pro Person."),
        ("Late Check-out", "20.00", "Bis 14 Uhr, je nach Verfügbarkeit."),
        ("Flasche Hauswein", "19.00", "Rot oder weiß, 0,75 L."),
    ],
}
_PRODUCTS_FALLBACK = [
    ("Beispiel-Produkt 1", "9.90", "Ersetzen Sie diesen Text durch Ihre Beschreibung."),
    ("Beispiel-Produkt 2", "14.90", "Ein zweites Beispiel für Ihr Sortiment."),
    ("Beispiel-Produkt 3", "19.90", "Demo-Inhalt — jederzeit löschbar."),
]

# --- Услуги (booking): (name, duration_min, price_eur) -------------------------
_SERVICES = {
    "tour_operator": [
        ("Stadtführung", 90, "25.00"),
        ("Tagesausflug", 480, "89.00"),
        ("Weinprobe", 120, "45.00"),
        ("Fahrradtour", 180, "35.00"),
    ],
    # W3: friseur/werkstatt — primary архетипа = услуги по времени (booking).
    "friseur": [
        ("Haarschnitt Damen", 45, "39.00"),
        ("Haarschnitt Herren", 30, "25.00"),
        ("Färben & Strähnen", 90, "69.00"),
        ("Waschen, Schneiden, Föhnen", 60, "45.00"),
    ],
    "werkstatt": [
        ("Inspektion", 90, "129.00"),
        ("Ölwechsel", 45, "69.00"),
        ("Reifenwechsel", 30, "39.00"),
        ("HU/AU (TÜV)", 60, "119.00"),
    ],
    "other": [
        ("Beratungsgespräch", 60, "60.00"),
        ("Premium-Service", 90, "95.00"),
        ("Basis-Service", 30, "40.00"),
    ],
}

# --- Номера (stays): (name, type, quantity, price_eur, max_guests) -------------
_STAY_UNITS = {
    "hotel": [
        ("Einzelzimmer", "room", 3, "59.00", 1),
        ("Doppelzimmer", "room", 5, "89.00", 2),
        ("Familienzimmer", "room", 2, "129.00", 4),
        ("Suite", "room", 1, "189.00", 2),
    ],
}

# --- События (events): (title, in_days, capacity, price_eur) -------------------
_EVENTS = {
    "tour_operator": [
        ("Geführte Altstadt-Tour", 7, 20, "15.00"),
        ("Weinabend", 14, 30, "39.00"),
    ],
    # W3: архетип «Veranstalter/Events» — билеты его primary.
    "events": [
        ("Live-Konzert", 14, 120, "29.00"),
        ("Comedy-Abend", 21, 80, "24.00"),
        ("Workshop-Tag", 30, 25, "89.00"),
    ],
    "other": [("Workshop: Basics", 10, 12, "49.00")],
    "hotel": [("Candle-Light-Dinner", 5, 20, "59.00")],
}

_CATEGORY_NAME = {"de": "Beliebt"}
_MAX_PROMOS = 3
_PROMO_DISCOUNTS = [20, 15, 25]  # % для первых демо-акций


def has_demo(tenant) -> bool:
    demo = (tenant.site_config or {}).get("demo") if isinstance(tenant.site_config, dict) else None
    demo = demo or {}
    return any(demo.get(k) for k in ("products", "promotions", "services", "stay_units", "events"))


def _eur(value) -> Decimal:
    return Decimal(value)


def load_demo(tenant) -> bool:
    """Создать демо-контент под тип бизнеса в текущей (tenant) схеме. False — уже есть.

    Атомарно (всё или ничего): при сбое любого шага создание откатывается, чтобы
    не оставить осиротевшие объекты без записи в site_config["demo"].
    """
    if has_demo(tenant):
        return False
    from django.db import transaction

    with transaction.atomic():
        _seed_demo(tenant)
    return True


def _purge_orphan_demo() -> None:
    """Убрать демо-объекты от прерванной прошлой загрузки (self-heal).

    Срабатывает только когда has_demo()==False (вызывается из _seed_demo после
    guard'а) — значит в site_config нет валидных ссылок, а в БД могли остаться
    «осиротевшие» демо-объекты (напр., категория demo-beliebt от старой
    не-атомарной загрузки, упавшей до сохранения refs). Иначе повторное
    «Demo laden» вечно падало бы на UNIQUE-слаге категории."""
    from django.db import connection

    from apps.catalog.models import Category, Product
    from apps.promotions.models import Promotion

    schema = connection.schema_name
    promo_ids = [
        str(pid)
        for pid in Promotion.all_objects.filter(metadata__demo=True).values_list("id", flat=True)
    ]
    if promo_ids:
        from apps.aggregator.tasks import sync_listing

        Promotion.all_objects.filter(pk__in=promo_ids).hard_delete()
        for pid in promo_ids:
            sync_listing(schema, pid)
    Product.all_objects.filter(metadata__demo=True).hard_delete()
    # Категория demo-beliebt маркера не имеет (нет metadata) → чистим по слагу
    # (включая soft-deleted, чтобы освободить даже alive-уникальность наверняка).
    Category.all_objects.filter(slug="demo-beliebt").hard_delete()


def _seed_demo(tenant) -> None:
    """Создание объектов демо (внутри transaction.atomic). Контент — только для
    активных модулей: товары/категория всегда (catalog — core); акции — promotions;
    услуги — booking; номера — stays; события — events. Хуки материализуют листинги.
    """
    from apps.catalog.models import Category, Product

    _purge_orphan_demo()  # self-heal: убрать остатки прерванной прошлой загрузки

    is_active = tenant.is_module_active
    refs = {
        "category": "",
        "products": [],
        "promotions": [],
        "services": [],
        "stay_units": [],
        "events": [],
    }

    # --- каталог (всегда) ---
    products = _PRODUCTS.get(tenant.business_type, _PRODUCTS_FALLBACK)
    category = Category.objects.create(name=_CATEGORY_NAME, slug="demo-beliebt", is_active=True)
    refs["category"] = str(category.pk)
    created_products = []
    for i, (name, price, desc) in enumerate(products):
        product = Product.objects.create(
            name={"de": name},
            description={"de": desc},
            base_price=_eur(price),
            category=category,
            is_active=True,
            is_featured=(i < 3),
            metadata={"demo": True},
        )
        created_products.append(product)
        refs["products"].append(str(product.pk))

    # --- акции (если модуль активен и есть товары) ---
    if is_active("promotions") and created_products:
        from apps.promotions.models import Promotion

        now = timezone.now()
        for i, product in enumerate(created_products[:_MAX_PROMOS]):
            discount = _PROMO_DISCOUNTS[i % len(_PROMO_DISCOUNTS)]
            promo = Promotion.objects.create(
                title={"de": f"{product.name['de']} –{discount} %"},
                description={"de": "Demo-Angebot — zum Ausprobieren."},
                product=product,
                promo_type=Promotion.DISCOUNT,
                discount_percent=discount,
                status="active",
                starts_at=now,
                ends_at=now + timedelta(days=14),
                metadata={"demo": True},
            )
            refs["promotions"].append(str(promo.pk))

    # --- услуги (booking) ---
    if is_active("booking") and _SERVICES.get(tenant.business_type):
        from apps.booking.models import Service

        for name, minutes, price in _SERVICES[tenant.business_type]:
            svc = Service.objects.create(
                name=name, duration_minutes=minutes, price_cents=int(_eur(price) * 100)
            )
            refs["services"].append(str(svc.pk))

    # --- номера (stays) ---
    if is_active("stays") and _STAY_UNITS.get(tenant.business_type):
        from apps.stays.models import StayUnit

        for name, utype, qty, price, guests in _STAY_UNITS[tenant.business_type]:
            unit = StayUnit.objects.create(
                name=name,
                type=utype,
                quantity=qty,
                price_cents=int(_eur(price) * 100),
                max_guests=guests,
                is_active=True,
            )
            refs["stay_units"].append(str(unit.pk))

    # --- события (events) ---
    if is_active("events") and _EVENTS.get(tenant.business_type):
        from apps.events.models import Event

        now = timezone.now()
        for title, in_days, capacity, price in _EVENTS[tenant.business_type]:
            event = Event.objects.create(
                title=title,
                starts_at=now + timedelta(days=in_days),
                capacity=capacity,
                price_cents=int(_eur(price) * 100),
                status=Event.STATUS_PUBLISHED,
            )
            refs["events"].append(str(event.pk))

    cfg = siteconfig.normalize(tenant.site_config)
    cfg["demo"] = refs
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config", "updated_at"])


def clear_demo(tenant) -> bool:
    """Удалить ровно демо-объекты (hard-delete) + зачистить листинги агрегатора.

    False — демо не было. Порядок: акции → товары (Promotion.product=SET_NULL, но
    листинг удобнее снять до товаров) → услуги/номера/события. Листинги
    агрегатора снимаются явным sync (источник исчез → remove)."""
    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    demo = cfg.get("demo") or {}
    if not has_demo(tenant):
        return False

    from django.db import connection

    schema = connection.schema_name

    promo_ids = list(demo.get("promotions") or [])
    if promo_ids:
        from apps.aggregator.tasks import sync_listing
        from apps.promotions.models import Promotion

        Promotion.all_objects.filter(pk__in=promo_ids).hard_delete()
        for pid in promo_ids:
            sync_listing(schema, pid)

    if demo.get("products") or demo.get("category"):
        from apps.catalog.models import Category, Product

        Product.all_objects.filter(pk__in=demo.get("products") or []).hard_delete()
        if demo.get("category"):
            Category.all_objects.filter(pk=demo["category"]).hard_delete()

    if demo.get("services"):
        from apps.booking.models import Service

        Service.objects.filter(pk__in=demo["services"]).delete()

    stay_ids = list(demo.get("stay_units") or [])
    if stay_ids:
        from apps.aggregator.tasks import sync_stay_listing
        from apps.stays.models import StayUnit

        StayUnit.objects.filter(pk__in=stay_ids).delete()
        for uid in stay_ids:
            sync_stay_listing(schema, uid)

    event_ids = list(demo.get("events") or [])
    if event_ids:
        from apps.aggregator.tasks import sync_event_listing
        from apps.events.models import Event

        Event.objects.filter(pk__in=event_ids).delete()
        for eid in event_ids:
            sync_event_listing(schema, eid)

    cfg = siteconfig.normalize(tenant.site_config)
    cfg.pop("demo", None)
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config", "updated_at"])
    return True
