"""FB-33 стопка 15 K0 (S14-catalog-500): корни кабинетных префиксов не дают 500.

`/catalog/` и `/imports/` разбирались в `storefront-content-page` (`<slug:slug>/` витрины):
у приложений не было пути `""`, а у страницы витрины нет права в `view_perms` → 500
(`ImproperlyConfigured`) при `PERMS_STRICT`, 403 с записью в лог в проде. Решение владельца
(план §14.3): `/catalog/` → экран товаров (пункт «Produkte» живёт в «Sortiment»),
`/imports/` → «Import starten». Страница витрины под кабинетным префиксом — 404 (Y10: с `<h1>`
и ссылкой назад).
"""

from importlib import import_module
from uuid import uuid4

import pytest
from django.conf import settings as dj_settings
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.http import Http404
from django.test import RequestFactory, override_settings
from django.urls import resolve, reverse

from apps.core import packages, permissions, view_perms
from apps.core.i18n_cabinet import CABINET_PREFIXES
from apps.core.middleware import CabinetOwnerAccessMiddleware
from apps.core.models import Membership
from apps.core.tests import gates
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

URLCONF = "config.urls_tenant"
#: корень префикса → экран, на который он ведёт (решение владельца §14.3)
INDEX_TARGETS = {
    "catalog:index": "sellable-manage",
    "imports:index": "imports:start",
}
CONTENT_PAGE = "storefront-content-page"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = URLCONF


def _tenant():
    return TenantFactory(slug=f"k0-{uuid4().hex[:6]}", name="K0")


def _user(role=None, perms=None):
    user = get_user_model().objects.create_user(
        username=f"k0-{uuid4().hex[:8]}", password="pw12345678"
    )
    if role is not None:
        Membership.objects.create(user=user, role=role, permissions=perms or {})
    return user


def _staff_without_rights():
    return _user(Membership.ROLE_STAFF, {"remove": sorted(permissions.PRESETS["staff"])})


def _request(path, tenant, user):
    request = RequestFactory().get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant
    return request


@override_settings(PERMS_STRICT=True)
@pytest.mark.parametrize("prefix", CABINET_PREFIXES)
def test_cabinet_prefix_root_never_500(prefix):
    """№6: корень каждого кабинетного префикса — владельцу 200/302, сотруднику без права
    403 (или 200/302 у открытого экрана), а не 500."""
    tenant = _tenant()
    match = resolve(prefix, urlconf=URLCONF)
    assert match.view_name != CONTENT_PAGE, f"{prefix} уходит на страницу витрины"
    rule = view_perms.rule_for(match.view_name)
    assert rule is not None, f"{prefix}: у {match.view_name!r} нет права"

    owner = gates.open_as(_request(prefix, tenant, _user(Membership.ROLE_OWNER)), gates.ok)
    assert owner.status_code in (200, 302), prefix

    staff = gates.open_as(_request(prefix, tenant, _staff_without_rights()), gates.ok)
    expected = (200, 302) if rule.read == view_perms.OPEN else (403,)
    assert staff.status_code in expected, prefix


@pytest.mark.parametrize(("index", "target"), sorted(INDEX_TARGETS.items()))
def test_index_rule_equals_target(index, target):
    """№2: у корня то же право и та же запись пакетов, что у экрана, куда он ведёт."""
    assert view_perms.rule_for(index) is not None, index
    assert view_perms.rule_for(index) == view_perms.rule_for(target)
    for key, package in packages.PACKAGES.items():
        allow = package.cabinet_allow
        if allow is None:
            continue
        assert (index in allow) == (target in allow), (key, index)


@pytest.mark.parametrize(("index", "target"), sorted(INDEX_TARGETS.items()))
def test_index_redirects_owner_to_target(index, target):
    tenant = _tenant()
    path = reverse(index)
    response = gates.open_as(_request(path, tenant, _user(Membership.ROLE_OWNER)))
    assert response.status_code == 302
    assert response["Location"] == reverse(target)


@pytest.mark.parametrize("index", sorted(INDEX_TARGETS))
def test_index_redirect_needs_membership(index):
    """№28: без Membership — 403 пола, аноним — на вход; адрес цели не раскрывается."""
    tenant = _tenant()
    path = reverse(index)
    outsider = gates.open_as(_request(path, tenant, _user()))
    assert outsider.status_code == 403

    from django.contrib.auth.models import AnonymousUser

    anon = gates.open_as(_request(path, tenant, AnonymousUser()))
    assert anon.status_code == 302
    assert reverse(INDEX_TARGETS[index]) not in anon["Location"].split("?")[0]


@override_settings(PERMS_STRICT=True)
@pytest.mark.parametrize("prefix", CABINET_PREFIXES)
def test_content_page_under_cabinet_prefix_404(prefix):
    """№6: адрес, разобравшийся в страницу витрины, на кабинетном префиксе — 404, не 500.
    Проверка — по имени маршрута, второго списка путей нет."""
    tenant = _tenant()
    request = _request(prefix, tenant, _user(Membership.ROLE_OWNER))
    match = resolve("/impressum-k0/", urlconf=URLCONF)
    assert match.view_name == CONTENT_PAGE
    request.resolver_match = match
    with pytest.raises(Http404):
        CabinetOwnerAccessMiddleware(None).process_view(
            request, match.func, match.args, match.kwargs
        )


def test_content_page_outside_cabinet_untouched():
    tenant = _tenant()
    request = _request("/impressum-k0/", tenant, _user(Membership.ROLE_OWNER))
    match = resolve("/impressum-k0/", urlconf=URLCONF)
    request.resolver_match = match
    assert (
        CabinetOwnerAccessMiddleware(None).process_view(
            request, match.func, match.args, match.kwargs
        )
        is None
    )


def test_cabinet_404_has_h1_and_back_link():
    """Y10: 404 под кабинетным префиксом — простая страница с `<h1>` и ссылкой назад."""
    from apps.core.not_found_views import storefront_404

    tenant = _tenant()
    request = _request("/catalog/nicht-da/", tenant, _user(Membership.ROLE_OWNER))
    response = storefront_404(request, Http404())
    assert response.status_code == 404
    html = response.content.decode()
    assert "<h1" in html
    assert '<a href="/"' in html
