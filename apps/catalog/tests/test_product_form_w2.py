"""W2 (упрощение формы товара): порядок полей, секции/аккордеоны, режим Простой/Эксперт,
гейт пищевой маркировки по архетипу. Ключевой замок — ВСЕ поля остаются в DOM во всех
режимах (иначе Save стёр бы скрытые, как баг W0)."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import views
from apps.catalog.forms import ProductForm
from apps.tenants.tests.factories import TenantFactory


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user("o", "o@test.de", "pw12345678")


def _render(user, tenant):
    req = RequestFactory().get("/catalog/products/new/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user
    req.tenant = tenant
    return views.product_create(req).content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("business_type", "cfg"),
    [
        ("bakery", {}),  # еда, эксперт
        ("bakery", {"ui_mode": "simple"}),  # еда, простой
        ("friseur", {}),  # не-еда, эксперт
        ("friseur", {"ui_mode": "simple"}),  # не-еда, простой
    ],
)
def test_all_fields_stay_in_dom(user, business_type, cfg):
    """W0-урок: скрытие (Простой/не-еда) — только CSS; поля обязаны быть в DOM, иначе Save
    придёт без них и затрёт значения."""
    tenant = TenantFactory(business_type=business_type, site_config=cfg)
    body = _render(user, tenant)
    form = ProductForm(tenant=tenant)
    missing = [n for n in form.fields if f"id_{n}" not in body]
    assert not missing, f"поля не в DOM (Save их сотрёт): {missing}"


@pytest.mark.django_db
def test_name_renders_before_price(user):
    """Порядок починен: название — в первой секции, раньше цены (было 17-м полем)."""
    body = _render(user, TenantFactory(business_type="bakery"))
    assert body.index("id_name_de") < body.index("id_base_price")


@pytest.mark.django_db
def test_food_section_gated_by_archetype(user):
    """Пищевая маркировка видна только гастро/еде; у прочих архетипов секция скрыта (CSS)."""
    nonfood = _render(user, TenantFactory(business_type="friseur"))
    i = nonfood.find("data-food-section")
    assert i != -1 and "hidden" in nonfood[i : i + 80]  # у friseur — скрыта
    food = _render(user, TenantFactory(business_type="bakery"))
    j = food.find("data-food-section")
    assert j != -1 and "hidden" not in food[j : j + 80]  # у пекарни — видна


@pytest.mark.django_db
def test_simple_mode_hides_advanced_keeps_fields(user):
    """Ф1: в Простом режиме продвинутые ТАБЫ скрыты, но их поля остаются в DOM."""
    body = _render(user, TenantFactory(business_type="bakery", site_config={"ui_mode": "simple"}))
    assert "id_stock_quantity" in body and "id_cost_price" in body  # поля в DOM
    i = body.find('data-pf-tab="preis"')
    assert i != -1 and "hidden" in body[i : i + 80]  # продвинутый таб скрыт


# --- Ф1: переключатель языка (per-language ввод) ----------------------------
@pytest.mark.django_db
def test_language_switcher_shown_for_multi_locale(user):
    """Ф1: при ≥2 языках — пилюли-переключатель; поля неосновных языков в DOM, но
    скрыты (data-i18n-loc), видна только базовая локаль. Все поля остаются (Save)."""
    tenant = TenantFactory(business_type="bakery", enabled_locales=["de", "en"])
    body = _render(user, tenant)
    assert 'data-i18n-pill="de"' in body and 'data-i18n-pill="en"' in body  # пилюли
    assert "id_name_de" in body and "id_name_en" in body  # оба языка в DOM
    i = body.find('data-i18n-loc="en"')
    assert i != -1 and "hidden" in body[i : i + 60]  # EN по умолчанию скрыт
    j = body.find('data-i18n-loc="de"')
    assert j != -1 and "hidden" not in body[j : j + 60]  # база (de) видна


@pytest.mark.django_db
def test_no_language_switcher_for_single_locale(user):
    """Один язык → переключателя нет (форма как раньше), поля на месте."""
    body = _render(user, TenantFactory(business_type="bakery", enabled_locales=["de"]))
    assert 'data-i18n-pill="' not in body  # кнопок-пилюль нет (JS-селектор не считаем)
    assert "id_name_de" in body
