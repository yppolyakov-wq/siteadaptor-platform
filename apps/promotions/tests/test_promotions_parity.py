"""SF-2 C0: характеризационные замки /aktionen/ ДО свода на каркас listing.html.

Прецедент UB1-3 (test_listing_parity/test_index_parity): замораживаем не HTML
целиком, а стабильные маркеры разметки и их взаимный порядок. Секции-групп
(Prospekt-логика, фидбэк владельца 2026-07-29/08-07) обязаны пережить рефактор
байт-в-байт по структуре: заголовок → чипы групп → секции с <h2> и счётчиком →
«More offers» в конце → плоская сетка при выбранном фильтре → empty-текст.
"""

import pytest
from django.test import RequestFactory

from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

GRID = 'data-grid="promo_list"'
GRID_CLASSES = "grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6"
CHIP = "px-3 py-1.5 rounded-full"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(slug):
    return TenantFactory(schema_name="public", slug=slug, name="PP")


def _body(tenant, params=None):
    req = RequestFactory().get("/aktionen/", params or {})
    req.tenant = tenant
    return public_views.promotion_list(req).content.decode()


def _promo(title, group="", **kw):
    return Promotion.objects.create(title={"de": title}, status="active", group=group, **kw)


def test_grouped_sections_order_and_markers():
    tenant = _tenant("pp1")
    _promo("WoA", "Wochenangebote")
    _promo("WoB", "Wochenangebote")
    _promo("Einzel", "Solo")  # одиночная группа → блок «More offers» в конце

    body = _body(tenant)
    # порядок: h1 → чипы групп → секция группы (h2 + счётчик) → грид карточек
    h1 = body.index("text-2xl md:text-3xl font-bold")
    chips = body.index(CHIP)
    section = body.index('<section class="mb-8">')
    h2 = body.index('<h2 class="text-lg font-bold mb-3">')
    grid = body.index(GRID)
    assert h1 < chips < section < h2 < grid
    # секцию получает только группа с >=MIN_GROUP_SECTION акций; одиночные — в
    # хвостовой блок (его <h2> — «More offers», группа пустая)
    assert body.count('<section class="mb-8">') == 2
    assert "Wochenangebote</h2>" not in body  # счётчик внутри h2
    assert "· 2</span>" in body and "· 1</span>" in body
    # грид секций — прежние классы и общий grid_key переключателя вида
    assert GRID_CLASSES in body
    assert "with grid_key" not in body  # include отработал, не утёк текстом
    # чип «All» ведёт на голый URL, чипы групп — на ?gruppe=
    assert "?gruppe=Wochenangebote" in body and "?gruppe=Solo" in body


def test_filtered_view_is_flat_grid_and_keeps_other_chips():
    tenant = _tenant("pp2")
    _promo("WoA", "Wochenangebote")
    _promo("WoB", "Wochenangebote")
    _promo("RaA", "Räumung")
    _promo("RaB", "Räumung")

    body = _body(tenant, {"gruppe": "Wochenangebote"})
    # выбран фильтр → секций нет, одна плоская сетка
    assert '<section class="mb-8">' not in body
    assert body.count(GRID) == 1
    assert "WoA" in body and "RaA" not in body
    # чипы ДРУГИХ групп остаются видимыми (метки строятся по нефильтрованной выдаче)
    assert "?gruppe=R%C3%A4umung" in body or "?gruppe=Räumung" in body


def test_empty_state():
    tenant = _tenant("pp3")
    body = _body(tenant)
    assert GRID not in body
    assert "text-gray-400" in body  # empty-строка присутствует


def test_single_group_only_flat_when_no_sections_qualify():
    tenant = _tenant("pp4")
    _promo("Solo1", "A")
    _promo("Solo2", "B")
    body = _body(tenant)
    # ни одна группа не набрала MIN_GROUP_SECTION → плоская сетка без секций
    assert '<section class="mb-8">' not in body
    assert body.count(GRID) == 1
