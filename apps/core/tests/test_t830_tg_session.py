"""T-8.30: вход из Telegram Mini App — сессия только в лёгкие экраны (план t8-30 §1.4–1.5)."""

import time
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache.backends.locmem import LocMemCache
from django.http import Http404, HttpResponse
from django.test import RequestFactory
from django.urls import resolve, reverse

from apps.core import lite_cabinet, owner_login, tg_login
from apps.core.middleware import TelegramLiteScopeMiddleware
from apps.core.models import Membership
from apps.platform_bot import links
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
UID = 515151


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr("django_tenants.models.schema_exists", lambda name: True)
    store = LocMemCache(f"tg-session-{uuid.uuid4()}", {})
    monkeypatch.setattr(tg_login, "cache", store)
    from apps.core import ratelimit

    monkeypatch.setattr(ratelimit, "cache", LocMemCache(f"rl-{uuid.uuid4()}", {}))


def _tenant(lite=False):
    slug = f"tgs-{uuid.uuid4().hex[:6]}"
    t = TenantFactory(schema_name=slug.replace("-", "_"), slug=slug, name="Krume")
    t.site_config = {"profile": "aktionen"} if lite else {}
    t.save()
    return t


def _owner(role=Membership.ROLE_OWNER):
    o = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(username=f"tgs-{o}", password="pw12345678")
    Membership.objects.create(user=user, role=role)
    return user


def _req(tenant, method="get", path="/tg/start/x/", user=None):
    rf = RequestFactory()
    req = rf.post(path, {}) if method == "post" else rf.get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    req.user = user or AnonymousUser()
    req.COOKIES["sessionid"] = "stand-cookie"  # is_tg_session читает сессию только с кукой
    return req


def _linked():
    t = _tenant()
    user = _owner()
    links.bind(UID, t, user_pk=user.pk)
    return t, user


def _start(t, user, method="post"):
    token = tg_login.issue(t.schema_name, user.pk, UID, lang="ru")
    req = _req(t, method, f"/tg/start/{token}/")
    return token, req, tg_login.tg_start(req, token)


# --- передача и вход ---------------------------------------------------------------------


def test_get_does_not_consume():
    t, user = _linked()
    token = tg_login.issue(t.schema_name, user.pk, UID)
    resp = tg_login.tg_start(_req(t), token)
    assert resp.status_code == 200 and tg_login.peek(t.schema_name, token)


def test_post_logs_in_with_flag_and_12h_expiry():
    t, user = _linked()
    _token, req, resp = _start(t, user)
    assert resp.status_code == 302 and resp.url == "/dashboard/"
    assert req.user.pk == user.pk
    flag = req.session[tg_login.SESSION_KEY]
    assert flag["uid"] == UID and flag["exp"] > time.time() + 11 * 3600
    assert req.session.get_expiry_age() == 12 * 3600
    assert req.session["cabinet_lang"] == "ru"
    assert req.session.get("_schema") is not None


def test_token_single_use():
    t, user = _linked()
    token, _req1, _resp = _start(t, user)
    with pytest.raises(Http404):
        tg_login.tg_start(_req(t, "post"), token)


def test_token_bound_to_schema():
    t, user = _linked()
    token = tg_login.issue("other_schema", user.pk, UID)
    with pytest.raises(Http404):
        tg_login.tg_start(_req(t, "post"), token)


def test_email_token_not_accepted_and_vice_versa(monkeypatch):
    t, user = _linked()
    monkeypatch.setattr(owner_login, "cache", tg_login.cache)
    mail_token = owner_login.issue_token(t.schema_name, "x@example.com")
    with pytest.raises(Http404):
        tg_login.tg_start(_req(t, "post"), mail_token)
    tg_token = tg_login.issue(t.schema_name, user.pk, UID)
    with pytest.raises(Http404):
        owner_login.owner_start(_req(t, "post"), tg_token)


def test_demoted_between_issue_and_post():
    t, user = _linked()
    token = tg_login.issue(t.schema_name, user.pk, UID)
    Membership.objects.filter(user=user).update(role=Membership.ROLE_STAFF)
    with pytest.raises(Http404):
        tg_login.tg_start(_req(t, "post"), token)


def test_unlinked_between_issue_and_post():
    t, user = _linked()
    token = tg_login.issue(t.schema_name, user.pk, UID)
    links.unbind(t)
    with pytest.raises(Http404):
        tg_login.tg_start(_req(t, "post"), token)


def test_malformed_token_404_without_cache_lookup():
    t, _user = _linked()
    assert tg_login.tg_start(_req(t), "../../x").status_code == 404


def test_other_login_drops_flag():
    t, user = _linked()
    _token, req, _resp = _start(t, user)
    from django.contrib.auth import login

    login(req, user, backend="django.contrib.auth.backends.ModelBackend")
    assert tg_login.SESSION_KEY not in req.session


# --- граница доступа ---------------------------------------------------------------------


def _tg_request(t, user, path, method="get", **headers):
    req = _req(t, method, path, user=user)
    for key, value in headers.items():
        req.META[key] = value
    req.session[tg_login.SESSION_KEY] = {"uid": UID, "exp": int(time.time()) + 3600}
    req.resolver_match = resolve(path)
    return req


def _scope(req):
    mw = TelegramLiteScopeMiddleware(lambda r: HttpResponse("ok"))
    return mw.process_view(req, req.resolver_match.func, (), req.resolver_match.kwargs)


@pytest.mark.parametrize(
    "name",
    [
        "dashboard",
        "lite-business",
        "lite-share",
        "lite-visibility",
        "sellable-manage",
        "promotions:promotion-list",
        "promotions:promotion-quick",
        "catalog:product-create",
        "promotions:reservation-list",  # T-8.30e: касса
        "promotions:redeem",
    ],
)
def test_lite_screens_allowed(name):
    t, user = _linked()
    assert _scope(_tg_request(t, user, reverse(name))) is None


@pytest.mark.parametrize(
    "path",
    [
        "/dashboard/settings/",
        "/dashboard/billing/",
        "/dashboard/settings/team/",
        "/dashboard/integrationen/",
        "/imports/website/",
        "/dashboard/verkaeufe/",
        "/dashboard/site/home/",
        "/catalog/categories/",
    ],
)
def test_other_cabinet_screens_redirect_to_info(path):
    t, user = _linked()
    resp = _scope(_tg_request(t, user, path))
    assert resp.status_code == 302 and resp.url == reverse("tg-lite-info")


@pytest.mark.parametrize(
    "path", ["/dashboard/integrationen/telegram-aktivieren/", "/dashboard/telegram/connect/"]
)
def test_bot_management_post_refused(path):
    t, user = _linked()
    resp = _scope(_tg_request(t, user, path, method="post"))
    assert resp.status_code == 302 and resp.url == reverse("tg-lite-info")


@pytest.mark.parametrize(
    "path,method",
    [
        ("/promotions/redeem/R-ABC123/", "get"),
        ("/promotions/redeem/R-ABC123/action/", "post"),
        ("/promotions/reservations/00000000-0000-4000-8000-000000000001/action/", "post"),
    ],
)
def test_counter_screens_with_args_allowed(path, method):
    """T-8.30e: касса (резервы, погашение) открыта в Telegram."""
    t, user = _linked()
    assert _scope(_tg_request(t, user, path, method=method)) is None


def test_staff_cannot_use_counter_in_tg():
    t, user = _linked()
    Membership.objects.filter(user=user).update(role=Membership.ROLE_STAFF)
    resp = _scope(_tg_request(t, user, "/promotions/redeem/"))
    assert resp.url.endswith("?grund=beendet")


def test_fetch_gets_json_403():
    t, user = _linked()
    req = _tg_request(t, user, "/dashboard/palette-search/", HTTP_ACCEPT="application/json")
    resp = _scope(req)
    assert resp.status_code == 403 and b"tg_lite" in resp.content


def test_unknown_authenticated_view_sees_anonymous():
    t, user = _linked()
    req = _tg_request(t, user, "/team/beitreten/abc/")
    assert _scope(req) is None and not req.user.is_authenticated


def test_whitelist_names_resolve():
    """Каждое имя списка существует (опечатка = экран тихо закрыт)."""
    from django.urls import NoReverseMatch

    for name in tg_login.TG_LITE_VIEWS:
        try:
            reverse(name)
        except NoReverseMatch as exc:
            if "with no arguments" not in str(exc) and "arguments '()'" not in str(exc):
                pytest.fail(f"unknown view name {name}")


def test_expired_session_logged_out():
    t, user = _linked()
    req = _tg_request(t, user, "/dashboard/")
    req.session[tg_login.SESSION_KEY]["exp"] = int(time.time()) - 1
    resp = _scope(req)
    assert resp.url.endswith("?grund=abgelaufen") and not req.user.is_authenticated


@pytest.mark.parametrize("revoke", ["unbind", "block", "restrict", "demote"])
def test_revocation_ends_session(revoke, monkeypatch):
    t, user = _linked()
    if revoke == "unbind":
        links.unbind(t)
    elif revoke == "block":
        links.mark_blocked(UID)
    elif revoke == "restrict":
        monkeypatch.setattr("apps.platform_bot.rights.is_restricted", lambda uid: True)
    else:
        Membership.objects.filter(user=user).update(role=Membership.ROLE_STAFF)
    resp = _scope(_tg_request(t, user, "/dashboard/"))
    assert resp.url.endswith("?grund=beendet")


def test_normal_session_untouched():
    t, user = _linked()
    req = _req(t, path="/dashboard/settings/", user=user)
    req.resolver_match = resolve("/dashboard/settings/")
    assert _scope(req) is None and req.user.is_authenticated


def test_full_cabinet_tenant_sees_lite_in_tg_session():
    """Р-5: у полного кабинета в Telegram — те же лёгкие экраны."""
    from apps.core import views

    t, user = _linked()
    from apps.tenants import onboarding

    onboarding.mark_complete(t)
    req = _tg_request(t, user, "/dashboard/")
    assert lite_cabinet.is_lite_request(req)
    body = views.dashboard(req).content.decode()
    assert "data-lite-home" in body
    plain = _req(t, path="/dashboard/", user=user)
    assert not lite_cabinet.is_lite_request(plain)


def test_visibility_hides_bot_management_in_tg_session():
    t, user = _linked()
    t.disabled_modules = ["telegram"]
    t.save()
    body = lite_cabinet.lite_visibility(
        _tg_request(t, user, "/dashboard/sichtbarkeit/")
    ).content.decode()
    assert "/dashboard/integrationen/telegram-aktivieren/" not in body
    assert "data-own-bot-email-only" in body
    plain = _req(t, path="/dashboard/sichtbarkeit/", user=user)
    assert "/dashboard/integrationen/telegram-aktivieren/" in (
        lite_cabinet.lite_visibility(plain).content.decode()
    )


def test_info_page_renders():
    t, _user = _linked()
    req = _req(t, path="/tg/nur-in-der-app/?grund=beendet")
    body = tg_login.tg_lite_info(req).content.decode()
    assert 'data-tg-lite-info="beendet"' in body and "/anmelden/link/" in body


def test_info_page_speaks_cabinet_language():
    """Путь не кабинетный — язык берётся из выбора кабинета в сессии (стенд: был язык браузера)."""
    t, _user = _linked()
    req = _req(t, path="/tg/nur-in-der-app/")
    req.session["cabinet_lang"] = "ru"
    body = tg_login.tg_lite_info(req).content.decode()
    from django.utils import translation

    with translation.override("ru"):
        expected = translation.gettext("Mit E-Mail anmelden")
    assert expected in body


# Ссылки лёгких экранов, которые в Telegram ОСОЗНАННО ведут на «nur per E-Mail»:
# настройки/деньги/интеграции (Р-2); касса с T-8.30e — в белом списке. Новая ссылка с лёгкого
# экрана обязана попасть либо в белый список, либо сюда — иначе тест красный.
EMAIL_ONLY = {
    "integrations-home",
    "gbp-sync",
    "notifications-settings",
    "payment-settings",
    "domains",
    "portal-stats",
    "settings",
    "modules",
    "languages",
    "site-home",
    "owner-login-link",
    "telegram-settings",
}


def _links_of(body):
    import re

    found = set()
    for raw in re.findall(r'(?:href|action)="(/[^"#?]*)', body):
        if raw.startswith("//") or raw.startswith(("/static/", "/media/")):
            continue
        found.add(raw)
    return found


def test_lite_screens_link_only_to_allowed_or_email_only():
    """Ревью: каждая ссылка/форма лёгкого экрана в Telegram резолвится в белый список
    или в осознанный список «только по e-mail» (без немых редиректов на info)."""
    from django.urls import Resolver404

    from apps.core import views
    from apps.core.i18n_cabinet import CABINET_PREFIXES
    from apps.promotions import views as promo_views
    from apps.tenants import onboarding

    t, user = _linked()
    t.site_config = {"profile": "aktionen"}
    t.save()
    onboarding.mark_complete(t)
    from apps.loyalty.models import Voucher
    from apps.promotions import services
    from apps.promotions.tests.factories import PromotionFactory

    promo = PromotionFactory(status="active", title={"de": "Brot"}, available_quantity=5)
    res = services.reserve(promo, name="Anna", email="anna@test.de")
    Voucher.objects.create(code="C-TEST01", label="Brot", promotion=promo, max_uses=1)
    screens = {
        "/dashboard/": views.dashboard,
        "/dashboard/sichtbarkeit/": lite_cabinet.lite_visibility,
        "/promotions/": promo_views.promotion_list,
        "/promotions/reservations/": promo_views.reservation_list,
        "/promotions/redeem/": promo_views.redeem_home,
    }
    detail = {
        f"/promotions/redeem/{res.reference_code}/": res.reference_code,
        "/promotions/redeem/C-TEST01/": "C-TEST01",
        "/promotions/redeem/R-NOPE00/": "R-NOPE00",
    }
    stray = set()
    bodies = [(p, v(_tg_request(t, user, p)).content.decode()) for p, v in screens.items()]
    bodies += [
        (p, promo_views.redeem_detail(_tg_request(t, user, p), c).content.decode())
        for p, c in detail.items()
    ]
    for path, body in bodies:
        for link in _links_of(body):
            try:
                name = resolve(link).view_name
            except Resolver404:
                continue
            if not link.startswith(CABINET_PREFIXES) and name not in tg_login.TG_LITE_VIEWS:
                continue
            if name not in tg_login.TG_LITE_VIEWS and name not in EMAIL_ONLY:
                stray.add((path, name))
    assert not stray


def test_fetch_without_json_header_gets_403_not_html():
    t, user = _linked()
    req = _tg_request(t, user, "/dashboard/settings/", HTTP_SEC_FETCH_MODE="cors")
    assert _scope(req).status_code == 403


def test_email_login_after_tg_restores_normal_expiry():
    t, user = _linked()
    _token, req, _resp = _start(t, user)
    from django.contrib.auth import login

    login(req, user, backend="django.contrib.auth.backends.ModelBackend")
    assert "_session_expiry" not in req.session


def test_untouched_wizard_does_not_redirect_tg_session():
    from apps.core import views

    t, user = _linked()
    t.site_config = {"profile": "aktionen"}
    t.save()
    resp = views.dashboard(_tg_request(t, user, "/dashboard/"))
    assert resp.status_code == 200
