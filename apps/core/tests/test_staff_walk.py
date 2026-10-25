"""KA-12 E11.2: сценарий «сотрудник» на каждом экране кабинета.

План — docs/ka-12-e11-checks-plan-2026-10-23.md. Политика (решение владельца 2026-08-06):
owner-only — пути замороженного эталона `legacy_role_gates` (вчерашние префиксы и
декораторы); финансовые выгрузки — owner + admin. KA-12 E6.7c-4: код читает только реестр
прав `view_perms`, а этот замок держит паритет «пустые права = вчерашний доступ».

Экран открываем так же, как браузер: путь → мидлвари доступа → вьюха по `resolve()`.
"""

from importlib import import_module
from uuid import uuid4

import pytest
from django.conf import settings
from django.conf import settings as dj_settings
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.http import HttpResponseNotFound
from django.test import RequestFactory
from django.urls import Resolver404, URLPattern, URLResolver, get_resolver, resolve, reverse

from apps.core import modules, nav_registry, view_perms
from apps.core.middleware import CabinetOwnerAccessMiddleware
from apps.core.models import Membership
from apps.core.tests import legacy_role_gates as LG
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

# Представительные типы: товар, номера, запись, заявки, онлайн-магазин, лёгкая ступень.
REPRESENTATIVE = ["bakery", "hotel", "friseur", "catering", "online_shop", "aktionen"]

# Owner-only пути без записи в навигации — с причиной (POST-приёмники и выгрузки).
EXPECTED_OWNER_ONLY_UNLISTED = {
    "/dashboard/verkaeufe/export.csv": "CSV продаж — кнопка в тулбаре списка (KA-12 E2.2)",
    "/dashboard/channels/config/": "POST-приёмник настроек канала",
    "/dashboard/channels/connect/": "POST-приёмник подключения канала",
    "/dashboard/channels/toggle/": "POST-приёмник вкл/выкл канала",
    "/dashboard/settings/notifications/telegram/": "POST-приёмник ссылки на общий бот",
    "/dashboard/integrationen/telegram-aktivieren/": "POST-приёмник включения модуля",
    "/dashboard/telegram/connect/": "POST-приёмник токена своего бота",
    "/dashboard/telegram/disconnect/": "POST-приёмник отключения своего бота",
    "/crm/export.csv": "кнопка выгрузки на экране CRM, не пункт меню",
    "/dashboard/stays/berichte/export.csv": "кнопка выгрузки на экране отчётов",
    "/imports/website/": "вход из экрана импорта",
    "/dashboard/geschaeft/": "лёгкий кабинет: пункт своего меню (lite_cabinet)",
    "/dashboard/channels/google/": "вход с экрана каналов",
    "/dashboard/erstattung/": "POST-приёмник частичного возврата с карточки сделки (B2-4)",
}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(kind):
    business_type = "other" if kind == "aktionen" else kind
    tenant = TenantFactory(
        slug=f"sw-{kind[:8]}-{uuid4().hex[:4]}",
        name="SW",
        business_type=business_type,
        disabled_modules=modules.default_disabled_for(business_type),
        bank_iban="DE89370400440532013000",
    )
    if kind == "aktionen":
        tenant.site_config = {**(tenant.site_config or {}), "profile": "aktionen"}
        tenant.save(update_fields=["site_config"])
    return tenant


def _user(role):
    user = get_user_model().objects.create_user(
        username=f"sw-{role}-{uuid4().hex[:6]}", password="pw12345678"
    )
    Membership.objects.create(user=user, role=role)
    return user


def _open(path, tenant, user, method="get", data=None):
    """Путь через мидлварь ролей → вьюха, как в браузере."""
    request = getattr(RequestFactory(), method)(path, data or {})
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    MessageMiddleware(lambda r: None).process_request(request)
    request._dont_enforce_csrf_checks = True
    request.user = user
    request.tenant = tenant

    middleware = CabinetOwnerAccessMiddleware(None)

    def view(req):
        # Как в Django: __call__ (пол) → resolve → process_view (право маршрута) → вьюха.
        try:
            match = resolve(path.split("?")[0])
        except Resolver404:
            return HttpResponseNotFound()
        req.resolver_match = match
        denied = middleware.process_view(req, match.func, match.args, match.kwargs)
        if denied is not None:
            return denied
        return match.func(req, *match.args, **match.kwargs)

    middleware.get_response = view
    return middleware(request)


def _screens(tenant, user):
    """Беспараметрные экраны, которые этот пользователь видит в навигации и палитре."""
    names = set()
    for item in modules.sidebar_nav(tenant, user):
        names.add(item["url_name"])
        names.update(child["url_name"] for child in item["children"])
    for entry in nav_registry.palette_entries():
        mod = entry["module_key"]
        if mod is not None and not modules.is_module_active(tenant, mod):
            continue
        if nav_registry.allowed_for_business(entry["url_name"], tenant):
            names.add(entry["url_name"])
    paths = {}
    for name in names:
        path = reverse(name)
        spec = modules.module_for_path(path)
        if spec is None or modules.is_module_active(tenant, spec.key):
            paths[name] = path
    return paths


# --- источник истины ---------------------------------------------------------------


def test_middleware_floor_is_part_of_yesterdays_owner_zone():
    for prefix in CabinetOwnerAccessMiddleware._OWNER_FLOOR:
        assert prefix.startswith(LG.LEGACY_OWNER_ONLY_PREFIXES), prefix


def test_owner_only_nav_entries_match_middleware():
    """owner_only-запись навигации ⇔ путь под owner-префиксом (или объяснённое исключение)."""
    for name in nav_registry.owner_only_url_names():
        path = reverse(name)
        assert LG.legacy_role_for_path(path) == LG.ROLE_OWNER_ONLY, (
            f"{name} помечен owner_only, но мидлварь его не закрывает: {path}"
        )
    covered = {reverse(name) for name in nav_registry.owner_only_url_names()}
    for prefix in LG.LEGACY_OWNER_ONLY_PREFIXES:
        if any(path.startswith(prefix) for path in covered):
            continue
        assert prefix in EXPECTED_OWNER_ONLY_UNLISTED, (
            f"owner-only префикс {prefix} без owner_only-записи и без причины в списке"
        )


def _walk_patterns(patterns, prefix=""):
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from _walk_patterns(p.url_patterns, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            yield prefix + str(p.pattern), p.callback


def test_perm_decorated_views_match_their_route_rule():
    """`@perm_required(key)` обязан совпадать с правилом маршрута в view_perms."""
    problems = []
    for route, callback in _walk_patterns(get_resolver("config.urls_tenant").url_patterns):
        key = getattr(callback, "_required_perm", "")
        if not key:
            continue
        name = resolve("/" + route.replace("<uuid:pk>", str(uuid4()))).view_name
        rule = view_perms.rule_for(name)
        if rule is None or key not in (rule.read, rule.write):
            problems.append(f"{name}: декоратор {key}, правило {rule}")
    assert problems == []


def test_decorated_list_of_yesterday_is_still_guarded_on_the_view():
    """Пути с uuid middleware по префиксу не видел — гейт был на вьюхе; он остаётся там."""
    by_name = {}
    for route, callback in _walk_patterns(get_resolver("config.urls_tenant").url_patterns):
        if getattr(callback, "_required_perm", ""):
            try:
                name = resolve("/" + route.replace("<uuid:pk>", str(uuid4()))).view_name
            except Exception:  # noqa: BLE001 — путь с другими параметрами
                continue
            by_name[name] = callback._required_perm
    assert set(LG.LEGACY_DECORATED) <= set(by_name), set(LG.LEGACY_DECORATED) - set(by_name)


# --- обход экранов -----------------------------------------------------------------


@pytest.mark.parametrize("kind", REPRESENTATIVE)
@pytest.mark.parametrize("role", [Membership.ROLE_STAFF, Membership.ROLE_ADMIN])
def test_staff_and_admin_walk(kind, role):
    tenant = _tenant(kind)
    user = _user(role)
    screens = _screens(tenant, user)
    assert len(screens) >= 5, f"{kind}: обход пустой — замок ничего бы не проверил"
    bad = []
    for name, path in sorted(screens.items()):
        required = LG.legacy_role_for_path(path)
        response = _open(path, tenant, user)
        status = response.status_code
        if required == LG.ROLE_OWNER_ONLY:
            expected_ok = status == 403
        elif required == LG.ROLE_FINANCE:
            expected_ok = status == (200 if role == Membership.ROLE_ADMIN else 403)
        else:
            location = response.get("Location", "") if status == 302 else ""
            # 302 на логин у вошедшего пользователя = сломанная сессия или вьюха.
            expected_ok = status == 200 or (status == 302 and settings.LOGIN_URL not in location)
        if not expected_ok:
            bad.append(f"{name} {path} → {status} (нужно: {required or 'открыто'})")
    assert bad == [], f"{kind}/{role}: " + "; ".join(bad)


@pytest.mark.parametrize("kind", REPRESENTATIVE)
def test_staff_nav_hides_owner_only(kind):
    tenant = _tenant(kind)
    staff = _user(Membership.ROLE_STAFF)
    visible = set()
    for item in modules.sidebar_nav(tenant, staff):
        visible.add(item["url_name"])
        visible.update(child["url_name"] for child in item["children"])
    leaked = {n for n in visible if LG.legacy_role_for_path(reverse(n))}
    assert leaked == set()


@pytest.mark.parametrize("kind", REPRESENTATIVE)
def test_staff_pages_show_no_owner_data(kind):
    """На открытых сотруднику страницах — ни IBAN бизнеса, ни ссылок в owner-only зону."""
    tenant = _tenant(kind)
    staff = _user(Membership.ROLE_STAFF)
    leaks = []
    for name, path in sorted(_screens(tenant, staff).items()):
        if LG.legacy_role_for_path(path):
            continue
        resp = _open(path, tenant, staff)
        if resp.status_code != 200 or not hasattr(resp, "content"):
            continue
        body = resp.content.decode(errors="ignore")
        if "DE89370400440532013000" in body or "DE89 3704" in body:
            leaks.append(f"{name}: IBAN")
        for prefix in LG.LEGACY_OWNER_ONLY_PREFIXES:
            if f'href="{prefix}' in body or f"href='{prefix}" in body:
                leaks.append(f"{name}: ссылка {prefix}")
    assert leaks == [], f"{kind}: " + "; ".join(leaks)


@pytest.mark.parametrize("prefix", LG.LEGACY_OWNER_ONLY_PREFIXES)
def test_staff_post_to_owner_only_is_rejected(prefix):
    tenant = _tenant("bakery")
    staff = _user(Membership.ROLE_STAFF)
    before = (tenant.name, tenant.bank_iban, dict(tenant.site_config or {}))
    # Мидлварь отвечает 403 раньше маршрута — проверяем и префиксы без своего маршрута.
    resp = _open(prefix, tenant, staff, method="post", data={"name": "Übernommen"})
    # E6.7c-4: префикс без своего маршрута — 404 (права живут на маршрутах), иначе 403.
    assert resp.status_code in (403, 404)
    tenant.refresh_from_db()
    assert (tenant.name, tenant.bank_iban, dict(tenant.site_config or {})) == before
