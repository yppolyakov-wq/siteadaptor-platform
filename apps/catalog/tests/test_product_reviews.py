"""A1/A2: отзывы о товаре — верификация покупателя, агрегат, витрина, приём формы."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import reviews as product_reviews
from apps.catalog.tests.factories import ProductFactory
from apps.orders.models import Order, OrderItem
from apps.promotions import public_views
from apps.promotions.models import Customer
from apps.reviews.models import Review
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _buy(product, email, *, ref="O-REV001", status="confirmed"):
    """Создать заказ с товаром на email (для верификации покупателя)."""
    customer = Customer.objects.create(name="Buyer", email=email)
    order = Order.objects.create(customer=customer, reference_code=ref, status=status)
    OrderItem.objects.create(
        order=order, product=product, qty=1, unit_price="3.00", title_snapshot=str(product)
    )
    return order


def _get(path):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(name="Hofladen", address="Feldweg 1")
    return request


def _post(path, data):
    request = RequestFactory().post(path, data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(name="Hofladen", address="Feldweg 1")
    return request


# --- верификация покупателя -------------------------------------------------
def test_has_purchased_true_for_buyer():
    product = ProductFactory()
    _buy(product, "buyer@test.de")
    assert product_reviews.has_purchased(product, "Buyer@Test.de") is True  # без регистра


def test_has_purchased_false_without_order():
    product = ProductFactory()
    assert product_reviews.has_purchased(product, "nobody@test.de") is False


def test_has_purchased_false_for_cancelled_order():
    product = ProductFactory()
    _buy(product, "buyer@test.de", status="cancelled")
    assert product_reviews.has_purchased(product, "buyer@test.de") is False


def test_has_purchased_false_for_other_product():
    p1, p2 = ProductFactory(), ProductFactory()
    _buy(p1, "buyer@test.de")
    assert product_reviews.has_purchased(p2, "buyer@test.de") is False


# --- агрегат ----------------------------------------------------------------
def test_summary_averages_published_only():
    product = ProductFactory()
    kind_id = {"entity_kind": "product", "entity_id": product.pk}
    Review.objects.create(**kind_id, rating=5, author_name="A", email="a@t.de")
    Review.objects.create(**kind_id, rating=3, author_name="B", email="b@t.de")
    Review.objects.create(**kind_id, rating=1, author_name="C", email="c@t.de", is_published=False)
    s = product_reviews.summary(product)
    assert s["count"] == 2 and s["avg"] == 4.0


def test_summary_empty():
    assert product_reviews.summary(ProductFactory()) == {"avg": None, "count": 0}


# --- витрина (GET) ----------------------------------------------------------
def test_detail_renders_published_reviews_and_form():
    product = ProductFactory()
    Review.objects.create(
        entity_kind="product",
        entity_id=product.pk,
        rating=5,
        author_name="Köhler",
        email="k@t.de",
        comment="Sehr lecker",
    )
    body = public_views.product_detail(
        _get(f"/sortiment/{product.pk}/"), pk=product.pk
    ).content.decode()
    assert "Köhler" in body and "Sehr lecker" in body
    assert "bewertungen" in body  # секция-якорь
    assert "storefront-product-review" not in body  # url резолвится в href, не как имя
    assert f"/sortiment/{product.pk}/bewerten/" in body  # action формы


def test_detail_hidden_review_not_shown():
    product = ProductFactory()
    Review.objects.create(
        entity_kind="product",
        entity_id=product.pk,
        rating=2,
        author_name="Geheim",
        email="g@t.de",
        is_published=False,
    )
    body = public_views.product_detail(
        _get(f"/sortiment/{product.pk}/"), pk=product.pk
    ).content.decode()
    assert "Geheim" not in body


# --- приём формы (POST) -----------------------------------------------------
def test_submit_creates_review_for_verified_buyer():
    product = ProductFactory()
    _buy(product, "buyer@test.de")
    data = {"author_name": "Buyer", "email": "buyer@test.de", "rating": "5", "comment": "Top!"}
    resp = public_views.product_review_submit(
        _post(f"/sortiment/{product.pk}/bewerten/", data), pk=product.pk
    )
    assert resp.status_code == 302
    r = Review.objects.get(entity_kind="product", entity_id=product.pk, email="buyer@test.de")
    assert r.rating == 5 and r.author_name == "Buyer" and r.is_published and r.verified


def test_submit_rejected_for_non_buyer():
    product = ProductFactory()
    data = {"author_name": "Fake", "email": "fake@test.de", "rating": "5", "comment": "Spam"}
    resp = public_views.product_review_submit(
        _post(f"/sortiment/{product.pk}/bewerten/", data), pk=product.pk
    )
    assert resp.status_code == 302
    assert not Review.objects.filter(entity_kind="product", entity_id=product.pk).exists()


def test_submit_invalid_rating_rejected():
    product = ProductFactory()
    _buy(product, "buyer@test.de")
    data = {"author_name": "Buyer", "email": "buyer@test.de", "rating": "9"}
    public_views.product_review_submit(
        _post(f"/sortiment/{product.pk}/bewerten/", data), pk=product.pk
    )
    assert not Review.objects.filter(entity_kind="product", entity_id=product.pk).exists()


def test_submit_updates_existing_review():
    product = ProductFactory()
    _buy(product, "buyer@test.de")
    Review.objects.create(
        entity_kind="product",
        entity_id=product.pk,
        rating=3,
        author_name="Buyer",
        email="buyer@test.de",
    )
    data = {"author_name": "Buyer", "email": "buyer@test.de", "rating": "5", "comment": "Besser!"}
    public_views.product_review_submit(
        _post(f"/sortiment/{product.pk}/bewerten/", data), pk=product.pk
    )
    reviews = Review.objects.filter(
        entity_kind="product", entity_id=product.pk, email="buyer@test.de"
    )
    assert reviews.count() == 1 and reviews.first().rating == 5  # обновлён, не задвоен


# --- UA4-2 (product остаётся per-block) ------------------------------------
def test_product_detail_section_order_parity():
    """UA4-2: товар НЕ мигрируется в body-цикл — его секции реестра распределены по
    блокам (description/info в detail_aside, reviews в detail_body, related в
    detail_wide). Фиксируем порядок aside description → aside info → body reviews →
    wide related как замок раскладки (перенос в body сломал бы sticky-колонку)."""
    from apps.catalog.tests.factories import CategoryFactory

    cat = CategoryFactory()
    product = ProductFactory(
        name={"de": "ParitBrot"},
        description={"de": "Frisch gebacken im Steinofen."},
        origin="Region Allgäu",
        ingredients="Mehl, Wasser, Salz",
        category=cat,
    )
    ProductFactory(name={"de": "AnderBrot"}, category=cat)  # related: та же категория
    Review.objects.create(
        entity_kind="product", entity_id=product.pk, rating=5, author_name="K", email="k@t.de"
    )
    body = public_views.product_detail(
        _get(f"/sortiment/{product.pk}/"), pk=product.pk
    ).content.decode()
    markers = [
        'data-edit-field="description"',  # описание (aside)
        "Region Allgäu",  # LMIV-инфо (aside)
        'id="bewertungen"',  # отзывы (body) — не href="#bewertungen" из aside-рейтинга
        "More from this category",  # похожие (wide)
    ]
    positions = [body.find(m) for m in markers]
    assert all(p >= 0 for p in positions), positions
    assert positions == sorted(positions)  # порядок aside → body → wide сохранён
