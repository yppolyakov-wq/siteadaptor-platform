"""KA-12 E10 (Волна 5): замки скорости — число запросов не растёт с числом строк.

План — `docs/ka-12-w5-e10-speed-plan-2026-10-26.md`. Каждый замок сравнивает N и 3N
строк: разница в запросах обязана быть нулевой. Плюс паритет — предзагрузка не меняет
ни одного значения, которое карточка показывает.
"""

import itertools
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.catalog.models import (
    Combo,
    ComboGroup,
    ComboOption,
    ModifierGroup,
    ModifierOption,
    Product,
    ProductVariant,
)
from apps.catalog.prefetch import prefetch_cards
from apps.catalog.tests.factories import ProductFactory
from apps.core import roles
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_N = itertools.count()


def _queries(fn):
    with CaptureQueriesContext(connection) as ctx:
        fn()
    return len(ctx.captured_queries)


def _rich_product():
    p = ProductFactory(base_price=Decimal("5.00"))
    ProductVariant.objects.create(product=p, label=f"S{next(_N)}", price=Decimal("4.00"))
    ProductVariant.objects.create(
        product=p, label=f"L{next(_N)}", price=Decimal("6.00"), stock_quantity=0
    )
    ProductVariant.objects.create(product=p, label=f"X{next(_N)}", is_active=False)
    g = ModifierGroup.objects.create(product=p, name="Extras")
    ModifierOption.objects.create(group=g, label="Käse", price_delta=Decimal("1.00"))
    ModifierOption.objects.create(group=g, label="Aus", is_active=False)
    ModifierGroup.objects.create(product=p, name="Leer", is_active=False)
    return p


def _card_values(p):
    return (
        p.has_variants,
        p.price_from,
        p.in_stock,
        p.has_modifiers,
        [v.pk for v in p.active_variants],
        [[o.pk for o in g.active_options] for g in p.modifier_groups_active],
    )


# --- предзагрузка карточки ------------------------------------------------------------


def test_prefetched_card_values_equal_unprefetched():
    """Паритет: всё, что читает карточка, совпадает с предзагрузкой и без неё."""
    _rich_product()
    ProductFactory(base_price=Decimal("3.00"))  # товар без вариантов и опций
    plain = {p.pk: _card_values(p) for p in Product.objects.all()}
    loaded = prefetch_cards(list(Product.objects.all()))
    assert {p.pk: _card_values(p) for p in loaded} == plain


def test_prefetched_card_reads_without_queries():
    products = prefetch_cards([_rich_product(), _rich_product()])
    products = prefetch_cards(Product.objects.filter(pk__in=[p.pk for p in products]))
    assert _queries(lambda: [_card_values(p) for p in products]) == 0


def test_prefetch_query_count_does_not_grow_with_products():
    for _ in range(2):
        _rich_product()
    few = _queries(lambda: prefetch_cards(list(Product.objects.all())))
    for _ in range(4):
        _rich_product()
    many = _queries(lambda: prefetch_cards(list(Product.objects.all())))
    assert few == many


def test_attach_promos_prefetches_cards():
    """Карточные поверхности витрины готовят товары через `attach_promos` — после него
    свойства карточки читаются без запросов."""
    from apps.promotions.price_layer import attach_promos

    for _ in range(3):
        _rich_product()
    products = attach_promos(Product.objects.all())
    assert _queries(lambda: [_card_values(p) for p in products]) == 0


# --- кабинет: «Sortiment» ----------------------------------------------------------------


def _combo():
    combo = Combo.objects.create(name=f"Menü {next(_N)}", price=Decimal("9.90"))
    g = ComboGroup.objects.create(combo=combo, label="Getränk", min_select=1, max_select=1)
    ComboOption.objects.create(group=g, product=ProductFactory(), price_delta=Decimal("1.00"))
    ComboOption.objects.create(group=g, product=ProductFactory(), price_delta=0)
    return combo


def test_sellable_manage_queries_do_not_grow_with_rows():
    from apps.core.sellable_manage import sellable_manage_sections_for

    tenant = TenantFactory(slug=f"e10s{next(_N)}", name="E10")
    for _ in range(2):
        _rich_product()
        _combo()
    sellable_manage_sections_for(tenant)  # прогрев
    few = _queries(lambda: sellable_manage_sections_for(tenant))
    for _ in range(4):
        _rich_product()
        _combo()
    many = _queries(lambda: sellable_manage_sections_for(tenant))
    assert few == many


# --- общий контекст: сайдбар и членство -------------------------------------------------


def test_anonymous_storefront_request_builds_no_sidebar():
    """Посетитель витрины кабинета не видит — сайдбар (реестр, подписи настроек с
    запросами к команде) для него не строится."""
    from apps.core.context import modules_nav

    tenant = TenantFactory(slug=f"e10a{next(_N)}", name="E10")
    req = RequestFactory().get("/")
    req.tenant = tenant
    req.user = AnonymousUser()
    with CaptureQueriesContext(connection) as ctx:
        nav = modules_nav(req)
    assert nav["nav_compact"] == []
    assert not any("core_membership" in q["sql"] for q in ctx.captured_queries)


def test_membership_is_read_once_per_request_object():
    user = get_user_model().objects.create_user(username=f"e10u{next(_N)}", password="pw")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    assert _queries(lambda: roles.role_of(user)) == 1
    assert _queries(lambda: (roles.role_of(user), roles.has_cabinet_access(user))) == 0


def test_membership_memo_follows_saves():
    """Мемо не переживает изменение членства — ни создание, ни смену роли, ни удаление."""
    user = get_user_model().objects.create_user(username=f"e10m{next(_N)}", password="pw")
    assert roles.has_cabinet_access(user) is False
    m = Membership.objects.create(user=user, role=Membership.ROLE_STAFF)
    assert roles.role_of(user) == Membership.ROLE_STAFF
    m.role = Membership.ROLE_ADMIN
    m.save()
    assert roles.role_of(user) == Membership.ROLE_ADMIN
    m.delete()
    assert roles.has_cabinet_access(user) is False


# --- «Offene Posten» и список событий ----------------------------------------------------


def test_open_items_queries_do_not_grow_with_rows():
    from apps.crm.models import Customer
    from apps.finance.bank import open_items
    from apps.orders.models import Order

    tenant = TenantFactory(slug=f"e10o{next(_N)}", name="E10")

    def _orders(n):
        for _ in range(n):
            c = Customer.objects.create(name=f"K{next(_N)}", email=f"k{next(_N)}@test.de")
            Order.objects.create(
                customer=c,
                reference_code=f"E10{next(_N):05d}",
                total=Decimal("12.00"),
                payment_method="vorkasse",
                payment_state="unpaid",
            )

    _orders(2)
    open_items(tenant)  # прогрев кэшей реестра статусов
    few = _queries(lambda: open_items(tenant))
    _orders(4)
    many = _queries(lambda: open_items(tenant))
    assert few == many
    assert len(open_items(tenant)) >= 6


def test_event_list_counts_seats_in_one_query():
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.events import services, views
    from apps.events.models import Event

    tenant = TenantFactory(slug=f"e10e{next(_N)}", name="E10")
    user = get_user_model().objects.create_user(username=f"e10o{next(_N)}", password="pw")

    def _events(n):
        for _ in range(n):
            e = Event.objects.create(
                title=f"E{next(_N)}",
                starts_at=timezone.now() + timedelta(days=3),
                status=Event.STATUS_PUBLISHED,
                capacity=20,
                price_cents=1000,
            )
            services.book_ticket(e, name="A", email=f"a{next(_N)}@test.de", auto_confirm=True)

    def _render():
        req = RequestFactory().get("/dashboard/events/")
        SessionMiddleware(lambda r: None).process_request(req)
        MessageMiddleware(lambda r: None).process_request(req)
        req.user = user
        req.tenant = tenant
        return views.event_list.__wrapped__(req)

    _events(2)
    _render()  # прогрев: реестр статусов/шаблоны кэшируются на первом рендере
    few = _queries(_render)
    _events(4)
    many = _queries(_render)
    assert few == many
    assert b"1/20" in _render().content
