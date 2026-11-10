"""NT-A2: центр подписок «Benachrichtigungen auswählen» (план nt-notification-preferences §2 A2).

Замки: diff только по видам центра; раздел покрывает свои категории; все категории — раздел;
лимит по итоговому числу без частичной записи; DOI v2 — GET без эффектов, POST только
добавляет, мусор отбрасывается; одинаковый ответ анонима; тема портала; каналы раздельно.
"""

import uuid
from unittest import mock

import pytest
from django.http import QueryDict
from django.test import override_settings
from django.utils import timezone

from apps.aggregator import follow, follow_center, follow_views
from apps.aggregator.models import FollowSubscription, PortalUser
from apps.aggregator.tests.test_follow import _listing, _portal, _req, _stamp, _tenant
from apps.core import city_categories as cc

pytestmark = pytest.mark.django_db
CITY = "Solingen"
FOOD = "lebensmittel-getraenke"


def _user():
    return PortalUser.objects.create(email=f"{uuid.uuid4().hex}@kunde.test")


def _sel(**kw):
    return follow_center.Selection(**{k: set(v) for k, v in kw.items()})


def _kinds(user):
    return set(
        FollowSubscription.objects.filter(user=user).values_list("target_kind", "target_key")
    )


def test_apply_diff_touches_only_center_kinds():
    portal = _portal()
    user = _user()
    tenant = _tenant()
    follow.follow_now(
        user, follow.Target("business", tenant.schema_name), frequency="daily", portal=portal
    )
    follow_center.apply(
        user,
        _sel(categories={"brot-backwaren", "obst-gemuese"}, tags={"vegan"}),
        frequency="weekly",
        portal=portal,
    )
    assert ("category", "brot-backwaren") in _kinds(user)
    result = follow_center.apply(
        user, _sel(categories={"brot-backwaren"}), frequency="weekly", portal=portal
    )
    assert (result.added, result.removed) == (0, 2)
    assert _kinds(user) == {("business", tenant.schema_name), ("category", "brot-backwaren")}
    assert set(
        FollowSubscription.objects.filter(user=user, target_kind="category").values_list(
            "frequency", flat=True
        )
    ) == {"weekly"}


def test_section_covers_its_categories_and_full_set_folds():
    portal = _portal()
    norm = follow_center.normalize(_sel(sections={FOOD}, categories={"brot-backwaren"}), portal)
    assert norm.sections == {FOOD} and norm.categories == set()
    members = {c.key for c in cc.CATEGORIES if c.section == FOOD}
    norm = follow_center.normalize(_sel(categories=members), portal)
    assert norm.sections == {FOOD} and norm.categories == set()
    junk = follow_center.normalize(
        _sel(categories={"weg", FOOD}, tags={"erfunden", "halal"}, districts={"nope"}), portal
    )
    assert junk.categories == set() and junk.tags == {"halal"} and junk.districts == set()


def test_limit_counts_final_set_and_writes_nothing(settings):
    settings.AGGREGATOR_FOLLOW = {**settings.AGGREGATOR_FOLLOW, "max_follows": 2}
    portal = _portal()
    user = _user()
    follow_center.apply(user, _sel(tags={"vegan"}), frequency="daily", portal=portal)
    with pytest.raises(follow.FollowLimitReached):
        follow_center.apply(
            user, _sel(tags={"vegan", "bio", "halal"}), frequency="daily", portal=portal
        )
    assert _kinds(user) == {("tag", "vegan")}
    # замена в пределах лимита проходит (итог = 2)
    follow_center.apply(user, _sel(tags={"bio", "halal"}), frequency="daily", portal=portal)
    assert _kinds(user) == {("tag", "bio"), ("tag", "halal")}


def test_channels_do_not_mix():
    portal = _portal()
    user = _user()
    follow_center.apply(
        user,
        _sel(tags={"vegan"}),
        frequency="daily",
        portal=portal,
        channel=FollowSubscription.CHANNEL_TELEGRAM,
    )
    follow_center.apply(user, _sel(), frequency="daily", portal=portal)
    assert FollowSubscription.objects.filter(user=user, channel="telegram").count() == 1


def test_theme_portal_drops_foreign_categories():
    portal = _portal(theme_categories=["brot-backwaren"])
    norm = follow_center.normalize(_sel(categories={"brot-backwaren", "obst-gemuese"}), portal)
    assert norm.categories == {"brot-backwaren"}
    assert [n["section"].key for n in follow_center.tree(portal)] == [FOOD]


def test_brands_only_existing():
    portal = _portal()
    tenant = _tenant()
    _listing(tenant, brand="Bosch")
    _listing(tenant, brand="bosch")
    assert follow_center.brands(portal) == [("bosch", "Bosch")]  # одна марка, без регистра


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_logged_in_post_saves_and_redirects():
    portal = _portal()
    user = _user()
    data = QueryDict(mutable=True)
    data.setlist("kategorie", ["brot-backwaren"])
    data.setlist("merkmal", ["halal"])
    data["frequency"] = "daily"
    req = _req("post", "/folgen/auswahl/", data, portal=portal, user=user)
    resp = follow_views.follow_center_view(req)
    assert resp.status_code == 302 and "ok=1" in resp["Location"]
    assert _kinds(user) == {("category", "brot-backwaren"), ("tag", "halal")}
    req = _req("get", "/folgen/auswahl/", portal=portal, user=user)
    html = follow_views.follow_center_view(req).content.decode()
    assert 'value="brot-backwaren" data-ft-cat checked' in html
    assert "no-store" in follow_views.follow_center_view(req).get("Cache-Control", "")


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_anonymous_gets_one_doi_and_confirm_only_adds(isolated_ratelimit):
    portal = _portal()
    email = f"{uuid.uuid4().hex}@kunde.test"
    existing = PortalUser.objects.create(email=email)
    follow_center.apply(existing, _sel(tags={"bio"}), frequency="daily", portal=portal)
    data = QueryDict(mutable=True)
    data.setlist("kategorie", ["brot-backwaren"])
    data.update({"email": email, "frequency": "weekly", "stamp": _stamp(), "website": ""})
    with mock.patch("apps.aggregator.tasks.send_follow_confirm_email.delay") as send:
        resp = follow_views.follow_center_view(
            _req("post", "/folgen/auswahl/", data, portal=portal)
        )
    assert resp.status_code == 200 and send.call_count == 1
    url = send.call_args.kwargs["url"]
    token = url.rstrip("/").rsplit("/", 1)[1]
    # GET подтверждения ничего не меняет
    follow_views.follow_confirm(_req("get", "/", portal=portal), token)
    assert ("category", "brot-backwaren") not in _kinds(existing)
    resp = follow_views.follow_confirm(_req("post", "/", portal=portal), token)
    assert resp.status_code == 200
    assert _kinds(existing) == {("tag", "bio"), ("category", "brot-backwaren")}  # bio не стёрт


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_anonymous_response_same_when_rate_limited(isolated_ratelimit):
    portal = _portal()
    data = QueryDict(mutable=True)
    data.setlist("merkmal", ["vegan"])
    data.update(
        {"email": "x@kunde.test", "frequency": "daily", "stamp": _stamp(), "website": "bot"}
    )
    with mock.patch("apps.aggregator.tasks.send_follow_confirm_email.delay") as send:
        resp = follow_views.follow_center_view(
            _req("post", "/folgen/auswahl/", data, portal=portal)
        )
    assert resp.status_code == 200 and send.call_count == 0
    assert "data-follow-check-inbox" in resp.content.decode()  # тот же ответ, что при отправке


def test_center_token_revalidated():
    portal = _portal()
    token = follow_center.make_token(
        email="a@kunde.test",
        selection=_sel(categories={"brot-backwaren", "weg"}, tags={"erfunden"}),
        frequency="daily",
        portal=portal,
        locale="de",
    )
    payload = follow.load_doi_token(token)
    sel = follow_center.selection_of(payload, portal)
    assert sel.categories == {"brot-backwaren"} and sel.tags == set()
    assert timezone.now()
