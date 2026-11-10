"""NT-B1: темы рассылки магазина (план nt-notification-preferences §3).

Замки: кампания с темой T — «все темы» и «T» получают, «только U» — нет, неподтвердившие и
отписавшиеся — нет; суммы LTV не удваиваются у клиента с двумя темами; set_topics — пусто или
все = «все», снятые темы удаляются; тему с кампанией не удалить (PROTECT).
"""

import uuid

import pytest
from django.db.models import ProtectedError
from django.utils import timezone

from apps.promotions import newsletter
from apps.promotions.models import (
    Customer,
    CustomerNewsletterTopic,
    NewsletterCampaign,
    NewsletterTopic,
)

pytestmark = pytest.mark.django_db


def _customer(**kw):
    kw.setdefault("email", f"{uuid.uuid4().hex}@kunde.test")
    kw.setdefault("marketing_opt_in", True)
    kw.setdefault("marketing_opt_in_at", timezone.now())
    return Customer.objects.create(**kw)


def _topics():
    return (
        NewsletterTopic.objects.create(name="Mittagstisch", position=1),
        NewsletterTopic.objects.create(name="Events", position=2),
    )


def test_campaign_topic_reaches_all_and_topic_subscribers():
    lunch, events = _topics()
    everything = _customer()
    lunch_only = _customer()
    events_only = _customer()
    newsletter.set_topics(lunch_only, [lunch.pk], source="form")
    newsletter.set_topics(events_only, [events.pk], source="form")
    _customer(marketing_opt_in=False)
    _customer(unsubscribed=True)
    got = set(newsletter.consented_customers(lunch))
    assert got == {everything, lunch_only}
    assert set(newsletter.consented_customers()) == {everything, lunch_only, events_only}


def test_send_campaign_respects_topic(monkeypatch):
    lunch, events = _topics()
    sent = []
    monkeypatch.setattr(newsletter, "notify", lambda **kw: sent.append(kw["recipient"]))
    import apps.telegram.notify as tg

    monkeypatch.setattr(tg, "send_to_customer", lambda *a, **k: None)
    a, b = _customer(), _customer()
    newsletter.set_topics(b, [events.pk], source="form")
    campaign = NewsletterCampaign.objects.create(subject="S", body="B", topic=lunch)
    assert newsletter.send_campaign(campaign, base_url="https://x") == 1
    assert sent == [a.email]


def test_segment_ltv_not_doubled_with_two_topics():
    from apps.finance.models import RevenueEntry

    lunch, events = _topics()
    c = _customer()
    newsletter.set_topics(c, [lunch.pk], source="form")  # одна тема из двух
    CustomerNewsletterTopic.objects.create(customer=c, topic=events)
    RevenueEntry.objects.create(
        customer=c, amount="10.00", date=timezone.localdate(), source="manual", source_ref="r1"
    )
    seg = list(newsletter.segment_customers(top_ltv=5, topic=lunch))
    assert seg == [c] and seg[0]._ltv == 10


def test_set_topics_all_and_narrowing():
    lunch, events = _topics()
    c = _customer()
    assert newsletter.set_topics(c, [lunch.pk, events.pk], source="form") == "all"
    assert not CustomerNewsletterTopic.objects.filter(customer=c).exists()
    assert newsletter.set_topics(c, [lunch.pk], source="preferences") == "some"
    assert newsletter.selected_topic_ids(c) == {str(lunch.pk)}
    # мусор вместо тем — выбор не трогаем (ревью NT-B: иначе молча «все темы»)
    assert newsletter.set_topics(c, ["x", "999999"], source="form") == "some"
    assert newsletter.selected_topic_ids(c) == {str(lunch.pk)}


def test_topic_with_campaign_protected():
    lunch, _events = _topics()
    NewsletterCampaign.objects.create(subject="S", body="B", topic=lunch)
    with pytest.raises(ProtectedError):
        lunch.delete()


# --- NT-B2: форма с темами + DOI --------------------------------------------------------


def _ip_req(method="get", data=None):
    from apps.promotions.tests.test_newsletter import _req

    req = _req(method, data)
    req.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.3"
    return req


def test_form_shows_topics_and_doi_applies_them_on_post_only():
    from apps.promotions import public_views

    lunch, _events = _topics()
    html = public_views.newsletter_signup(_ip_req()).content.decode()
    assert "data-newsletter-topics" in html and "Mittagstisch" in html
    email = f"{uuid.uuid4().hex}@kunde.test"
    captured = {}
    orig = newsletter.send_doi_email

    def spy(customer, *, base_url, topics=None):
        captured["topics"] = topics
        captured["token"] = newsletter.doi_token(customer, topics)
        return orig(customer, base_url=base_url, topics=topics)

    import unittest.mock as m

    with m.patch.object(newsletter, "send_doi_email", spy):
        public_views.newsletter_signup(_ip_req("post", {"email": email, "thema": [str(lunch.pk)]}))
    assert captured["topics"] == [str(lunch.pk)]
    c = Customer.objects.get(email=email)
    public_views.newsletter_confirm(_ip_req(), captured["token"])  # GET — ничего
    assert not CustomerNewsletterTopic.objects.filter(customer=c).exists()
    public_views.newsletter_confirm(_ip_req("post"), captured["token"])
    c.refresh_from_db()
    assert c.marketing_opt_in and newsletter.selected_topic_ids(c) == {str(lunch.pk)}


def test_old_string_token_still_confirms():
    c = _customer(marketing_opt_in=False, marketing_opt_in_at=None)
    from django.core import signing

    token = signing.dumps(str(c.pk), salt="newsletter-doi")
    assert newsletter.load_doi(token) == (c, None)


def test_foreign_topics_in_token_dropped():
    lunch, _events = _topics()
    c = _customer()
    token = newsletter.doi_token(c, [str(lunch.pk), "00000000-0000-0000-0000-000000000000"])
    _cust, topics = newsletter.load_doi(token)
    newsletter.set_topics(c, topics, source="form")
    assert newsletter.selected_topic_ids(c) == {str(lunch.pk)}


# --- NT-B3: страница «Themen wählen» -----------------------------------------------------


@pytest.mark.urls("config.urls_tenant")
def test_preferences_get_no_side_effects_and_narrowing():
    from apps.promotions import public_views

    lunch, events = _topics()
    c = _customer()
    req = _ip_req()
    resp = public_views.newsletter_preferences(req, c.unsubscribe_token)
    html = resp.content.decode()
    assert f'value="{lunch.pk}" checked' in html and f'value="{events.pk}" checked' in html
    assert not CustomerNewsletterTopic.objects.filter(customer=c).exists()
    public_views.newsletter_preferences(
        _ip_req("post", {"action": "save", "thema": [str(events.pk)]}), c.unsubscribe_token
    )
    assert newsletter.selected_topic_ids(c) == {str(events.pk)}
    # расширить отсюда нельзя: lunch не добавится
    public_views.newsletter_preferences(
        _ip_req("post", {"action": "save", "thema": [str(events.pk), str(lunch.pk)]}),
        c.unsubscribe_token,
    )
    assert newsletter.selected_topic_ids(c) == {str(events.pk)}


@pytest.mark.urls("config.urls_tenant")
def test_preferences_all_off_and_empty_selection_unsubscribe():
    from apps.promotions import public_views

    _topics()
    a, b = _customer(), _customer()
    public_views.newsletter_preferences(_ip_req("post", {"action": "all_off"}), a.unsubscribe_token)
    public_views.newsletter_preferences(_ip_req("post", {"action": "save"}), b.unsubscribe_token)
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.unsubscribed and b.unsubscribed


@pytest.mark.urls("config.urls_tenant")
def test_preferences_unknown_token_404():
    from django.http import Http404

    from apps.promotions import public_views

    with pytest.raises(Http404):
        public_views.newsletter_preferences(_ip_req(), uuid.uuid4())


def test_campaign_footer_has_prefs_link_only_with_topics(monkeypatch):
    bodies = []
    monkeypatch.setattr(newsletter, "notify", lambda **kw: bodies.append(kw["body"]))
    import apps.telegram.notify as tg

    monkeypatch.setattr(tg, "send_to_customer", lambda *a, **k: None)
    _customer()
    newsletter.send_campaign(
        NewsletterCampaign.objects.create(subject="S", body="B"), base_url="https://x"
    )
    assert "/newsletter/einstellungen/" not in bodies[-1]
    _topics()
    newsletter.send_campaign(
        NewsletterCampaign.objects.create(subject="S2", body="B"), base_url="https://x"
    )
    assert "/newsletter/einstellungen/" in bodies[-1]


# --- Ревью NT-B: тихое расширение, отписка без тем, старый токен, повтор DOI ------------


def test_inactive_topic_does_not_collapse_to_all():
    lunch, events = _topics()
    c = _customer()
    newsletter.set_topics(c, [lunch.pk, events.pk], source="form")
    newsletter.set_topics(c, [lunch.pk], source="form")
    events.is_active = False
    events.save()
    # клиент оставил lunch при выключенной events — НЕ «все темы» (будущие не придут)
    newsletter.set_topics(c, [lunch.pk], source="preferences")
    assert CustomerNewsletterTopic.objects.filter(customer=c).exists()
    future = NewsletterTopic.objects.create(name="Neu")
    assert c not in set(newsletter.consented_customers(future))


def test_token_with_only_inactive_topics_keeps_selection():
    lunch, events = _topics()
    NewsletterTopic.objects.create(name="Kuchen")
    c = _customer(marketing_opt_in=False, marketing_opt_in_at=None)
    token = newsletter.doi_token(c, [str(events.pk)])
    events.is_active = False
    events.save()
    _cust, topics = newsletter.load_doi(token)
    assert newsletter.set_topics(c, topics, source="form") == "all"
    # но у клиента с выбором ничего не меняется
    newsletter.set_topics(c, [lunch.pk], source="form")
    newsletter.set_topics(c, [str(events.pk)], source="form")
    assert newsletter.selected_topic_ids(c) == {str(lunch.pk)}


def test_stale_doi_token_does_not_widen_after_narrowing():
    lunch, events = _topics()
    c = _customer()
    token = newsletter.doi_token(c, [str(lunch.pk), str(events.pk)])
    import time as _time

    _time.sleep(1.1)
    newsletter.set_topics(c, [events.pk], source="preferences")
    _cust, topics = newsletter.load_doi(token)
    assert topics is None


@pytest.mark.urls("config.urls_tenant")
def test_preferences_without_topics_save_does_not_unsubscribe():
    from apps.promotions import public_views

    c = _customer()
    public_views.newsletter_preferences(_ip_req("post", {"action": "save"}), c.unsubscribe_token)
    c.refresh_from_db()
    assert not c.unsubscribed


def test_full_selection_by_subscriber_sends_no_new_doi():
    from unittest import mock

    from apps.promotions import public_views

    lunch, events = _topics()
    c = _customer()
    with mock.patch.object(newsletter, "send_doi_email") as doi:
        public_views.newsletter_signup(
            _ip_req("post", {"email": c.email, "thema": [str(lunch.pk), str(events.pk)]})
        )
    assert not doi.called


def test_prefs_line_queries_once_per_send(django_assert_max_num_queries):
    _topics()
    customers = [_customer() for _ in range(5)]
    cache: dict = {}
    newsletter._prefs_line(customers[0], "https://x.test", cache)
    with django_assert_max_num_queries(0):
        for c in customers:
            newsletter._prefs_line(c, "https://x.test", cache)


# --- NT-B4: темы в кабинете -------------------------------------------------------------


def _cabinet_post(data):
    from apps.promotions import views

    req = _ip_req("post", data)
    from django.contrib.messages.storage.fallback import FallbackStorage

    req.session = {}
    req._messages = FallbackStorage(req)
    req.user = _owner()
    return views.newsletter_campaigns(req)


def _owner():
    from django.contrib.auth import get_user_model

    U = get_user_model()
    name = uuid.uuid4().hex
    return U.objects.create_user(username=name, email=f"{name}@o.test", password="x")


@pytest.mark.urls("config.urls_tenant")
def test_cabinet_topic_add_toggle_and_protected_delete():
    _cabinet_post({"action": "topic_add", "name": "Mittagstisch"})
    _cabinet_post({"action": "topic_add", "name": "mittagstisch"})  # дубль
    assert NewsletterTopic.objects.count() == 1
    t = NewsletterTopic.objects.get()
    _cabinet_post({"action": "topic_toggle", "topic": str(t.pk)})
    t.refresh_from_db()
    assert not t.is_active
    _cabinet_post({"action": "topic_toggle", "topic": str(t.pk)})
    _cabinet_post({"action": "create", "subject": "Hallo", "body": "Text", "topic": str(t.pk)})
    camp = NewsletterCampaign.objects.get()
    assert camp.topic == t
    _cabinet_post({"action": "topic_delete", "topic": str(t.pk)})
    assert NewsletterTopic.objects.filter(pk=t.pk).exists()  # PROTECT → только выключить
    _cabinet_post({"action": "topic_delete", "topic": "kaputt"})  # мусор — без 500


@pytest.mark.urls("config.urls_tenant")
def test_cabinet_campaign_rejects_inactive_topic():
    t = NewsletterTopic.objects.create(name="Alt", is_active=False)
    _cabinet_post({"action": "create", "subject": "Hallo", "body": "Text", "topic": str(t.pk)})
    assert not NewsletterCampaign.objects.exists()


def test_coupon_campaign_form_takes_active_topic_only():
    from apps.promotions.campaign_pages import create_campaign
    from apps.promotions.forms import CouponCampaignForm

    on = NewsletterTopic.objects.create(name="An")
    off = NewsletterTopic.objects.create(name="Aus", is_active=False)
    base = {"name": "K", "discount_percent": 10, "valid_days": 30, "subject": "S"}
    assert not CouponCampaignForm({**base, "topic": str(off.pk)}).is_valid()
    form = CouponCampaignForm({**base, "topic": str(on.pk)})
    assert form.is_valid(), form.errors
    assert create_campaign(form).topic == on


# --- NT-B5: темы в личном кабинете клиента ---------------------------------------------


@pytest.mark.urls("config.urls_tenant")
def test_account_profile_sets_topics_with_sentinel_only(monkeypatch):
    from django.contrib.messages.storage.fallback import FallbackStorage

    from apps.account import auth, views

    lunch, events = _topics()
    c = _customer()
    monkeypatch.setattr(auth, "current_customer", lambda request: c)
    monkeypatch.setattr(views, "_require_account_active", lambda request: None)

    def post(data):
        req = _ip_req("post", data)
        req.session = {}
        req._messages = FallbackStorage(req)
        return views.profile_view(req)

    # без сентинела (старая форма) темы не трогаются
    post({"name": "A", "marketing": "on", "thema": [str(lunch.pk)]})
    assert newsletter.selected_topic_ids(c) == set()
    post({"name": "A", "marketing": "on", "topics_present": "1", "thema": [str(lunch.pk)]})
    assert newsletter.selected_topic_ids(c) == {str(lunch.pk)}
    row = CustomerNewsletterTopic.objects.get(customer=c)
    assert row.source == CustomerNewsletterTopic.SOURCE_ACCOUNT
    # из кабинета клиента можно и расширить (вошедший — подтверждённая личность)
    post({"name": "A", "marketing": "on", "topics_present": "1"})
    assert newsletter.selected_topic_ids(c) == set()


@pytest.mark.urls("config.urls_tenant")
def test_cabinet_audience_matches_consented_customers():
    """Ревью NT: агрегат адресатов совпадает с фильтром отправки."""
    from django.contrib.messages.storage.fallback import FallbackStorage

    from apps.promotions import views

    lunch, events = _topics()
    _customer()
    only_lunch = _customer()
    newsletter.set_topics(only_lunch, [lunch.pk], source="form")
    NewsletterCampaign.objects.create(subject="S", body="B", topic=events)
    req = _ip_req()
    req.session = {}
    req._messages = FallbackStorage(req)
    req.user = _owner()
    captured = {}
    import unittest.mock as m

    def fake_render(request, template, ctx):
        captured.update(ctx)
        from django.http import HttpResponse

        return HttpResponse("")

    with m.patch.object(views, "render", fake_render):
        views.newsletter_campaigns(req)
    by_name = {t.name: t.audience for t in captured["topics"]}
    assert by_name["Mittagstisch"] == newsletter.consented_customers(lunch).count() == 2
    assert by_name["Events"] == newsletter.consented_customers(events).count() == 1
    assert captured["campaigns"][0].audience == 1
