"""O-9: страница со своей темой обязана называть себя в <title>.

Стенд аутлета: у всех десяти направлений и тридцати девяти полок заголовок вкладки
был один и тот же — «Unsere Produkte», у страницы группы акций — «Aktionen». Для
магазина это и SEO-дубли, и слепые вкладки: десять открытых полок неразличимы.
Движок мета (SEO-1) заготовку `category` держал, но листинг звал её как `listing`.
"""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _request(path, params=None):
    request = RequestFactory().get(path, params or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(name="Zweitgut", address="Hauptstr. 1")
    return request


def _title(html):
    start = html.index("<title>") + len("<title>")
    return html[start : html.index("</title>", start)].strip()


def test_category_page_title_names_the_category():
    cat = CategoryFactory(slug="damenmode", name={"de": "Damenmode"})
    ProductFactory(name={"de": "Kleid"}, category=cat)

    generic = _title(public_views.product_list(_request("/sortiment/")).content.decode())
    page = _title(
        public_views.product_list(
            _request("/sortiment/damenmode/"), slug="damenmode"
        ).content.decode()
    )
    assert "Damenmode" in page
    assert "Zweitgut" in page  # имя магазина остаётся
    assert page != generic  # корень каталога и направление больше не тёзки


def test_promo_group_page_title_names_the_group():
    Promotion.objects.create(
        title={"de": "Kleid −40 %"}, status="active", group="Mode-Sale", discount_percent=40
    )
    generic = _title(public_views.promotion_list(_request("/aktionen/")).content.decode())
    page = _title(
        public_views.promotion_list(
            _request("/aktionen/", {"gruppe": "Mode-Sale"})
        ).content.decode()
    )
    assert "Mode-Sale" in page
    assert "Zweitgut" in page
    assert page != generic
    # Обзор всех акций обязан остаться ПОДПИСАННЫМ. Блок, объявленный внутри
    # {% if %}, Django собирает всё равно — обзор получал «<title> — Магазин</title>»
    # с пустым первым сегментом. Здесь нет resolver_match, поэтому движок мета
    # молчит и «своим именем» законно оказывается имя магазина; ловим сам симптом —
    # заголовок, начинающийся с разделителя, то есть страницу без названия.
    assert generic.strip() and not generic.lstrip().startswith(("—", "·", "-"))
