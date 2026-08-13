"""Шаблоны витрины (ранний срез M20): пресеты site_config + применение + галерея."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware

from apps.core.views import home_builder_view
from apps.promotions import public_views
from apps.tenants import siteconfig, sitetemplates
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _enabled(tenant):
    cfg = siteconfig.normalize(tenant.site_config)
    return [s["key"] for s in cfg["sections"] if s["enabled"]]


def _request(rf, method, user, tenant, data=None):
    request = getattr(rf, method)("/dashboard/site/home/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant
    return request


def test_templates_for_puts_recommended_first():
    order = [t["key"] for t in sitetemplates.templates_for("cafe")]
    assert order[0] == "gastro"  # cafe → рекомендован «gastro»
    # все шаблоны присутствуют ровно один раз
    assert sorted(order) == sorted(t["key"] for t in sitetemplates.TEMPLATES)


@pytest.mark.parametrize(
    ("business_type", "template_key", "primary_section"),
    [
        ("friseur", "termine", "services"),
        ("werkstatt", "termine", "services"),
        ("handwerker", "handwerk", "before_after"),
        ("events", "veranstaltung", "events"),
        # E1/E4 «задача-первым»: у отеля primary-задача на дефолт-главной. Поиск
        # дат переехал В hero (hero_widget, отдельный замок ниже), карточки
        # номеров — секцией. Раньше hotel не проверялся и дыра проскочила.
        ("hotel", "gastgeber", "stay_rooms"),
        # E2: tour_operator дефолтит на events-first veranstaltung (не about-first
        # dienstleister) — туры/события с датами на первом экране.
        ("tour_operator", "veranstaltung", "events"),
    ],
)
def test_s6_archetype_template_recommended_and_keeps_primary(
    business_type, template_key, primary_section
):
    # S6: у каждого нового архетипа есть рекомендованный шаблон (первым в галерее),
    # и он ВКЛЮЧАЕТ секцию-главного-товара (не прячет её, как generic-шаблоны).
    order = [t["key"] for t in sitetemplates.templates_for(business_type)]
    assert order[0] == template_key
    tpl = sitetemplates.get_template(template_key)
    assert primary_section in tpl["sections"]


def test_gastgeber_hero_carries_stay_search_widget():
    # E4 «задача-первым»: у отеля поиск дат ВНУТРИ hero (первый экран). Шаблон
    # несёт site_defaults.hero_widget="stays"; apply_template доносит его до
    # конфига (normalize оставляет валидное значение).
    from apps.tenants import siteconfig

    tpl = sitetemplates.get_template("gastgeber")
    assert tpl["site_defaults"]["hero_widget"] == "stays"
    tenant = TenantFactory(schema_name="t_hw", business_type="hotel")
    assert sitetemplates.apply_template(tenant, "gastgeber") is True
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["site_defaults"]["hero_widget"] == "stays"
    # E4: смена Look'а не сбрасывает интерактивный hero (hero_widget сохраняется,
    # т.к. это выбор раскладки, а не визуальная тема семейства).
    assert sitetemplates.apply_look(tenant, "nacht") is True
    tenant.refresh_from_db()
    assert tenant.site_config["site_defaults"]["hero_widget"] == "stays"


def test_termine_hero_carries_services_widget():
    # R2 «первый экран»: у friseur/werkstatt топ-услуги + «Termin buchen» ВНУТРИ
    # hero. Шаблон termine несёт site_defaults.hero_widget="services"; apply_template
    # доносит; смена Look'а сохраняет (как у отеля).
    from apps.tenants import siteconfig

    tpl = sitetemplates.get_template("termine")
    assert tpl["site_defaults"]["hero_widget"] == "services"
    tenant = TenantFactory(schema_name="t_sw", business_type="friseur")
    assert sitetemplates.apply_template(tenant, "termine") is True
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["site_defaults"]["hero_widget"] == "services"
    assert sitetemplates.apply_look(tenant, "warm") is True
    tenant.refresh_from_db()
    assert tenant.site_config["site_defaults"]["hero_widget"] == "services"


def test_hero_widget_partial_renders_services_gated_by_module(settings):
    # R2: партиал hero-виджета рендерит топ-услуги при hero_widget="services" +
    # непустом services_preview; при пустом — ничего (без регрессии).
    settings.ROOT_URLCONF = "config.urls_tenant"
    import uuid
    from types import SimpleNamespace

    from django.template.loader import render_to_string

    svc = SimpleNamespace(pk=uuid.uuid4(), name_localized=lambda *a: "Haarschnitt")
    on = render_to_string(
        "storefront/sections/_hero_widget.html",
        {"hero_widget": "services", "services_preview": [svc]},
    )
    assert "Haarschnitt" in on
    off = render_to_string(
        "storefront/sections/_hero_widget.html",
        {"hero_widget": "services", "services_preview": []},
    )
    assert off.strip() == ""


def test_gastro_hero_carries_tiles_widget():
    # Батч A «гастро-сплит»: у кафе/ресторана плитки-входы ВНУТРИ hero. Шаблон
    # gastro несёт site_defaults.hero_widget="gastro"; apply_template доносит;
    # смена Look'а сохраняет (как stays/services).
    from apps.tenants import siteconfig

    tpl = sitetemplates.get_template("gastro")
    assert tpl["site_defaults"]["hero_widget"] == "gastro"
    tenant = TenantFactory(schema_name="t_gw", business_type="restaurant")
    assert sitetemplates.apply_template(tenant, "gastro") is True
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["site_defaults"]["hero_widget"] == "gastro"
    assert sitetemplates.apply_look(tenant, "warm") is True
    tenant.refresh_from_db()
    assert tenant.site_config["site_defaults"]["hero_widget"] == "gastro"


def test_hero_widget_gastro_renders_tiles(settings):
    # Батч A: плитки Reservieren (гейт booking) + Speisekarte всегда + Angebot des
    # Tages только при активной акции (fail-safe: нет акции → плитки две).
    settings.ROOT_URLCONF = "config.urls_tenant"
    from django.template.loader import render_to_string

    from apps.promotions.models import Promotion

    two = render_to_string(
        "storefront/sections/_hero_widget.html",
        {"hero_widget": "gastro", "storefront_booking_enabled": True},
    )
    assert "Tisch reservieren" in two and "Speisekarte" in two
    assert "Angebot des Tages" not in two  # активных акций нет

    Promotion.objects.create(
        title={"de": "Mittagstisch"},
        status="active",
        promo_type="reservation",
        available_quantity=5,
    )
    three = render_to_string(
        "storefront/sections/_hero_widget.html",
        {"hero_widget": "gastro", "storefront_booking_enabled": True},
    )
    assert "Angebot des Tages" in three and "Mittagstisch" in three

    no_booking = render_to_string(
        "storefront/sections/_hero_widget.html",
        {"hero_widget": "gastro", "storefront_booking_enabled": False},
    )
    assert "Tisch reservieren" not in no_booking and "Speisekarte" in no_booking


def test_deal_of_day_prefers_daily_recurrence():
    # Тег deal_of_day: recurrence=daily — «акция дня» — приоритетнее прочих.
    from apps.promotions.models import Promotion
    from apps.tenants.templatetags.siteui import deal_of_day

    assert deal_of_day() is None  # нет активных → None (fail-safe)
    other = Promotion.objects.create(title={"de": "Sonstige"}, status="active")
    daily = Promotion.objects.create(
        title={"de": "Tagesdeal"}, status="active", recurrence=Promotion.DAILY
    )
    assert deal_of_day().pk == daily.pk
    daily.delete()
    assert deal_of_day().pk == other.pk


def test_hero_widget_partial_renders_date_search_gated_by_module(settings):
    # E4: партиал hero-виджета рендерит поиск дат при hero_widget="stays" +
    # активном модуле stays; при неактивном — пусто (без регрессии).
    settings.ROOT_URLCONF = "config.urls_tenant"
    from django.template.loader import render_to_string

    on = render_to_string(
        "storefront/sections/_hero_widget.html",
        {"hero_widget": "stays", "storefront_stays_enabled": True},
    )
    assert "Verfügbarkeit prüfen" in on and 'name="von"' in on
    off = render_to_string(
        "storefront/sections/_hero_widget.html",
        {"hero_widget": "stays", "storefront_stays_enabled": False},
    )
    assert off.strip() == ""


def test_apply_template_sets_layout_and_keeps_texts_and_onboarding():
    tenant = TenantFactory(
        schema_name="t_tpl",
        business_type="bakery",
        site_config={"hero_title": "Mein Laden", "onboarding": {"step": 2}},
    )
    assert sitetemplates.apply_template(tenant, "minimal") is True
    tenant.refresh_from_db()
    assert _enabled(tenant) == ["hero", "contact"]  # раскладка «minimal»
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["hero_title"] == "Mein Laden"  # непустой текст сохранён
    assert cfg["hero_style"] == "plain"  # minimal — белый баннер
    assert tenant.primary_color == "#111827"  # акцент шаблона
    assert tenant.site_config["onboarding"] == {"step": 2}  # onboarding не затёрт


def test_apply_template_fills_empty_texts():
    tenant = TenantFactory(schema_name="t_tpl2", business_type="bakery", site_config={})
    sitetemplates.apply_template(tenant, "laden")
    tenant.refresh_from_db()
    assert _enabled(tenant) == ["hero", "promotions", "products", "about", "contact"]
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["hero_title"]  # дефолт шаблона подставлен
    assert cfg["hero_style"] == "accent"
    assert tenant.primary_color == "#4f46e5"


def test_apply_unknown_template_is_noop():
    tenant = TenantFactory(schema_name="t_tpl3")
    assert sitetemplates.apply_template(tenant, "does-not-exist") is False


def test_builder_apply_template(rf, settings):
    # W11-5: галерея шаблонов переехала со страницы «Site» в Studio (область
    # «Schnellstart»); ветка apply_template — та же библиотека.
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(schema_name="t_view", business_type="cafe", site_config={})
    user = get_user_model().objects.create_user("u", "u@test.de", "pw12345678")

    resp = home_builder_view(
        _request(rf, "post", user, tenant, {"action": "apply_template", "template": "gastro"})
    )
    assert resp.status_code in (301, 302)
    tenant.refresh_from_db()
    assert _enabled(tenant) == ["hero", "products", "promotions", "contact"]


def test_builder_template_gallery_renders(rf, settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(schema_name="t_view2", business_type="bakery", disabled_modules=[])
    user = get_user_model().objects.create_user("u2", "u2@test.de", "pw12345678")

    html = home_builder_view(_request(rf, "get", user, tenant)).content.decode()
    assert "Klassischer Laden" in html  # карточка шаблона в галерее
    assert "Café &amp; Restaurant" in html


def test_builder_ignores_invalid_accent(rf, settings):
    """W6/W11-5: акцент пишется только валидным hex (единый источник — билдер)."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(
        schema_name="t_acc2", business_type="bakery", primary_color="#123456", site_config={}
    )
    user = get_user_model().objects.create_user("ub", "ub@test.de", "pw12345678")

    home_builder_view(_request(rf, "post", user, tenant, {"accent": "rot"}))
    tenant.refresh_from_db()
    assert tenant.primary_color == "#123456"  # невалидный hex проигнорирован


def test_accent_hero_renders_in_storefront(rf, settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory.build(
        name="Hero Co",
        primary_color="#0e7490",
        site_config={"hero_style": "accent", "sections": [{"key": "hero", "enabled": True}]},
    )
    request = rf.get("/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant

    body = public_views.storefront_home(request).content.decode()
    assert "var(--accent" in body  # цветной hero использует CSS-переменную
    assert "#0e7490" in body  # переменная определена из primary_color


def test_hero_widget_bakery_renders_direction_tiles(settings):
    """Фидбэк 2026-07-30 («Our offerings не практичен»): плитки-направления
    Bäckerei — Aktionen (гейт: активная акция) / Sortiment всегда /
    Wunschzeit (гейт orders) / Partyservice (гейт jobs)."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from django.template.loader import render_to_string

    from apps.promotions.models import Promotion

    ctx = {
        "hero_widget": "bakery",
        "storefront_orders_enabled": True,
        "storefront_jobs_enabled": True,
    }
    body = render_to_string("storefront/sections/_hero_widget.html", ctx)
    assert "Sortiment ansehen" in body
    assert "Zur Wunschzeit vorbestellen" in body
    assert "Partyservice anfragen" in body
    assert "Aktionen & Angebote" not in body  # активных акций нет — плитка скрыта

    Promotion.objects.create(title={"de": "Brotdeal"}, status="active")
    with_promo = render_to_string("storefront/sections/_hero_widget.html", ctx)
    assert "Aktionen & Angebote" in with_promo and "Brotdeal" in with_promo

    lean = render_to_string(
        "storefront/sections/_hero_widget.html",
        {"hero_widget": "bakery", "storefront_orders_enabled": False},
    )
    assert "Partyservice anfragen" not in lean
    assert "Zur Wunschzeit vorbestellen" not in lean
    assert "Sortiment ansehen" in lean  # fail-safe: минимум — каталог


def test_bakery_kit_slider_plus_widget_and_no_archetypes_section():
    """Кит BAKERY: 3 слайда баннера, секция архетипов выключена; механизм
    hero_widget цел (normalize держит ключ).

    DS-8: сам кит переведён на Fokus — плитки задач в баннере СНЯТЫ
    (hero_widget=""), их работу несут CTA шапки + компакт-плитки направлений;
    первый экран ведёт к ОДНОМУ действию."""
    from apps.tenants import siteconfig
    from apps.tenants.demo_kits import KITS

    kit = KITS["bakery"]
    assert kit.hero_widget == ""
    assert len(kit.heroes) == 3
    assert kit.enable_archetypes_section is False
    cfg = siteconfig.normalize({"site_defaults": {"hero_widget": "bakery"}, "heroes": kit.heroes})
    assert cfg["site_defaults"]["hero_widget"] == "bakery"


def test_hero_widget_butcher_same_tiles_meat_flavor(settings):
    """2026-07-30 («тот же набор»): butcher — та же ветка направлений, что bakery
    (Aktionen/Sortiment/Wunschzeit/Partyservice), мясной сабтекст Partyservice."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from django.template.loader import render_to_string

    body = render_to_string(
        "storefront/sections/_hero_widget.html",
        {
            "hero_widget": "butcher",
            "storefront_orders_enabled": True,
            "storefront_jobs_enabled": True,
        },
    )
    assert "Sortiment ansehen" in body
    assert "Zur Wunschzeit vorbestellen" in body
    assert "Platten, Buffets & Grillservice für Ihre Feier" in body
    assert "belegte Brötchen" not in body  # bakery-сабтекст не течёт в мясную


def test_butcher_kit_slider_plus_widget():
    """Кит BUTCHER: слайдер (3 слайда) + hero_widget="butcher", архетипы выкл."""
    from apps.tenants import siteconfig
    from apps.tenants.demo_kits import KITS

    kit = KITS["butcher"]
    assert kit.hero_widget == "butcher"
    assert len(kit.heroes) == 3
    assert kit.enable_archetypes_section is False
    cfg = siteconfig.normalize({"site_defaults": {"hero_widget": "butcher"}})
    assert cfg["site_defaults"]["hero_widget"] == "butcher"


def test_hero_widget_mode_renders_boutique_tiles(settings):
    """M0 Boutique (план mode-boutique-plan-2026-07-30): плитки-направления —
    Sale (гейт: живая акция) / Sortiment / Neuheiten / Gutschein (гейт gift)."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from django.template.loader import render_to_string

    from apps.promotions.models import Promotion

    ctx = {"hero_widget": "mode", "storefront_gift_enabled": True}
    body = render_to_string("storefront/sections/_hero_widget.html", ctx)
    assert "Sortiment ansehen" in body
    assert "Neuheiten" in body and "?sort=newest" in body
    assert "Geschenkgutschein" in body
    assert ">Sale</span>" not in body  # живой акции нет — плитка Sale скрыта

    Promotion.objects.create(title={"de": "Sommerkleider"}, status="active")
    with_sale = render_to_string("storefront/sections/_hero_widget.html", ctx)
    assert ">Sale</span>" in with_sale and "Sommerkleider" in with_sale

    no_gift = render_to_string("storefront/sections/_hero_widget.html", {"hero_widget": "mode"})
    assert "Geschenkgutschein" not in no_gift


def test_clothing_kit_slider_widget_honest_texts():
    """Кит CLOTHING: слайдер (3) + hero_widget=mode, архетип-секция выкл.
    M2 (2026-07-30): Warteliste per-size и Größentabelle РЕАЛИЗОВАНЫ — тексты
    демо снова обещают их честно (замок перевёрнут осознанно), таблицы заданы."""
    from apps.tenants import siteconfig
    from apps.tenants.demo_kits import KITS

    kit = KITS["clothing"]
    assert kit.hero_widget == "mode"
    assert len(kit.heroes) == 3
    assert kit.enable_archetypes_section is False
    assert "Warteliste" in kit.about_text
    assert set(kit.size_tables) == {"damen", "herren"}
    cfg = siteconfig.normalize({"site_defaults": {"hero_widget": "mode"}})
    assert cfg["site_defaults"]["hero_widget"] == "mode"
