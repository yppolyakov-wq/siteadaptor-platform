"""CabinetOwnerAccessMiddleware: доступ к кабинету — только членам тенанта.

Fail-closed поверх @login_required: аутентифицированный пользователь без строки
Membership в схеме тенанта получает 403 на кабинет-путях (закрывает захват
тенанта через саморегистрацию). Аноним, публичная схема и витрина — не трогаются.
"""

from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.middleware import CabinetOwnerAccessMiddleware
from apps.core.models import Membership

pytestmark = pytest.mark.django_db


def _user(name="u1"):
    return get_user_model().objects.create_user(
        username=name, email=f"{name}@t.de", password="pw12345678"
    )


def _call(path, *, user, schema_name="t_biz"):
    req = RequestFactory().get(path)
    req.user = user
    req.tenant = SimpleNamespace(schema_name=schema_name)
    mw = CabinetOwnerAccessMiddleware(lambda request: HttpResponse("ok"))
    return mw(req)


def test_authenticated_non_member_blocked_on_cabinet():
    user = _user()  # без Membership
    for path in (
        "/dashboard/",
        "/catalog/products/",
        "/crm/",
        "/promotions/redeem/",
        "/willkommen/",
    ):
        assert _call(path, user=user).status_code == 403, path


def test_member_allowed_on_cabinet():
    user = _user("owner1")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    assert _call("/dashboard/", user=user).status_code == 200


def test_anonymous_passes_through():
    # Аноним — не наша забота: @login_required отредиректит на логин (здесь 200 от заглушки).
    assert _call("/dashboard/", user=AnonymousUser()).status_code == 200


def test_public_schema_not_gated():
    user = _user("pub")  # без Membership
    assert _call("/dashboard/", user=user, schema_name="public").status_code == 200


def test_storefront_paths_not_gated():
    user = _user("visitor")  # без Membership
    for path in ("/", "/sortiment/", "/termin/", "/konto/", "/accounts/login/"):
        assert _call(path, user=user).status_code == 200, path
