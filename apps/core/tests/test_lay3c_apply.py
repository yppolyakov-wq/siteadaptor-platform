"""LAY-3c — лимит и размер страницы ДЕЙСТВУЮТ, а не только сохраняются.

После LAY-3b владелец может задать «сколько рядов показывать» и «сколько выводить
на странице», но вьюхи эти ключи не читали: размер страницы каталога считала
формула (20 при пяти колонках, иначе 24), а лимит секции главной — только
`limit_<ключ>`. Настройка, которая сохраняется и ничего не делает, — тот же класс
дефекта, что контрол без настройки (правило STU-9).

Замки написаны ДО правок и краснеют на текущем коде.
"""

import pytest
from django.test import RequestFactory

from apps.catalog.models import Category, Product
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(slug, layout):
    t = TenantFactory(schema_name="public", slug=slug, name=slug.upper())
    cfg = siteconfig.normalize({**(t.site_config or {}), "catalog_layout": layout})
    t.site_config = cfg
    t.save(update_fields=["site_config"])
    return t


def _products(n):
    cat = Category.objects.create(name={"de": "Alles"}, slug="alles")
    for i in range(n):
        Product.objects.create(
            name={"de": f"P{i:02d}"}, category=cat, base_price="1.00", is_active=True
        )


def _body(tenant, params=None):
    req = RequestFactory().get("/sortiment/", params or {})
    req.tenant = tenant
    return public_views.product_list(req).content.decode()


def test_catalog_page_size_comes_from_the_owner():
    """Задан `page_size` — на странице ровно столько товаров."""
    tenant = _tenant("lay3c1", {"preset": "cols3", "page_size": 6})
    _products(10)
    body = _body(tenant)
    shown = [f"P{i:02d}" for i in range(10) if f"P{i:02d}" in body]
    assert len(shown) == 6, f"на странице {len(shown)} товаров вместо 6"


def test_catalog_page_size_falls_back_to_the_old_formula():
    """Без ключа — прежнее поведение (24, а при пяти колонках 20)."""
    tenant = _tenant("lay3c2", {"preset": "cols3"})
    _products(3)
    assert "P00" in _body(tenant)
    lay = siteconfig.normalize(tenant.site_config)["catalog_layout"]
    assert "page_size" not in lay


# ── Секции главной: ряды задают лимит превью ────────────────────────────────


def test_effective_limit_prefers_the_explicit_number():
    """Generic-функция: явное число сильнее рядов (её зовут и с `limit_<ключ>`)."""
    layout = siteconfig.normalize_layout({"preset": "cols4", "rows": 2})
    assert siteconfig.effective_limit(layout, explicit=6) == 6


def test_home_section_rows_win_over_the_stored_limit():
    """У СЕКЦИИ ряды побеждают: `limit` материализуется всегда (дефолтом), и
    отличить «владелец выставил 8» от «8 по умолчанию» нечем. Правило простое:
    выставил ряды — получил ряды; не трогал — работает прежний лимит."""
    cfg = siteconfig.normalize(
        {
            "sections": [
                {"key": "products", "enabled": True, "layout": {"preset": "cols4", "rows": 2}}
            ]
        }
    )
    assert siteconfig.section_limit(cfg, "products") == 8
    cfg_plain = siteconfig.normalize(
        {"sections": [{"key": "products", "enabled": True, "limit": 5}]}
    )
    assert siteconfig.section_limit(cfg_plain, "products") == 5


def test_section_limit_falls_back_to_rows_times_columns():
    layout = siteconfig.normalize_layout({"preset": "cols4", "rows": 2})
    assert siteconfig.effective_limit(layout) == 8


def test_home_section_row_offers_the_rows_control():
    """Контрол «Рядов» есть и у секции главной — иначе ключ задать нечем.

    Имя поля НЕ `rows_<ключ>`: `rows_products` уже занят капом строк прайс-вида
    (MEN-24c), и коллизия молча перепутала бы два разных числа.
    """
    from types import SimpleNamespace

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.core import views

    tenant = TenantFactory(schema_name="public", slug="lay3c3", name="LAY3C3")
    req = RequestFactory().get("/dashboard/site/home/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    body = views.home_builder_view(req).content.decode()
    assert 'name="grid_rows_products"' in body
    assert 'name="rows_products"' in body, "кап прайс-вида не должен исчезнуть"
