"""T-8.10d.1: подписка портала сочетанием фильтров (`docs/t8-10d1-combined-follows-plan-2026-11-18.md`):
одна кнопка «Folgen» на выдаче, чипы на странице подтверждения, подпись «Friseur · Mitte,
Burg/Höhscheid · familienfreundlich», замена старых одиночных подписок галочкой."""

import pytest

from apps.aggregator import follow, follow_query, follow_views
from apps.aggregator.models import FollowSubscription, PortalUser
from apps.aggregator.tests.test_follow_query import CITY, _email, _portal, _qd, _req

pytestmark = pytest.mark.django_db

KAT, MITTE, BURG, TAG = "friseur", "mitte", "burg-hoehscheid", "familienfreundlich"


def _combo():
    return _qd(art="suche", kat=KAT, stadtteil=[MITTE, BURG], merkmal=TAG)


def test_combination_label_groups_values_by_type():
    target = follow.parse_target(_combo(), portal=_portal())
    assert target.kind == FollowSubscription.TARGET_QUERY
    label = target.label
    assert label.startswith("Friseur · ") and label.endswith(" · familienfreundlich")
    assert "Burg/Höhscheid, Mitte" in label and label.count(" · ") == 2, label


def test_follow_page_shows_chips_with_remove_and_add_links(settings):
    settings.ROOT_URLCONF = "config.urls_portal"
    portal = _portal()
    resp = follow_views.follow_page(_req("get", "/folgen/", _combo(), portal=portal))
    html = resp.content.decode()
    assert html.count("data-follow-chip") == 4  # Friseur, Mitte, Burg/Höhscheid, familienfreundlich
    assert 'data-follow-add="stadtteil"' in html and 'data-follow-add="merkmal"' in html
    groups = follow_query.combo_groups(
        follow.parse_target(_combo(), portal=portal).query, _combo(), city=CITY
    )
    stadt = next(g for g in groups if g["name"] == "stadtteil")
    removed = next(c["remove"] for c in stadt["chips"] if c["label"] == "Mitte")
    assert "stadtteil=" + BURG in removed and "stadtteil=" + MITTE not in removed


def test_logged_in_resident_can_replace_covered_single_follows(settings):
    settings.ROOT_URLCONF = "config.urls_portal"
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    for params in ({"bereich": KAT}, {"stadtteil": MITTE}, {"stadtteil": "wald"}):
        follow.follow_now(
            user,
            follow.parse_target(_qd(**params), portal=portal),
            frequency="daily",
            portal=portal,
        )
    page = follow_views.follow_page(_req("get", "/folgen/", _combo(), portal=portal, user=user))
    assert "data-follow-replace" in page.content.decode()
    data = {**{k: v for k, v in _combo().lists()}, "frequency": "daily", "replace_singles": "1"}
    req = _req("post", "/folgen/?" + _combo().urlencode(), data, portal=portal, user=user)
    req.GET = _combo()
    follow_views.follow_page(req)
    kinds = set(
        FollowSubscription.objects.filter(user=user).values_list("target_kind", "target_key")
    )
    assert (FollowSubscription.TARGET_DISTRICT, "wald") in kinds, "не покрытая — остаётся"
    assert (FollowSubscription.TARGET_DISTRICT, MITTE) not in kinds
    assert any(k == FollowSubscription.TARGET_QUERY for k, _ in kinds)


def test_without_the_checkbox_old_follows_stay(settings):
    settings.ROOT_URLCONF = "config.urls_portal"
    portal = _portal()
    user = PortalUser.objects.create(email=_email())
    follow.follow_now(
        user,
        follow.parse_target(_qd(stadtteil=MITTE), portal=portal),
        frequency="daily",
        portal=portal,
    )
    data = {"frequency": "daily"}
    req = _req("post", "/folgen/", data, portal=portal, user=user)
    req.GET = _combo()
    follow_views.follow_page(req)
    assert FollowSubscription.objects.filter(user=user, target_key=MITTE).exists()
