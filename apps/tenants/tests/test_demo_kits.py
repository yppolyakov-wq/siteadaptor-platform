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


# --- PR-C: подкатегории + двуязычность сидера (платформенная инфра) ---


def _p_simple(name, price="3.00", desc="", img="vegan", **kw):
    return demo_kits._p(name, price, desc, img, **kw)


def test_seeds_subcategories_and_bilingual_names(monkeypatch):
    """Магазин→подкатегории (parent/child) + двуязычные имена категорий/товаров +
    i18n-оверлей site_config + EN-лейблы меню — всё через инфраструктуру кита."""
    from django.utils import translation

    from apps.tenants import menu

    kit = demo_kits.DemoKit(
        key="t_subcat",
        label="Subcat Test",
        business_type="retail",
        accent="#16a34a",
        hero_image_kw="shop",
        hero_title="Laden",
        hero_text="Test",
        about_title="Über",
        about_text="x",
        seed_records=True,
        categories=[
            (
                {"de": "Shop", "en": "Shop"},
                "shop",
                [],
                [  # подкатегории
                    (
                        {"de": "Würstchen", "en": "Sausages"},
                        "wuerstchen",
                        [
                            _p_simple(
                                {"de": "Bratwurst", "en": "Grill Sausage"},
                                desc={"de": "lecker", "en": "tasty"},
                            ),
                        ],
                    ),
                    ({"de": "Süßes", "en": "Sweets"}, "suesses", [_p_simple("Keks")]),
                ],
            ),
        ],
        i18n={"en": {"hero_title": "Store", "section_titles": {"products": "Products"}}},
        menus={
            "top": {
                "style": "classic",
                "sticky": True,
                "items": [
                    {
                        "label": "Über uns",
                        "label_i18n": {"en": "About us"},
                        "type": "page",
                        "target": "about",
                    },
                ],
            }
        },
    )
    monkeypatch.setitem(demo_kits.KITS, kit.key, kit)
    tenant = _tenant()
    assert demo_kits.apply_kit(tenant, kit.key) is True

    # Подкатегории: родитель Shop + двое детей с parent FK.
    shop = Category.objects.get(slug="demo-shop")
    children = Category.objects.filter(parent=shop)
    assert children.count() == 2
    wurst = Category.objects.get(slug="demo-wuerstchen")
    assert wurst.parent_id == shop.pk
    # Двуязычное имя категории и товара.
    assert wurst.name == {"de": "Würstchen", "en": "Sausages"}
    bratwurst = Product.objects.get(name__de="Bratwurst")
    assert bratwurst.name["en"] == "Grill Sausage"
    assert bratwurst.description == {"de": "lecker", "en": "tasty"}

    # i18n-оверлей site_config сохранён, localize даёт EN.
    cfg = tenant.site_config
    assert cfg["i18n"]["en"]["hero_title"] == "Store"
    from apps.tenants import siteconfig

    assert siteconfig.localize(cfg, "en")["hero_title"] == "Store"
    assert siteconfig.localize(cfg, "de")["hero_title"] == "Laden"

    # Меню: EN-лейбл узла под локалью en, DE — базовый.
    with translation.override("en"):
        assert menu.resolve_menu(tenant, "top")[0]["label"] == "About us"
    with translation.override("de"):
        assert menu.resolve_menu(tenant, "top")[0]["label"] == "Über uns"


def test_demo_image_is_themed_and_deterministic():
    # ключ без реального фото → детерминированный SVG-URL (фолбэк)
    url = demo_kits.demo_image("unfotografiertes gericht", lock=5)
    assert url == "/medien/demo.svg?kw=unfotografiertes+gericht&w=800&h=600&lock=5"


def test_apply_restaurant_kit_builds_full_site():
    tenant = _tenant()
    assert demo_kits.apply_kit(tenant, "restaurant") is True

    # каталог: несколько категорий + товары с фото
    assert Category.objects.filter(slug__startswith="demo-").count() == 4
    products = Product.objects.filter(metadata__demo=True)
    assert products.count() >= 28
    assert all(
        p.images and p.images[0]["url"].startswith(("/medien/", "/static/demo/photos/"))
        for p in products
    )
    # варианты (Pizza klein/groß) и аллергены проставлены
    assert ProductVariant.objects.count() >= 6
    assert products.filter(allergens__contains=["gluten"]).exists()
    # акции (4 — сетка кратна 2)
    assert Promotion.objects.filter(metadata__demo=True).count() == 4

    # site_config: фото-hero, акцент, галерея, контент-секции
    cfg = tenant.site_config
    assert cfg["hero_image"].startswith(("/medien/", "/static/demo/photos/"))
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
    from apps.loyalty.models import LoyaltyProgram

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
    """Демо «Pranasy» (двуязычное): Restaurant и Shop — отдельные сущности (пункты
    меню + категории), секция «Bereiche», слайдер, обложки разделов."""
    tenant = TenantFactory(schema_name="public", slug="p", name="P", business_type="restaurant")
    assert demo_kits.apply_kit(tenant, "pranasy") is True
    cfg = tenant.site_config

    # Restaurant и Shop — отдельные верхнеуровневые категории; Shop с подкатегориями.
    assert Category.objects.filter(slug="demo-restaurant", parent__isnull=True).exists()
    shop = Category.objects.get(slug="demo-shop")
    assert shop.parent_id is None
    assert Category.objects.filter(parent=shop).count() == 3
    # S2: секция «Unsere Bereiche» включена
    assert "archetypes" in {s["key"] for s in cfg["sections"] if s["enabled"]}
    # S7: меню — Restaurant и Shop отдельными пунктами + группа Treue & Aktionen
    top_labels = [i["label"] for i in cfg["menus"]["top"]["items"]]
    assert "Restaurant" in top_labels and "Shop" in top_labels
    assert "Catering" in top_labels and "Retreats" in top_labels
    assert cfg["menus"]["bottom"]["enabled"] is True
    # S3: обложка раздела catalog (интро)
    assert cfg["archetypes"]["catalog"]["intro"]
    # M20U-2: слайдер баннеров — 3 слайда; первый ведёт в Restaurant-меню.
    assert len(cfg["heroes"]) == 3
    assert all(h["image"] and h["title"] and h["button_url"] for h in cfg["heroes"])
    assert cfg["heroes"][0]["button_url"] == "/sortiment/?kategorie=demo-restaurant"
    # M20U-7: кастомные заголовки секций
    assert cfg["section_titles"]["products"] == "Speisekarte & Shop"
    assert cfg["section_titles"]["events"] == "Retreats bei Pranasy"
    # M20U-7 (per-page): события — сеткой cols2
    assert cfg["events_index_layout"]["preset"] == "cols2"
    # i18n: оверлей переводов витрины присутствует
    assert cfg["i18n"]["en"]["hero_title"]
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
    # Restaurant и Shop резолвятся на свои категории.
    assert by["Restaurant"]["url"] == "/sortiment/?kategorie=demo-restaurant"
    assert by["Shop"]["url"] == "/sortiment/?kategorie=demo-shop"
    # Группа «Treue & Aktionen» с детьми (Treue → loyalty минимум резолвится).
    treue_group = by["Treue & Aktionen"]
    child_labels = {c["label"] for c in treue_group["children"]}
    assert "Treue" in child_labels


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

    # номера заведены — с описанием и фото (разные категории)
    assert StayUnit.objects.filter(is_active=True).count() == 4
    fam = StayUnit.objects.get(name="Familienzimmer")
    assert fam.max_guests == 4 and fam.min_nights == 2 and fam.description
    assert len(fam.images) == 3 and fam.images[0]["is_primary"] is True
    assert fam.image_url.startswith(("/medien/", "/static/demo/photos/"))
    # у каждого номера есть описание и хотя бы одно фото
    for u in StayUnit.objects.all():
        assert u.description and u.images
    # UA4-4b: демо-отзывы о номерах засеяны (generic reviews.Review, entity_kind='stay')
    from apps.reviews.models import Review

    assert Review.objects.filter(entity_kind="stay", is_published=True).count() == 3
    # G8/#6 отзывы клиентов (SHARED) + рейтинг + секция «reviews»
    from apps.aggregator.models import BusinessRating, BusinessReview
    from apps.core.templatetags.seo import storefront_reviews

    assert BusinessReview.objects.filter(tenant_schema="public").count() == 3
    assert BusinessRating.objects.get(tenant_schema="public").review_count == 3
    assert {s["key"] for s in tenant.site_config["sections"] if s["enabled"]} >= {"reviews"}
    revs = storefront_reviews(6)  # тег читает SHARED по connection.schema_name (public)
    assert len(revs) == 3 and revs[0]["stars"].count("★") >= 4

    # #7 универсальные Extras к брони (Frühstück/Parkplatz …)
    from apps.core.models import Extra

    assert Extra.objects.filter(scope="stays").count() == 4
    assert Extra.objects.get(label="Frühstücksbuffet").per_night is True

    # E4 депозит + A5a сезонный тариф на Doppelzimmer
    from apps.stays.models import SeasonRate

    doppel = StayUnit.objects.get(name="Doppelzimmer Seeblick")
    assert doppel.deposit_cents == 3000
    assert SeasonRate.objects.filter(unit=doppel, price_cents=11900).exists()
    # H3 богатая карточка: площадь/кровать/удобства
    assert doppel.area_sqm == 24 and doppel.bed_type
    assert "wifi" in doppel.amenities and "balcony" in doppel.amenities
    # H1 тарифы (4), H9 Kurtaxe, H6 Hausordnung, H4a промокод
    from apps.loyalty.models import Voucher
    from apps.stays.models import RatePlan, StaySettings

    assert RatePlan.objects.filter(is_active=True).count() == 4
    st = StaySettings.load()
    assert st.kurtaxe_cents == 250 and st.house_rules
    promo = Voucher.objects.get(code="SOMMER10")
    assert promo.discount_percent == 10
    # «по 2 примера» на каждый тип скидки/настройки:
    # G4: по 2 правила авто-скидки каждого типа (los/early_bird/last_minute)
    rules = st.clean_auto_rules()
    from collections import Counter

    kinds = Counter(r["kind"] for r in rules)
    assert kinds["los"] == 2 and kinds["early_bird"] == 2 and kinds["last_minute"] == 2
    # G7: 2 тарифа с предоплатой (частичная 30 % + полная 100 %)
    prepay_rates = list(RatePlan.objects.filter(prepayment_percent__gt=0))
    assert len(prepay_rates) == 2
    assert {r.prepayment_percent for r in prepay_rates} == {30, 100}
    # G4a/H4a: 2 промокода (процентный SOMMER10 + фикс-сумма WILLKOMMEN20)
    assert Voucher.objects.get(code="WILLKOMMEN20").discount_cents == 2000
    # H2 секция поиска на главной включена
    assert "stay_search" in {s["key"] for s in cfg["sections"] if s["enabled"]}
    # брони в кабинете (подтверждённые) с H5 adults и H9 Kurtaxe в итоге
    confirmed = StayBooking.objects.filter(status=StayBooking.STATUS_CONFIRMED)
    assert confirmed.count() >= 1
    b = confirmed.first()
    assert b.adults >= 1 and b.kurtaxe_cents > 0
    # секции акций/товаров выключены (нет каталога); карточки номеров на главной
    # включены, а тизер-секция «Bereiche» для отеля выключена (был бы дубль).
    enabled = {s["key"] for s in cfg["sections"] if s["enabled"]}
    assert "stay_rooms" in enabled
    assert "archetypes" not in enabled
    assert "promotions" not in enabled and "products" not in enabled
    # пустые архетипы по-прежнему помечены скрытыми в конфиге (на случай включения)
    assert cfg["archetypes"]["catalog"]["hidden"] is True
    assert cfg["archetypes"]["booking"]["hidden"] is True
    # меню ведёт на номера
    assert any(i["target"] == "stays" for i in cfg["menus"]["top"]["items"])
    assert tenant.is_module_active("stays")

    # Разнообразие демо-броней: статусы (pending/confirmed/fulfilled/cancelled)
    assert StayBooking.objects.filter(status=StayBooking.STATUS_PENDING).exists()
    assert StayBooking.objects.filter(status=StayBooking.STATUS_FULFILLED).exists()
    assert StayBooking.objects.filter(status=StayBooking.STATUS_CANCELLED).exists()
    # G4a: бронь с применённым промокодом (скидка)
    assert StayBooking.objects.filter(discount_cents__gt=0).exists()
    # G5: мультикомнатная бронь среди демо-броней (rooms ≥ 2)
    assert StayBooking.objects.filter(rooms__gte=2).exists()
    # A5/C4: Wartungs-Block (Sperrung) для визуального календаря наличия
    from apps.stays.models import UnitBlock

    assert UnitBlock.objects.exists()
    # G6: несколько цифровых Meldescheine (Online-Checkin)
    from apps.stays.models import GuestRegistration

    assert GuestRegistration.objects.filter(signed_at__isnull=False).count() >= 3
    # G3: согласия на рассылку + примеры кампаний (≥2 sent + draft)
    from apps.promotions.models import Customer, NewsletterCampaign

    assert Customer.objects.filter(marketing_opt_in=True).count() >= 3
    assert NewsletterCampaign.objects.filter(status="sent").count() >= 2
    assert NewsletterCampaign.objects.filter(status="draft").exists()
    # G11: каналы продаж + импортированная из канала бронь
    from apps.stays.models import Channel

    assert Channel.objects.count() >= 2
    assert StayBooking.objects.filter(source_channel="booking").exclude(external_ref="").exists()


def test_apply_aktionsmarkt_kit_covers_all_promo_types():
    """Aktionsmarkt: акции всех типов/видов + ваучеры + описание в FAQ."""
    from apps.loyalty.models import LoyaltyProgram, Voucher
    from apps.promotions.models import Promotion

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
    # A3: богатая карточка — у услуг есть описание и фото
    faerben = Service.objects.get(name="Färben")
    assert faerben.description and faerben.image_url
    assert Resource.objects.filter(is_active=True).count() == 2  # 2 Stühle
    # A3: профили мастеров — должность, био, фото у staff-ресурсов
    lea = Resource.objects.get(name="Lea")
    assert lea.title and lea.bio and lea.photo_url
    assert Booking.objects.filter(status=Booking.STATUS_CONFIRMED).exists()  # seed_records
    # A3/G9b Mehrfachkarte: тарифы + одна выданная карта
    from apps.booking.models import Pass, PassPlan

    assert PassPlan.objects.filter(is_active=True).count() == 2
    waschen = Service.objects.get(name="Waschen & Föhnen")
    assert PassPlan.objects.filter(credits=10, service=waschen).exists()  # привязка к услуге
    assert Pass.objects.filter(credits_total=10).exists()  # выдана клиенту
    for m in ("booking", "loyalty", "orders", "customer_account"):
        assert tenant.is_module_active(m)
    # UA4-4b: демо-отзывы об услугах засеяны (generic reviews.Review, entity_kind='service')
    from apps.reviews.models import Review

    assert Review.objects.filter(entity_kind="service", is_published=True).count() == 3


def test_apply_werkstatt_kit_jobs_booking_catalog():
    """Werkstatt: симбиоз jobs (смета) + booking (услуги) + catalog (Teile)."""
    from apps.booking.models import Service
    from apps.jobs.models import Job

    tenant = TenantFactory(schema_name="public", slug="we", name="WE", business_type="other")
    assert demo_kits.apply_kit(tenant, "werkstatt") is True
    assert Service.objects.filter(name="Ölwechsel", price_cents=4900).exists()
    assert Product.objects.filter(metadata__demo=True).count() == 5  # Teile & Zubehör
    assert Job.objects.count() >= 2  # seed_records → Kostenvoranschläge
    for m in ("booking", "jobs", "orders", "customer_account"):
        assert tenant.is_module_active(m)
    # A9: режим Kfz-Werkstatt — флаг + структурные данные авто (Kennzeichen/HSN/TSN)
    assert tenant.site_config["jobs_vehicle"] is True
    assert Job.objects.filter(vehicle_plate="DO-MV 1234", vehicle_hsn="0603").exists()


def test_werkstatt_kit_rich_service_card_and_reviews(settings):
    """UA4-3/UA4-4b демо-A9: богатая карточка услуги (attributes/FAQ/primary_action)
    и service-отзывы засеяны, секции видны на витринной детали услуги."""
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.booking import public_views
    from apps.booking.models import Service
    from apps.reviews.models import Review

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(schema_name="public", slug="we2", name="WE2", business_type="other")
    assert demo_kits.apply_kit(tenant, "werkstatt") is True

    svc = Service.objects.get(name="Inspektion")
    assert svc.attributes and isinstance(svc.attributes, list)
    assert svc.faq and svc.faq[0]["q"] and svc.faq[0]["a"]
    assert svc.primary_action == "request"
    # 3 опубликованных service-отзыва, ≥1 — именно об Inspektion
    assert Review.objects.filter(entity_kind="service", is_published=True).count() == 3
    assert Review.objects.filter(entity_kind="service", entity_id=str(svc.pk)).exists()

    # витрина: деталь услуги рендерит секции attributes/FAQ/отзывы
    request = RequestFactory().get(f"/leistung/{svc.pk}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    body = public_views.service_detail(request, pk=svc.pk).content.decode()
    assert "Fehlerspeicher" in body  # attributes
    assert "Herstellergarantie" in body  # FAQ
    assert "läuft wie neu" in body  # отзыв


def test_apply_handwerker_kit_jobs_services_no_shop():
    """A7 Handwerker: ядро jobs (Angebot/Festpreis) + booking-Leistungen, без shop."""
    from apps.booking.models import Service
    from apps.jobs.models import Job

    tenant = TenantFactory(schema_name="public", slug="hw", name="HW", business_type="other")
    assert demo_kits.apply_kit(tenant, "handwerker") is True

    # booking: Leistungen с Festpreisen + бесплатная Vor-Ort-Beratung (0 €)
    assert Service.objects.filter(name="Vor-Ort-Beratung (kostenlos)", price_cents=0).exists()
    assert Service.objects.filter(name="Sanitär: Armatur tauschen", price_cents=12000).exists()
    # jobs: seed_records создаёт Angebote (с суммами, со строками)
    jobs = Job.objects.all()
    assert jobs.count() >= 2 and jobs.filter(gross__gt=0).exists()
    # нет shop → нет демо-товаров; модули jobs/booking активны, без orders
    assert Product.objects.filter(metadata__demo=True).count() == 0
    for m in ("jobs", "booking", "customer_account"):
        assert tenant.is_module_active(m)

    # витрина: услуги + отзывы + Trust/USP + контент-секции, без products/promotions
    cfg = tenant.site_config
    assert tenant.primary_color == "#ea580c"
    enabled = {s["key"] for s in cfg["sections"] if s["enabled"]}
    assert {"hero", "services", "usp_bar", "reviews", "cta", "faq", "before_after"} <= enabled
    assert "products" not in enabled and "promotions" not in enabled
    assert cfg["cta"]["button_url"] == "/anfrage/"  # primary CTA = Angebot anfordern
    # A7: кейсы «Vorher / Nachher» — слайдер с before/after-фото и текстом
    ba = cfg["before_after"]
    assert len(ba) == 2
    assert ba[0]["before"] and ba[0]["after"] and ba[0]["text"]


def test_apply_retreat_kit_events_program_and_tickets():
    """Retreat: события с Programm/анкетой + проданные билеты + finance-выручка."""
    from apps.events.models import Event, Ticket
    from apps.finance.models import RevenueEntry

    tenant = TenantFactory(schema_name="public", slug="rt", name="RT", business_type="other")
    assert demo_kits.apply_kit(tenant, "retreat") is True

    published = Event.objects.filter(status=Event.STATUS_PUBLISHED)
    assert published.count() == 7  # 4 базовых + Frauen-Retreat + Ayurveda + RT2 Online-Event
    # RT4: блог — 2 опубликованные записи
    from apps.events.models import BlogPost

    assert BlogPost.objects.filter(is_published=True).count() == 2
    # RT2: онлайн/Zoom-событие с ссылкой доступа
    online = Event.objects.get(is_online=True)
    assert online.online_url.startswith("https://") and not online.city
    # богатый dict-спек: Programm, анкета, длительность, безлимит мест
    retreat = Event.objects.get(title="Waldlicht Wochenend-Retreat")
    assert retreat.program and len(retreat.program) == 3
    assert retreat.questions and retreat.ends_at is not None
    assert retreat.capacity == 18 and retreat.price_cents == 29000
    # A6 ценовые тиры билета
    assert retreat.has_tiers and len(retreat.tier_list) == 3
    assert retreat.from_price_cents == 23000  # Mehrbettzimmer — минимальный тир
    assert Event.objects.get(title="Sommer-Festival der Achtsamkeit").capacity == 0
    # UA4-4b: демо-отзывы о событиях засеяны (generic reviews.Review, entity_kind='event')
    from apps.reviews.models import Review

    assert Review.objects.filter(entity_kind="event", is_published=True).count() == 3
    # R3 преподаватели, R4 депозит, R5 проживание, R6 гео — на главном ретрите
    assert retreat.teachers.count() == 2
    assert retreat.deposit_percent == 30
    assert retreat.offers_accommodation and retreat.accommodation_units.count() == 3
    assert retreat.latitude is not None and retreat.longitude is not None
    # R2 таксономия фильтров + новые направления (ayurveda)
    cats = set(published.values_list("category", flat=True))
    assert {"yoga", "ayurveda", "klang", "achtsamkeit"} <= cats

    # «ретрит-лендинг»: развёрнутые блоки + фото места на главном событии
    assert retreat.images and retreat.image_url.startswith(("/medien/", "/static/demo/photos/"))
    L = retreat.landing
    assert L["for_whom"] and L["includes"] and L["faq"] and L["price_includes"]
    assert L["hosts"] and L["hosts"][0]["photo"].startswith(("/medien/", "/static/demo/photos/"))

    # seed_records → проданные билеты (auto_confirm) → finance НДС 19 %
    assert Ticket.objects.filter(status=Ticket.STATUS_CONFIRMED).exists()
    assert RevenueEntry.objects.filter(source="event").exists()
    # R8: флагман требует waiver, засеянные билеты подписаны
    from apps.events.models import TicketWaiver

    assert retreat.waiver_required
    assert TicketWaiver.objects.filter(ticket__event=retreat).exists()

    # композиция архетипов: booking-услуги + catalog (Shop)
    from apps.booking.models import Service

    assert Service.objects.filter(name="Einzel-Yogastunde (1:1)", price_cents=5500).exists()
    assert Product.objects.filter(metadata__demo=True).count() == 4
    for m in ("events", "booking", "orders", "customer_account", "stays", "jobs"):
        assert tenant.is_module_active(m)


def test_apply_shop_kit_retail_features():
    """Retail-кит: варианты (R1), Grundpreis (R2), остаток (R3), GTIN (A1),
    доставка с PLZ-зонами (A2) + заказ с доставкой в кабинете."""
    from apps.catalog.models import Product, ProductVariant
    from apps.orders.models import Order

    tenant = TenantFactory(schema_name="public", slug="sh", name="SH", business_type="retail")
    assert demo_kits.apply_kit(tenant, "shop") is True

    # R2 Grundpreis: весовой товар (€/kg)
    honig = Product.objects.get(name__de="Bio-Honig")
    assert honig.unit == "kg" and honig.grundpreis is not None
    assert honig.gtin == "4012345000057"  # A1 EAN
    # R1 варианты с собственным остатком/EAN (R3/A1)
    vars_ = ProductVariant.objects.filter(product=honig).order_by("sort_order")
    assert vars_.count() == 2
    assert vars_[0].stock_quantity == 24 and vars_[1].stock_quantity == 8
    assert vars_[1].gtin == "4012345000064"
    # R3 остаток на простом товаре
    assert Product.objects.get(name__de="Eier vom Hof, 10er").stock_quantity == 15

    # A2 доставка + PLZ-зоны на тенанте
    assert tenant.delivery_enabled and len(tenant.delivery_zones) == 3
    # seed_records → заказ с доставкой в кабинете
    assert Order.objects.filter(fulfillment=Order.FULFILLMENT_DELIVERY).exists()
    assert tenant.is_module_active("orders")
    # A1/A2: отзывы о товаре засеяны на первых товарах каталога (опубликованы)
    from apps.reviews.models import Review

    assert Review.objects.filter(entity_kind="product", is_published=True).count() == 3


def test_seed_command_unknown_kit_warns_clearly():
    """Неизвестный кит → заметное предупреждение со списком доступных + подсказкой
    про пересборку контейнера (частая причина в Docker), без обращения к БД."""
    from io import StringIO

    from django.core.management import call_command

    err = StringIO()
    call_command("seed_demo_tenants", kit="does-not-exist", stderr=err)
    out = err.getvalue()
    assert "Unbekannter Kit" in out and "does-not-exist" in out
    assert "Verfügbare Kits" in out and "restaurant" in out
    assert "deploy.sh single" in out  # подсказка про старый образ


def test_hotel_portal_seed_creates_portal_and_domain_to_public():
    """H8a/багфикс: seed hotel-портала создаёт И AggregatorPortal, И Domain(host→public).
    Без Domain django-tenants отдаёт 404 на hotels.<base> (репро прежнего «Not Found»)."""
    from django_tenants.utils import get_public_schema_name

    from apps.aggregator.models import AggregatorPortal
    from apps.tenants.management.commands.seed_demo_tenants import Command
    from apps.tenants.models import Domain, Tenant

    public = Tenant.objects.filter(schema_name=get_public_schema_name()).first()
    if public is None:
        public = TenantFactory(schema_name=get_public_schema_name(), slug="public", name="Public")

    Command()._ensure_hotel_portal()

    host = "hotels.siteadaptor.de"  # TENANT_DOMAIN_BASE в test = siteadaptor.de
    assert AggregatorPortal.objects.filter(host=host, business_type="hotel").exists()
    assert Domain.objects.filter(domain=host, tenant=public).exists()  # ← фикс роутинга

    Command()._ensure_hotel_portal()  # идемпотентно: повтор не плодит дублей
    assert Domain.objects.filter(domain=host).count() == 1
    assert AggregatorPortal.objects.filter(host=host).count() == 1


def test_kit_seeds_collections(monkeypatch):
    """UB3-2: спека kit.collections создаёт подборки и связывает услуги по индексам
    (порядок создания сидером) — чипы-фасет видны в демо сразу."""
    from apps.booking.models import Service
    from apps.collections.models import Collection

    kit = demo_kits.DemoKit(
        key="t_cols",
        label="Collections Test",
        business_type="other",
        accent="#9333ea",
        hero_image_kw="hair",
        hero_title="Salon",
        hero_text="Test",
        enable_modules=["booking"],
        services=[("Schnitt", 30, "25"), ("Färben", 90, "69"), ("Bart", 15, "12")],
        collections=[
            ("Damen", {"services": [0, 1]}),
            ("Herren", {"services": [2]}),
        ],
    )
    monkeypatch.setitem(demo_kits.KITS, kit.key, kit)
    tenant = _tenant()
    assert demo_kits.apply_kit(tenant, kit.key) is True

    damen = Collection.objects.get(slug="damen")
    herren = Collection.objects.get(slug="herren")
    assert damen.sort_order == 0 and herren.sort_order == 1
    assert set(damen.services.values_list("name", flat=True)) == {"Schnitt", "Färben"}
    assert list(herren.services.values_list("name", flat=True)) == ["Bart"]
    assert Service.objects.count() == 3


# --- L3d: мультиязычный демо-засев (per-locale оверлеи) ---


def test_friseur_kit_seeds_service_i18n_overlays():
    from apps.booking.models import Service

    demo_kits.apply_kit(_tenant(), "friseur")
    svc = Service.objects.get(name="Haarschnitt Damen")
    assert svc.name_i18n == {"en": "Women's haircut"}
    assert svc.description_i18n.get("en", "").startswith("Wash, cut")
    # услуги без EN-дикта остаются без оверлея (база = плоское de)
    assert Service.objects.filter(name_i18n={}).exists()


def test_hotel_kit_seeds_stayunit_i18n_overlays():
    from apps.stays.models import StayUnit

    tenant = TenantFactory(schema_name="public", slug="h", name="H", business_type="hotel")
    demo_kits.apply_kit(tenant, "hotel")
    unit = StayUnit.objects.get(name="Doppelzimmer Seeblick")
    assert unit.name_i18n == {"en": "Double room lake view"}


def test_restaurant_kit_seeds_combos_with_i18n():
    from apps.catalog.models import Combo

    demo_kits.apply_kit(_tenant(), "restaurant")
    combo = Combo.objects.get(name="Mittags-Kombo")
    assert combo.name_i18n == {"en": "Lunch combo"}
    assert combo.description_i18n.get("en", "").startswith("Starter")
    group = combo.groups.first()
    assert group is not None and group.options.count() == 2  # Bruschetta + Caprese
    assert Combo.objects.filter(name="Familien-Paket").exists()


def test_apply_bakery_kit_dedicated_bakery():
    """Волна 1 (демо-под-тип): dedicated Bäckerei-кит — хлебный каталог с LMIV-
    аллергенами и Grundpreis, killer-акции (Feierabendtüte/Wochenangebot/abends −50 %),
    Stempelkarte, отзывы о товаре. Metzgerei-контента нет."""
    from apps.catalog.models import Product
    from apps.loyalty.models import LoyaltyProgram
    from apps.promotions.models import Promotion
    from apps.reviews.models import Review

    tenant = TenantFactory(schema_name="public", slug="bk", name="BK", business_type="bakery")
    assert demo_kits.apply_kit(tenant, "bakery") is True

    # Хлебный каталог: аллергены (LMIV) и весовой Grundpreis на хлебе
    brot = Product.objects.get(name__de="Bauernbrot 1 kg")
    assert "gluten" in brot.allergens and brot.unit == "kg" and brot.grundpreis is not None
    assert Product.objects.filter(name__de="Feierabendtüte").exists()
    # killer-акции пекарни: surprise (Anti-Food-Waste) + weekly + daily
    promos = Promotion.objects.filter(status="active")
    assert promos.filter(is_surprise=True).exists()
    assert promos.filter(recurrence="weekly").exists()
    assert promos.filter(recurrence="daily").exists()
    groups = set(promos.values_list("group", flat=True))
    assert {"Wochenangebote", "Anti-Food-Waste"} <= groups
    # лояльность + отзывы о товаре + модуль заказов (Vorbestellung/C&C)
    assert LoyaltyProgram.objects.filter(is_active=True).exists()
    assert Review.objects.filter(entity_kind="product", is_published=True).count() == 3
    assert tenant.is_module_active("orders")


def test_bakery_kit_seeds_lots_with_mhd():
    """Склад-2 E1.5: еда-кит включает учёт партий (lots_enabled) и сеет демо-Chargen с
    MHD; Σ остатков партий сходится со счётчиком товара (реконсиляция Вариант A)."""
    from apps.catalog.models import Product
    from apps.inventory.models import Lot
    from apps.inventory.services import lot_balance

    tenant = TenantFactory(schema_name="public", slug="bk2", name="BK2", business_type="bakery")
    demo_kits.apply_kit(tenant, "bakery")
    assert tenant.site_config.get("lots_enabled") is True  # тумблер учёта партий вкл
    assert Lot.objects.filter(mhd__isnull=False).exists()  # партии с MHD засеяны
    # реконсиляция: у товара с партиями Σlot == счётчик (без вариантов)
    prod = Product.objects.filter(lots__isnull=False, stock_quantity__gt=0).distinct().first()
    assert prod is not None
    assert lot_balance(prod) == prod.stock_quantity


def test_apply_butcher_kit_dedicated_metzgerei():
    """Волна 1: dedicated Metzgerei-кит — весовой Grundpreis €/kg, Grillpaket-
    Vorbestellung (reservation), Partyservice через jobs (Anfrage со сметой)."""
    from apps.catalog.models import Product
    from apps.jobs.models import Job
    from apps.promotions.models import Promotion

    tenant = TenantFactory(schema_name="public", slug="mz", name="MZ", business_type="butcher")
    assert demo_kits.apply_kit(tenant, "butcher") is True

    # Весовой товар: Grundpreis €/kg (PAngV — ключевой для мясной)
    hack = Product.objects.get(name__de="Rinderhackfleisch 1 kg")
    assert hack.unit == "kg" and hack.grundpreis is not None
    # Grillpaket-Vorbestellung: reservation-акция с лимитом в группе «Vorbestellung»
    grill = Promotion.objects.get(group="Vorbestellung")
    assert grill.promo_type == Promotion.RESERVATION and grill.available_quantity == 20
    # Partyservice: jobs-модуль активен, сметы-примеры (Buffet) засеяны
    assert tenant.is_module_active("jobs")
    assert Job.objects.filter(title__icontains="Partyservice").exists()


def test_apply_cafe_kit_dedicated_cafe():
    """Волна 2: dedicated Café-кит — компактная кофейная карта (НЕ ужин-ресторан),
    бронь столика (booking-ресурс), Kaffeepass 7 штампов, Mittagstisch/Happy-Hour."""
    from apps.booking.models import Resource
    from apps.catalog.models import Product
    from apps.loyalty.models import LoyaltyProgram
    from apps.promotions.models import Promotion

    tenant = TenantFactory(schema_name="public", slug="cf", name="CF", business_type="cafe")
    assert demo_kits.apply_kit(tenant, "cafe") is True

    # кофейная карта с вариантами размеров и веган-тегами
    capp = Product.objects.get(name__de="Cappuccino")
    assert capp.variants.count() == 2 and "milch" in capp.allergens
    assert Product.objects.filter(diets__contains=["vegan"]).count() >= 3
    assert Product.objects.count() <= 20  # компактно, не ресторан на 33 позиции
    # бронь столика + Kaffeepass (7 штампов)
    assert tenant.is_module_active("booking")
    assert Resource.objects.filter(type="table").exists()
    assert LoyaltyProgram.objects.filter(stamps_required=7).exists()
    # Mittagstisch (weekly reservation) + Happy Hour (daily)
    promos = Promotion.objects.filter(status="active")
    assert promos.filter(promo_type=Promotion.RESERVATION, recurrence="weekly").exists()
    assert promos.filter(recurrence="daily").exists()


def test_apply_clothing_kit_dedicated_boutique():
    """Волна 2: dedicated Mode-кит — размерные варианты с per-size остатком
    (0 → Warteliste-стори), Versand deutschlandweit (без PLZ-зон), Sale-группа."""
    from apps.catalog.models import Product, ProductVariant
    from apps.promotions.models import Promotion

    tenant = TenantFactory(schema_name="public", slug="nw", name="NW", business_type="clothing")
    assert demo_kits.apply_kit(tenant, "clothing") is True

    # размерные варианты: у кардигана размер M ausverkauft (склад 0) → Warteliste
    cardigan = Product.objects.get(name__de="Strickcardigan Wolke")
    sizes = {v.label: v.stock_quantity for v in ProductVariant.objects.filter(product=cardigan)}
    assert sizes == {"S": 4, "M": 0, "L": 2}
    # футболка: 4 размера S–XL
    shirt = Product.objects.get(name__de="Basic T-Shirt Bio-Baumwolle")
    assert ProductVariant.objects.filter(product=shirt).count() == 4
    # Versand: доставка включена БЕЗ PLZ-зон (deutschlandweit, flat 4,90/frei ab 80)
    assert tenant.delivery_enabled and tenant.delivery_zones == []
    assert tenant.delivery_free_cents == 8000
    # Sale-акции: процент + festpreis (durchgestrichen)
    promos = Promotion.objects.filter(status="active", group="Sale")
    assert promos.filter(discount_percent=30).exists()
    assert promos.filter(price_override__gt=0).exists()


def test_apply_tours_kit_dedicated_tour_operator():
    """Волна 3: dedicated Tour-Operator-кит — регулярные туры (booking-слоты с
    party-size), датированные события с тирами/депозитом, гиды-Teacher, без каталога."""
    from apps.booking.models import Resource, Service
    from apps.catalog.models import Product
    from apps.events.models import Event, Teacher

    tenant = TenantFactory(
        schema_name="public", slug="tg", name="TG", business_type="tour_operator"
    )
    assert demo_kits.apply_kit(tenant, "tours") is True

    # регулярные туры = booking-услуги; слот-ресурс суммирует размер группы
    assert Service.objects.count() == 3
    res = Resource.objects.get()
    assert res.counts_party_size and res.capacity == 16
    # датированные: 3 события, у Weinprobe тиры, у Ausflug депозит 20 %
    assert Event.objects.count() == 3
    wein = Event.objects.get(title="Weinprobe im Gewölbekeller")
    assert wein.has_tiers and len(wein.tier_list) == 2
    ausflug = Event.objects.get(title="Tagesausflug: Moseltal & Burg Eltz")
    assert ausflug.deposit_percent == 20
    # гиды как Teacher-сущности, слинкованы с событиями
    assert Teacher.objects.count() == 2
    assert wein.teachers.count() == 2
    # без каталога (тур — не товар)
    assert Product.objects.count() == 0


def test_kit_custom_statuses_applied_and_resolve():
    """FB-3 Вариант B: демо-киты заводят кастом-статусы в site_config; резолвятся end-to-end."""
    from apps.core import status_registry

    tenant = TenantFactory(schema_name="public", slug="ws", name="WS", business_type="werkstatt")
    assert demo_kits.apply_kit(tenant, "werkstatt") is True
    tenant.refresh_from_db()
    cd = status_registry.custom_descriptors(tenant, "booking")
    assert "teile_bestellt" in cd and cd["teile_bestellt"].blocks_capacity
    assert cd["teile_bestellt"].label == "Teile bestellt"
    edges = status_registry.custom_edges(tenant, "booking")
    assert ("confirmed", "teile_bestellt") in edges and ("teile_bestellt", "fulfilled") in edges
