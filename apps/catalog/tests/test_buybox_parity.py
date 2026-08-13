"""UA3-1 слайс 2 (шаг 0): характеризационные замки buy-box товара ДО свода на единый
`_buybox.html` — action/точный набор полей/якорь/sold-out (план
docs/ua3-1-buybox-plan-2026-07-02.md §4). Написаны на ТЕКУЩЕМ коде — свод обязан
оставить их зелёными байт-в-байт."""

import re
from urllib.parse import quote

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.models import ModifierGroup, ModifierOption, ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def form_block(body, action_attr):
    """Единственный <form>…</form> с этим action= в открывающем теге."""
    forms = re.findall(r"<form[^>]*>.*?</form>", body, flags=re.S)
    hits = [f for f in forms if action_attr in f[: f.index(">")]]
    assert len(hits) == 1, f"{len(hits)} forms with {action_attr}"
    return hits[0]


def field_names(form_html):
    """Точный набор name= полей формы (input/select/textarea, включая hidden)."""
    return set(re.findall(r'name="([^"]+)"', form_html))


def _detail(product, tenant=None):
    request = RequestFactory().get(f"/sortiment/{product.pk}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant or TenantFactory.build()  # orders активен по умолчанию
    return public_views.product_detail(request, pk=product.pk).content.decode()


def test_cart_form_simple_product_exact_fields():
    p = ProductFactory()
    body = _detail(p)
    assert 'id="kaufen"' in body  # якорь buy-box (цель buybar)
    form = form_block(body, 'action="/warenkorb/add/"')
    assert field_names(form) == {"csrfmiddlewaretoken", "product", "qty"}
    assert f'name="product" value="{p.pk}"' in form  # hidden pk


def test_cart_form_variants_and_modifiers_fields():
    p = ProductFactory()
    ProductVariant.objects.create(product=p, label="Groß", price="4.50")
    g = ModifierGroup.objects.create(product=p, name="Extras", min_select=0, max_select=0)
    ModifierOption.objects.create(group=g, label="Käse", price_delta="1.00")
    body = _detail(p)
    form = form_block(body, 'action="/warenkorb/add/"')
    assert field_names(form) == {"csrfmiddlewaretoken", "product", "variant", "mod", "qty"}


def test_sold_out_hides_form_and_buybar():
    p = ProductFactory(stock_quantity=0)
    body = _detail(p)
    assert "Ausverkauft" in body
    assert "/warenkorb/add/" not in body  # формы нет (waitlist у товара нет по дизайну)
    assert "data-buybar" not in body  # мобильный buybar скрыт без in_stock


def test_orders_module_off_hides_buybox_entirely():
    # GK-14: с активным jobs тупика больше нет — вместо корзины Anfrage-CTA
    # (browse-only Speisekarte у catering); формы корзины по-прежнему нет.
    p = ProductFactory()
    body = _detail(p, tenant=TenantFactory.build(disabled_modules=["orders"]))
    assert "/warenkorb/add/" not in body
    assert "Ausverkauft" not in body  # блока нет целиком, не sold-out-ветка
    # Product.name — i18n-dict; в контракте sellable.name — локализованная строка.
    # MEN-11: CTA открывает попап с формой (фрагмент /anfrage/formular/), префилл AF-1 тот же.
    assert f"/anfrage/formular/?betreff={quote(p.get_i18n('name'))}" in body


def test_orders_and_jobs_off_no_cta_at_all():
    # Оба модуля выключены → как раньше: buy-box пуст (нет и Anfrage-ссылки).
    p = ProductFactory()
    body = _detail(p, tenant=TenantFactory.build(disabled_modules=["orders", "jobs"]))
    assert "/warenkorb/add/" not in body
    assert "/anfrage/" not in body
