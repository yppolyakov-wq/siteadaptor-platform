"""T-8.7 «Folgen»: подписки жителя портала, DOI, сводка, отписка.

E-mail/IP — uuid: счётчики rate-limit живут в общем Redis дольше теста.
Время сводки задаётся явно (`now=`), часовой пояс — Europe/Berlin из настроек.
"""

import uuid
from datetime import datetime, timedelta
from unittest import mock

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.core import mail, signing
from django.http import Http404
from django.test import RequestFactory, override_settings
from django.urls import resolve, reverse
from django.utils import timezone

from apps.aggregator import account_views, follow, follow_digest, follow_views, tasks
from apps.aggregator.models import (
    AggregatorListing,
    AggregatorPortal,
    FollowDigest,
    FollowSubscription,
    PortalUser,
)
from apps.tenants.quickstart import FORM_STAMP_SALT
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
BERLIN = timezone.get_default_timezone()


def _email():
    return f"{uuid.uuid4().hex}@kunde.test"


def _portal(**kw):
    host = kw.pop("host", f"{uuid.uuid4().hex[:8]}.solingen.test")
    defaults = {"kind": "city", "city": "Solingen", "title": {"de": "Solingen"}, "is_active": True}
    defaults.update(kw)
    return AggregatorPortal.objects.create(host=host, **defaults)


def _tenant(**kw):
    kw.setdefault("city", "Solingen")
    return TenantFactory(**kw)


def _listing(tenant, **kw):
    defaults = {
        "tenant_schema": tenant.schema_name,
        "tenant_slug": tenant.slug,
        "business_name": tenant.name,
        "business_type": tenant.business_type,
        "city": "Solingen",
        "listing_kind": AggregatorListing.KIND_PROMOTION,
        "source_ref": uuid.uuid4().hex,
        "title": {"de": "Brot"},
        "detail_url": f"https://{tenant.slug}.siteadaptor.de/p/1/",
        "is_active": True,
        "city_category": "brot-backwaren",
        "district": "ohligs-aufderhoehe-merscheid",
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _stamp(age=120):
    return signing.dumps(timezone.now().timestamp() - age, salt=FORM_STAMP_SALT)


def _req(method, path, data=None, portal=None, user=None):
    factory = getattr(RequestFactory(), method)
    request = factory(path, data or {}, HTTP_X_FORWARDED_FOR=f"10.{uuid.uuid4().int % 255}.0.1")
    SessionMiddleware(lambda r: None).process_request(request)
    request.portal = portal
    if user is not None:
        request.session["portal_user_id"] = user.pk
    return request


def _at(hour, minute=0, day=None):
    day = day or datetime(2026, 10, 21)  # среда
    return timezone.make_aware(day.replace(hour=hour, minute=minute), BERLIN)


def _user(**kw):
    return PortalUser.objects.create(email=_email(), **kw)


# --- цели ---------------------------------------------------------------------------------


def test_parse_target_business_section_category_district():
    portal = _portal()
    tenant = _tenant()
    t = follow.parse_target({"unternehmen": tenant.slug}, portal=portal)
    assert t == follow.Target("business", tenant.schema_name)
    assert follow.parse_target(
        {"bereich": "lebensmittel-getraenke"}, portal=portal
    ) == follow.Target("section", "lebensmittel-getraenke", "Solingen")
    # категория сворачивается в свой раздел (Р-1b)
    assert follow.parse_target({"bereich": "brot-backwaren"}, portal=portal).key == (
        "lebensmittel-getraenke"
    )
    assert follow.parse_target({"stadtteil": "Ohligs"}, portal=portal) == follow.Target(
        "district", "ohligs-aufderhoehe-merscheid", "Solingen"
    )
    assert follow.parse_target({"bereich": "nope"}, portal=portal) is None
    assert follow.parse_target({"stadtteil": "nope"}, portal=portal) is None
    # без портала раздел/район не привязаны к городу
    assert follow.parse_target({"bereich": "lebensmittel-getraenke"}, portal=None) is None


def test_demo_and_withheld_business_cannot_be_followed():
    portal = _portal()
    demo = _tenant(is_demo=True)
    withheld = _tenant(in_city_catalog=False)
    assert follow.parse_target({"unternehmen": demo.slug}, portal=portal) is None
    assert follow.parse_target({"unternehmen": withheld.slug}, portal=portal) is None


# --- DOI ----------------------------------------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_post_follow_writes_nothing_until_confirmed(monkeypatch):
    sent = []
    monkeypatch.setattr(tasks.send_follow_confirm_email, "delay", lambda **kw: sent.append(kw))
    portal = _portal()
    tenant = _tenant()
    email = _email()
    resp = follow_views.follow_page(
        _req(
            "post",
            f"/folgen/?unternehmen={tenant.slug}",
            {"email": email, "frequency": "instant", "stamp": _stamp()},
            portal=portal,
        )
    )
    assert resp.status_code == 200
    assert b"data-follow-check-inbox" in resp.content
    assert FollowSubscription.objects.count() == 0
    assert PortalUser.objects.filter(email=email).count() == 0
    assert len(sent) == 1 and sent[0]["email"] == email
    assert sent[0]["url"].startswith(f"https://{portal.host}/folgen/bestaetigen/")


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_same_response_for_any_outcome(monkeypatch):
    sent = []
    monkeypatch.setattr(tasks.send_follow_confirm_email, "delay", lambda **kw: sent.append(kw))
    portal = _portal()
    tenant = _tenant()
    path = f"/folgen/?unternehmen={tenant.slug}"
    cases = [
        {"email": _email(), "frequency": "daily", "stamp": _stamp(), "website": "x"},  # honeypot
        {"email": _email(), "frequency": "daily", "stamp": _stamp(age=0)},  # слишком быстро
        {"email": _email(), "frequency": "daily", "stamp": "garbage"},  # без метки
        {"email": "not-an-email", "frequency": "daily", "stamp": _stamp()},
    ]
    for data in cases:
        resp = follow_views.follow_page(_req("post", path, data, portal=portal))
        assert resp.status_code == 200
        assert b"data-follow-check-inbox" in resp.content
    assert sent == []


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_rate_limit_per_email(monkeypatch):
    sent = []
    monkeypatch.setattr(tasks.send_follow_confirm_email, "delay", lambda **kw: sent.append(kw))
    portal = _portal()
    tenant = _tenant()
    email = _email()
    for _ in range(5):
        follow_views.follow_page(
            _req(
                "post",
                f"/folgen/?unternehmen={tenant.slug}",
                {"email": email, "frequency": "daily", "stamp": _stamp()},
                portal=portal,
            )
        )
    assert len(sent) == follow_views.EMAIL_RL[0]


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_confirm_get_is_side_effect_free_post_creates_and_is_idempotent():
    portal = _portal()
    tenant = _tenant()
    email = _email()
    token = follow.make_doi_token(
        email=email,
        target=follow.Target("business", tenant.schema_name),
        frequency="instant",
        portal=portal,
        locale="ru",
    )
    resp = follow_views.follow_confirm(
        _req("get", f"/folgen/bestaetigen/{token}/", portal=portal), token
    )
    assert resp.status_code == 200
    assert b"data-follow-confirm" in resp.content
    assert resp["Referrer-Policy"] == "no-referrer"
    assert "no-store" in resp["Cache-Control"]
    assert PortalUser.objects.filter(email=email).count() == 0

    for _ in range(2):
        resp = follow_views.follow_confirm(
            _req("post", f"/folgen/bestaetigen/{token}/", portal=portal), token
        )
        assert resp.status_code == 200
        assert b"data-follow-done" in resp.content
    user = PortalUser.objects.get(email=email)
    assert user.locale == "ru"
    assert user.follow_token
    subs = list(user.follows.all())
    assert len(subs) == 1
    assert subs[0].frequency == "instant"
    assert subs[0].confirmed_at is not None
    assert subs[0].portal_id == portal.pk
    assert subs[0].token


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_expired_or_tampered_token_400():
    portal = _portal()
    for token in ("garbage", signing.dumps({"e": "x@y.z", "k": "business"}, salt="other")):
        resp = follow_views.follow_confirm(
            _req("post", f"/folgen/bestaetigen/{token}/", portal=portal), token
        )
        assert resp.status_code == 400
    assert PortalUser.objects.count() == 0


def test_instant_only_for_business():
    portal = _portal()
    user = _user()
    section = follow.Target("section", "lebensmittel-getraenke", "Solingen")
    sub = follow.follow_now(user, section, frequency="instant", portal=portal)
    assert sub.frequency == "daily"  # понижено
    assert follow.set_frequency(sub, "instant") is False
    assert follow.set_frequency(sub, "weekly") is True
    tenant = _tenant()
    biz = follow.follow_now(
        user, follow.Target("business", tenant.schema_name), frequency="instant", portal=portal
    )
    assert biz.frequency == "instant"


def test_confirm_refuses_business_that_left_catalog():
    portal = _portal()
    tenant = _tenant()
    token = follow.make_doi_token(
        email=_email(),
        target=follow.Target("business", tenant.schema_name),
        frequency="daily",
        portal=portal,
        locale="de",
    )
    tenant.in_city_catalog = False
    tenant.save(update_fields=["in_city_catalog"])
    assert follow.confirm(follow.load_doi_token(token)) is None
    assert FollowSubscription.objects.count() == 0


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_logged_in_user_follows_without_doi(monkeypatch):
    sent = []
    monkeypatch.setattr(tasks.send_follow_confirm_email, "delay", lambda **kw: sent.append(kw))
    portal = _portal()
    tenant = _tenant()
    user = _user(last_login_at=timezone.now())
    resp = follow_views.follow_page(
        _req(
            "post",
            f"/folgen/?unternehmen={tenant.slug}",
            {"frequency": "weekly"},
            portal=portal,
            user=user,
        )
    )
    assert resp.status_code == 200
    assert b"data-follow-done" in resp.content
    assert sent == []
    assert user.follows.get().frequency == "weekly"


# --- кнопки и кэш -------------------------------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_follow_button_is_link_not_form_on_cached_pages():
    from apps.aggregator import portal_views

    portal = _portal()
    tenant = _tenant()
    _listing(tenant)
    request = _req("get", "/stadtteil/ohligs-aufderhoehe-merscheid/", portal=portal)
    resp = portal_views.portal_home(request, district="ohligs-aufderhoehe-merscheid")
    html = resp.content.decode()
    assert 'data-follow-button="off"' in html
    assert "/folgen/?stadtteil=ohligs-aufderhoehe-merscheid" in html
    assert "csrfmiddlewaretoken" not in html  # кэш P0-1 цел

    request = _req("get", "/?kat=lebensmittel-getraenke", {"kat": "lebensmittel-getraenke"}, portal)
    resp = portal_views.portal_home(request)
    html = resp.content.decode()
    assert "/folgen/?bereich=lebensmittel-getraenke" in html
    assert "csrfmiddlewaretoken" not in html


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_business_page_button_and_following_state_hidden_for_demo():
    from apps.aggregator import reviews_views

    portal = _portal()
    tenant = _tenant()
    resp = reviews_views.business_page(
        _req("get", f"/unternehmen/{tenant.slug}/", portal=portal), tenant.slug
    )
    assert 'data-follow-button="off"' in resp.content.decode()
    user = _user(last_login_at=timezone.now())
    follow.follow_now(
        user, follow.Target("business", tenant.schema_name), frequency="daily", portal=portal
    )
    resp = reviews_views.business_page(
        _req("get", f"/unternehmen/{tenant.slug}/", portal=portal, user=user), tenant.slug
    )
    assert 'data-follow-button="on"' in resp.content.decode()
    demo = _tenant(is_demo=True)
    # T-8.26 S1: демо-бизнес виден только на портале-превью (show_demo)…
    with pytest.raises(Http404):
        reviews_views.business_page(
            _req("get", f"/unternehmen/{demo.slug}/", portal=portal), demo.slug
        )
    preview = _portal(show_demo=True)
    resp = reviews_views.business_page(
        _req("get", f"/unternehmen/{demo.slug}/", portal=preview), demo.slug
    )
    # …и даже там без кнопки «Folgen».
    assert "data-follow-button" not in resp.content.decode()


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_konto_lists_follows_and_toggle_changes_frequency():
    portal = _portal()
    tenant = _tenant()
    user = _user(last_login_at=timezone.now())
    sub = follow.follow_now(
        user, follow.Target("business", tenant.schema_name), frequency="daily", portal=portal
    )
    resp = account_views.account(_req("get", "/konto/", portal=portal, user=user))
    html = resp.content.decode()
    assert 'data-follow-row="business:' in html
    assert tenant.name in html
    resp = follow_views.follow_toggle(
        _req(
            "post",
            "/konto/folgen/",
            {"action": "frequency", "sub": sub.token, "frequency": "instant"},
            portal=portal,
            user=user,
        )
    )
    assert resp.status_code == 302
    sub.refresh_from_db()
    assert sub.frequency == "instant"
    # чужой токен не трогает
    other = _user(last_login_at=timezone.now())
    follow_views.follow_toggle(
        _req(
            "post",
            "/konto/folgen/",
            {"action": "remove", "sub": sub.token},
            portal=portal,
            user=other,
        )
    )
    assert FollowSubscription.objects.filter(pk=sub.pk).exists()


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_toggle_next_rejects_foreign_host():
    portal = _portal()
    tenant = _tenant()
    user = _user(last_login_at=timezone.now())
    resp = follow_views.follow_toggle(
        _req(
            "post",
            "/konto/folgen/",
            {"unternehmen": tenant.slug, "next": "//evil.test/x"},
            portal=portal,
            user=user,
        )
    )
    assert resp["Location"] == reverse("portal-account")
    assert user.follows.count() == 1


# --- сводка -------------------------------------------------------------------------------


def _setup_follow(frequency="daily", kind="business", confirmed_days_ago=3):
    portal = _portal()
    tenant = _tenant()
    user = _user()
    if kind == "business":
        target = follow.Target("business", tenant.schema_name)
    elif kind == "section":
        target = follow.Target("section", "lebensmittel-getraenke", "Solingen")
    else:
        target = follow.Target("district", "ohligs-aufderhoehe-merscheid", "Solingen")
    sub = follow.follow_now(user, target, frequency=frequency, portal=portal)
    FollowSubscription.objects.filter(pk=sub.pk).update(
        confirmed_at=timezone.now() - timedelta(days=confirmed_days_ago)
    )
    sub.refresh_from_db()
    return portal, tenant, user, sub


def test_digest_sections_cap_total_and_links():
    portal, tenant, user, sub = _setup_follow()
    for i in range(7):
        _listing(tenant, title={"de": f"Neu {i}"})
    now = _at(9)
    assert follow_digest.digest_for_user(user, now=now) is True
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == [user.email]
    assert msg.extra_headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert f"https://{portal.host}/folgen/abmelden/" in msg.extra_headers["List-Unsubscribe"]
    body = msg.body
    assert body.count("Neu ") == follow_digest.ITEMS_PER_FOLLOW
    assert "Alle anzeigen (7)" in body
    assert f"https://{portal.host}/unternehmen/{tenant.slug}/?ch=digest" in body
    assert "ch=digest" in body
    sub.refresh_from_db()
    assert sub.last_sent_at == now
    digest = FollowDigest.objects.get(user=user)
    assert digest.period_key == "d:2026-10-21"
    assert len(digest.item_keys) == follow_digest.ITEMS_PER_FOLLOW


def test_empty_digest_not_sent_and_last_sent_untouched():
    _portal, _tenant_, user, sub = _setup_follow()
    assert follow_digest.digest_for_user(user, now=_at(9)) is False
    assert mail.outbox == []
    assert FollowDigest.objects.count() == 0
    sub.refresh_from_db()
    assert sub.last_sent_at is None


def test_section_and_district_only_offer_kinds_business_all_kinds():
    portal, tenant, user, section_sub = _setup_follow(kind="section")
    _listing(tenant, listing_kind=AggregatorListing.KIND_PRODUCT, title={"de": "Produktneu"})
    _listing(tenant, title={"de": "Aktionneu"})
    now = _at(9)
    sections = follow_digest.build_digest(user, [section_sub], now=now).sections
    titles = [i.title_text for i in sections[0].items]
    assert titles == ["Aktionneu"]
    biz_sub = follow.follow_now(
        user, follow.Target("business", tenant.schema_name), frequency="daily", portal=portal
    )
    FollowSubscription.objects.filter(pk=biz_sub.pk).update(
        confirmed_at=timezone.now() - timedelta(days=1)
    )
    biz_sub.refresh_from_db()
    sections = follow_digest.build_digest(user, [biz_sub], now=now).sections
    assert sorted(i.title_text for i in sections[0].items) == ["Aktionneu", "Produktneu"]


def test_demo_withheld_expired_never_in_digest():
    portal, tenant, user, sub = _setup_follow(kind="district")
    demo_tenant = _tenant(is_demo=True)
    _listing(demo_tenant, is_demo=True, title={"de": "Demo"})
    _listing(tenant, ends_at=timezone.now() - timedelta(hours=1), title={"de": "Abgelaufen"})
    _listing(tenant, hidden_at=timezone.now(), title={"de": "Versteckt"})
    _listing(
        tenant,
        listing_kind=AggregatorListing.KIND_EVENT,
        starts_at=timezone.now() - timedelta(days=1),
        title={"de": "Vorbei"},
    )
    withheld = _tenant(in_city_catalog=False)
    _listing(withheld, title={"de": "Zurückgehalten"})
    assert follow_digest.build_digest(user, [sub], now=_at(9)) is None


def test_items_after_confirmation_only():
    portal, tenant, user, sub = _setup_follow(confirmed_days_ago=0)
    old = _listing(tenant, title={"de": "Alt"})
    AggregatorListing.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(days=2)
    )
    assert follow_digest.build_digest(user, [sub], now=_at(9)) is None


def test_recreated_listing_not_resent():
    portal, tenant, user, sub = _setup_follow()
    listing = _listing(tenant, source_ref="promo-1")
    assert follow_digest.digest_for_user(user, now=_at(9)) is True
    listing.delete()
    _listing(tenant, source_ref="promo-1")  # синк пересоздал строку → новый created_at
    assert follow_digest.digest_for_user(user, now=_at(9, day=datetime(2026, 10, 22))) is False
    assert len(mail.outbox) == 1


def test_since_floor_keeps_alle_anzeigen_superset():
    """Каждый элемент секции есть в выдаче по ссылке «Alle anzeigen» (блок ⊆ ленты)."""
    from apps.aggregator import portal_views

    portal, tenant, user, sub = _setup_follow(kind="section", confirmed_days_ago=40)
    fresh = _listing(tenant, title={"de": "Frisch"})
    stale = _listing(tenant, title={"de": "Zu alt"})
    AggregatorListing.objects.filter(pk=stale.pk).update(
        created_at=timezone.now() - timedelta(days=20)
    )
    digest = follow_digest.build_digest(user, [sub], now=timezone.now())
    assert [i.pk for i in digest.sections[0].items] == [fresh.pk]
    url = digest.sections[0].more_url
    assert url == f"https://{portal.host}/?kat=lebensmittel-getraenke&neu=1&ch=digest"
    with override_settings(ROOT_URLCONF="config.urls_portal"):
        req = _req("get", "/", {"kat": "lebensmittel-getraenke", "neu": "1"}, portal=portal)
        html = portal_views.portal_home(req).content.decode()
    assert "Frisch" in html


def test_daily_gate_before_8_then_once_after_and_catch_up():
    portal, tenant, user, sub = _setup_follow()
    _listing(tenant)
    assert follow_digest.digest_for_user(user, now=_at(7, 59)) is False
    assert follow_digest.digest_for_user(user, now=_at(10)) is True  # beat в 8 лежал — ушло в 10
    assert follow_digest.digest_for_user(user, now=_at(11)) is False  # не дважды в день
    assert len(mail.outbox) == 1


def test_weekly_monday_and_catch_up_once_per_week():
    portal, tenant, user, sub = _setup_follow(frequency="weekly")
    FollowSubscription.objects.filter(pk=sub.pk).update(
        confirmed_at=_at(12, day=datetime(2026, 10, 14))
    )
    _listing(tenant)
    sunday = datetime(2026, 10, 18)
    assert follow_digest.digest_for_user(user, now=_at(9, day=sunday)) is False
    tuesday = datetime(2026, 10, 20)
    assert follow_digest.digest_for_user(user, now=_at(9, day=tuesday)) is True  # догнал
    later = _listing(tenant)  # новинка ПОСЛЕ письма вторника (часы теста идут вперёд)
    AggregatorListing.objects.filter(pk=later.pk).update(
        created_at=_at(12, day=datetime(2026, 10, 24))
    )
    wednesday = datetime(2026, 10, 21)
    assert follow_digest.digest_for_user(user, now=_at(9, day=wednesday)) is False
    next_monday = datetime(2026, 10, 26)
    assert follow_digest.digest_for_user(user, now=_at(9, day=next_monday)) is True


def test_one_mail_per_day_for_daily_plus_weekly_and_instant_excluded():
    portal, tenant, user, sub = _setup_follow()
    other = _tenant()
    weekly = follow.follow_now(
        user, follow.Target("business", other.schema_name), frequency="weekly", portal=portal
    )
    third = _tenant()
    instant = follow.follow_now(
        user, follow.Target("business", third.schema_name), frequency="instant", portal=portal
    )
    FollowSubscription.objects.filter(pk__in=[weekly.pk, instant.pk]).update(
        confirmed_at=timezone.now() - timedelta(days=3)
    )
    _listing(tenant, title={"de": "T1"})
    _listing(other, title={"de": "T2"})
    _listing(third, title={"de": "T3"})
    assert follow_digest.digest_for_user(user, now=_at(9)) is True
    assert len(mail.outbox) == 1
    body = mail.outbox[0].body
    assert "T1" in body and "T2" in body and "T3" not in body


def test_digest_dedupe_period_unique_and_smtp_failure_rolls_back():
    portal, tenant, user, sub = _setup_follow()
    _listing(tenant)
    now = _at(9)
    digest = follow_digest.build_digest(user, [sub], now=now)
    with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("smtp")):
        with pytest.raises(OSError):
            follow_digest.send(digest, period_key="d:x", now=now)
    assert FollowDigest.objects.count() == 0
    sub.refresh_from_db()
    assert sub.last_sent_at is None
    assert follow_digest.send(digest, period_key="d:x", now=now) is True
    assert follow_digest.send(digest, period_key="d:x", now=now) is False
    assert len(mail.outbox) == 1


def test_run_daily_fans_out_only_due_users(monkeypatch):
    queued = []
    monkeypatch.setattr(tasks.send_follow_digest_user, "delay", lambda **kw: queued.append(kw))
    portal, tenant, user, sub = _setup_follow()
    _, _, inactive_user, _ = _setup_follow()
    inactive_user.is_active = False
    inactive_user.save()
    _, _, instant_user, _ = _setup_follow(frequency="instant")
    assert follow_digest.run_daily(now=_at(7)) == 0
    assert follow_digest.run_daily(now=_at(8)) == 1
    assert queued[0]["user_id"] == user.pk
    assert queued[0]["dedupe_key"] == f"follow:{user.pk}:d:2026-10-21:8"


def test_instant_batches_per_user_and_respects_quiet_hours(monkeypatch):
    queued = []
    monkeypatch.setattr(tasks.send_follow_instant_user, "delay", lambda **kw: queued.append(kw))
    portal, tenant, user, sub = _setup_follow(frequency="instant")
    _listing(tenant, title={"de": "I1"})
    _listing(tenant, title={"de": "I2"})
    assert follow_digest.run_instant(now=_at(22, 30)) == 0
    assert follow_digest.run_instant(now=_at(6, 30)) == 0
    assert follow_digest.run_instant(now=_at(12, 7)) == 1  # fan-out: один житель
    assert queued[0]["user_id"] == user.pk
    assert follow_digest.instant_for_user(user, now=_at(12, 7)) is True
    assert len(mail.outbox) == 1
    assert "I1" in mail.outbox[0].body and "I2" in mail.outbox[0].body
    assert FollowDigest.objects.get(user=user).period_key == "i:2026-10-21T12:00"
    assert follow_digest.instant_for_user(user, now=_at(12, 20)) is False  # ничего нового
    assert follow_digest.instant_for_user(user, now=_at(22, 20)) is False  # тихие часы


def test_digest_rendered_in_user_locale():
    portal, tenant, user, sub = _setup_follow()
    user.locale = "en"
    user.save()
    _listing(tenant)
    assert follow_digest.digest_for_user(user, now=_at(9)) is True
    assert "View all" in mail.outbox[0].body or "Show all" in mail.outbox[0].body


def test_purge_digest_rows_older_than_retention():
    user = _user()
    old = FollowDigest.objects.create(user=user, period_key="d:old")
    FollowDigest.objects.filter(pk=old.pk).update(sent_at=timezone.now() - timedelta(days=91))
    FollowDigest.objects.create(user=user, period_key="d:new")
    assert follow_digest.purge() == 1
    assert FollowDigest.objects.filter(period_key="d:new").exists()


# --- управление и отписка -----------------------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_manage_page_lists_only_own_follows_and_unknown_token_404():
    portal, tenant, user, sub = _setup_follow()
    _, _, other_user, other_sub = _setup_follow()
    token = follow.ensure_follow_token(user)
    resp = follow_views.follow_manage(
        _req("get", f"/folgen/verwalten/{token}/", portal=portal), token
    )
    html = resp.content.decode()
    assert sub.token in html and other_sub.token not in html
    assert resp["Referrer-Policy"] == "no-referrer"
    from django.http import Http404

    with pytest.raises(Http404):
        follow_views.follow_manage(_req("get", "/folgen/verwalten/x/", portal=portal), "x")


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_one_click_post_unsubscribe_all_csrf_exempt_and_forgets_implicit_user():
    portal, tenant, user, sub = _setup_follow()
    token = follow.ensure_follow_token(user)
    # GET из подвала письма — только страница с кнопкой
    resp = follow_views.follow_unsubscribe(
        _req("get", f"/folgen/abmelden/{token}/?alle=1", {"alle": "1"}, portal=portal), token
    )
    assert resp.status_code == 200 and b"data-follow-unsubscribe" in resp.content
    assert FollowSubscription.objects.filter(user=user).exists()
    # POST почтовика (RFC 8058)
    request = RequestFactory().post(
        f"/folgen/abmelden/{token}/?alle=1",
        "List-Unsubscribe=One-Click",
        content_type="application/x-www-form-urlencoded",
    )
    request.portal = portal
    resp = follow_views.follow_unsubscribe(request, token)
    assert resp.status_code == 200 and b"data-follow-unsubscribed" in resp.content
    assert FollowSubscription.objects.filter(user_id=user.pk).count() == 0
    assert not PortalUser.objects.filter(pk=user.pk).exists()  # неявный житель забыт


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_unsubscribe_single_keeps_user_with_login():
    portal, tenant, user, sub = _setup_follow()
    user.last_login_at = timezone.now()
    user.save()
    request = RequestFactory().post(f"/folgen/abmelden/{sub.token}/")
    request.portal = portal
    resp = follow_views.follow_unsubscribe(request, sub.token)
    assert resp.status_code == 200
    assert not FollowSubscription.objects.filter(pk=sub.pk).exists()
    assert PortalUser.objects.filter(pk=user.pk).exists()


def test_forget_if_empty_keeps_user_with_favorites():
    from apps.aggregator.models import FavoriteListing

    portal, tenant, user, sub = _setup_follow()
    FavoriteListing.objects.create(user=user, listing=_listing(tenant))
    follow.unsubscribe_all(user)
    assert PortalUser.objects.filter(pk=user.pk).exists()


# --- маршруты -----------------------------------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_public")
def test_entdecken_business_route_resolves_to_business_page():
    match = resolve("/entdecken/unternehmen/x/")
    assert match.url_name == "portal-business"
    assert resolve("/entdecken/folgen/").url_name == "aggregator-follow"


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_robots_disallow_folgen():
    from apps.aggregator import portal_views

    portal = _portal()
    resp = portal_views.portal_robots_txt(_req("get", "/robots.txt", portal=portal))
    assert b"Disallow: /folgen/" in resp.content


@override_settings(ROOT_URLCONF="config.urls_public")
def test_platform_robots_disallow_folgen():
    from apps.aggregator import views

    resp = views.robots_txt(RequestFactory().get("/robots.txt"))
    assert b"Disallow: /entdecken/folgen/" in resp.content


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_manage_remove_last_follow_of_implicit_user_shows_unsubscribed_not_404():
    portal, tenant, user, sub = _setup_follow()
    token = follow.ensure_follow_token(user)
    resp = follow_views.follow_manage(
        _req("post", f"/folgen/verwalten/{token}/", {"action": "remove", "sub": sub.token}, portal),
        token,
    )
    assert resp.status_code == 200 and b"data-follow-unsubscribed" in resp.content
    assert not PortalUser.objects.filter(pk=user.pk).exists()


def test_digest_sanitizes_tenant_text_and_drops_bad_links():
    portal, tenant, user, sub = _setup_follow()
    _listing(
        tenant,
        title={"de": "Angebot\nhttps://evil.test/login\nZeile"},
        detail_url="https://x.test/p/",
    )
    _listing(tenant, title={"de": "Kaputt"}, detail_url="javascript:alert(1)")
    digest = follow_digest.build_digest(user, [sub], now=_at(9))
    titles = [i.digest_title for i in digest.sections[0].items]
    assert titles == ["Angebot https://evil.test/login Zeile"]
    _subject, text, _html = follow_digest.render(digest)
    assert "\nhttps://evil.test/login" not in text


def test_business_digest_excludes_business_card_itself():
    portal, tenant, user, sub = _setup_follow()
    _listing(tenant, listing_kind=AggregatorListing.KIND_BUSINESS, title={"de": "Karte"})
    assert follow_digest.build_digest(user, [sub], now=_at(9)) is None


def test_stamp_is_single_use(monkeypatch):
    sent = []
    monkeypatch.setattr(tasks.send_follow_confirm_email, "delay", lambda **kw: sent.append(kw))
    portal = _portal()
    tenant = _tenant()
    stamp = _stamp()
    with override_settings(ROOT_URLCONF="config.urls_portal"):
        for _ in range(2):
            follow_views.follow_page(
                _req(
                    "post",
                    f"/folgen/?unternehmen={tenant.slug}",
                    {"email": _email(), "frequency": "daily", "stamp": stamp},
                    portal=portal,
                )
            )
    assert len(sent) == 1
