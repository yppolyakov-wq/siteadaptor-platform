"""Track B3a: пресеты акций по вертикали пред-заполняют форму создания."""

import pytest
from django.test import RequestFactory

from apps.promotions import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


class _User:
    is_authenticated = True
    is_active = True


def _req(path, business_type="bakery"):
    request = RequestFactory().get(path)
    request.user = _User()
    request.tenant = TenantFactory.build(business_type=business_type)
    return request


def test_vertical_presets_are_listed():
    resp = views.promotion_create(_req("/promotions/new/"))
    assert resp.status_code == 200
    assert b"Feierabend-T" in resp.content  # кнопка пресета пекарни


def test_preset_prefills_form():
    resp = views.promotion_create(_req("/promotions/new/?preset=feierabend"))
    assert resp.status_code == 200
    assert b"Feierabend-\xc3\x9cberraschungst" in resp.content  # title_de предзаполнен (UTF-8)


def test_unknown_preset_is_safe():
    resp = views.promotion_create(_req("/promotions/new/?preset=nope"))
    assert resp.status_code == 200


def test_promotion_form_language_switcher_and_tabs():
    """Ф1: у акции — переключатель языка (title/description по языкам, не все сразу) + табы.
    Поля обоих языков в DOM (Save собирает всё); TenantFactory даёт de+en."""
    body = views.promotion_create(_req("/promotions/new/")).content.decode()
    assert 'data-i18n-pill="de"' in body and 'data-i18n-pill="en"' in body  # пилюли
    assert "id_title_de" in body and "id_title_en" in body  # оба языка в DOM
    assert 'data-pf-tab="rabatt"' in body and 'data-pf-tab="zeit"' in body  # табы
    # EN-группа по умолчанию скрыта, база (de) видна
    i = body.find('data-i18n-loc="en"')
    assert i != -1 and "hidden" in body[i : i + 60]


@pytest.mark.parametrize(
    ("business_type", "key", "title"),
    [
        ("friseur", "neukunde", "Neukunden-Rabatt"),
        ("werkstatt", "check", "Frühjahrs-Check"),
        ("handwerker", "saison", "Saison-Aktion"),
        ("events", "fruehbucher", "Frühbucher-Rabatt"),
    ],
)
def test_s6_archetype_presets_prefill(business_type, key, title):
    # S6-архетипы: у каждого свой пресет (не только generic _COMMON), заголовок
    # предзаполняется в форме создания при ?preset=<key>.
    resp = views.promotion_create(_req(f"/promotions/new/?preset={key}", business_type))
    assert resp.status_code == 200
    assert title.encode("utf-8") in resp.content
