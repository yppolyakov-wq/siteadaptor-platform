"""DL-13 (2026-09-02): композиционные примитивы шести новых дизайнов.

C1 hero fullscreen (без фото — честный accent) · C2 hero bento (бренд-плитка
всегда, прочие по данным) · C3 /aktionen/ «по времени» (ключ promo_grouping,
панель кабинета, ось сборки) · C4 лимит акций главной 9 + «Alle Aktionen» ·
C5 Grundpreis по промо-цене · C6 слайдер без автопрокрутки на телефоне ·
селект стиля баннера в билдере (Save больше не затирает split).
План: docs/dl13-six-designs-plan-2026-09-02.md §2.
"""

from datetime import timedelta
from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory
from django.utils import timezone

from apps.catalog.tests.factories import ProductFactory
from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants import siteconfig, sitetemplates
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

HERO_ON = [{"key": "hero", "enabled": True}]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path="/", **kw):
    request = RequestFactory().get(path, kw)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    return request


def _home(tenant, path="/"):
    request = _req(path)
    request.tenant = tenant
    return public_views.storefront_home(request).content.decode()


def _promo(title, **kw):
    return Promotion.objects.create(title={"de": title}, status="active", **kw)


# ── normalize ───────────────────────────────────────────────────────────────


def test_hero_styles_registry_and_normalize():
    assert siteconfig.HERO_STYLES == ("plain", "accent", "split", "fullscreen", "bento")
    assert [k for k, _ in siteconfig.HERO_STYLE_LABELS] == list(siteconfig.HERO_STYLES)
    for style in siteconfig.HERO_STYLES:
        assert siteconfig.normalize({"hero_style": style})["hero_style"] == style
    assert siteconfig.normalize({"hero_style": "junk"})["hero_style"] == "plain"


def test_promo_grouping_presence_minimal():
    assert "promo_grouping" not in siteconfig.normalize({})
    assert "promo_grouping" not in siteconfig.normalize({"promo_grouping": ""})
    assert "promo_grouping" not in siteconfig.normalize({"promo_grouping": "junk"})
    assert siteconfig.normalize({"promo_grouping": "time"})["promo_grouping"] == "time"


def test_promotions_limit_default_nine_and_viewall():
    cfg = siteconfig.normalize({})
    row = next(s for s in cfg["sections"] if s["key"] == "promotions")
    assert row["limit"] == 9 and row["show_all"] is True
    assert siteconfig.section_limit(cfg, "promotions") == 9


# ── C1 fullscreen ───────────────────────────────────────────────────────────


def test_hero_fullscreen_renders_photo_text_and_deal_card():
    tenant = TenantFactory(
        schema_name="public",
        slug="fs1",
        name="FS",
        disabled_modules=[],
        site_config={
            "sections": HERO_ON,
            "hero_style": "fullscreen",
            "hero_title": "Frische Woche",
            "hero_image": "/media/hero.jpg",
        },
    )
    _promo("Deal FS", ends_at=timezone.now() + timedelta(days=2))
    html = _home(tenant)
    assert "data-hero-fullscreen" in html
    assert 'src="/media/hero.jpg"' in html and "Frische Woche" in html
    assert "data-hero-deal" in html and "Deal FS" in html  # стеклянная карточка акции
    assert "data-hero-slider" not in html


def test_hero_fullscreen_without_photo_falls_back_to_accent():
    tenant = TenantFactory.build(
        site_config={"sections": HERO_ON, "hero_style": "fullscreen", "hero_title": "Ohne Foto"}
    )
    html = _home(tenant)
    assert "data-hero-fullscreen" not in html
    assert "var(--accent" in html and "Ohne Foto" in html  # accent-плита, не пусто


def test_hero_fullscreen_takes_first_slide_when_no_flat_image():
    tenant = TenantFactory.build(
        site_config={
            "sections": HERO_ON,
            "hero_style": "fullscreen",
            "heroes": [{"image": "/media/slide.jpg", "title": "A"}],
        }
    )
    html = _home(tenant)
    assert "data-hero-fullscreen" in html and 'src="/media/slide.jpg"' in html


# ── C2 bento ────────────────────────────────────────────────────────────────


def test_hero_bento_brand_tile_always_and_data_tiles_gated():
    tenant = TenantFactory(
        schema_name="public",
        slug="bn1",
        name="Bento Markt",
        disabled_modules=[],
        opening_hours_structured={},  # фабрика даёт часы по умолчанию — здесь без них
        site_config={"sections": HERO_ON, "hero_style": "bento", "hero_title": "Hallo Bento"},
    )
    html = _home(tenant)
    assert "data-hero-bento" in html and 'data-bento="brand"' in html
    assert "Hallo Bento" in html and 'data-edit="hero_title"' in html
    # без акций/категорий/часов — плитки выпадают, newsletter (модуль promotions) есть
    assert 'data-bento="deal"' not in html
    assert 'data-bento="category"' not in html
    assert 'data-bento="hours"' not in html
    assert 'data-bento="newsletter"' in html
    _promo("Bento Deal")
    html = _home(tenant)
    assert 'data-bento="deal"' in html and "Bento Deal" in html


def test_hero_bento_hours_tile_from_structured_hours():
    tenant = TenantFactory(
        schema_name="public",
        slug="bn2",
        name="BN2",
        disabled_modules=[],
        opening_hours_structured={str(d): ["08:00", "18:00"] for d in range(7)},
        site_config={"sections": HERO_ON, "hero_style": "bento"},
    )
    html = _home(tenant)
    assert 'data-bento="hours"' in html


# ── C3 «по времени» ─────────────────────────────────────────────────────────


def _aktionen(tenant, params=None):
    req = _req("/aktionen/", **(params or {}))
    req.tenant = tenant
    return public_views.promotion_list(req).content.decode()


def test_time_grouping_sections_in_urgency_order():
    tenant = TenantFactory(
        schema_name="public",
        slug="tg1",
        name="TG",
        disabled_modules=[],
        site_config={"promo_grouping": "time"},
    )
    now = timezone.localtime()
    end_today = now.replace(hour=23, minute=59)
    _promo("Dauer-Deal", group="Wochenangebote")
    _promo("Heute-Deal", ends_at=end_today)
    _promo("Woche-Deal", ends_at=end_today + timedelta(days=6 - now.weekday()))
    _promo("Spaeter-Deal", ends_at=now + timedelta(days=40))
    body = _aktionen(tenant)
    heute, woche, laenger, dauer = (
        body.index("Endet heute"),
        body.index("Endet diese Woche"),
        body.index("Länger gültig"),
        body.index("Dauerhaft"),
    )
    assert heute < woche < laenger < dauer
    # четыре секции по сроку; тематическая группа владельца заголовком не рисуется
    # (чип-фильтр «Wochenangebote» сверху остаётся — фильтры прежние)
    assert body.count('<section class="mb-8">') == 4
    assert '<h2 class="text-lg font-bold mb-3">Wochenangebote' not in body
    # одиночная секция «Endet heute» есть (порог MIN_GROUP_SECTION не действует)
    assert body.index("Heute-Deal") > heute


def test_time_grouping_off_by_default_and_filters_flatten():
    tenant = TenantFactory(schema_name="public", slug="tg2", name="TG2", disabled_modules=[])
    _promo("A", group="Wochenangebote")
    _promo("B", group="Wochenangebote")
    body = _aktionen(tenant)
    assert "Endet diese Woche" not in body and "Dauerhaft" not in body  # прежние группы
    tenant.site_config = {"promo_grouping": "time"}
    tenant.save()
    assert "Dauerhaft" in _aktionen(tenant)
    assert "Dauerhaft" not in _aktionen(tenant, {"q": "A"})  # фильтр → плоская сетка


def test_promo_page_mode_endpoint_targeted_write():
    from django.contrib.auth import get_user_model
    from django.contrib.messages.storage.fallback import FallbackStorage

    from apps.promotions import views as cab_views

    tenant = TenantFactory(
        schema_name="public",
        slug="pm1",
        name="PM",
        disabled_modules=[],
        site_config={"notify": {"customer": {"email": True}}},
    )
    user = get_user_model().objects.create_user("pm1", "pm1@test.de", "pw12345678")

    def post(mode):
        req = RequestFactory().post("/promotions/aktionsseite/", {"mode": mode})
        req.tenant = tenant
        req.user = user
        req.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
        req._messages = FallbackStorage(req)
        return cab_views.promotion_page_mode(req)

    assert post("time").status_code == 302
    tenant.refresh_from_db()
    assert tenant.site_config["promo_grouping"] == "time"
    assert tenant.site_config["notify"] == {"customer": {"email": True}}  # чужой ключ цел
    post("")
    tenant.refresh_from_db()
    assert "promo_grouping" not in tenant.site_config


def test_bundle_axis_promo_grouping_sets_and_resets():
    cfg = siteconfig.normalize({})
    sitetemplates._apply_bundle_axes(cfg, {"promo_grouping": "time"})
    assert cfg["promo_grouping"] == "time"
    sitetemplates._apply_bundle_axes(cfg, {"promo_grouping": ""})
    assert "promo_grouping" not in cfg
    sitetemplates._apply_bundle_axes(cfg, {"hero_style": "split"})  # ось не упомянута → цел
    assert "promo_grouping" not in cfg
    assert sitetemplates._DEAL_BASE["promo_grouping"] == ""  # дил-сборки сбрасывают


# ── C4 лимит 9 ──────────────────────────────────────────────────────────────


def test_home_promotions_limit_counts_cards_exactly():
    tenant = TenantFactory(
        schema_name="public",
        slug="lim2",
        name="LIM2",
        disabled_modules=[],
        site_config={"sections": [{"key": "promotions", "enabled": True}]},
    )
    for i in range(12):
        _promo(f"Karte-{i:02d}")
    html = _home(tenant)
    assert html.count("Karte-") == 9
    assert "data-promo-viewall" in html and "/aktionen/" in html
    # владелец может поднять лимит в Studio
    tenant.site_config = {"sections": [{"key": "promotions", "enabled": True, "limit": 12}]}
    assert _home(tenant).count("Karte-") == 12
    # show_all=False прячет ссылку
    tenant.site_config = {"sections": [{"key": "promotions", "enabled": True, "show_all": False}]}
    assert "data-promo-viewall" not in _home(tenant)


def test_home_ending_soon_chips_come_from_full_list():
    """Полоса «Endet bald» (spotlight) — из полной выборки, не из среза 9."""
    tenant = TenantFactory(
        schema_name="public",
        slug="lim3",
        name="LIM3",
        disabled_modules=[],
        site_config={"sections": [{"key": "promotions", "enabled": True, "style": "spotlight"}]},
    )
    for i in range(10):
        _promo(f"Alt-{i:02d}", ends_at=timezone.now() + timedelta(days=30))
    _promo("Bald-Deal", ends_at=timezone.now() + timedelta(hours=5))  # свежайшая → срез не режет
    html = _home(tenant)
    assert "Bald-Deal" in html and "data-promo-ending" in html


# ── C5 Grundpreis ───────────────────────────────────────────────────────────


def test_promotion_grundpreis_from_promo_price():
    product = ProductFactory(base_price="4.00", unit="g", content_amount="500")
    promo = _promo("Kaffee", product=product, discount_percent=25)  # 3.00 € / 500 g
    gp = promo.grundpreis
    assert gp is not None and str(gp[0]) == "6.00" and gp[1] == "kg"
    assert _promo("Frei").grundpreis is None  # свободная акция — нет
    tenant = TenantFactory(
        schema_name="public",
        slug="gp1",
        name="GP",
        disabled_modules=[],
        site_config={"sections": [{"key": "promotions", "enabled": True}]},
    )
    html = _home(tenant)
    assert "data-grundpreis" in html and "/ kg" in html
    req = _req(f"/p/{promo.pk}/")
    req.tenant = tenant
    detail = public_views.promotion_detail(req, promo.pk).content.decode()
    assert "data-grundpreis" in detail
    # mystery: цена скрыта → Grundpreis не выдаёт её на карточке
    promo.discount_style = "mystery"
    promo.save()
    html = _home(tenant)
    assert "data-grundpreis" not in html


# ── C6 слайдер ──────────────────────────────────────────────────────────────


def test_slider_autoplay_guarded_on_mobile_and_reduced_motion():
    tenant = TenantFactory.build(
        site_config={
            "sections": HERO_ON,
            "heroes": [{"image": "/media/a.jpg"}, {"image": "/media/b.jpg"}],
        }
    )
    html = _home(tenant)
    assert "data-hero-slider" in html
    assert "(max-width: 767px)" in html and "prefers-reduced-motion: reduce" in html
    assert "mouseenter" in html and "focusin" in html


# ── билдер: селект стиля баннера ─────────────────────────────────────────────


def test_builder_hero_style_select_saves_split_and_new_styles():
    from django.contrib.auth import get_user_model
    from django.contrib.messages.storage.fallback import FallbackStorage

    from apps.core import views as core_views

    tenant = TenantFactory(schema_name="public", slug="hs1", name="HS", disabled_modules=[])
    user = get_user_model().objects.create_user("hs1", "hs1@test.de", "pw12345678")

    def call(method, data=None):
        req = getattr(RequestFactory(), method)("/dashboard/site/home/", data or {})
        req.tenant = tenant
        req.user = user
        req.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
        req._messages = FallbackStorage(req)
        return core_views.home_builder_view(req)

    html = call("get").content.decode()
    assert 'name="hero_style"' in html and 'value="fullscreen"' in html and 'value="bento"' in html
    for style in ("split", "fullscreen", "bento"):
        call("post", {"hero_title": "X", "hero_style": style, "font": "system"})
        tenant.refresh_from_db()
        assert tenant.site_config["hero_style"] == style
    # легаси-чекбокс (старые формы) — прежняя семантика
    call("post", {"hero_title": "X", "hero_accent": "on", "font": "system"})
    tenant.refresh_from_db()
    assert tenant.site_config["hero_style"] == "accent"
