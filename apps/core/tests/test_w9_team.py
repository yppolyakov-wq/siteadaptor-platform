"""W9-10 (Р-7, аудит 2026-08-05): «Team & Zugriff» — членства/роли/инвайт + owner-гейт.

Замки плана §2: staff не открывает billing/Recht/Team (middleware, fail-closed
для реального HTTP); последний owner неудаляем/непонижаем; инвайт-токен
одноразовый с TTL; принятие создаёт User+Membership и логинит.
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core import team
from apps.core.middleware import CabinetOwnerAccessMiddleware
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _user(role=None):
    o = uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"u-{o}@t.de", email=f"u-{o}@t.de", password="pw12345678"
    )
    if role:
        Membership.objects.create(user=user, role=role)
    return user


def _req(path="/dashboard/settings/team/", method="get", data=None, user=None, tenant=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user or _user(Membership.ROLE_OWNER)
    req.tenant = tenant or TenantFactory(business_type="restaurant")
    return req


# --- owner-only гейт (middleware) ---------------------------------------------
def test_middleware_blocks_staff_on_owner_only_paths():
    mw = CabinetOwnerAccessMiddleware(lambda r: HttpResponse("ok"))
    tenant = TenantFactory(business_type="restaurant")
    staff = _user(Membership.ROLE_STAFF)
    for path in ("/dashboard/billing/", "/dashboard/recht/", "/dashboard/settings/team/"):
        resp = mw(_req(path, user=staff, tenant=tenant))
        assert resp.status_code == 403, path
    # обычный кабинет staff доступен
    assert mw(_req("/dashboard/", user=staff, tenant=tenant)).status_code == 200


def test_middleware_allows_owner_on_owner_only_paths():
    mw = CabinetOwnerAccessMiddleware(lambda r: HttpResponse("ok"))
    tenant = TenantFactory(business_type="restaurant")
    owner = _user(Membership.ROLE_OWNER)
    for path in ("/dashboard/billing/", "/dashboard/recht/", "/dashboard/settings/team/"):
        assert mw(_req(path, user=owner, tenant=tenant)).status_code == 200, path


# --- инвайт: одноразовость/TTL/валидация ---------------------------------------
def test_invite_token_one_shot_and_validation():
    assert team.issue_invite("kein-mail", Membership.ROLE_STAFF) is None
    assert team.issue_invite("a@b.de", Membership.ROLE_OWNER) is None  # owner нельзя
    token = team.issue_invite("Neu@Example.de", Membership.ROLE_STAFF)
    assert token
    assert team.peek_invite(token) == {"email": "neu@example.de", "role": "staff"}
    assert team.consume_invite(token) == {"email": "neu@example.de", "role": "staff"}
    assert team.consume_invite(token) is None  # одноразовость
    assert team.peek_invite(token) is None


# --- принятие: User+Membership+login -------------------------------------------
def test_join_creates_user_membership_and_logs_in():
    tenant = TenantFactory(business_type="restaurant")
    token = team.issue_invite("crew@example.de", Membership.ROLE_STAFF)
    req = _req(
        f"/team/beitreten/{token}/",
        "post",
        {"password1": "geheim123", "password2": "geheim123"},
        user=_user(),  # аноним не нужен — вьюха логинит присоединившегося
        tenant=tenant,
    )
    resp = team.team_join(req, token)
    assert resp.status_code == 302 and resp["Location"] == "/dashboard/"
    joined = get_user_model().objects.get(username="crew@example.de")
    assert joined.membership.role == Membership.ROLE_STAFF
    # повторное использование того же токена — ссылка мертва
    resp = team.team_join(_req(f"/team/beitreten/{token}/", tenant=tenant), token)
    assert resp.status_code == 404


def test_join_weak_password_rejected():
    tenant = TenantFactory(business_type="restaurant")
    token = team.issue_invite("crew2@example.de", Membership.ROLE_ADMIN)
    resp = team.team_join(
        _req(
            f"/team/beitreten/{token}/",
            "post",
            {"password1": "kurz", "password2": "kurz"},
            tenant=tenant,
        ),
        token,
    )
    assert resp.status_code == 200  # форма с ошибкой, токен НЕ израсходован
    assert team.peek_invite(token) is not None


# --- guard'ы последнего owner ---------------------------------------------------
def test_last_owner_cannot_be_revoked_or_demoted():
    tenant = TenantFactory(business_type="restaurant")
    owner = _user(Membership.ROLE_OWNER)
    m = owner.membership
    team.team_view(
        _req(
            method="post",
            data={"action": "revoke", "membership_id": m.pk},
            user=owner,
            tenant=tenant,
        )
    )
    assert Membership.objects.filter(pk=m.pk).exists()  # жив
    team.team_view(
        _req(
            method="post",
            data={"action": "role", "membership_id": m.pk, "role": "staff"},
            user=owner,
            tenant=tenant,
        )
    )
    m.refresh_from_db()
    assert m.role == Membership.ROLE_OWNER  # не понижен


def test_second_owner_allows_role_change_and_revoke():
    tenant = TenantFactory(business_type="restaurant")
    owner = _user(Membership.ROLE_OWNER)
    second = _user(Membership.ROLE_OWNER)
    m2 = second.membership
    team.team_view(
        _req(
            method="post",
            data={"action": "role", "membership_id": m2.pk, "role": "admin"},
            user=owner,
            tenant=tenant,
        )
    )
    m2.refresh_from_db()
    assert m2.role == Membership.ROLE_ADMIN
    team.team_view(
        _req(
            method="post",
            data={"action": "revoke", "membership_id": m2.pk},
            user=owner,
            tenant=tenant,
        )
    )
    assert not Membership.objects.filter(pk=m2.pk).exists()
    assert get_user_model().objects.filter(pk=second.pk).exists()  # User остаётся


def test_team_page_renders_members_and_invite_form():
    owner = _user(Membership.ROLE_OWNER)
    body = team.team_view(_req(user=owner)).content.decode()
    assert owner.email in body
    assert 'name="action" value="invite"' in body
    assert "letzter Inhaber" in body  # единственный owner защищён и помечен
