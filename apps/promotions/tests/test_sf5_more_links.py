"""SF-5 (фидбэк владельца 2026-09-03): «Alle anzeigen» — только когда за ссылкой
реально больше, чем показано.

Владелец: «зачем кнопка показать все, если их всего 3 или 4. Кнопка появляется,
если их больше, чем показывается на экране». Три поверхности со ссылкой в шапке:
полка каталога (Regale, обрезка на 8), секция группы акций на /aktionen/ и лента
«Weitere Aktionen» на детали акции.
"""

from __future__ import annotations

from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory

from apps.catalog.models import Category
from apps.catalog.tests.factories import ProductFactory
from apps.promotions import public_views
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ALLE = "Alle anzeigen"


def _request(path):
    request = RequestFactory().get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    return request


def _catalog(tenant, slug=None, path="/sortiment/"):
    request = _request(path)
    request.tenant = tenant
    return public_views.product_list(request, slug=slug).content.decode()


def _shelf_tree(n_products):
    parent = Category.objects.create(
        name={"de": "Catering"}, slug="catering", is_active=True, page_style="regale"
    )
    sub = Category.objects.create(
        name={"de": "Suppen"}, slug="suppen", is_active=True, parent=parent
    )
    for k in range(n_products):
        ProductFactory(name={"de": f"Suppe {k}"}, category=sub, base_price="4.90")
    return parent, sub


def test_shelf_link_hidden_when_shelf_shows_everything():
    tenant = TenantFactory(schema_name="public", slug="sf5a", name="A", disabled_modules=[])
    _shelf_tree(3)
    html = _catalog(tenant, slug="catering", path="/sortiment/catering/")
    assert 'data-shelf="suppen"' in html, "полка должна рендериться"
    assert ALLE not in html, "3 товара из 3 — ссылка ведёт в тот же набор"


def test_shelf_link_shown_when_shelf_is_truncated():
    tenant = TenantFactory(schema_name="public", slug="sf5b", name="B", disabled_modules=[])
    _shelf_tree(11)  # полка режется на 8
    html = _catalog(tenant, slug="catering", path="/sortiment/catering/")
    assert 'data-shelf="suppen"' in html and ALLE in html


def test_promo_group_section_has_no_dead_link():
    """Секции строятся по НЕотфильтрованной выдаче — группа показана целиком,
    ссылка вела бы в тот же набор. Вход на страницу группы остаётся чипами."""
    # ссылка в шапке секции живёт только у раскладки «лента» (A3) — её и проверяем
    tenant = TenantFactory(
        schema_name="public",
        slug="sf5c",
        name="C",
        disabled_modules=[],
        site_config={"promo_layout": "slider"},
    )
    for i in range(3):
        PromotionFactory(title={"de": f"Deal {i}"}, status="active", group="Wochenangebote")
    request = _request("/aktionen/")
    request.tenant = tenant
    html = public_views.promotion_list(request).content.decode()
    assert "Wochenangebote" in html
    assert 'href="?gruppe=' not in html, "мёртвая ссылка секции"
    assert "?gruppe=Wochenangebote" in html, "чип группы — единственный вход на её страницу"


def test_promo_detail_related_link_follows_the_data():
    tenant = TenantFactory(schema_name="public", slug="sf5d", name="D", disabled_modules=[])
    promo = PromotionFactory(title={"de": "Haupt"}, status="active")
    for i in range(3):
        PromotionFactory(title={"de": f"Andere {i}"}, status="active")
    request = _request(f"/p/{promo.pk}/")
    request.tenant = tenant
    form = public_views.PublicReservationForm()
    ctx = public_views._detail_ctx(request, promo, form)
    assert len(ctx["related_promos"]) == 3 and ctx["related_more"] is False
    for i in range(7):  # 3 + 7 = 10 > 8 в ленте
        PromotionFactory(title={"de": f"Mehr {i}"}, status="active")
    ctx = public_views._detail_ctx(request, promo, form)
    assert len(ctx["related_promos"]) == 8 and ctx["related_more"] is True
