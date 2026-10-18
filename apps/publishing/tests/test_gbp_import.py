"""Д3-3 (GBP-Sync): Offer-посты Google → черновики акций. Замки 10–15, 18–21 плана
docs/d3-gbp-sync-plan-2026-10-18.md §4/§9. Решения владельца: импорт в ЧЕРНОВИК, повторно не
постим, импортированный пост при окончании акции у Google не удаляем (В-6), без миграции (В-8),
код купона — текстом в описании + metadata (В-9)."""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.promotions.models import Promotion
from apps.publishing import adapters, gbp, gbp_import, services, views
from apps.publishing.models import Channel, Publication
from apps.tenants.tests.factories import TenantFactory

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_tenant")]

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=BERLIN)


def _offer(name="accounts/1/locations/2/localPosts/9", **over):
    post = {
        "name": name,
        "languageCode": "de",
        "topicType": "OFFER",
        "state": "LIVE",
        "summary": "Zwei Brötchen zum Preis von einem.",
        "event": {
            "title": "Brötchen-Woche",
            "schedule": {
                "startDate": {"year": 2026, "month": 10, "day": 17},
                "startTime": {"hours": 8},
                "endDate": {"year": 2026, "month": 10, "day": 25},
            },
        },
        "offer": {"couponCode": "BROT2", "termsConditions": "Solange Vorrat reicht."},
        "updateTime": "2026-10-17T07:00:00Z",
    }
    post.update(over)
    return post


@pytest.fixture
def channel():
    from apps.secrets import crypto

    return Channel.objects.create(
        type=Channel.GOOGLE_BUSINESS,
        is_enabled=True,
        config={"refresh_token": crypto.encrypt("rt"), "location": "accounts/1/locations/2"},
    )


@pytest.fixture
def tenant():
    return TenantFactory.build(
        schema_name="t_gbpi", enabled_locales=["de", "en"], default_locale="de"
    )


@pytest.fixture
def google(monkeypatch):
    state = {"posts": [_offer()], "complete": True}
    monkeypatch.setattr(gbp, "access_token", lambda config: "tok")
    monkeypatch.setattr(
        gbp, "iter_local_posts", lambda token, v4: (list(state["posts"]), state["complete"])
    )
    monkeypatch.setattr(gbp_import, "_public_url", lambda url: url)
    return state


def _run(channel, tenant):
    return gbp_import.import_offers(channel, tenant, now=NOW)


# --- 10–15 ---------------------------------------------------------------------------------


def test_live_offer_becomes_one_draft_with_mapped_fields(channel, tenant, google):
    result = _run(channel, tenant)
    assert result.created == 1
    (promo,) = Promotion.objects.all()
    assert promo.status == "draft" and promo.promo_type == Promotion.DISCOUNT
    assert promo.title == {"de": "Brötchen-Woche"}
    desc = promo.description["de"]
    assert "Zwei Brötchen" in desc and "Solange Vorrat reicht." in desc and "BROT2" in desc
    assert promo.starts_at == datetime(2026, 10, 17, 8, 0, tzinfo=BERLIN)
    assert promo.ends_at == datetime(2026, 10, 25, 23, 59, 59, tzinfo=BERLIN)
    assert promo.price_override is None and promo.discount_percent is None
    assert promo.compare_at_price is None
    assert promo.metadata["source"] == "gbp"
    assert promo.metadata["gbp_post"] == "accounts/1/locations/2/localPosts/9"
    assert promo.metadata["gbp_coupon_code"] == "BROT2"


def test_second_run_is_idempotent(channel, tenant, google):
    _run(channel, tenant)
    result = _run(channel, tenant)
    assert result.created == 0
    assert Promotion.objects.count() == 1
    (pub,) = Publication.objects.all()
    assert pub.dedupe_key == "gbp-import:accounts/1/locations/2/localPosts/9"
    assert pub.status == "published" and pub.external_ref == pub.dedupe_key.split(":", 1)[1]


@pytest.mark.parametrize(
    "over",
    [
        {"topicType": "STANDARD"},
        {"topicType": "EVENT"},
        {"topicType": "ALERT"},
        {"state": "REJECTED"},
        {"state": "PROCESSING"},
    ],
)
def test_non_offer_or_not_live_skipped(channel, tenant, google, over):
    google["posts"] = [_offer(**over)]
    assert _run(channel, tenant).created == 0
    assert not Promotion.objects.exists()


def test_own_posts_are_not_imported(channel, tenant, google):
    own = Promotion.objects.create(title={"de": "Unsere"}, status="active")
    Publication.objects.create(
        promotion=own,
        channel=channel,
        status="published",
        external_ref="accounts/1/locations/2/localPosts/9",
        dedupe_key=f"publish:{own.id}:{channel.id}",
    )
    assert _run(channel, tenant).created == 0
    assert Promotion.objects.count() == 1


def test_ended_offer_skipped(channel, tenant, google):
    post = _offer()
    post["event"]["schedule"]["endDate"] = {"year": 2026, "month": 10, "day": 1}
    google["posts"] = [post]
    assert _run(channel, tenant).created == 0


def test_dismissed_post_not_reimported(channel, tenant, google):
    _run(channel, tenant)
    promo = Promotion.objects.get()
    gbp_import.dismiss(channel.pk, promo)
    assert not Promotion.objects.filter(pk=promo.pk).exists()  # черновик удалён (мягко)
    _run(channel, tenant)
    assert Promotion.objects.count() == 0
    channel.refresh_from_db()
    assert promo.metadata["gbp_post"] in channel.config["gbp_dismissed"]


def test_dismiss_keeps_non_draft_and_caps_list(channel, tenant, google):
    _run(channel, tenant)
    promo = Promotion.objects.get()
    Promotion.objects.filter(pk=promo.pk).update(status="active")
    promo.refresh_from_db()
    with pytest.raises(ValueError):
        gbp_import.dismiss(channel.pk, promo)
    Channel.update_config(
        channel.pk, lambda c: c.__setitem__("gbp_dismissed", [f"x/{i}" for i in range(400)])
    )
    Promotion.objects.filter(pk=promo.pk).update(status="draft")
    promo.refresh_from_db()
    gbp_import.dismiss(channel.pk, promo)
    channel.refresh_from_db()
    assert len(channel.config["gbp_dismissed"]) == gbp_import.DISMISS_MAX
    assert channel.config["gbp_dismissed"][-1] == promo.metadata["gbp_post"]


# --- 18–19: не постим повторно и не удаляем пост владельца ---------------------------------


def test_activation_of_imported_draft_does_not_repost(channel, tenant, google, monkeypatch):
    _run(channel, tenant)
    promo = Promotion.objects.get()
    calls = []
    monkeypatch.setattr(adapters.requests, "post", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(services.publish_to_channel, "delay", lambda **kw: calls.append(kw))
    services.on_promotion_transition(promo, "active")
    pub = Publication.objects.get(promotion=promo, channel=channel)
    assert pub.status == "published"
    # pause → reactivate: снятая (removed) импортированная публикация не уходит снова в очередь
    Publication.objects.filter(pk=pub.pk).update(status="removed")
    services.on_promotion_transition(promo, "active")
    pub.refresh_from_db()
    assert pub.status == "removed"
    assert [
        c for c in calls if isinstance(c, dict) and c.get("publication_id") == str(pub.id)
    ] == []
    # и сам адаптер, если до него дойдёт, не постит
    assert adapters._gbp_publish(pub) == pub.external_ref
    assert calls == []


def test_end_of_imported_promotion_does_not_delete_owners_post(
    channel, tenant, google, monkeypatch
):
    _run(channel, tenant)
    pub = Publication.objects.get()
    deletes = []
    monkeypatch.setattr(adapters.requests, "delete", lambda *a, **k: deletes.append(a))
    monkeypatch.setattr(adapters, "_gbp_access_token", lambda config: "tok")
    adapters._gbp_remove(pub)
    assert deletes == []
    # обычная акция удаляется как раньше
    own = Promotion.objects.create(title={"de": "x"}, status="active")
    own_pub = Publication.objects.create(
        promotion=own,
        channel=channel,
        status="published",
        external_ref="accounts/1/locations/2/localPosts/77",
        dedupe_key=f"publish:{own.id}:{channel.id}",
    )

    class _R:
        status_code = 200

        def raise_for_status(self):
            return None

    monkeypatch.setattr(adapters.requests, "delete", lambda *a, **k: deletes.append(a) or _R())
    adapters._gbp_remove(own_pub)
    assert len(deletes) == 1


# --- 20–21: внешний текст -------------------------------------------------------------------


def test_text_is_cleaned_and_capped(channel, tenant, google):
    google["posts"] = [
        _offer(
            summary="<script>alert(1)</script>Hallo​\u0007 Welt" + "x" * 6000,
            event={"title": "<b>Titel</b>‮" + "y" * 400, "schedule": {}},
        )
    ]
    _run(channel, tenant)
    promo = Promotion.objects.get()
    title, desc = promo.title["de"], promo.description["de"]
    assert "<" not in title and "‮" not in title and len(title) <= gbp_import.TITLE_MAX
    assert "<script>" not in desc and "​" not in desc and "\u0007" not in desc
    assert len(desc) <= gbp_import.DESCRIPTION_MAX
    assert desc.startswith("alert(1)Hallo Welt") or "Hallo Welt" in desc


def test_title_falls_back_to_summary_first_line(channel, tenant, google):
    google["posts"] = [_offer(event={"schedule": {}}, summary="Erste Zeile\nZweite")]
    _run(channel, tenant)
    assert Promotion.objects.get().title == {"de": "Erste Zeile"}


@pytest.mark.parametrize(
    "url", ["http://example.com/x", "javascript:alert(1)", "https://10.0.0.1/"]
)
def test_bad_redeem_url_dropped(channel, tenant, google, monkeypatch, url):
    from apps.core import ssrf

    monkeypatch.undo()
    monkeypatch.setattr(gbp, "access_token", lambda config: "tok")
    monkeypatch.setattr(
        gbp, "iter_local_posts", lambda token, v4: ([_offer(offer={"redeemOnlineUrl": url})], True)
    )
    assert ssrf  # реальная проверка публичности адреса
    _run(channel, tenant)
    assert "gbp_redeem_url" not in Promotion.objects.get().metadata


def test_foreign_language_goes_to_default_locale(channel, tenant, google):
    google["posts"] = [_offer(languageCode="fr")]
    _run(channel, tenant)
    assert set(Promotion.objects.get().title) == {"de"}


def test_english_post_kept_in_english(channel, tenant, google):
    google["posts"] = [_offer(languageCode="en-GB")]
    _run(channel, tenant)
    assert set(Promotion.objects.get().title) == {"en"}


def test_malformed_posts_never_crash(channel, tenant, google):
    google["posts"] = [None, 5, {"topicType": "OFFER", "state": "LIVE"}, {"name": "x"}]
    assert _run(channel, tenant).created == 0


def test_without_location_not_configured(tenant, google):
    ch = Channel.objects.create(type=Channel.GOOGLE_BUSINESS, config={"refresh_token": "rt"})
    with pytest.raises(gbp.GbpError):
        gbp_import.import_offers(ch, tenant, now=NOW)


# --- клиент: localPosts ------------------------------------------------------------------


def test_iter_local_posts_pages_and_reports_incomplete(monkeypatch):
    class _R:
        def __init__(self, data, status=200):
            self._d, self.status_code = data, status

        def json(self):
            return self._d

    pages = {
        None: _R({"localPosts": [{"name": "a"}], "nextPageToken": "p2"}),
        "p2": _R({}, 500),
    }
    monkeypatch.setattr(gbp.requests, "get", lambda url, **kw: pages[kw["params"].get("pageToken")])
    posts, complete = gbp.iter_local_posts("tok", "accounts/1/locations/2")
    assert posts == [{"name": "a"}] and complete is False


# --- экран ---------------------------------------------------------------------------------


@pytest.fixture
def owner(django_user_model):
    from apps.core.models import Membership

    user = django_user_model.objects.create_user(username=f"o{uuid.uuid4().hex[:6]}", password="x")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    return user


def _req(user, path, data, tenant):
    request = RequestFactory().post(path, data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant
    return request


def test_import_button_creates_drafts_and_lists_them(
    owner, channel, tenant, google, isolated_ratelimit, monkeypatch
):
    monkeypatch.setattr(timezone, "now", lambda: NOW)
    resp = views.gbp_import(_req(owner, "/dashboard/channels/google/angebote/", {}, tenant))
    assert resp.status_code == 302
    channel.refresh_from_db()
    assert channel.config["gbp_sync"]["posts_pulled_at"]
    page = views.gbp_sync(_req(owner, "/dashboard/channels/google/", {}, tenant)).content.decode()
    assert "Brötchen-Woche" in page and "data-gbp-draft" in page


def test_import_rate_limited(owner, channel, tenant, google, isolated_ratelimit, monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: NOW)
    calls = []
    real = gbp.iter_local_posts
    monkeypatch.setattr(gbp, "iter_local_posts", lambda t, v: calls.append(1) or real(t, v))
    for _ in range(2):
        views.gbp_import(_req(owner, "/dashboard/channels/google/angebote/", {}, tenant))
    assert len(calls) == 1


def test_dismiss_view_only_gbp_drafts(owner, channel, tenant, google, isolated_ratelimit):
    _run(channel, tenant)
    promo = Promotion.objects.get()
    other = Promotion.objects.create(title={"de": "eigene"}, status="draft")
    path = "/dashboard/channels/google/angebote/ablehnen/"
    views.gbp_dismiss(_req(owner, path, {"promotion": str(other.pk)}, tenant))
    assert Promotion.objects.filter(pk=other.pk).exists()
    views.gbp_dismiss(_req(owner, path, {"promotion": str(promo.pk)}, tenant))
    assert not Promotion.objects.filter(pk=promo.pk).exists()


def test_staff_forbidden(django_user_model, channel, tenant, google, isolated_ratelimit):
    from apps.core.models import Membership

    staff = django_user_model.objects.create_user(username=f"s{uuid.uuid4().hex[:6]}", password="x")
    Membership.objects.create(user=staff, role=Membership.ROLE_STAFF)
    resp = views.gbp_import(_req(staff, "/dashboard/channels/google/angebote/", {}, tenant))
    assert resp.status_code == 403 and not Promotion.objects.exists()


def test_promotion_list_badge_and_filter(owner, channel, tenant, google):
    from apps.promotions import views as promo_views

    _run(channel, tenant)
    Promotion.objects.create(title={"de": "Eigene Aktion"}, status="draft")
    request = RequestFactory().get("/promotions/", {"quelle": "gbp"})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = owner
    request.tenant = tenant
    html = promo_views.promotion_list(request).content.decode()
    assert "data-gbp-badge" in html and "Brötchen-Woche" in html
    assert "Eigene Aktion" not in html
