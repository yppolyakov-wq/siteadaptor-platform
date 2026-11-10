"""NT-A3: частичная и полная отписка (план nt-notification-preferences §2 A3).

Замки: one-click POST без выбора (RFC 8058) — ровно одна подписка (паритет); POST с `subs`
снимает только выбранные и не трогает чужие; GET ничего не меняет; последняя подписка
неявного жителя — страница «abgemeldet», без 404.
"""

import uuid

import pytest
from django.utils import timezone

from apps.aggregator import follow, follow_views
from apps.aggregator.models import FollowSubscription, PortalUser
from apps.aggregator.tests.test_follow import _portal, _req

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_portal")]


def _user():
    return PortalUser.objects.create(email=f"{uuid.uuid4().hex}@kunde.test")


def _sub(user, key, portal):
    return FollowSubscription.objects.create(
        user=user,
        target_kind="tag",
        target_key=key,
        city="Solingen",
        portal=portal,
        token=uuid.uuid4().hex,
        confirmed_at=timezone.now(),
    )


def _post(path, pairs, portal):
    data = {}
    for k, v in pairs:
        data.setdefault(k, []).append(v)  # RequestFactory кодирует списки как повторы ключа
    return _req("post", path, data, portal=portal)


def test_one_click_without_selection_removes_only_that_sub():
    portal = _portal()
    user = _user()
    a, b = _sub(user, "vegan", portal), _sub(user, "bio", portal)
    req = _post("/", [("List-Unsubscribe", "One-Click")], portal)
    follow_views.follow_unsubscribe(req, a.token)
    assert list(FollowSubscription.objects.filter(user=user)) == [b]


def test_selected_removes_only_chosen_and_ignores_foreign():
    portal = _portal()
    user, other = _user(), _user()
    a, b, c = _sub(user, "vegan", portal), _sub(user, "bio", portal), _sub(user, "halal", portal)
    foreign = _sub(other, "vegan", portal)
    req = _post(
        "/",
        [
            ("action", "remove_selected"),
            ("subs", a.token),
            ("subs", b.token),
            ("subs", foreign.token),
        ],
        portal,
    )
    follow_views.follow_unsubscribe(req, a.token)
    assert list(FollowSubscription.objects.filter(user=user)) == [c]
    assert FollowSubscription.objects.filter(pk=foreign.pk).exists()


def test_get_lists_all_with_current_checked_and_changes_nothing():
    portal = _portal()
    user = _user()
    a, b = _sub(user, "vegan", portal), _sub(user, "bio", portal)
    html = follow_views.follow_unsubscribe(
        _req("get", "/", portal=portal), a.token
    ).content.decode()
    assert f'value="{a.token}" checked' in html and f'value="{b.token}"' in html
    assert f'value="{b.token}" checked' not in html
    assert FollowSubscription.objects.filter(user=user).count() == 2


def test_selecting_last_sub_of_implicit_user_shows_page():
    portal = _portal()
    user = _user()
    a = _sub(user, "vegan", portal)
    req = _post("/", [("action", "remove_selected"), ("subs", a.token)], portal)
    resp = follow_views.follow_unsubscribe(req, a.token)
    assert resp.status_code == 200 and "data-follow-unsubscribed" in resp.content.decode()
    assert not PortalUser.objects.filter(pk=user.pk).exists()


def test_manage_page_remove_selected():
    portal = _portal()
    user = _user()
    a, b = _sub(user, "vegan", portal), _sub(user, "bio", portal)
    token = follow.ensure_follow_token(user)
    html = follow_views.follow_manage(_req("get", "/", portal=portal), token).content.decode()
    assert "data-follow-select" in html
    req = _post("/", [("action", "remove_selected"), ("subs", b.token)], portal)
    follow_views.follow_manage(req, token)
    assert list(FollowSubscription.objects.filter(user=user)) == [a]


def test_all_via_page_button():
    portal = _portal()
    user = _user()
    a = _sub(user, "vegan", portal)
    _sub(user, "bio", portal)
    follow_views.follow_unsubscribe(_post("/", [("action", "remove_all")], portal), a.token)
    assert not FollowSubscription.objects.filter(user_id=user.pk).exists()
