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


def test_catalog_subcats_first_toggle_off_hides_cards():
    """Тумблер catalog_subcats_first=False → карточки подкатегорий не выводятся."""
    parent = CategoryFactory(slug="brot", name={"de": "Brot"})
    CategoryFactory(slug="roggen", name={"de": "Roggen"}, parent=parent, sort_order=1)
    req = _req(params={"kategorie": "brot"})
    req.tenant.site_config = {"catalog_subcats_first": False}
    body = public_views.product_list(req).content.decode()
    assert "kategorie=roggen" not in body  # карточки подкатегорий скрыты


def test_catalog_sort_by_price():
    """Сортировка ?sort=price_asc/price_desc меняет порядок (keyset по base_price)."""
    ProductFactory(name={"de": "TeuerX"}, base_price="9.00")
    ProductFactory(name={"de": "BilligX"}, base_price="1.00")
    asc = public_views.product_list(_req(params={"sort": "price_asc"})).content.decode()
    assert asc.index("BilligX") < asc.index("TeuerX")  # дешёвый раньше
    desc = public_views.product_list(_req(params={"sort": "price_desc"})).content.decode()
    assert desc.index("TeuerX") < desc.index("BilligX")  # дорогой раньше


def test_catalog_default_sort_from_config():
    """Дефолтная сортировка витрины (catalog_sort) применяется без ?sort=."""
    ProductFactory(name={"de": "TeuerY"}, base_price="9.00")
    ProductFactory(name={"de": "BilligY"}, base_price="1.00")
    req = _req()
    req.tenant.site_config = {"catalog_sort": "price_asc"}
    body = public_views.product_list(req).content.decode()
    assert body.index("BilligY") < body.index("TeuerY")


def test_catalog_price_filter():
    """Фасет цены: ?preis_von/preis_bis сужает по base_price (composes с keyset)."""
    ProductFactory(name={"de": "BilligP"}, base_price="1.00")
    ProductFactory(name={"de": "MittelP"}, base_price="5.00")
    ProductFactory(name={"de": "TeuerP"}, base_price="9.00")
    body = public_views.product_list(
        _req(params={"preis_von": "4", "preis_bis": "6"})
    ).content.decode()
    assert "MittelP" in body
    assert "BilligP" not in body and "TeuerP" not in body


def test_catalog_price_filter_shown_only_with_spread():
    """Поле диапазона цены показываем только при разбросе цен (иначе шум)."""
    # Разброс есть → форма с полем preis_von.
    ProductFactory(name={"de": "A"}, base_price="1.00")
    ProductFactory(name={"de": "B"}, base_price="9.00")
    body = public_views.product_list(_req()).content.decode()
    assert 'name="preis_von"' in body


def test_catalog_price_filter_hidden_without_spread():
    """Одна цена у всех товаров → поле диапазона цены не выводится."""
    ProductFactory(name={"de": "A"}, base_price="3.00")
    ProductFactory(name={"de": "B"}, base_price="3.00")
    body = public_views.product_list(_req()).content.decode()
    assert 'name="preis_von"' not in body


def test_catalog_badge_facet_filters_and_lists_present_only():
    """Фасет-бейдж: фильтрует по badge и показывает только присутствующие бейджи."""
    ProductFactory(name={"de": "NeuP"}, badge="neu")
    ProductFactory(name={"de": "BeliebtP"}, badge="beliebt")
    ProductFactory(name={"de": "PlainP"})
    body = public_views.product_list(_req()).content.decode()
    assert 'value="neu"' in body and 'value="beliebt"' in body  # присутствующие — в селекте
    assert 'value="empfehlung"' not in body  # отсутствующий бейдж не предлагаем
    only_neu = public_views.product_list(_req(params={"badge": "neu"})).content.decode()
    assert "NeuP" in only_neu
    assert "BeliebtP" not in only_neu and "PlainP" not in only_neu


def test_catalog_in_stock_filter():
    """«Nur verfügbare»: скрывает распроданное (stock 0), оставляет untracked/в наличии."""
    ProductFactory(name={"de": "AusverkauftP"}, stock_quantity=0)
    ProductFactory(name={"de": "VorraetigP"}, stock_quantity=5)
    ProductFactory(name={"de": "UntrackedP"}, stock_quantity=None)
    body = public_views.product_list(_req(params={"nur_verfuegbar": "1"})).content.decode()
    assert "VorraetigP" in body and "UntrackedP" in body
    assert "AusverkauftP" not in body


def test_catalog_in_stock_filter_respects_variants():
    """С вариантами наличие считается по вариантам (зеркало Product.in_stock)."""
    from apps.catalog.models import ProductVariant

    has = ProductFactory(name={"de": "HatVorratP"}, stock_quantity=0)
    ProductVariant.objects.create(product=has, label="M", stock_quantity=3)
    out = ProductFactory(name={"de": "VariantenLeerP"}, stock_quantity=0)
    ProductVariant.objects.create(product=out, label="M", stock_quantity=0)
    body = public_views.product_list(_req(params={"nur_verfuegbar": "1"})).content.decode()
    assert "HatVorratP" in body  # есть вариант в наличии → товар показан
    assert "VariantenLeerP" not in body  # все варианты распроданы → скрыт


def test_catalog_stock_toggle_hidden_when_nothing_sold_out():
    """Тумблер наличия не выводим, если ничего не распродано (untracked-каталог)."""
    ProductFactory(name={"de": "A"}, stock_quantity=None)
    ProductFactory(name={"de": "B"}, stock_quantity=7)
    body = public_views.product_list(_req()).content.decode()
    assert 'name="nur_verfuegbar"' not in body


def test_catalog_filters_hidden_by_builder_toggle():
    """Тумблер catalog_show_filters=False скрывает панель фасетов (и диету)."""
    ProductFactory(name={"de": "A"}, base_price="1.00", badge="neu", stock_quantity=0)
    ProductFactory(name={"de": "B"}, base_price="9.00")
    req = _req()
    req.tenant.site_config = {"catalog_show_filters": False}
    body = public_views.product_list(req).content.decode()
    assert 'name="preis_von"' not in body
    assert 'name="badge"' not in body
    assert 'name="nur_verfuegbar"' not in body


def test_catalog_active_facet_carried_into_sort_form():
    """Активный фасет (badge) переносится скрытым полем в форму сортировки."""
    ProductFactory(name={"de": "NeuP"}, badge="neu")
    ProductFactory(name={"de": "PlainP"})
    body = public_views.product_list(
        _req(params={"badge": "neu", "sort": "price_asc"})
    ).content.decode()
    assert '<input type="hidden" name="badge" value="neu">' in body


def test_catalog_card_shows_product_rating():
    """A1/A2: карточка каталога показывает ★ среднее + число отзывов (bulk-агрегат)."""
    from apps.reviews.models import Review

    p = ProductFactory(name={"de": "BewertetBrot"})
    Review.objects.create(
        entity_kind="product", entity_id=p.pk, rating=5, author_name="A", email="a@x.de"
    )
    Review.objects.create(
        entity_kind="product", entity_id=p.pk, rating=4, author_name="B", email="b@x.de"
    )
    body = public_views.product_list(_req()).content.decode()
    assert 'title="2 reviews"' in body and "(2)" in body  # рейтинг-строка + число отзывов
    assert "4,5" in body or "4.5" in body  # среднее (5+4)/2 (DE-локаль → запятая)


def test_catalog_card_hidden_rating_without_reviews():
    """Без опубликованных отзывов рейтинг-строка на карточке не выводится."""
    p = ProductFactory(name={"de": "OhneBewertung"})
    from apps.reviews.models import Review

    # Снятый с публикации отзыв не учитывается (как и отсутствие отзывов).
    Review.objects.create(
        entity_kind="product",
        entity_id=p.pk,
        rating=5,
        author_name="A",
        email="a@x.de",
        is_published=False,
    )
    body = public_views.product_list(_req()).content.decode()
    assert "(1)" not in body  # скрытый отзыв не даёт рейтинг


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


def test_catalog_search_q_narrows_and_carries_into_cursor():
    """UB2-2: ?q= сужает выдачу (i18n, EN-локаль тоже) и уезжает в cursor-ссылку
    «Show more»; пустой поиск — свой empty-state."""
    ProductFactory(name={"de": "Roggenbrot", "en": "Rye bread"})
    ProductFactory(name={"de": "Kuchen"})
    body = public_views.product_list(_req(params={"q": "rye"})).content.decode()
    assert "Roggenbrot" in body and "Kuchen" not in body  # найден по EN-локали
    assert "data-listing-toolbar" in body
    assert "Nothing found" in public_views.product_list(_req(params={"q": "zzz"})).content.decode()
    for i in range(25):
        ProductFactory(name={"de": f"Brot {i} Roggen"})
    body_more = public_views.product_list(_req(params={"q": "rogg"})).content.decode()
    assert "cursor=" in body_more and "q=rogg" in body_more  # q в keyset-carry


def test_catalog_origin_and_rating_facets_end_to_end():
    """UB2-3: селекты Herkunft/Rating рендерятся при данных и фильтруют выдачу."""
    from apps.reviews.models import Review

    hof = ProductFactory(name={"de": "Hofeier"}, origin="Hof Müller")
    plain = ProductFactory(name={"de": "Mehl"})
    Review.objects.create(entity_kind="product", entity_id=hof.pk, rating=5, is_published=True)
    body = public_views.product_list(_req()).content.decode()
    assert 'name="herkunft"' in body and "Hof Müller" in body
    assert 'name="bewertung"' in body  # есть отзывы → рейтинг-фасет виден
    body_o = public_views.product_list(_req(params={"herkunft": "Hof Müller"})).content.decode()
    assert "Hofeier" in body_o and "Mehl" not in body_o
    body_r = public_views.product_list(_req(params={"bewertung": "4"})).content.decode()
    assert "Hofeier" in body_r and "Mehl" not in body_r
    assert plain.pk  # (использован выше косвенно)
