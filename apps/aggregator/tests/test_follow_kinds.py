"""NT-A1: подписка на категорию, признак и марку (план docs/nt-notification-preferences-plan-2026-11-10.md).

Замки: разбор ссылки «Folgen»; письмо по подписке ⊆ «Alle anzeigen» той же области; позиция,
совпавшая с категорией и разделом, приходит один раз — под категорией; перенос старых
подписок-поисков из одного условия; лимит письма не отбрасывает подписки молча.
"""

import importlib
import uuid
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.aggregator import follow, follow_digest
from apps.aggregator.models import AggregatorListing, FollowSubscription, PortalUser
from apps.aggregator.tests.test_follow import _listing, _portal, _tenant

pytestmark = pytest.mark.django_db
CITY = "Solingen"


def _user():
    return PortalUser.objects.create(email=f"{uuid.uuid4().hex}@kunde.test")


def _sub(user, kind, key, portal=None, **kw):
    return FollowSubscription.objects.create(
        user=user,
        target_kind=kind,
        target_key=key,
        city=CITY,
        portal=portal,
        token=uuid.uuid4().hex,
        confirmed_at=timezone.now() - timedelta(days=1),
        **kw,
    )


def test_parse_tag_and_brand_targets():
    portal = _portal()
    assert follow.parse_target({"merkmal": "vegan"}, portal=portal) == follow.Target(
        "tag", "vegan", CITY
    )
    assert follow.parse_target({"merkmal": "erfunden"}, portal=portal) is None
    brand = follow.parse_target({"marke": "  Bosch "}, portal=portal)
    assert brand == follow.Target("brand", "bosch", CITY)
    assert follow.parse_target({"marke": "Bosch"}, portal=None) is None  # нужен город


def test_category_items_are_exactly_category_scope():
    portal = _portal()
    tenant = _tenant()
    bread = _listing(tenant, city_category="brot-backwaren")
    _listing(tenant, city_category="obst-gemuese")
    sub = _sub(_user(), "category", "brot-backwaren", portal)
    since = timezone.now() - timedelta(days=2)
    assert list(follow.items_for(sub, since=since)) == [bread]
    assert "kat=brot-backwaren" in follow.scope_url(sub)


def test_tag_and_brand_items():
    portal = _portal()
    tenant = _tenant()
    vegan = _listing(tenant, city_tags=["vegan"])
    _listing(tenant, city_tags=["bio"])
    drill = _listing(tenant, brand="Bosch", city_category="werkzeug")
    user = _user()
    since = timezone.now() - timedelta(days=2)
    assert list(follow.items_for(_sub(user, "tag", "vegan", portal), since=since)) == [vegan]
    brand_sub = _sub(user, "brand", "bosch", portal)
    assert list(follow.items_for(brand_sub, since=since)) == [drill]
    assert follow.describe(brand_sub).endswith("Bosch")  # подпись — как в каталоге
    assert "marke=bosch" in follow.scope_url(brand_sub)


def test_offer_in_category_and_section_shown_once_under_category():
    portal = _portal()
    tenant = _tenant()
    item = _listing(tenant, city_category="brot-backwaren")
    user = _user()
    section = _sub(user, "section", "lebensmittel-getraenke", portal)
    category = _sub(user, "category", "brot-backwaren", portal)
    digest = follow_digest.build_digest(user, [section, category])
    assert [s.sub.pk for s in digest.sections] == [category.pk]
    assert digest.sections[0].items == [item]


def test_digest_reads_all_follows_and_caps_items(settings):
    portal = _portal()
    tenant = _tenant()
    user = _user()
    subs = []
    for i in range(25):  # больше прежних 20: ни одна подписка не выпадает молча
        _listing(tenant, brand=f"Marke{i}")
        subs.append(_sub(user, "brand", f"marke{i}", portal))
    assert len(follow_digest.build_digest(user, subs).sections) == 25
    settings.AGGREGATOR_FOLLOW = {**settings.AGGREGATOR_FOLLOW, "max_items_per_mail": 7}
    digest = follow_digest.build_digest(user, subs)
    assert sum(len(s.items) for s in digest.sections) == 7
    assert follow_digest.max_follows_per_mail() >= follow.max_follows()


def test_migration_moves_single_condition_queries_and_merges_twins():
    mig = importlib.import_module("apps.aggregator.migrations.0041_nt_follow_kinds_data")
    from django.apps import apps as registry

    user = _user()
    cat = _sub(user, "query", "h1", query={"v": 1, "p": [["kat", "brot-backwaren"]]})
    tag = _sub(user, "query", "h2", query={"v": 1, "p": [["merkmal", "vegan"]]})
    early = timezone.now() - timedelta(days=30)
    twin_q = _sub(user, "query", "h3", query={"v": 1, "p": [["marke", "Bosch"]]})
    FollowSubscription.objects.filter(pk=twin_q.pk).update(confirmed_at=early)
    twin = _sub(user, "brand", "bosch")
    two = _sub(user, "query", "h4", query={"v": 1, "p": [["kat", "brot-backwaren"], ["q", "x"]]})
    section_q = _sub(user, "query", "h5", query={"v": 1, "p": [["kat", "lebensmittel-getraenke"]]})

    mig.forward(registry, None)
    mig.forward(registry, None)  # идемпотентно

    cat.refresh_from_db()
    tag.refresh_from_db()
    assert (cat.target_kind, cat.target_key, cat.query) == ("category", "brot-backwaren", {})
    assert (tag.target_kind, tag.target_key) == ("tag", "vegan")
    assert not FollowSubscription.objects.filter(pk=twin_q.pk).exists()
    twin.refresh_from_db()
    assert twin.confirmed_at == early  # согласие — более раннее
    assert FollowSubscription.objects.get(pk=two.pk).target_kind == "query"
    assert FollowSubscription.objects.get(pk=section_q.pk).target_kind == "query"


def test_kinds_have_labels():
    labels = dict(FollowSubscription.TARGETS)
    for kind in ("category", "tag", "brand"):
        assert labels[kind]
    assert set(follow.CENTER_KINDS) <= set(labels)
    assert AggregatorListing.OFFER_KINDS


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_follow_page_offers_section_switch_for_category():
    from apps.aggregator import follow_views
    from apps.aggregator.tests.test_follow import _req

    portal = _portal()
    req = _req("get", "/folgen/", {"bereich": "brot-backwaren"}, portal=portal)
    html = follow_views.follow_page(req).content.decode()
    assert "umfang=bereich" in html and "data-follow-scope" in html
    req = _req("get", "/folgen/", {"bereich": "brot-backwaren", "umfang": "bereich"}, portal=portal)
    html = follow_views.follow_page(req).content.decode()
    assert 'href="?bereich=brot-backwaren"' in html
