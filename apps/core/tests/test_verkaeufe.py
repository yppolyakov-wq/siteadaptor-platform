"""Единая страница продаж /dashboard/verkaeufe/ (2026-08-03).

Решения владельца: вкладки по kind (primary всегда, прочие при наличии продаж),
виды Kalender/Board/Liste per-kind с persist'ом, classic_ui — прежнее поведение.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from apps.core import sales_page, views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(path="/dashboard/verkaeufe/", data=None, method="get", **tenant_kw):
    import uuid

    request = getattr(RequestFactory(), method)(path, data or {})
    request.user = get_user_model().objects.create_user(
        username=f"v-{uuid.uuid4().hex[:10]}", password="pw12345678"
    )
    request.session = {}
    request._messages = FallbackStorage(request)
    request.tenant = TenantFactory.build(**tenant_kw)
    return request


def _hotel(**kw):
    # disabled_modules=[] включил бы ВСЕ модули реестра (fail-open) — у отеля
    # primary стал бы events. Берём честный стартовый набор архетипа.
    from apps.core.modules import default_disabled_for

    return dict(
        business_type="hotel",
        disabled_modules=list(default_disabled_for("hotel")),
        **kw,
    )


def test_hotel_first_tab_is_stay_and_default_view_is_kalender():
    """Требование владельца: у отеля первым — календарь броней номеров, всегда."""
    body = views.verkaeufe(_req(**_hotel())).content.decode()
    assert "data-sales-tabs" in body
    assert "belegungsplan" in body  # таблица шахматки отрендерена
    assert "Übernachtungen" in body


def test_secondary_tab_hidden_without_sales_and_appears_with_first_sale():
    """«Показывать раздел, только если есть продажи»: booking-вкладка отеля
    прячется, пока нет ни одной записи, и появляется с первой."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.booking.models import Booking, Customer, Resource

    body = views.verkaeufe(_req(**_hotel())).content.decode()
    assert "?tab=booking" not in body  # продаж услуг нет — вкладки нет

    start = timezone.now() + timedelta(days=1)
    Booking.objects.create(
        resource=Resource.objects.create(name="Spa"),
        start=start,
        end=start + timedelta(hours=1),
        customer=Customer.objects.create(name="Gast", email="g@t.de"),
    )
    body = views.verkaeufe(_req(**_hotel())).content.decode()
    assert "?tab=booking" in body


def test_primary_tab_visible_even_with_zero_sales():
    """Primary-kind виден ВСЕГДА (пустой Belegungsplan — с CTA, не пропажа)."""
    body = views.verkaeufe(_req(**_hotel())).content.decode()
    assert "Übernachtungen" in body


def test_view_switch_persists_choice_per_kind():
    """POST на verkaeufe-view пишет sales_views[kind]; следующий заход
    открывает сохранённый вид без ?view=."""
    from apps.core.modules import default_disabled_for
    from apps.tenants.tests.factories import TenantFactory as TF

    tenant = TF(business_type="hotel", disabled_modules=list(default_disabled_for("hotel")))
    req = _req(method="post", data={"kind": "stay", "view": "board"})
    req.tenant = tenant
    resp = views.verkaeufe_view_set(req)
    assert resp.status_code == 302
    assert tenant.site_config["sales_views"] == {"stay": "board"}
    # мусорный вид молча игнорируется
    req2 = _req(method="post", data={"kind": "stay", "view": "hackerman"})
    req2.tenant = tenant
    views.verkaeufe_view_set(req2)
    assert tenant.site_config["sales_views"] == {"stay": "board"}


def test_saved_view_resolves_and_bad_saved_value_falls_back():
    tenant = TenantFactory.build(
        business_type="hotel", site_config={"sales_views": {"stay": "liste"}}
    )
    assert sales_page.resolve_view(tenant, "stay") == "liste"
    tenant.site_config = {"sales_views": {"stay": "kaputt"}}
    assert sales_page.resolve_view(tenant, "stay") == "kalender"  # архетипный дефолт


def test_classic_ui_redirects_to_legacy_entry():
    """Страховка редизайна: classic живёт на прежних страницах (правило ST)."""
    req = _req(**_hotel(site_config={"classic_ui": True}))
    resp = views.verkaeufe(req)
    assert resp.status_code == 302
    assert "/dashboard/stays/" in resp["Location"]


def test_normalize_sales_views_is_presence_minimal():
    from apps.tenants import siteconfig

    assert siteconfig.normalize_sales_views(None) == {}
    assert siteconfig.normalize_sales_views({"stay": "kaputt", "x": "board"}) == {}
    assert siteconfig.normalize_sales_views({"stay": "board"}) == {"stay": "board"}
    # normalize целиком: ключ не материализуется пустым
    cfg = siteconfig.normalize({})
    assert "sales_views" not in cfg


def test_reservation_never_a_secondary_tab():
    """Решение владельца §4.4: резервы живут в Marketing — вкладкой не
    становятся даже при наличии продаж (у не-promotions-primary тенанта).
    Проверяем на реестре: visible_kinds фильтрует reservation до запросов."""
    from apps.promotions.models import Reservation
    from apps.promotions.tests.factories import CustomerFactory, PromotionFactory

    Reservation.objects.create(promotion=PromotionFactory(), customer=CustomerFactory(), quantity=1)
    from apps.core.modules import default_disabled_for

    tenant = TenantFactory.build(
        business_type="bakery", disabled_modules=list(default_disabled_for("bakery"))
    )
    assert "reservation" not in sales_page.visible_kinds(tenant)
