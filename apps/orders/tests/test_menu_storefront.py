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


def test_included_group_never_shows_surcharge_and_pool_keeps_zero_price():
    """Ревью MEN-17: при своде плиток в общий чип потерялись два условия старой
    разметки — у included-группы надбавка не показывается (её не берут с гостя),
    а свободная сборка печатала цену ВСЕГДА, включая 0,00 €."""
    combo = Combo.objects.create(name="Menü", price=Decimal("30.00"), free_pool=False)
    inc = ComboGroup.objects.create(
        combo=combo, label="Inklusive", min_select=1, max_select=1, included=True
    )
    ComboOption.objects.create(
        group=inc, product=ProductFactory(name={"de": "Brot"}), price_delta=Decimal("2.50")
    )
    body = public_views.combo_detail_public(_req(method="get"), pk=combo.pk).content.decode()
    assert "Brot" in body and "+2,50" not in body and "+2.50" not in body

    from apps.catalog.models import Category

    cat = Category.objects.create(name={"de": "Getränke"}, slug="zc-drinks")
    ProductFactory(
        name={"de": "Leitungswasser"}, base_price=Decimal("0.00"), category=cat, course="getraenk"
    )
    pool = Combo.objects.create(
        name="Freie Wahl", price=Decimal("0.00"), free_pool=True, category=cat
    )
    body = public_views.combo_detail_public(_req(method="get"), pk=pool.pk).content.decode()
    assert "Leitungswasser" in body and "0,00" in body


def test_pool_shows_dishes_with_unknown_course():
    """Ревью MEN-17: блюдо с Gang'ом вне реестра (импорт/старые данные) молча
    выпадало из конструктора — `pool_products` считает его блюдом, а группировка
    ходила только по COURSES. Такие блюда уезжают в «Weitere»."""
    from apps.catalog.models import Category

    cat = Category.objects.create(name={"de": "Speisen"}, slug="zc-unknown")
    ProductFactory(name={"de": "Mystery-Teller"}, category=cat, course="fantasie")
    combo = Combo.objects.create(
        name="Freie Wahl", price=Decimal("0.00"), free_pool=True, category=cat
    )
    body = public_views.combo_detail_public(_req(method="get"), pk=combo.pk).content.decode()
    assert "Mystery-Teller" in body


def test_pool_courses_collapse_into_accordion():
    """MEN-19 (фидбэк «портянка при большом ассортименте»): каждый Gang —
    <details> со счётчиком, открыт только первый; ВСЕ блюда остаются в DOM
    (чекбоксы в закрытых details отправляются с формой)."""
    from apps.catalog.models import Category

    cat = Category.objects.create(name={"de": "Speisen"}, slug="ac-cat")
    for i in range(4):
        ProductFactory(name={"de": f"Vorspeise {i}"}, category=cat, course="vorspeise")
    for i in range(4):
        ProductFactory(name={"de": f"Hauptgang {i}"}, category=cat, course="hauptgang")
    combo = Combo.objects.create(
        name="Freie Wahl", price=Decimal("0.00"), free_pool=True, category=cat
    )
    body = public_views.combo_detail_public(_req(method="get"), pk=combo.pk).content.decode()
    assert body.count("data-dish-tile") == 8  # ничего не спрятано из DOM
    # гармошки Gang'ов помечены классом group/gang (в шапке есть свой details)
    gangs = body.split('class="mt-3 group/gang')[1:]
    # счётчик Gang'а — в своей span-обёртке (голый count("(4)") ловил бы
    # «★★★★ (4)» из формы отзывов MEN-21)
    assert len(gangs) == 2 and body.count('text-gray-400">(4)</span>') == 2
    # открыт ровно первый Gang: атрибут open стоит у первой гармошки и только у неё
    assert " open>" in "<details " + gangs[0].split(">", 1)[0] + ">"
    assert body.count('rounded-xl border border-gray-200" open>') == 1


# --- MEN-21: блоки под карточкой набора (отзывы/примеры/CTA/слайдер) ---------


def _buy_combo(combo, email, *, status="confirmed"):
    """Заказ с комбо-позицией (FK OrderItem.combo) — верификация покупателя."""
    from apps.orders.models import OrderItem
    from apps.promotions.models import Customer

    customer = Customer.objects.create(name="Buyer", email=email)
    order = Order.objects.create(
        customer=customer, reference_code=f"O-{uuid.uuid4().hex[:8]}", status=status
    )
    OrderItem.objects.create(
        order=order, combo=combo, qty=1, unit_price="42.00", title_snapshot=str(combo)
    )
    return order


def test_has_bought_combo_verifier():
    from apps.catalog.reviews import has_bought_combo

    combo, _g, _opt = _wedding_set()
    _buy_combo(combo, "buyer@test.de")
    assert has_bought_combo(combo, "Buyer@Test.de") is True  # без регистра
    assert has_bought_combo(combo, "nobody@test.de") is False


def test_has_bought_combo_false_for_cancelled_and_other_combo():
    combo, _g, _opt = _wedding_set()
    other = Combo.objects.create(name="Anderes Menü", price=Decimal("30.00"))
    _buy_combo(combo, "storno@test.de", status="cancelled")
    from apps.catalog.reviews import has_bought_combo

    assert has_bought_combo(combo, "storno@test.de") is False
    assert has_bought_combo(other, "buyer@test.de") is False


def test_combo_detail_renders_review_section_with_action():
    combo, _g, _opt = _wedding_set()
    from apps.reviews.models import Review

    Review.objects.create(
        entity_kind="combo", entity_id=combo.pk, rating=5, author_name="Anna B.", email="a@t.de"
    )
    body = public_views.combo_detail_public(_req(method="get"), pk=combo.pk).content.decode()
    assert 'id="bewertungen"' in body and "Anna B." in body
    assert f"/kombi/{combo.pk}/bewerten/" in body  # форма постит в новый приёмник


def test_combo_review_submit_buyer_creates_review_stranger_rejected():
    combo, _g, _opt = _wedding_set()
    _buy_combo(combo, "buyer@test.de")
    from apps.reviews.models import Review

    data = {"author_name": "Käufer", "email": "buyer@test.de", "rating": "5", "comment": "Top"}
    resp = public_views.combo_review_submit(_req(data=data), pk=combo.pk)
    assert resp.status_code == 302 and resp["Location"].endswith("#bewertungen")
    assert Review.objects.filter(entity_kind="combo", entity_id=combo.pk).count() == 1

    stranger = {"author_name": "Fremd", "email": "fremd@test.de", "rating": "4"}
    public_views.combo_review_submit(_req(data=stranger), pk=combo.pk)
    assert Review.objects.filter(entity_kind="combo", entity_id=combo.pk).count() == 1


def test_combo_detail_related_slider_same_category_only_excludes_self():
    from apps.catalog.models import Category

    cat = Category.objects.create(name={"de": "Hochzeit"}, slug="rel-hochzeit")
    other_cat = Category.objects.create(name={"de": "Business"}, slug="rel-business")
    combo = Combo.objects.create(name="Menü Klassik", price=Decimal("45.00"), category=cat)
    sibling = Combo.objects.create(name="Menü Wahl", price=Decimal("52.00"), category=cat)
    Combo.objects.create(name="Business-Lunch", price=Decimal("19.00"), category=other_cat)
    body = public_views.combo_detail_public(_req(method="get"), pk=combo.pk).content.decode()
    assert "Weitere Menüs aus dieser Kategorie" in body and "Menü Wahl" in body
    assert "Business-Lunch" not in body
    # сам набор в слайдере не дублируется: карточки-ссылки ведут только на соседей
    assert f'href="/kombi/{sibling.pk}/"' in body
    assert f'href="/kombi/{combo.pk}/"' not in body
    # без категории/сиблингов блока нет
    solo = public_views.combo_detail_public(_req(method="get"), pk=sibling.pk).content.decode()
    assert "Menü Klassik" in solo  # обратная сторона: сиблинг видит соседа
    lone = Combo.objects.create(name="Solo-Menü", price=Decimal("10.00"))
    body_lone = public_views.combo_detail_public(_req(method="get"), pk=lone.pk).content.decode()
    assert "Weitere Menüs aus dieser Kategorie" not in body_lone


def test_combo_detail_event_cta_and_gallery_examples():
    combo, _g, _opt = _wedding_set()
    tenant = _browse_only(
        site_config={"gallery": [{"url": "/media/demo/fest1.webp"}]},
    )
    body = public_views.combo_detail_public(_req(method="get", tenant=tenant), pk=combo.pk)
    body = body.content.decode()
    assert "Beispiele unserer Arbeit" in body and "/media/demo/fest1.webp" in body
    assert "Sie planen eine Veranstaltung?" in body
    # заявка — попапом (MEN-11), не страницей
    assert "/anfrage/formular/?betreff=" in body and "/anfrage/?betreff=" not in body


def test_combo_detail_blocks_gated_by_data():
    combo, _g, _opt = _wedding_set()
    tenant = TenantFactory.build(disabled_modules=["orders", "jobs"])
    body = public_views.combo_detail_public(
        _req(method="get", tenant=tenant), pk=combo.pk
    ).content.decode()
    assert "Beispiele unserer Arbeit" not in body  # галереи нет
    assert "Sie planen eine Veranstaltung?" not in body  # jobs выключен
