"""KA-12 E11.2: сценарий «сотрудник» на каждом экране кабинета.

План — docs/ka-12-e11-checks-plan-2026-10-23.md. Политика (решение владельца 2026-08-06):
admin и staff пока одинаковы; owner-only — пути `roles.OWNER_ONLY_PREFIXES` и вьюхи под
`@owner_required`; финансовые выгрузки — owner + admin. Ожидания тест выводит из этих
источников, а не прописывает руками: новый owner-only экран не требует правки замка.

Экран открываем так же, как браузер: путь → мидлвари доступа → вьюха по `resolve()`.
"""

from importlib import import_module
from uuid import uuid4

import pytest
from django.conf import settings
from django.conf import settings as dj_settings
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.test import RequestFactory
from django.urls import URLPattern, URLResolver, get_resolver, resolve, reverse

from apps.core import modules, nav_registry, roles
from apps.core.middleware import CabinetOwnerAccessMiddleware
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

# Представительные типы: товар, номера, запись, заявки, онлайн-магазин, лёгкая ступень.
REPRESENTATIVE = ["bakery", "hotel", "friseur", "catering", "online_shop", "aktionen"]

# Owner-only пути без записи в навигации — с причиной (POST-приёмники и выгрузки).
EXPECTED_OWNER_ONLY_UNLISTED = {
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

    def view(req):
        # resolve — ПОСЛЕ мидлвари, как в Django: роль проверяется раньше маршрута.
        match = resolve(path.split("?")[0])
        req.resolver_match = match
        return match.func(req, *match.args, **match.kwargs)

    return CabinetOwnerAccessMiddleware(view)(request)


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


def test_middleware_reads_the_single_source():
    assert CabinetOwnerAccessMiddleware._OWNER_ONLY is roles.OWNER_ONLY_PREFIXES
    assert CabinetOwnerAccessMiddleware._FINANCE_EXPORTS is roles.FINANCE_EXPORT_PREFIXES


def test_owner_only_nav_entries_match_middleware():
    """owner_only-запись навигации ⇔ путь под owner-префиксом (или объяснённое исключение)."""
    for name in nav_registry.owner_only_url_names():
        path = reverse(name)
        assert roles.required_role_for_path(path) == roles.ROLE_OWNER_ONLY, (
            f"{name} помечен owner_only, но мидлварь его не закрывает: {path}"
        )
    covered = {reverse(name) for name in nav_registry.owner_only_url_names()}
    for prefix in roles.OWNER_ONLY_PREFIXES:
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


def test_role_decorated_views_are_declared():
    """Вьюха под `owner_required`/`finance_export_required` либо лежит под префиксом
    той же роли, либо имеет параметр в пути (uuid) — тогда гейт держит только декоратор."""
    problems = []
    for route, callback in _walk_patterns(get_resolver("config.urls_tenant").url_patterns):
        required = getattr(callback, "_required_role", "")
        if not required:
            continue
        if "<" in route:
            continue  # путь с параметром — middleware его не видит, гейт в декораторе
        path = "/" + route
        if roles.required_role_for_path(path) != required:
            problems.append(f"{path}: декоратор требует {required}, префикса нет")
    assert problems == []


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
        required = roles.required_role_for_path(path)
        response = _open(path, tenant, user)
        status = response.status_code
        if required == roles.ROLE_OWNER_ONLY:
            expected_ok = status == 403
        elif required == roles.ROLE_FINANCE:
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
    leaked = {n for n in visible if roles.required_role_for_path(reverse(n))}
    assert leaked == set()


@pytest.mark.parametrize("kind", REPRESENTATIVE)
def test_staff_pages_show_no_owner_data(kind):
    """На открытых сотруднику страницах — ни IBAN бизнеса, ни ссылок в owner-only зону."""
    tenant = _tenant(kind)
    staff = _user(Membership.ROLE_STAFF)
    leaks = []
    for name, path in sorted(_screens(tenant, staff).items()):
        if roles.required_role_for_path(path):
            continue
        resp = _open(path, tenant, staff)
        if resp.status_code != 200 or not hasattr(resp, "content"):
            continue
        body = resp.content.decode(errors="ignore")
        if "DE89370400440532013000" in body or "DE89 3704" in body:
            leaks.append(f"{name}: IBAN")
        for prefix in roles.OWNER_ONLY_PREFIXES:
            if f'href="{prefix}' in body or f"href='{prefix}" in body:
                leaks.append(f"{name}: ссылка {prefix}")
    assert leaks == [], f"{kind}: " + "; ".join(leaks)


@pytest.mark.parametrize("prefix", roles.OWNER_ONLY_PREFIXES)
def test_staff_post_to_owner_only_is_rejected(prefix):
    tenant = _tenant("bakery")
    staff = _user(Membership.ROLE_STAFF)
    before = (tenant.name, tenant.bank_iban, dict(tenant.site_config or {}))
    # Мидлварь отвечает 403 раньше маршрута — проверяем и префиксы без своего маршрута.
    resp = _open(prefix, tenant, staff, method="post", data={"name": "Übernommen"})
    assert resp.status_code == 403
    tenant.refresh_from_db()
    assert (tenant.name, tenant.bank_iban, dict(tenant.site_config or {})) == before
