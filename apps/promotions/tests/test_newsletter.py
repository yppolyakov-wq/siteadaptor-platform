"""G3: рассылки гостям — Double-Opt-In и отправка только согласившимся."""

import pytest
from django.test import RequestFactory

from apps.notifications.models import Notification
from apps.promotions import newsletter, public_views
from apps.promotions.models import Customer, NewsletterCampaign

pytestmark = pytest.mark.django_db


def _req(method="get", data=None):
    rf = RequestFactory()
    req = getattr(rf, method)("/newsletter/", data or {})
    req.tenant = type("T", (), {"name": "Pension"})()

    def build(path):
        return "http://hotel.test" + path

    req.build_absolute_uri = lambda p="/": build(p if p.startswith("/") else "/" + p)
    return req


def test_signup_creates_unconfirmed_and_sends_doi():
    resp = public_views.newsletter_signup(_req("post", {"email": "g@test.de", "name": "Gast"}))
    assert resp.status_code == 200
    c = Customer.objects.get(email="g@test.de")
    assert c.marketing_opt_in is False  # согласие ещё не подтверждено
    assert Notification.objects.filter(type="newsletter_doi", recipient="g@test.de").exists()


def test_signup_honeypot_ignored():
    # бот заполнил honeypot `website` → ни Customer, ни письма, нейтральный «sent»
    resp = public_views.newsletter_signup(
        _req("post", {"email": "bot@test.de", "name": "Bot", "website": "spam"})
    )
    assert resp.status_code == 200
    assert not Customer.objects.filter(email="bot@test.de").exists()
    assert not Notification.objects.filter(type="newsletter_doi").exists()


def test_signup_already_subscribed_is_neutral_and_no_resend():
    # уже подтверждённый подписчик → нейтральный ответ (не раскрываем статус) и БЕЗ повторного письма
    Customer.objects.create(name="Sub", email="sub@test.de", marketing_opt_in=True)
    public_views.newsletter_signup(_req("post", {"email": "sub@test.de"}))
    assert not Notification.objects.filter(type="newsletter_doi", recipient="sub@test.de").exists()


def test_confirm_sets_opt_in():
    c = Customer.objects.create(name="A", email="a@test.de")
    token = newsletter.doi_token(c)
    public_views.newsletter_confirm(_req(), token)
    c.refresh_from_db()
    assert c.marketing_opt_in is True and c.marketing_opt_in_at is not None


def test_bad_doi_token_is_safe():
    assert newsletter.load_doi_token("garbage") is None


def test_send_campaign_only_to_consented():
    Customer.objects.create(name="Yes", email="yes@test.de", marketing_opt_in=True)
    Customer.objects.create(name="No", email="no@test.de", marketing_opt_in=False)
    Customer.objects.create(
        name="Unsub", email="unsub@test.de", marketing_opt_in=True, unsubscribed=True
    )
    Customer.objects.create(name="NoMail", email="", marketing_opt_in=True)
    camp = NewsletterCampaign.objects.create(subject="Hallo", body="News")
    n = newsletter.send_campaign(camp, base_url="http://hotel.test")
    assert n == 1
    camp.refresh_from_db()
    assert camp.status == NewsletterCampaign.STATUS_SENT and camp.recipient_count == 1
    assert Notification.objects.filter(type="newsletter_campaign", recipient="yes@test.de").exists()
    assert not Notification.objects.filter(recipient="no@test.de").exists()


def test_send_campaign_idempotent():
    Customer.objects.create(name="Yes", email="yes@test.de", marketing_opt_in=True)
    camp = NewsletterCampaign.objects.create(subject="S", body="B")
    newsletter.send_campaign(camp, base_url="http://hotel.test")
    # повторная отправка — no-op (уже sent)
    assert newsletter.send_campaign(camp, base_url="http://hotel.test") == 1
    assert Notification.objects.filter(type="newsletter_campaign").count() == 1
