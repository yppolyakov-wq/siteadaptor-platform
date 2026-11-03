"""UX-D D6.6: Team — список строками, страница участника, страница приглашения.

Раньше роль менялась select'ом с автосабмитом (WCAG 3.2.2), права каждого участника были
`<details>` на общей странице, приглашение — раскрытая форма рядом со списком."""

import re
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.core import team
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
OWNER, ADMIN, STAFF = Membership.ROLE_OWNER, Membership.ROLE_ADMIN, Membership.ROLE_STAFF


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _member(role, perms=None):
    o = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"tp-{o}@t.de", email=f"tp-{o}@t.de", password="pw12345678"
    )
    return Membership.objects.create(user=user, role=role, permissions=perms or {})


def _req(user, method="get", data=None, path="/dashboard/settings/team/"):
    req = getattr(RequestFactory(), method)(
        path, data or {}, REMOTE_ADDR=f"10.9.{uuid.uuid4().int % 250}.1"
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user
    req.tenant = TenantFactory(business_type="restaurant")
    return req


def test_list_rows_link_to_member_pages_without_forms():
    owner, staff = _member(OWNER), _member(STAFF)
    html = team.team_view(_req(owner.user)).content.decode()
    rows = re.findall(r"<a [^>]*data-member-row>.*?</a>", html, re.S)
    assert len(rows) == 2 and all("<input" not in r and "<select" not in r for r in rows)
    assert f'href="/dashboard/settings/team/{staff.pk}/"' in html
    assert '<select id="role-' not in html  # роль с автосабмитом onchange снята (WCAG 3.2.2)


def test_member_page_role_buttons_change_role():
    owner, staff = _member(OWNER), _member(STAFF)
    html = team.team_member(_req(owner.user), pk=staff.pk).content.decode()
    assert 'name="role" onchange' not in html and '<select id="role-' not in html
    assert re.search(r'<button type="submit" name="role" value="admin"', html)
    team.team_member(
        _req(owner.user, "post", {"action": "role", "membership_id": str(staff.pk), "role": ADMIN}),
        pk=staff.pk,
    )
    staff.refresh_from_db()
    assert staff.role == ADMIN


def test_member_page_revoke_goes_back_to_list_and_needs_confirmation():
    owner, staff = _member(OWNER), _member(STAFF)
    html = team.team_member(_req(owner.user), pk=staff.pk).content.decode()
    form = html.split('value="revoke"', 1)[1].split("</form>", 1)[0]
    assert 'data-danger="1"' in form
    resp = team.team_member(
        _req(owner.user, "post", {"action": "revoke", "membership_id": str(staff.pk)}), pk=staff.pk
    )
    assert (
        resp.url == "/dashboard/settings/team/"
        and not Membership.objects.filter(pk=staff.pk).exists()
    )


def test_member_page_foreign_id_in_post_is_404():
    owner, a, b = _member(OWNER), _member(STAFF), _member(STAFF)
    with pytest.raises(Http404):
        team.team_member(
            _req(owner.user, "post", {"action": "revoke", "membership_id": str(b.pk)}), pk=a.pk
        )
    assert Membership.objects.filter(pk=b.pk).exists()


def test_staff_without_team_edit_cannot_act_on_member_page():
    owner = _member(OWNER)
    staff = _member(STAFF, {"add": ["team.view"]})
    team.team_member(
        _req(staff.user, "post", {"action": "revoke", "membership_id": str(owner.pk)}), pk=owner.pk
    )
    assert Membership.objects.filter(pk=owner.pk).exists()


def test_unknown_member_is_404():
    owner = _member(OWNER)
    with pytest.raises(Http404):
        team.team_member(_req(owner.user), pk=uuid.uuid4())


def test_invite_page_issues_token_and_returns_to_list():
    owner = _member(OWNER)
    resp = team.team_invite(
        _req(
            owner.user,
            "post",
            {"action": "invite", "email": "neu@t.de", "role": STAFF},
            path="/dashboard/settings/team/einladen/",
        )
    )
    assert resp.status_code == 302 and resp.url == "/dashboard/settings/team/"


def test_invite_page_respects_unconfirmed_email():
    owner = _member(OWNER)
    req = _req(owner.user, "post", {"action": "invite", "email": "neu@t.de", "role": STAFF})
    req.tenant.email_pending = True
    resp = team.team_invite(req)
    assert resp.url == "/dashboard/settings/team/einladen/"


def test_permissions_match_team():
    from apps.core import view_perms

    r = view_perms.RULES
    assert r["team-invite"] == r["team-member"] == r["team"]
