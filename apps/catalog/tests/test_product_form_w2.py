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
        ("bakery", {}),  # еда
        ("friseur", {}),  # не-еда
    ],
)
def test_all_fields_stay_in_dom(user, business_type, cfg):
    """W0-урок: скрытие (не-еда) — только CSS; поля обязаны быть в DOM, иначе Save
    придёт без них и затрёт значения. (SM-1: режим Простой/Эксперт снесён.)"""
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
def test_labeling_tab_hidden_for_nonfood(user):
    """FB-1: вся вкладка «Kennzeichnung» (пищевая: Allergene/Zusatzstoffe/Zutaten/Herkunft)
    скрыта у не-гастро — но панель и поля остаются в DOM (W0 → Save не стирает)."""
    nonfood = _render(user, TenantFactory(business_type="friseur"))
    i = nonfood.find('data-pf-tab="kennz"')
    assert i != -1 and "hidden" in nonfood[i : i + 90]  # кнопка вкладки скрыта
    assert 'data-pf-panel="kennz"' in nonfood  # панель в DOM
    assert 'name="origin"' in nonfood and 'name="ingredients"' in nonfood  # поля в DOM
    food = _render(user, TenantFactory(business_type="bakery"))
    j = food.find('data-pf-tab="kennz"')
    assert j != -1 and "hidden" not in food[j : j + 90]  # у пекарни вкладка видна


@pytest.mark.django_db
def test_advanced_tabs_visible_for_everyone(user):
    """SM-1: продвинутые табы видны каждому. SR-2 (осознанная переписка):
    таба «Preis & stock» больше НЕТ — цена и наличие живут ПОСТОЯННОЙ правой
    колонкой (data-price-rail), видимой на любом табе; Marketing — таб как был."""
    body = _render(user, TenantFactory(business_type="bakery"))
    assert "id_stock_quantity" in body and "id_cost_price" in body
    assert 'data-pf-tab="preis"' not in body and 'data-pf-panel="preis"' not in body
    i = body.find("data-price-rail")
    assert i != -1
    # цена — вне какой-либо панели: её id встречается ПОСЛЕ маркера рейла
    assert body.find("id_base_price", i) != -1
    i = body.find('data-pf-tab="markt"')
    assert i != -1 and "hidden" not in body[i : i + 80]


@pytest.mark.django_db
def test_inline_new_category_created_on_save(user):
    """SR-2: поле «Neue Kategorie» на карточке товара создаёт категорию при
    Save и назначает её товару (селект при этом перебивается)."""
    from apps.catalog.forms import ProductForm
    from apps.catalog.models import Category

    TenantFactory(business_type="bakery")
    form = ProductForm(
        {
            "name_de": "Brot",
            "description_de": "",
            "base_price": "4.20",
            "currency": "EUR",
            "new_category": "Backwaren",
        },
        tenant=None,
    )
    assert form.is_valid(), form.errors
    product = form.save()
    assert product.category is not None
    assert Category.objects.get(pk=product.category_id).name["de"] == "Backwaren"


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


# --- Ф2: origin/ingredients переводимы per-товар (overlay) -------------------
@pytest.mark.django_db
def test_origin_ingredients_translatable(user):
    """Ф2: Herkunft/Zutaten переводимы (overlay origin_i18n/ingredients_i18n); база в
    плоском поле, перевод — на локали; на витрине — origin_localized/ingredients_localized."""
    from apps.catalog.models import Product

    tenant = TenantFactory(business_type="bakery", enabled_locales=["de", "en"])
    product = Product.objects.create(name={"de": "Brot"}, base_price="2.00")
    req = RequestFactory().post(
        f"/catalog/products/{product.pk}/edit/",
        {
            "name_de": "Brot",
            "base_price": "2.00",
            "currency": "EUR",
            "origin": "Deutschland",
            "origin_en": "Germany",
            "ingredients": "Mehl, Wasser",
            "ingredients_en": "Flour, water",
        },
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user
    req.tenant = tenant
    resp = views.product_edit(req, product.pk)
    assert resp.status_code == 302
    product.refresh_from_db()
    assert product.origin == "Deutschland"  # база (de) в плоском поле
    assert product.origin_i18n.get("en") == "Germany"  # перевод в оверлее
    assert product.origin_localized("en") == "Germany"
    assert product.origin_localized("de") == "Deutschland"  # база
    assert product.ingredients_localized("en") == "Flour, water"


@pytest.mark.django_db
def test_origin_i18n_inputs_in_dom_multi_locale(user):
    """Ф2: инпуты переводов origin/ingredients (origin_en/ingredients_en) в DOM при мультиязыке."""
    body = _render(user, TenantFactory(business_type="bakery", enabled_locales=["de", "en"]))
    assert 'name="origin_en"' in body and 'name="ingredients_en"' in body


@pytest.mark.django_db
def test_switcher_uses_event_delegation(user):
    """Регресс: скрипт свитчера/табов ДОЛЖЕН делегировать клики на document —
    партиал парсится раньше табов/панелей, прямое навешивание ловило пустой
    NodeList и кнопки не работали (фидбэк владельца 2026-07-09)."""
    body = _render(user, TenantFactory(business_type="bakery", enabled_locales=["de", "en"]))
    assert "__i18nSwitchBound" in body  # guard делегированного слушателя
    assert 'document.addEventListener("click"' in body  # делегирование, не per-node bind
