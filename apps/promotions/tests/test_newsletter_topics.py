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
    assert newsletter.set_topics(c, ["x", "999999"], source="form") == "all"


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
