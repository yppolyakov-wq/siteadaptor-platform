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


# ── ревью 1: сквозные проверки через настоящий стек middleware (`django.test.Client`) ──────

TEST_URLCONF = "apps.core.tests.urls_s15_k0_prefix"


@pytest.fixture
def client_for():
    from django.db import connections
    from django.test import Client

    from apps.tenants.tests.factories import DomainFactory

    def make(user=None, profile=None):
        tenant = _tenant()
        if profile:
            tenant.site_config = {**(tenant.site_config or {}), "profile": profile}
            tenant.save(update_fields=["site_config"])
        domain = DomainFactory(tenant=tenant, domain=f"{tenant.slug}.siteadaptor.de")
        client = Client(HTTP_HOST=domain.domain)
        if user is not None:
            from apps.core.session_schema import SESSION_SCHEMA_KEY

            client.force_login(user)
            # вход в тесте идёт на public — штамп схемы бизнеса, как при настоящем входе
            session = client.session
            session[SESSION_SCHEMA_KEY] = tenant.schema_name
            session.save()
        return client

    yield make
    connections["default"].set_schema_to_public()


def _get(client, path):
    from django.db import connections

    try:
        return client.get(path, secure=True)
    finally:
        connections["default"].set_schema_to_public()


def test_content_page_under_cabinet_prefix_404_full_stack(client_for, settings):
    """Ревью 1 №1: префикс без корня (тестовый urlconf) → страница витрины → 404 всем стеком,
    не 500 (`ImproperlyConfigured`) и не 403."""
    settings.PERMS_STRICT = True
    settings.ROOT_URLCONF = TEST_URLCONF
    client = client_for(_user(Membership.ROLE_OWNER))
    assert resolve("/crm/", urlconf=TEST_URLCONF).view_name == CONTENT_PAGE
    cabinet = _get(client, "/dashboard/")
    assert "/accounts/login/" not in cabinet.get("Location", ""), "владелец не вошёл"
    response = _get(client, "/crm/")
    assert response.status_code == 404


def test_cabinet_404_full_stack_has_h1_and_back_link(client_for, settings):
    """Ревью 1 №2 (Y10): Http404 из `process_view` → handler404 → простая страница с `<h1>`
    и ссылкой назад, без хрома витрины."""
    settings.PERMS_STRICT = True
    settings.ROOT_URLCONF = TEST_URLCONF
    response = _get(client_for(_user(Membership.ROLE_OWNER)), "/crm/")
    assert response.status_code == 404
    html = response.content.decode()
    assert "<h1" in html
    assert '<a href="/"' in html


@pytest.mark.parametrize("prefix", CABINET_PREFIXES)
def test_no_content_page_slug_shadowed_by_cabinet_root(prefix):
    """Ревью 1 №3: slug, совпадающий с кабинетным префиксом, не получает короткий адрес своей
    страницы (иначе `/catalog/` снова ушла бы на витрину)."""
    from apps.core import content_pages

    slug = prefix.strip("/")
    assert not content_pages.short_url_free(slug), slug


def test_index_staff_with_sortiment_redirects():
    """Ревью 1 №4: сотрудник с правом «Sortiment» проходит корень /catalog/ к экрану."""
    staff = _user(Membership.ROLE_STAFF)
    assert permissions.has_perm(staff, "sortiment.view")
    response = gates.open_as(_request(reverse("catalog:index"), _tenant(), staff))
    assert response.status_code == 302
    assert response["Location"] == reverse("sellable-manage")


@pytest.mark.parametrize("profile", [packages.AKTIONEN, packages.EINTRAG])
@pytest.mark.parametrize(("index", "target"), sorted(INDEX_TARGETS.items()))
def test_index_light_package_403(client_for, profile, index, target):
    """Ревью 1 №4: лёгкий пакет получает на корне тот же ответ, что на экране-цели:
    «In Ihrem Paket nicht enthalten» (403) или переход к открытому экрану."""
    owner = _user(Membership.ROLE_OWNER)
    client = client_for(owner, profile=profile)
    root = _get(client, reverse(index))
    target_allowed = target in packages.PACKAGES[profile].cabinet_allow
    if target_allowed:
        assert root.status_code == 302
        assert root["Location"] == reverse(target)
    else:
        assert root.status_code == 403
        assert _get(client, reverse(target)).status_code == 403


@pytest.mark.parametrize("role", [Membership.ROLE_ADMIN, Membership.ROLE_STAFF])
def test_imports_website_stays_owner_only(role):
    """Ревью 1 №4: корень /imports/ не открывает импорт с сайта — пол владельца как был."""
    tenant = _tenant()
    response = gates.open_as(_request(reverse("imports:website"), tenant, _user(role)), gates.ok)
    assert response.status_code == 403
    owner = gates.open_as(
        _request(reverse("imports:website"), tenant, _user(Membership.ROLE_OWNER)), gates.ok
    )
    assert owner.status_code == 200
