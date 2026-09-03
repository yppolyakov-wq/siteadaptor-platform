"""DL-19.4/19.5 — выбор ФОРМЫ карточки: плитки с предпросмотром в Studio и
per-объект поле в формах кабинета.

Запрос владельца 2026-09-03: «настройка вид карточки товара и там выбор из
вариантов и предпросмотр; можно в карточке акции/товара выбрать только для этого
товара или в общих настройках задать для всех; если в карточке выбираем — оно
приоритетнее». Замки держат оба конца: контрол в Studio → save → черновик, и
поле формы → модель → рендер (приоритет проверяет test_dl19_card_forms).
"""

from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import card_forms, views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _request(method, path, data=None, tenant=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _body(tenant):
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    assert resp.status_code == 200
    return resp.content.decode()


def _save(tenant, data):
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    return siteconfig.normalize(tenant.site_config)


# --- Studio ---------------------------------------------------------------------
def test_studio_shows_a_tile_with_a_preview_for_every_form():
    tenant = TenantFactory(schema_name="public", slug="dl19s", name="DL19S")
    body = _body(tenant)
    # считаем МАРКАП (атрибут с закрывающей скобкой): в партиале есть ещё JS-селекторы
    # «[data-cardform-picker]» — урок MEN: замок на голый маркер ловит строки скрипта.
    # DL-20 осознанно добавил две плитки-выборки (шаблоны СТРАНИЦ — категории и
    # группы акций) тем же партиалом — счётчик обновлён вместе с ними.
    assert body.count("data-cardform-picker>") == 4
    assert 'name="sd_card_style"' in body and 'name="sd_promo_card"' in body
    for key in card_forms.keys_for("product") | card_forms.keys_for("promo"):
        assert f'data-cf-key="{key}"' in body, key
    assert 'data-cf-key=""' in body  # «Standard» — тоже плитка, а не пустой пункт
    # у плитки есть мини-макет (предпросмотр), а не только подпись
    assert 'aria-hidden="true"' in body


def test_card_form_picker_is_not_hidden_behind_expert_mode():
    """Прецедент W11-5: настройка, спрятанная в expert-блок, в Простом режиме
    редактора не видна вообще — владелец её не находит. Выбор ФОРМЫ карточки —
    первичная настройка вида витрины, поэтому он ВНЕ [data-expert]."""
    tenant = TenantFactory(schema_name="public", slug="dl19e", name="DL19E")
    body = _body(tenant)
    for name in ('name="sd_card_style"', 'name="sd_promo_card"'):
        idx = body.index(name)
        expert_open = body.rfind('data-expert="1"', 0, idx)
        assert expert_open != -1  # expert-блоки на странице есть (иначе замок пуст)
        assert "</div>" in body[expert_open:idx], f"{name} оказался внутри expert-блока"


def test_studio_saves_and_drafts_the_new_forms():
    tenant = TenantFactory(schema_name="public", slug="dl19t", name="DL19T")
    cfg = _save(
        tenant, {"sd_card_style": "regal", "sd_promo_card": "coupon", "sd_card_radius": "0"}
    )
    assert cfg["site_defaults"]["card_style"] == "regal"
    assert cfg["site_defaults"]["promo_card"] == "coupon"
    # снятие формы законно (плитка «Standard») → ключа снова нет
    cfg = _save(tenant, {"sd_card_style": "", "sd_promo_card": "", "sd_card_radius": "0"})
    assert "card_style" not in cfg["site_defaults"]
    assert "promo_card" not in cfg["site_defaults"]


def test_live_draft_still_reads_the_same_field_names():
    """Плитки заменили <select>, но имя поля прежнее — иначе черновик и клик по
    Look'у молча перестали бы выставлять форму карточки."""
    tenant = TenantFactory(schema_name="public", slug="dl19d", name="DL19D")
    body = _body(tenant)
    assert "form.querySelector(\"[name='sd_card_style']\")" in body
    assert "form.querySelector(\"[name='sd_promo_card']\")" in body
    assert 'card_style: sdStyle ? sdStyle.value : ""' in body


# --- кабинет: per-объект --------------------------------------------------------
def test_product_form_offers_the_registry_and_saves_the_choice():
    from apps.catalog.forms import ProductForm
    from apps.catalog.tests.factories import ProductFactory

    p = ProductFactory()
    form = ProductForm(instance=p)
    keys = [k for k, _label in form.fields["card_style"].choices]
    assert keys == [k for k, _l, _h in card_forms.forms_for("product")]
    assert not form.fields["card_style"].required  # пусто = как в настройках сайта
    # форма акции товару не предлагается
    assert "coupon" not in keys


def test_promotion_form_offers_the_promo_registry():
    from apps.promotions.forms import PromotionForm

    form = PromotionForm()
    keys = [k for k, _label in form.fields["card_style"].choices]
    assert keys == [k for k, _l, _h in card_forms.forms_for("promo")]
    assert "coupon" in keys and "overlay" not in keys
