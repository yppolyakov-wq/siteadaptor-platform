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
    assert "data-combo-form" not in body  # формы корзины нет
    assert "Unverbindlich anfragen" in body
    assert "/anfrage/?betreff=" in body
    assert "Dessert" in body  # состав показан и без orders


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
