"""STU-3: охват настройки «для всех / только здесь» (вариант A владельца).

Владелец: «применить для всех или изменить только для этого товара или категории —
это как раз нужно в студии». Данные трёхуровневые с DL-19/20/21, но объектный уровень
правился ТОЛЬКО в формах кабинета. Здесь он появляется в Студии — и запись идёт мимо
большой формы билдера, точечно в одно поле одного объекта.

Замки держат три вещи: значение действительно доезжает до объекта; мусор и чужие
ссылки отбиваются (иначе «сохранили, а витрина молча показывает дефолт»); и снятие
охвата возвращает объект к наследованию, а не пишет пустую строку в общий ключ.
"""

import pytest

from apps.catalog.models import Category, Product
from apps.core import studio_scope
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return TenantFactory()


@pytest.fixture
def category():
    return Category.objects.create(name={"de": "Frische"}, slug="frische", is_active=True)


def test_own_value_wins_and_is_reported(tenant, category):
    tenant.site_config = {"site_defaults": {"category_page_style": "magazin"}}
    state = studio_scope.read_state(tenant, "category_page_style", "frische")
    assert state.site_value == "magazin"
    assert state.own_value == "" and not state.overridden

    studio_scope.write_value(tenant, "category_page_style", "frische", "regale")
    category.refresh_from_db()
    assert category.page_style == "regale"

    state = studio_scope.read_state(tenant, "category_page_style", "frische")
    assert state.own_value == "regale" and state.overridden
    assert state.site_value == "magazin", "общий дефолт не должен перезаписываться"


def test_clearing_returns_the_object_to_inheritance(tenant, category):
    studio_scope.write_value(tenant, "category_page_style", "frische", "regale")
    studio_scope.write_value(tenant, "category_page_style", "frische", "")
    category.refresh_from_db()
    assert category.page_style == ""
    assert not studio_scope.read_state(tenant, "category_page_style", "frische").overridden


def test_unknown_value_is_refused(tenant, category):
    """Иначе в базу ляжет код, которого нет в реестре, а витрина молча покажет
    дефолт — владелец будет думать, что выбор не сохраняется."""
    with pytest.raises(studio_scope.ScopeError):
        studio_scope.write_value(tenant, "category_page_style", "frische", "erfunden")
    category.refresh_from_db()
    assert category.page_style == ""


def test_missing_object_is_refused(tenant):
    with pytest.raises(studio_scope.ScopeError):
        studio_scope.write_value(tenant, "category_page_style", "gibt-es-nicht", "regale")
    with pytest.raises(studio_scope.ScopeError):
        studio_scope.read_state(tenant, "category_page_style", "")


def test_setting_without_object_level_is_refused(tenant):
    """У раскладки каталога объектного уровня нет — пилюля у неё не рисуется, и
    подделанный запрос не должен находить, куда писать."""
    with pytest.raises(studio_scope.ScopeError):
        studio_scope.write_value(tenant, "catalog_layout", "frische", "cols3")


def test_promo_group_is_stored_in_config_presence_minimal(tenant):
    """Модели группы нет — её выбор живёт в site_config; пустой ключ не храним."""
    studio_scope.write_value(tenant, "promo_group_style", "Wochenangebote", "prospekt")
    tenant.refresh_from_db()
    assert tenant.site_config["promo_groups"] == {"Wochenangebote": "prospekt"}

    studio_scope.write_value(tenant, "promo_group_style", "Wochenangebote", "")
    tenant.refresh_from_db()
    assert "promo_groups" not in tenant.site_config


def test_promo_group_write_keeps_neighbouring_keys(tenant):
    """Класс дефектов W6: точечная запись не имеет права ронять чужие ключи конфига."""
    tenant.site_config = {"ui_probe": "keep", "board": {"hidden": ["x"]}}
    tenant.save(update_fields=["site_config"])
    studio_scope.write_value(tenant, "promo_group_style", "Sale", "countdown")
    tenant.refresh_from_db()
    assert tenant.site_config["ui_probe"] == "keep"
    assert tenant.site_config["board"] == {"hidden": ["x"]}


def test_product_card_form_by_slug_and_uuid(tenant):
    """Деталь товара живёт на трёх роутах: uuid и два слаг-роута. Ссылка со страницы
    приходит в той форме, какая была в адресе, — оба варианта обязаны находиться."""
    product = Product.objects.create(name={"de": "Brot"}, slug="brot", base_price="2.50")

    studio_scope.write_value(tenant, "product_card_form", "brot", "regal")
    product.refresh_from_db()
    assert product.card_style == "regal"

    studio_scope.write_value(tenant, "product_card_form", str(product.pk), "lookbook")
    product.refresh_from_db()
    assert product.card_style == "lookbook"


def test_garbage_uuid_does_not_crash(tenant):
    with pytest.raises(studio_scope.ScopeError):
        studio_scope.read_state(tenant, "product_card_form", "не-uuid-и-не-слаг")


# ── эндпоинты ────────────────────────────────────────────────────────────────


def _req(method, path, data=None, tenant=None, authed=True):
    from importlib import import_module
    from types import SimpleNamespace

    from django.conf import settings as dj_settings
    from django.test import RequestFactory

    request = getattr(RequestFactory(), method)(path, data or {})
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.user = SimpleNamespace(is_authenticated=authed)
    request.tenant = tenant
    return request


def test_state_endpoint_reports_only_asked_settings(tenant, category, settings):
    import json

    from apps.core import views

    settings.ROOT_URLCONF = "config.urls_tenant"
    studio_scope.write_value(tenant, "category_page_style", "frische", "regale")
    resp = views.studio_scope_state(
        _req(
            "get",
            "/dashboard/site/scope/",
            {"ref": "frische", "settings": "category_page_style,catalog_layout"},
            tenant=tenant,
        )
    )
    data = json.loads(resp.content)
    assert data["ref"] == "frische"
    assert data["settings"]["category_page_style"]["own"] == "regale"
    # у раскладки объектного уровня нет — её просто нет в ответе, а не 500
    assert "catalog_layout" not in data["settings"]


def test_state_endpoint_is_quiet_on_unknown_page(tenant, settings):
    """Редактор открывается и там, где объекта нет; пустой ответ = пилюль не будет."""
    import json

    from apps.core import views

    settings.ROOT_URLCONF = "config.urls_tenant"
    resp = views.studio_scope_state(
        _req(
            "get",
            "/dashboard/site/scope/",
            {"ref": "", "settings": "category_page_style"},
            tenant=tenant,
        )
    )
    assert json.loads(resp.content)["settings"] == {}


def test_save_endpoint_rejects_garbage_with_400(tenant, category, settings):
    from apps.core import views

    settings.ROOT_URLCONF = "config.urls_tenant"
    resp = views.studio_scope_save(
        _req(
            "post",
            "/dashboard/site/scope/save/",
            {"setting": "category_page_style", "ref": "frische", "value": "erfunden"},
            tenant=tenant,
        )
    )
    assert resp.status_code == 400
    category.refresh_from_db()
    assert category.page_style == ""


def test_save_endpoint_writes_and_answers_state(tenant, category, settings):
    import json

    from apps.core import views

    settings.ROOT_URLCONF = "config.urls_tenant"
    resp = views.studio_scope_save(
        _req(
            "post",
            "/dashboard/site/scope/save/",
            {"setting": "category_page_style", "ref": "frische", "value": "regale"},
            tenant=tenant,
        )
    )
    assert resp.status_code == 200
    assert json.loads(resp.content) == {"ok": True, "own": "regale", "site": ""}
    category.refresh_from_db()
    assert category.page_style == "regale"


def test_endpoints_require_login(settings):
    """Оба вида читают и пишут данные тенанта — доступ анониму закрыт декоратором.

    Класс дефектов «декоратор съеден вставленным хелпером» (integrations_home,
    thread_poll) — поэтому проверяем сам факт обёртки, а не только поведение.
    """
    from apps.core import views

    for view in (views.studio_scope_state, views.studio_scope_save):
        assert getattr(view, "__wrapped__", None) is not None, view.__name__


def test_save_endpoint_is_post_only():
    from apps.core import views

    resp = views.studio_scope_save(_req("get", "/dashboard/site/scope/save/"))
    assert resp.status_code == 405
