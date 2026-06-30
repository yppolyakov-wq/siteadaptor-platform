"""Track C1: публичный каталог на витрине (список, карточка, превью, sitemap)."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path="/sortiment/", params=None):
    request = RequestFactory().get(path, params or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(name="Bäckerei X", address="Hauptstr. 1")
    return request


def test_product_list_shows_active_only():
    ProductFactory(name={"de": "AktivBrot"})
    ProductFactory(name={"de": "VerstecktBrot"}, is_active=False)
    deleted = ProductFactory(name={"de": "WegBrot"})
    deleted.delete()  # soft-delete

    body = public_views.product_list(_req()).content.decode()
    assert "AktivBrot" in body
    assert "VerstecktBrot" not in body
    assert "WegBrot" not in body


def test_product_list_filters_by_category():
    cat = CategoryFactory(slug="brot", name={"de": "Brot"})
    ProductFactory(name={"de": "Roggenbrot"}, category=cat)
    ProductFactory(name={"de": "Kuchenstück"})

    body = public_views.product_list(_req(params={"kategorie": "brot"})).content.decode()
    assert "Roggenbrot" in body
    assert "Kuchenstück" not in body


def test_catalog_chip_edit_link_in_preview():
    """SE-2c-2: в режиме редактора (?preview=1) на чипе категории есть ссылка правки;
    на обычной витрине — нет."""
    from django.urls import reverse

    cat = CategoryFactory(slug="brot", name={"de": "Brot"})
    ProductFactory(name={"de": "Roggenbrot"}, category=cat)  # чтобы чип категории появился
    edit_url = reverse("catalog:category-edit", args=[cat.pk])

    body_prev = public_views.product_list(_req(params={"preview": "1"})).content.decode()
    assert edit_url in body_prev and "data-cat-edit" in body_prev  # ссылка правки в редакторе

    body_plain = public_views.product_list(_req()).content.decode()
    assert edit_url not in body_plain  # на витрине посетителя ссылки нет


def test_catalog_shows_subcategories_first():
    """M20U-3: в категории с подкатегориями сначала выводятся подкатегории."""
    parent = CategoryFactory(slug="brot", name={"de": "Brot"})
    CategoryFactory(slug="roggen", name={"de": "Roggen"}, parent=parent, sort_order=1)
    body = public_views.product_list(_req(params={"kategorie": "brot"})).content.decode()
    assert "Roggen" in body
    assert "kategorie=roggen" in body  # ссылка на подкатегорию


def test_catalog_page_grid_from_config():
    """M20U-7 (per-page): сетка страницы каталога берётся из catalog_layout."""
    ProductFactory(name={"de": "Brot"})
    req = _req("/sortiment/")
    req.tenant.site_config = {"catalog_layout": {"preset": "cols4"}}
    body = public_views.product_list(req).content.decode()
    assert "lg:grid-cols-4" in body


def test_catalog_grid_uses_preview_draft():
    """SE-2a-2: при ?preview=1 сетка каталога берётся из черновика сессии (on-canvas)."""
    ProductFactory(name={"de": "Brot"})
    req = _req("/sortiment/", params={"preview": "1"})
    req.tenant.site_config = {"catalog_layout": {"preset": "cols2"}}  # сохранённый
    req.session["site_preview_draft"] = {"catalog_layout": {"preset": "cols4"}}  # черновик
    body = public_views.product_list(req).content.decode()
    assert "lg:grid-cols-4" in body  # показан черновик, не сохранённый cols2


def test_catalog_grid_has_canvas_section_marker():
    """SE-2a-2: грид каталога несёт data-sf-section='catalog' для on-canvas клика."""
    ProductFactory(name={"de": "Brot"})
    body = public_views.product_list(_req()).content.decode()
    assert 'data-sf-section="catalog"' in body


def test_unknown_category_redirects_to_full_list():
    resp = public_views.product_list(_req(params={"kategorie": "ghost"}))
    assert resp.status_code == 302
    assert resp.url == "/sortiment/"


def test_product_detail_renders_price_and_contacts():
    product = ProductFactory(
        name={"de": "Roggenbrot"}, description={"de": "Frisch gebacken"}, base_price="4.20"
    )
    body = public_views.product_detail(_req(f"/sortiment/{product.pk}/"), pk=product.pk)
    body = body.content.decode()
    assert "Roggenbrot" in body
    assert "4,20" in body  # DE-локаль: запятая
    assert "Frisch gebacken" in body
    assert "Hauptstr. 1" in body  # офлайн-покупка: контакты бизнеса


def test_product_detail_inline_edit_markers():
    """H1.2: имя и описание товара на детальной несут data-edit-model → редактор
    (его frame.load JS) делает их contenteditable. На публичной витрине инертны."""
    product = ProductFactory(name={"de": "Roggenbrot"}, description={"de": "Frisch"})
    body = public_views.product_detail(
        _req(f"/sortiment/{product.pk}/"), pk=product.pk
    ).content.decode()
    assert 'data-edit-model="product"' in body
    assert 'data-edit-field="name"' in body
    assert 'data-edit-field="description"' in body
    assert f'data-edit-pk="{product.pk}"' in body


def test_product_detail_uses_shared_media_gallery():
    """M20U-4: карточка товара переиспользует общую галерею (большое+миниатюры)."""
    product = ProductFactory(
        name={"de": "Roggenbrot"},
        images=[
            {"id": "a", "url": "https://img/a.jpg", "is_primary": True},
            {"id": "b", "url": "https://img/b.jpg"},
        ],
    )
    body = public_views.product_detail(
        _req(f"/sortiment/{product.pk}/"), pk=product.pk
    ).content.decode()
    assert "js-media-gallery" in body and 'data-src="https://img/b.jpg"' in body


def test_product_detail_mobile_buybar_when_orderable():
    """M20U-4: липкая панель покупки на детальной товара (orders активен, в наличии)."""
    product = ProductFactory(name={"de": "Roggenbrot"}, base_price="4.20")
    req = _req(f"/sortiment/{product.pk}/")
    req.tenant = TenantFactory.build(name="Bäckerei X", address="Hauptstr. 1", disabled_modules=[])
    body = public_views.product_detail(req, pk=product.pk).content.decode()
    assert "data-buybar" in body and "In den Warenkorb" in body
    assert 'id="kaufen"' in body


def test_product_detail_uses_unified_scaffold():
    """M20U-4: карточка товара наследует общий detail.html (2 колонки + sticky-aside)."""
    product = ProductFactory(name={"de": "Roggenbrot"}, base_price="4.20")
    body = public_views.product_detail(
        _req(f"/sortiment/{product.pk}/"), pk=product.pk
    ).content.decode()
    assert "max-w-5xl" in body  # каркас detail.html
    assert "lg:sticky" in body and "lg:grid-cols-2" in body


def test_product_detail_related_grid_from_config():
    """M20U-7 (per-page): сетка «похожих товаров» берётся из detail_related_layout."""
    cat = CategoryFactory(slug="brot", name={"de": "Brot"})
    product = ProductFactory(name={"de": "Roggenbrot"}, category=cat)
    ProductFactory(name={"de": "Dinkelbrot"}, category=cat)  # related
    req = _req(f"/sortiment/{product.pk}/")
    req.tenant.site_config = {"detail_related_layout": {"preset": "cols3"}}
    body = public_views.product_detail(req, pk=product.pk).content.decode()
    assert "Dinkelbrot" in body  # блок похожих отрисован
    assert "lg:grid-cols-3" in body  # пресет применён (дефолт был cols4)


def test_product_detail_404_for_inactive():
    product = ProductFactory(is_active=False)
    with pytest.raises(Http404):
        public_views.product_detail(_req(), pk=product.pk)


def test_home_archetype_default_enables_primary_section():
    """M20U-2: на ненастроенной главной секция «главного товара» архетипа включена сама."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.events.models import Event

    Event.objects.create(
        title="Yoga-Retreat",
        starts_at=timezone.now() + timedelta(days=10),
        status=Event.STATUS_PUBLISHED,
    )
    req = _req("/")
    req.tenant = TenantFactory.build(disabled_modules=[])  # все модули активны, конфиг без sections
    body = public_views.storefront_home(req).content.decode()
    assert "Yoga-Retreat" in body and "/veranstaltung/" in body


def test_home_archetype_default_skipped_when_sections_configured():
    """Если владелец задал композицию (есть sections), авто-включения нет."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.events.models import Event

    Event.objects.create(
        title="Yoga-Retreat",
        starts_at=timezone.now() + timedelta(days=10),
        status=Event.STATUS_PUBLISHED,
    )
    req = _req("/")
    req.tenant = TenantFactory.build(disabled_modules=[])
    req.tenant.site_config = {"sections": [{"key": "contact", "enabled": True}]}
    body = public_views.storefront_home(req).content.decode()
    # секции событий нет → ни карточки события (заголовок только в секции, не в навбаре)
    assert "Yoga-Retreat" not in body


def test_home_categories_section_when_enabled():
    """M20U-2: секция категорий на главной — карточки top-level → каталог с фильтром."""
    CategoryFactory(slug="brot", name={"de": "Brot"}, sort_order=1)
    CategoryFactory(slug="kuchen", name={"de": "Kuchen"}, sort_order=2)
    req = _req("/")
    req.tenant.site_config = {"sections": [{"key": "categories", "enabled": True}]}
    body = public_views.storefront_home(req).content.decode()
    assert "Brot" in body and "Kuchen" in body
    assert "kategorie=brot" in body  # ссылка на каталог с фильтром


def test_home_categories_section_hidden_by_default():
    CategoryFactory(slug="brot", name={"de": "Brot"})
    body = public_views.storefront_home(_req("/")).content.decode()
    assert "kategorie=brot" not in body  # секция выкл по умолчанию


def test_home_events_section_when_enabled():
    """M20U-2: секция мероприятий на главной — ближайшие события grid → /veranstaltung/."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.events.models import Event

    Event.objects.create(
        title="Yoga-Retreat",
        starts_at=timezone.now() + timedelta(days=10),
        status=Event.STATUS_PUBLISHED,
    )
    req = _req("/")
    req.tenant = TenantFactory.build(disabled_modules=[])  # все модули активны
    req.tenant.site_config = {"sections": [{"key": "events", "enabled": True}]}
    body = public_views.storefront_home(req).content.decode()
    assert "Yoga-Retreat" in body and "/veranstaltung/" in body
    assert "Jetzt buchen" in body  # M20U-5: действие покупки по режиму (booking)


def test_home_hero_cta_links_to_primary_item():
    """M20U-5: accent-hero показывает CTA на «главный товар» архетипа (events → /veranstaltung/)."""
    req = _req("/")
    req.tenant = TenantFactory.build(disabled_modules=[])  # все архетипы активны
    req.tenant.site_config = {
        "hero_style": "accent",
        "sections": [{"key": "hero", "enabled": True}],
    }
    body = public_views.storefront_home(req).content.decode()
    assert "data-hero-cta" in body
    assert "/veranstaltung/" in body  # events приоритетнее → primary item
    assert "Veranstaltungen" in body  # storefront_label архетипа


def test_home_sections_carry_sf_section_markers():
    """M20U-7 (B): секции главной несут data-sf-section (клик в live-preview билдера)."""
    body = public_views.storefront_home(_req("/")).content.decode()
    assert 'data-sf-section="contact"' in body  # включённая по умолчанию секция


def test_home_section_hidden_on_mobile_emits_responsive_class():
    """SE-3c-mid: hidden_on=['mobile'] секции рендерит max-sm:hidden на её обёртке."""
    req = _req("/")
    req.tenant.site_config = {
        "sections": [{"key": "contact", "enabled": True, "hidden_on": ["mobile"]}]
    }
    body = public_views.storefront_home(req).content.decode()
    assert "max-sm:hidden" in body
    assert "lg:hidden" not in body  # desktop НЕ скрыт


def test_home_section_visible_everywhere_has_no_hide_class():
    """SE-3c-mid: без hidden_on обёртка секции не несёт классов скрытия (без регрессии)."""
    req = _req("/")
    req.tenant.site_config = {"sections": [{"key": "contact", "enabled": True}]}
    body = public_views.storefront_home(req).content.decode()
    assert "max-sm:hidden" not in body
    assert "sm:max-lg:hidden" not in body


def test_home_plain_hero_has_no_cta():
    """Дефолтный (plain) hero — без CTA: легаси-витрина не меняется."""
    body = public_views.storefront_home(_req("/")).content.decode()
    assert "data-hero-cta" not in body


def test_home_shows_products_preview():
    ProductFactory(name={"de": "VorschauBrot"})
    body = public_views.storefront_home(_req("/")).content.decode()
    assert "VorschauBrot" in body
    assert "/sortiment/" in body


def test_product_card_has_inline_edit_hooks():
    """Фаза 1 (inline-content): имя товара на карточке размечено для инлайн-правки
    на канве витрины (data-edit-model/pk/field). На публичной витрине это просто
    data-атрибуты — contenteditable вешает только редактор-iframe."""
    p = ProductFactory(name={"de": "VorschauBrot"})
    body = public_views.storefront_home(_req("/")).content.decode()
    assert 'data-edit-model="product"' in body
    assert 'data-edit-field="name"' in body
    assert f'data-edit-pk="{p.pk}"' in body


def test_home_products_preview_respects_limit():
    """M20U-7: число товаров в превью главной берётся из конфига секции."""
    for i in range(10):
        ProductFactory(name={"de": f"Brot{i}"})
    req = _req("/")
    req.tenant.site_config = {"sections": [{"key": "products", "enabled": True, "limit": 3}]}
    body = public_views.storefront_home(req).content.decode()
    shown = sum(1 for i in range(10) if f"Brot{i}" in body)
    assert shown == 3


def test_home_products_source_featured_only():
    """M20U-7: источник «featured_only» показывает на главной только избранные товары."""
    ProductFactory(name={"de": "Star"}, is_featured=True)
    ProductFactory(name={"de": "Normal"}, is_featured=False)
    req = _req("/")
    req.tenant.site_config = {
        "sections": [{"key": "products", "enabled": True, "source": "featured_only"}]
    }
    body = public_views.storefront_home(req).content.decode()
    assert "Star" in body and "Normal" not in body


def test_home_section_hide_view_all_link():
    """M20U-7: владелец может скрыть ссылку «View all» секции."""
    ProductFactory(name={"de": "Brot"})
    req = _req("/")
    req.tenant.site_config = {"sections": [{"key": "products", "enabled": True, "show_all": False}]}
    body = public_views.storefront_home(req).content.decode()
    assert "Brot" in body  # секция отрисована
    assert "View all" not in body  # ссылка скрыта


def test_home_promotions_section_honors_layout_preset():
    """M20U-7: пресет раскладки применяется и к секции акций (cols3→cols4)."""
    from apps.promotions.tests.factories import PromotionFactory

    PromotionFactory()
    req = _req("/")
    req.tenant.site_config = {
        "sections": [{"key": "promotions", "enabled": True, "layout": {"preset": "cols4"}}]
    }
    body = public_views.storefront_home(req).content.decode()
    assert "lg:grid-cols-4" in body  # пресет применён (дефолт был cols3)


def test_home_team_section_honors_layout_preset():
    """M20U-7: пресет раскладки реально применяется к секции (team: cols4→cols2)."""
    req = _req("/")
    req.tenant.site_config = {
        "team": [{"name": "Anna", "role": "Chef", "photo": ""}],
        "sections": [{"key": "team", "enabled": True, "layout": {"preset": "cols2"}}],
    }
    body = public_views.storefront_home(req).content.decode()
    assert "Anna" in body
    assert "lg:grid-cols-2" in body  # пресет применён (дефолт был cols4)


def test_home_section_custom_heading():
    """M20U-7: владелец задаёт свой заголовок секции (вместо стандартного)."""
    ProductFactory(name={"de": "Brot"})
    req = _req("/")
    req.tenant.site_config = {"section_titles": {"products": "Frisch aus dem Ofen"}}
    body = public_views.storefront_home(req).content.decode()
    assert "Frisch aus dem Ofen" in body


def test_home_without_products_has_no_section():
    body = public_views.storefront_home(_req("/")).content.decode()
    assert "/sortiment/</a>" not in body  # ссылки «View all» нет без товаров


def test_sitemap_includes_products():
    product = ProductFactory()
    body = public_views.sitemap_xml(_req("/sitemap.xml")).content.decode()
    assert "/sortiment/</loc>" in body
    assert f"/sortiment/{product.pk}/" in body


def test_sitemap_without_products_skips_section():
    body = public_views.sitemap_xml(_req("/sitemap.xml")).content.decode()
    assert "/sortiment/" not in body


def test_contact_section_embeds_map_with_coords():
    """T1: при заданных координатах в секции контактов встроена карта Leaflet."""
    from decimal import Decimal

    req = _req("/")
    req.tenant.latitude = Decimal("51.1700000")
    req.tenant.longitude = Decimal("6.9400000")
    body = public_views.storefront_home(req).content.decode()
    assert "sf-contact-map" in body
    assert "leaflet" in body.lower()


def test_contact_section_without_coords_has_no_map():
    body = public_views.storefront_home(_req("/")).content.decode()
    assert "sf-contact-map" not in body


def test_storefront_chat_fab_when_inbox_active():
    """M22b: при активном модуле inbox на витрине — плавающая кнопка чата."""
    ProductFactory(name={"de": "AktivBrot"})
    req = _req()
    req.tenant = TenantFactory.build(name="Bäckerei X", address="Hauptstr. 1", disabled_modules=[])
    body = public_views.product_list(req).content.decode()
    assert "data-chat-fab" in body and "/nachricht/" in body


def test_storefront_chat_fab_hidden_when_inbox_off():
    req = _req()
    req.tenant = TenantFactory.build(name="Bäckerei X", disabled_modules=["inbox"])
    body = public_views.product_list(req).content.decode()
    assert "data-chat-fab" not in body


def test_storefront_includes_telegram_miniapp_sdk():
    """TG2: витрина подключает Telegram Web App SDK (Mini App)."""
    ProductFactory(name={"de": "AktivBrot"})
    body = public_views.product_list(_req()).content.decode()
    assert "telegram.org/js/telegram-web-app.js" in body
    assert "in-telegram" in body  # init-скрипт присутствует


def test_category_description_renders_when_category_selected():
    """«Категории с описанием»: при выбранной категории её i18n-описание выводится на
    странице каталога; без выбора (вся витрина) — не показывается."""
    cat = CategoryFactory(
        slug="brot", name={"de": "Brot"}, description={"de": "Frisch aus dem Holzofen"}
    )
    ProductFactory(name={"de": "Roggenbrot"}, category=cat)

    body = public_views.product_list(_req(params={"kategorie": "brot"})).content.decode()
    assert "Frisch aus dem Holzofen" in body

    body_all = public_views.product_list(_req()).content.decode()
    assert "Frisch aus dem Holzofen" not in body_all


def test_category_form_saves_i18n_description():
    from apps.catalog.forms import CategoryForm

    form = CategoryForm(
        data={
            "name_de": "Brot",
            "name_en": "Bread",
            "description_de": "Frisch gebacken",
            "description_en": "Freshly baked",
            "sort_order": 0,
        }
    )
    assert form.is_valid(), form.errors
    cat = form.save()
    assert cat.description == {"de": "Frisch gebacken", "en": "Freshly baked"}
    assert cat.get_i18n("description") == "Frisch gebacken"
