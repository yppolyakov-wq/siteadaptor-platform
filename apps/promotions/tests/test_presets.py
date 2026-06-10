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
