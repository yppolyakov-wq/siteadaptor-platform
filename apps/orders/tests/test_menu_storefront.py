"""MEN-3: витрина «наборов меню» — browse-гейт, попап блюда, per-person, предохранители.

Гейты: /kombi/ и попап блюда видны по каталогу (browse-only кейтеринг без orders);
действие «в корзину» остаётся за orders. Цены прячутся menu_show_prices (DS-7).
"""

import uuid
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.catalog.models import Combo, ComboGroup, ComboOption
from apps.catalog.tests.factories import ProductFactory
from apps.orders import public_views
from apps.orders.models import Order
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="post", data=None, session=None, tenant=None):
    request = getattr(RequestFactory(), method)("/kombi/", data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if session:
        request.session.update(session)
    request.tenant = tenant if tenant is not None else TenantFactory.build()
    return request


def _browse_only(**kw):
    """Кейтеринг-профиль: каталог виден, заказы выключены, заявки включены."""
    return TenantFactory.build(disabled_modules=["orders"], **kw)


def _wedding_set(**kw):
    combo = Combo.objects.create(name="Hochzeitsmenü", price=Decimal("42.00"), **kw)
    g = ComboGroup.objects.create(combo=combo, label="Dessert", min_select=1, max_select=1)
    opt = ComboOption.objects.create(group=g, product=ProductFactory(), price_delta=Decimal("2.50"))
    return combo, g, opt


# --- browse-гейт + anfrage-CTA ------------------------------------------------------


def test_combo_detail_visible_without_orders_with_anfrage_cta():
    """Browse-only кейтеринг ВИДИТ набор; вместо корзины — CTA заявки с префиллом."""
    combo, _g, _opt = _wedding_set()
    body = public_views.combo_detail_public(
        _req(method="get", tenant=_browse_only()), pk=combo.pk
    ).content.decode()
    assert 'action="/kombi/add/"' not in body  # формы корзины нет
    assert "Unverbindlich anfragen" in body
    # MEN-11: заявка открывается ПОПАПОМ (фрагмент формы), а не уводит на страницу
    assert "/anfrage/formular/?betreff=" in body
    assert "/anfrage/?betreff=" not in body
    assert "Dessert" in body  # состав показан и без orders
    # MEN-7 (находка стенда): выбор состава доступен и БЕЗ корзины — гость
    # собирает меню и отправляет заявку с ним (раньше контролов не было вовсе).
    assert 'name="opt-' in body and "data-anfrage-cta" in body


def test_combo_list_visible_without_orders():
    """/kombi/ отдаётся browse-only тенанту (каталог — core, всегда активен)."""
    combo, _g, _opt = _wedding_set()
    body = public_views.combo_list_public(
        _req(method="get", tenant=_browse_only())
    ).content.decode()
    assert "Hochzeitsmenü" in body


def test_combo_add_still_requires_orders():
    """Действие «в корзину» остаётся за orders — видимость каталога его не открывает."""
    combo, _g, opt = _wedding_set()
    add = _req(data={"combo": str(combo.pk), "opt": [str(opt.pk)]}, tenant=_browse_only())
    with pytest.raises(Http404):
        public_views.combo_add(add)


# --- попап блюда -------------------------------------------------------------------


def test_dish_info_popup_renders_markup():
    product = ProductFactory(
        name={"de": "Rinderfilet"},
        description={"de": "Rosa gebraten"},
        allergens=["gluten"],
        diets=["glutenfrei"],
    )
    body = public_views.dish_info(
        _req(method="get", tenant=_browse_only()), pk=product.pk
    ).content.decode()
    assert "Rinderfilet" in body and "Rosa gebraten" in body
    assert "data-quick-close" in body  # закрывается generic-модалкой
    assert "data-dish-info" in body


def test_dish_info_404_for_inactive_product():
    product = ProductFactory(is_active=False)
    with pytest.raises(Http404):
        public_views.dish_info(_req(method="get"), pk=product.pk)


def test_dish_tiles_and_popup_urls_in_detail():
    combo, _g, opt = _wedding_set()
    body = public_views.combo_detail_public(_req(method="get"), pk=combo.pk).content.decode()
    assert "data-dish-tile" in body
    assert f"/gericht/{opt.product.pk}/info/" in body


def test_dish_popup_shows_thumbstrip_only_for_multiple_photos():
    """MEN-17: у блюда с несколькими фото — лента миниатюр; с одним фото её нет
    (лишняя строка под картинкой). Подмена главного фото — делегированный
    обработчик в _base.html: <script> внутри innerHTML не исполняется."""
    one = ProductFactory(images=[{"id": "a", "url": "/media/a.jpg", "is_primary": True}])
    body = public_views.dish_info(_req(method="get"), pk=one.pk).content.decode()
    assert "data-dish-photo" in body and "data-dish-thumb" not in body

    many = ProductFactory(
        images=[
            {"id": "a", "url": "/media/a.jpg", "is_primary": True},
            {"id": "b", "url": "/media/b.jpg"},
        ]
    )
    body = public_views.dish_info(_req(method="get"), pk=many.pk).content.decode()
    assert body.count("data-dish-thumb") == 2
    assert 'data-dish-thumb="/media/b.jpg"' in body


def test_long_group_hides_tail_behind_details():
    """MEN-17 (фидбэк «портянка при большом количестве блюд»): первые 12 блюд
    видны, остальные — в <details>, но ВСЕ остаются в DOM (выбор возможен)."""
    combo = Combo.objects.create(name="Große Auswahl", price=Decimal("30.00"))
    group = ComboGroup.objects.create(combo=combo, label="Hauptgang", min_select=1, max_select=1)
    for i in range(15):
        ComboOption.objects.create(group=group, product=ProductFactory(name={"de": f"Gericht {i}"}))
    body = public_views.combo_detail_public(_req(method="get"), pk=combo.pk).content.decode()
    assert body.count("data-dish-tile") == 15  # ничего не потеряно
    assert "<details" in body and "Weitere 3" in body


# --- per-person + минимум персон ---------------------------------------------------


def test_per_person_detail_renders_min_and_label():
    combo, _g, _opt = _wedding_set(price_per_person=True, min_persons=20)
    body = public_views.combo_detail_public(_req(method="get"), pk=combo.pk).content.decode()
    assert 'min="20"' in body and 'value="20"' in body
    assert "Personen" in body
    assert "/ Person" in body or "Person</span>" in body


def test_combo_add_enforces_min_persons_and_raised_cap():
    combo, _g, opt = _wedding_set(price_per_person=True, min_persons=20)
    # ниже минимума → отказ, корзина пуста
    low = _req(data={"combo": str(combo.pk), "opt": [str(opt.pk)], "qty": "10"})
    public_views.combo_add(low)
    assert low.session.get("combo_cart", {}) == {}
    # 80 гостей > легаси-кап 50 — per-person кап поднят
    ok = _req(data={"combo": str(combo.pk), "opt": [str(opt.pk)], "qty": "80"})
    public_views.combo_add(ok)
    assert list(ok.session["combo_cart"].values()) == [80]


def test_checkout_revalidates_dead_option_and_min_persons():
    """Предохранитель плана §2: опция умерла после add → чекаут НЕ молчит
    (раньше options_from_ids тихо выкидывал её и заказ уходил дешевле)."""
    combo, _g, opt = _wedding_set()
    add = _req(data={"combo": str(combo.pk), "opt": [str(opt.pk)], "qty": "1"})
    public_views.combo_add(add)
    cc = add.session["combo_cart"]
    opt.is_active = False
    opt.save(update_fields=["is_active"])
    public_views.checkout(_req(data={"name": "K"}, session={"combo_cart": cc}))
    assert Order.objects.count() == 0

    # минимум персон проверяется и на чекауте (сессию можно накрутить)
    combo2, _g2, opt2 = _wedding_set(price_per_person=True, min_persons=20)
    cc2 = {f"{combo2.pk}|{opt2.pk}": 5}
    public_views.checkout(_req(data={"name": "K"}, session={"combo_cart": cc2}))
    assert Order.objects.count() == 0


# --- menu_show_prices (DS-7) -------------------------------------------------------


def test_browse_only_hides_prices_when_menu_show_prices_false():
    combo, _g, _opt = _wedding_set()
    tenant = _browse_only(site_config={"menu_show_prices": False})
    body = public_views.combo_detail_public(
        _req(method="get", tenant=tenant), pk=combo.pk
    ).content.decode()
    assert "44,50" not in body and "2,50" not in body  # цены скрыты целиком
    # а с дефолтом (ключа нет) browse-only цены показывает: «ab»-цена =
    # 42,00 + минимальная обязательная надбавка 2,50
    body2 = public_views.combo_detail_public(
        _req(method="get", tenant=_browse_only()), pk=combo.pk
    ).content.decode()
    assert "44,50" in body2


# --- MEN-4: свободная сборка (free_pool) -------------------------------------------


def _pool_setup():
    from apps.catalog.models import Category

    cat = Category.objects.create(name={"de": "Hochzeit"}, slug="men4-hochzeit")
    soup = ProductFactory(
        name={"de": "Kürbissuppe"}, base_price=Decimal("6.50"), category=cat, course="suppe"
    )
    main = ProductFactory(
        name={"de": "Rinderfilet"}, base_price=Decimal("18.00"), category=cat, course="hauptgang"
    )
    combo = Combo.objects.create(
        name="Freie Auswahl",
        price=Decimal("0.00"),
        free_pool=True,
        category=cat,
        price_per_person=True,
    )
    return combo, cat, soup, main


def test_free_pool_detail_grouped_by_course():
    combo, _cat, _soup, _main = _pool_setup()
    body = public_views.combo_detail_public(_req(method="get"), pk=combo.pk).content.decode()
    assert 'name="dish"' in body
    assert "Suppe" in body and "Hauptgericht" in body  # заголовки Gang'ов
    i_soup, i_main = body.find("Kürbissuppe"), body.find("Rinderfilet")
    assert 0 < i_soup < i_main  # порядок реестра COURSES
    assert 'data-delta="6.50"' in body and 'data-delta="18.00"' in body


def test_free_pool_add_validates_and_checkout_prices_server_side():
    combo, _cat, soup, main = _pool_setup()
    foreign = ProductFactory()  # блюдо ЧУЖОЙ категории — строгий отказ, не молчаливый дроп
    bad = _req(data={"combo": str(combo.pk), "dish": [str(foreign.pk)], "qty": "1"})
    public_views.combo_add(bad)
    assert bad.session.get("combo_cart", {}) == {}

    ok = _req(data={"combo": str(combo.pk), "dish": [str(soup.pk), str(main.pk)], "qty": "20"})
    public_views.combo_add(ok)
    cc = ok.session["combo_cart"]
    key = f"{combo.pk}|d:" + ",".join(sorted([str(soup.pk), str(main.pk)]))
    assert cc == {key: 20}

    public_views.checkout(_req(data={"name": "K"}, session={"combo_cart": cc}))
    order = Order.objects.get()
    item = order.items.get()
    assert item.unit_price == Decimal("24.50")  # 6,50 + 18,00 + базовая 0
    assert item.qty == 20 and order.total == Decimal("490.00")
    assert item.combo_id is None and item.product_id is None  # custom line
    assert len(item.modifiers) == 2  # снимок состава (блюдо + цена)


def test_free_pool_dead_dish_blocks_checkout():
    combo, _cat, soup, _main = _pool_setup()
    add = _req(data={"combo": str(combo.pk), "dish": [str(soup.pk)], "qty": "1"})
    public_views.combo_add(add)
    cc = add.session["combo_cart"]
    soup.is_active = False
    soup.save(update_fields=["is_active"])
    public_views.checkout(_req(data={"name": "K"}, session={"combo_cart": cc}))
    assert Order.objects.count() == 0


def test_cart_shows_pool_row_with_labels():
    combo, _cat, soup, main = _pool_setup()
    add = _req(data={"combo": str(combo.pk), "dish": [str(soup.pk), str(main.pk)], "qty": "20"})
    public_views.combo_add(add)
    body = public_views.cart_view(
        _req(method="get", session={"combo_cart": add.session["combo_cart"]})
    ).content.decode()
    assert "Freie Auswahl" in body and "Kürbissuppe" in body


def test_landing_shows_menu_sets_block():
    """MEN-4: лендинг направления (DS-7) — блок «Menü-Pakete» с бейджем минимума."""
    from apps.catalog.models import Category
    from apps.promotions import public_views as promo_views

    cat = Category.objects.create(
        name={"de": "Hochzeit"}, slug="men4-landing", description={"de": "Feiern mit Stil"}
    )
    Combo.objects.create(
        name="Hochzeitsmenü Klassik",
        price=Decimal("42.00"),
        category=cat,
        price_per_person=True,
        min_persons=20,
    )
    req = _req(method="get", tenant=TenantFactory.build(site_config={"category_landings": True}))
    body = promo_views.category_landing(req, slug="men4-landing").content.decode()
    assert "Menü-Pakete" in body and "Hochzeitsmenü Klassik" in body
    assert "ab 20 Personen" in body


def test_browse_only_pick_controls_and_person_field():
    """MEN-7: у browse-only набора есть контролы выбора, поле персон с минимумом
    и CTA-заявка; POST-форма корзины при этом не рендерится."""
    combo, g, opt = _wedding_set(price_per_person=True, min_persons=20)
    body = public_views.combo_detail_public(
        _req(method="get", tenant=_browse_only()), pk=combo.pk
    ).content.decode()
    assert f'name="opt-{g.pk}"' in body
    assert f'data-delta="{opt.price_delta}"' in body
    assert 'name="qty"' in body and 'min="20"' in body
    assert "<form" not in body.split("data-combo-form")[1].split("</div>")[0]
