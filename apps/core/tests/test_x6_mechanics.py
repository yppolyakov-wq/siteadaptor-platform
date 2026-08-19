"""X6 (план cabinet-cleanup §6.A6): консистентные механики кабинета.

- «＋» ведёт в ФОРМУ создания (у услуги/номера форма живёт на списке → ?neu=1);
- поиск есть и в «Sortiment» (по всем kind), и в generic-Liste продаж (все kind);
- черновик акции честно помечен и активируется первичной кнопкой;
- порядок видов одинаков на всех вкладках (Kalender · Board · Liste).
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.core import sales_page, sellable_manage
from apps.core.modules import default_disabled_for
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(business_type="friseur", enable=()):
    off = [m for m in default_disabled_for(business_type) if m not in enable]
    return TenantFactory(
        slug=f"x6-{business_type[:8]}-{uuid4().hex[:4]}",
        name="X6",
        business_type=business_type,
        disabled_modules=off,
    )


def _user():
    return get_user_model().objects.create_user(
        username=f"x6-{uuid4().hex[:8]}", email=f"x6-{uuid4().hex[:8]}@t.de", password="pw12345678"
    )


# --- X6-1: конвенция «＋» -----------------------------------------------------


def test_plus_targets_open_create_form():
    """У услуги/номера своей страницы создания нет — форма на списке, поэтому
    «＋» обязан вести туда с ?neu=1 (иначе владелец попадал в список и искал
    форму глазами)."""
    urls = {o["kind"]: o["url"] for o in sellable_manage.add_options(_tenant("hotel"))}
    assert urls["stay"].endswith("?neu=1#neu")
    urls = {o["kind"]: o["url"] for o in sellable_manage.add_options(_tenant("friseur"))}
    assert urls["service"].endswith("?neu=1#neu")
    # у товара своя страница создания — суффикс не нужен
    assert "?" not in urls["product"]


def test_services_list_opens_form_on_neu():
    from apps.booking import views as bviews

    t = _tenant("friseur")
    req = RequestFactory().get("/dashboard/booking/leistungen/", {"neu": "1"})
    req.tenant, req.user = t, _user()
    html = bviews.services_view(req).content.decode()
    assert 'id="neu"' in html
    assert 'value="create"' in html  # форма создания в DOM


# --- X6-2: поиск --------------------------------------------------------------


def test_sortiment_search_filters_across_kinds():
    from apps.booking.models import Service
    from apps.catalog.tests.factories import ProductFactory

    t = _tenant("friseur")
    ProductFactory(name={"de": "Shampoo Basic"})
    Service.objects.create(name="Haarschnitt Herren", duration_minutes=30)
    Service.objects.create(name="Föhnen", duration_minutes=15)

    found = sellable_manage.sellable_manage_sections_for(t, q="haarschnitt")
    names = [i.name for s in found for i in s["items"]]
    assert names == ["Haarschnitt Herren"]
    # поиск идёт по ВСЕМ kind сразу (товар находится тем же полем ввода)
    found = sellable_manage.sellable_manage_sections_for(t, q="shampoo")
    assert [i.name for s in found for i in s["items"]] == ["Shampoo Basic"]
    # пустой запрос = прежний обзор
    assert len(sellable_manage.sellable_manage_sections_for(t, q="")) >= 1


def test_generic_liste_search_by_code_and_customer():
    """Поиск в списке продаж был только у заказов (W10-3)."""
    from apps.core import transactions

    t = _tenant("friseur")
    from apps.booking.models import Booking, Resource, Service
    from apps.crm.models import Customer

    svc = Service.objects.create(name="Haarschnitt", duration_minutes=30)
    res = Resource.objects.create(name="Stuhl 1")
    c1 = Customer.objects.create(name="Frau Müller", email="mueller@t.de")
    c2 = Customer.objects.create(name="Herr Schmidt", email="schmidt@t.de")
    from django.utils import timezone

    now = timezone.now()
    Booking.objects.create(
        service=svc, resource=res, customer=c1, start=now, end=now, reference_code="B-MUE1"
    )
    Booking.objects.create(
        service=svc, resource=res, customer=c2, start=now, end=now, reference_code="B-SCH2"
    )

    sec = transactions.manage_sections_for(t, only="booking", q="müller")[0]
    assert [str(tx.customer) for tx in sec["transactions"]] == ["Frau Müller"]
    sec = transactions.manage_sections_for(t, only="booking", q="schmidt@t.de")[0]
    assert len(sec["transactions"]) == 1
    # и по коду сделки
    sec = transactions.manage_sections_for(t, only="booking", q="B-MUE1")[0]
    assert len(sec["transactions"]) == 1
    # без q — обе сделки
    sec = transactions.manage_sections_for(t, only="booking")[0]
    assert len(sec["transactions"]) == 2


# --- X6-3: ловушка черновика --------------------------------------------------


def test_promotion_draft_is_marked_and_activation_is_primary():
    from apps.promotions import views as pviews
    from apps.promotions.models import Promotion

    t = _tenant("friseur")
    promo = Promotion.objects.create(title="Sommer", promo_type="discount")
    assert promo.status == "draft"
    req = RequestFactory().get(f"/promotions/{promo.pk}/")
    req.tenant, req.user = t, _user()
    html = pviews.promotion_edit(req, promo.pk).content.decode()
    assert "Entwurf" in html  # не сырой код «draft»
    assert "Kunden sehen diese Aktion noch nicht." in html
    assert "Jetzt aktivieren" in html
    # первичная кнопка — именно активация
    idx = html.index("Jetzt aktivieren")
    assert "bg-indigo-600" in html[max(0, idx - 400) : idx]


# --- X6-5: порядок видов ------------------------------------------------------


def test_view_order_is_identical_across_kinds():
    order = ["kalender", "board", "liste"]
    for kind, views in sales_page.KIND_VIEWS.items():
        assert list(views) == [v for v in order if v in views], kind
