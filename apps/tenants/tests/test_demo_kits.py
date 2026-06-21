"""M20 demo: киты — полноценная showcase-витрина (apply_kit)."""

import pytest

from apps.catalog.models import (
    Category,
    ModifierGroup,
    ModifierOption,
    Product,
    ProductVariant,
)
from apps.promotions.models import Promotion
from apps.tenants import demo_kits
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant():
    return TenantFactory(schema_name="public", slug="x", name="X", business_type="restaurant")


def test_unknown_kit_returns_false():
    assert demo_kits.apply_kit(_tenant(), "nope") is False


def test_demo_image_is_themed_and_deterministic():
    url = demo_kits.demo_image("pizza margherita", lock=5)
    assert url == "https://loremflickr.com/800/600/pizza,margherita?lock=5"


def test_apply_restaurant_kit_builds_full_site():
    tenant = _tenant()
    assert demo_kits.apply_kit(tenant, "restaurant") is True

    # каталог: несколько категорий + товары с фото
    assert Category.objects.filter(slug__startswith="demo-").count() == 4
    products = Product.objects.filter(metadata__demo=True)
    assert products.count() >= 28
    assert all(p.images and p.images[0]["url"].startswith("https://") for p in products)
    # варианты (Pizza klein/groß) и аллергены проставлены
    assert ProductVariant.objects.count() >= 6
    assert products.filter(allergens__contains=["gluten"]).exists()
    # акции (4 — сетка кратна 2)
    assert Promotion.objects.filter(metadata__demo=True).count() == 4

    # site_config: фото-hero, акцент, галерея, контент-секции
    cfg = tenant.site_config
    assert cfg["hero_image"].startswith("https://loremflickr.com/")
    assert tenant.primary_color == "#b45309"
    assert len(cfg["gallery"]) == 6
    assert cfg["faq"] and cfg["testimonials"] and cfg["cta"]["button_url"] == "/sortiment/"
    assert cfg["gallery_video"].startswith("https://")  # T1: видео в галерее
    enabled = {s["key"] for s in cfg["sections"] if s["enabled"]}
    assert {"hero", "products", "promotions", "gallery", "faq", "cta"} <= enabled
    assert cfg["nav"]["style"] == "centered"


def test_restaurant_kit_seeds_pizza_modifiers():
    """Конструктор блюда (A4): пицца получает группы модификаторов с опциями."""
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "restaurant")

    pizza = Product.objects.get(name__de="Pizza Margherita")
    groups = list(pizza.modifier_groups.filter(is_active=True).order_by("sort_order"))
    names = [g.name for g in groups]
    assert "Teig" in names and "Beläge hinzufügen" in names
    # обязательная одиночная группа Teig (radio), множественная Beläge
    teig = next(g for g in groups if g.name == "Teig")
    assert teig.is_required and not teig.is_multi
    belaege = next(g for g in groups if g.name == "Beläge hinzufügen")
    assert belaege.is_multi and not belaege.is_required
    # надбавка цены у опции (Dick +1,00)
    assert ModifierOption.objects.filter(group=teig, label="Dick", price_delta=1).exists()
    # стейк тоже имеет конструктор (Beilage обязательна)
    steak = Product.objects.get(name__de="Rumpsteak")
    assert steak.modifier_groups.filter(name="Beilage", min_select__gte=1).exists()
    assert ModifierGroup.objects.filter(is_active=True).count() >= 5


def test_restaurant_kit_sets_dish_badges():
    """T1: бейджи блюд (Tagesgericht/Neu) проставлены в демо."""
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "restaurant")
    assert Product.objects.get(name__de="Lasagne").badge == "tagesgericht"
    pizza_veg = Product.objects.get(name__de="Pizza Vegetariana")
    assert pizza_veg.badge == "neu" and pizza_veg.badge_label == "Neu"


def test_restaurant_kit_enables_orders_and_delivery():
    """Демо-ресторан показывает онлайн-заказ: модуль orders включён + доставка с зонами."""
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "restaurant")

    assert "orders" not in (tenant.disabled_modules or [])
    assert tenant.is_module_active("orders")
    assert tenant.delivery_enabled is True
    assert tenant.delivery_fee_cents == 290
    assert tenant.delivery_free_cents == 2500
    assert tenant.delivery_min_cents == 1500
    # PLZ-зоны A2a
    plz = {z["plz"] for z in tenant.delivery_zones}
    assert {"40721", "40724"} <= plz


def test_restaurant_kit_seeds_events_catering_loyalty():
    """Демо-ресторан показывает события, кейтеринг (jobs) и лояльность."""
    from apps.events.models import Event
    from apps.promotions.models import LoyaltyProgram

    tenant = _tenant()
    demo_kits.apply_kit(tenant, "restaurant")

    # события опубликованы и в будущем
    events = Event.objects.filter(status=Event.STATUS_PUBLISHED)
    assert events.count() == 4
    assert events.filter(title="Live-Musik: Italienische Nacht").exists()
    # бесплатное (price 0) и платные
    assert events.filter(price_cents=0).exists() and events.filter(price_cents=3500).exists()

    # кейтеринг = модуль jobs активен (форма /anfrage/)
    assert tenant.is_module_active("jobs")

    # программа лояльности (штампы)
    program = LoyaltyProgram.objects.get(is_active=True)
    assert program.stamps_required == 10 and program.reward_label == "1 Gratis-Pizza"


def test_restaurant_kit_seeds_bookable_table():
    """Бронь столика работает: ресурс + недельное расписание → /termin/ даёт слоты."""
    from apps.booking import availability
    from apps.booking.models import AvailabilityRule, Resource

    tenant = _tenant()
    demo_kits.apply_kit(tenant, "restaurant")
    assert Resource.objects.filter(is_active=True).count() == 1
    assert AvailabilityRule.objects.count() == 7  # все дни недели
    resource = Resource.objects.first()
    # на ближайший день недельного окна есть свободные слоты
    from datetime import timedelta

    from django.utils import timezone

    found = any(
        availability.free_slots_with_spots(resource, (timezone.localdate() + timedelta(days=d)))
        for d in range(1, 8)
    )
    assert found


def test_apply_pranasy_kit_uses_constructor_features():
    """Демо «Pranasy» использует конструктор: группы акций, секция «Bereiche»,
    многоуровневое меню, обложки разделов."""
    tenant = TenantFactory(schema_name="public", slug="p", name="P", business_type="restaurant")
    assert demo_kits.apply_kit(tenant, "pranasy") is True
    cfg = tenant.site_config

    # направления = категории каталога
    assert Category.objects.filter(slug="demo-fastfood").exists()
    assert Category.objects.filter(slug="demo-fertig").exists()
    # S6: обе группы акций представлены
    groups = set(Promotion.objects.filter(metadata__demo=True).values_list("group", flat=True))
    assert {"Fastfood", "Fertiggerichte"} <= groups
    # S2: секция «Unsere Bereiche» включена
    assert "archetypes" in {s["key"] for s in cfg["sections"] if s["enabled"]}
    # S7: многоуровневое меню с подменю Speisekarte → Fastfood/Fertiggerichte
    speise = next(i for i in cfg["menus"]["top"]["items"] if i["label"] == "Speisekarte")
    assert [c["label"] for c in speise["children"]] == ["Fastfood", "Fertiggerichte"]
    assert cfg["menus"]["bottom"]["enabled"] is True
    # S3: обложка раздела catalog (интро + галерея)
    assert cfg["archetypes"]["catalog"]["intro"]
    assert cfg["archetypes"]["catalog"]["gallery"]
    # модули направлений активны
    for m in ("orders", "events", "jobs", "loyalty"):
        assert tenant.is_module_active(m)


def test_pranasy_menu_resolves_categories_and_promo_groups(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.tenants import menu

    tenant = TenantFactory(schema_name="public", slug="p2", name="P2", business_type="restaurant")
    demo_kits.apply_kit(tenant, "pranasy")
    items = menu.resolve_menu(tenant, "top")
    by = {i["label"]: i for i in items}
    # Speisekarte → дети-категории резолвятся
    child_urls = {c["url"] for c in by["Speisekarte"]["children"]}
    assert "/sortiment/?kategorie=demo-fastfood" in child_urls
    # Aktionen → promo_group резолвится (есть активная акция в группе)
    aktionen_children = {c["label"] for c in by["Aktionen"]["children"]}
    assert "Fastfood-Aktionen" in aktionen_children


def test_pranasy_seeds_records_for_all_archetypes():
    """seed_records: кабинет демо наполнен примерами по всем архетипам."""
    from apps.booking.models import Booking
    from apps.events.models import Ticket
    from apps.jobs.models import Job
    from apps.orders.models import Order

    tenant = TenantFactory(schema_name="public", slug="pr", name="PR", business_type="restaurant")
    demo_kits.apply_kit(tenant, "pranasy")

    assert Order.objects.count() >= 3  # заказы Click & Collect
    jobs = Job.objects.all()
    assert jobs.count() >= 2 and jobs.filter(gross__gt=0).exists()  # сметы с суммами
    assert Booking.objects.filter(status=Booking.STATUS_CONFIRMED).count() >= 1  # брони столика
    assert Ticket.objects.count() >= 1  # билеты на событие


def test_apply_hotel_kit_builds_stays_site():
    """Hotel-кит: движок stays — номера, обложка, меню, брони в кабинете."""
    from apps.stays.models import StayBooking, StayUnit

    tenant = TenantFactory(schema_name="public", slug="ho", name="HO", business_type="hotel")
    assert demo_kits.apply_kit(tenant, "hotel") is True
    cfg = tenant.site_config

    # номера заведены
    assert StayUnit.objects.filter(is_active=True).count() == 4
    assert StayUnit.objects.filter(name="Familienzimmer", max_guests=4).exists()
    # брони в кабинете (подтверждённые)
    assert StayBooking.objects.filter(status=StayBooking.STATUS_CONFIRMED).count() >= 1
    # секции акций/товаров выключены (нет каталога), архетипы — включены
    enabled = {s["key"] for s in cfg["sections"] if s["enabled"]}
    assert "archetypes" in enabled
    assert "promotions" not in enabled and "products" not in enabled
    # пустые архетипы скрыты из «Bereiche», stays — виден
    assert cfg["archetypes"]["catalog"]["hidden"] is True
    assert cfg["archetypes"]["booking"]["hidden"] is True
    assert not cfg["archetypes"].get("stays", {}).get("hidden")
    # меню ведёт на номера
    assert any(i["target"] == "stays" for i in cfg["menus"]["top"]["items"])
    assert tenant.is_module_active("stays")


def test_apply_aktionsmarkt_kit_covers_all_promo_types():
    """Aktionsmarkt: акции всех типов/видов + ваучеры + описание в FAQ."""
    from apps.promotions.models import LoyaltyProgram, Promotion, Voucher

    tenant = TenantFactory(schema_name="public", slug="am", name="AM", business_type="grocery")
    assert demo_kits.apply_kit(tenant, "aktionsmarkt") is True

    promos = Promotion.objects.filter(status="active")
    assert promos.count() >= 12
    # все типы/виды представлены
    assert promos.filter(discount_percent__gt=0).exists()  # %-скидка
    assert promos.filter(price_override__gt=0).exists()  # новый festпрайс
    assert promos.filter(
        promo_type=Promotion.RESERVATION, available_quantity__gt=0
    ).exists()  # лимит
    assert promos.filter(is_surprise=True).exists()  # Überraschungstüte
    assert promos.filter(show_countdown=True).exists()  # countdown
    assert (
        promos.filter(recurrence="daily").exists() and promos.filter(recurrence="weekly").exists()
    )
    # группы акций
    groups = set(promos.values_list("group", flat=True))
    assert {"Wochenangebote", "Dauertiefpreis", "Räumung", "Anti-Food-Waste"} <= groups

    # ваучеры/промокоды (фикс-коды)
    assert Voucher.objects.filter(code="WILLKOMMEN10", discount_percent=10).exists()
    sommer = Voucher.objects.get(code="SOMMER5")
    assert sommer.discount_cents == 500 and sommer.min_order_cents == 3000

    # лояльность + описание типов в FAQ
    assert LoyaltyProgram.objects.filter(is_active=True).exists()
    faq_q = " ".join(p["q"] for p in tenant.site_config["faq"])
    assert "Überraschungstüte" in faq_q and "Countdown" in faq_q and "Gutschein" in faq_q


def test_apply_friseur_kit_booking_services():
    """Friseur: booking-услуги (цена+длительность) + ресурсы + брони в кабинете."""
    from apps.booking.models import Booking, Resource, Service

    tenant = TenantFactory(schema_name="public", slug="fr", name="FR", business_type="other")
    assert demo_kits.apply_kit(tenant, "friseur") is True
    assert Service.objects.filter(is_active=True).count() == 6
    assert Service.objects.filter(name="Färben", price_cents=6900, duration_minutes=90).exists()
    assert Resource.objects.filter(is_active=True).count() == 2  # 2 Stühle
    assert Booking.objects.filter(status=Booking.STATUS_CONFIRMED).exists()  # seed_records
    for m in ("booking", "loyalty", "orders"):
        assert tenant.is_module_active(m)


def test_apply_werkstatt_kit_jobs_booking_catalog():
    """Werkstatt: симбиоз jobs (смета) + booking (услуги) + catalog (Teile)."""
    from apps.booking.models import Service
    from apps.jobs.models import Job

    tenant = TenantFactory(schema_name="public", slug="we", name="WE", business_type="other")
    assert demo_kits.apply_kit(tenant, "werkstatt") is True
    assert Service.objects.filter(name="Ölwechsel", price_cents=4900).exists()
    assert Product.objects.filter(metadata__demo=True).count() == 5  # Teile & Zubehör
    assert Job.objects.count() >= 2  # seed_records → Kostenvoranschläge
    for m in ("booking", "jobs", "orders"):
        assert tenant.is_module_active(m)


def test_apply_retreat_kit_events_program_and_tickets():
    """Retreat: события с Programm/анкетой + проданные билеты + finance-выручка."""
    from apps.events.models import Event, Ticket
    from apps.finance.models import RevenueEntry

    tenant = TenantFactory(schema_name="public", slug="rt", name="RT", business_type="other")
    assert demo_kits.apply_kit(tenant, "retreat") is True

    published = Event.objects.filter(status=Event.STATUS_PUBLISHED)
    assert published.count() == 4
    # богатый dict-спек: Programm, анкета, длительность, безлимит мест
    retreat = Event.objects.get(title="Waldlicht Wochenend-Retreat")
    assert retreat.program and len(retreat.program) == 3
    assert retreat.questions and retreat.ends_at is not None
    assert retreat.capacity == 18 and retreat.price_cents == 29000
    assert Event.objects.get(title="Sommer-Festival der Achtsamkeit").capacity == 0

    # seed_records → проданные билеты (auto_confirm) → finance НДС 19 %
    assert Ticket.objects.filter(status=Ticket.STATUS_CONFIRMED).exists()
    assert RevenueEntry.objects.filter(source="event").exists()

    # композиция архетипов: booking-услуги + catalog (Shop)
    from apps.booking.models import Service

    assert Service.objects.filter(name="Einzel-Yogastunde (1:1)", price_cents=5500).exists()
    assert Product.objects.filter(metadata__demo=True).count() == 4
    for m in ("events", "booking", "orders"):
        assert tenant.is_module_active(m)
