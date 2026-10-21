"""T-8.30l: вход клиента в ЛК через Telegram (Mini App магазина).

Фидбэк владельца: в Mini App «Konto → per E-Mail» ссылка не приходила, а пришедшая
открывается в браузере, не в Telegram. Вход по подписанному Telegram initData бота
ЭТОГО магазина: связь из /start → её клиент, иначе новый клиент только с именем.
План — docs/t8-30l-scanner-tg-login-plan-2026-10-21.md.
"""

import json
import time
import uuid
from urllib.parse import urlencode

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache.backends.locmem import LocMemCache
from django.test import RequestFactory

from apps.account import auth, views
from apps.core import ratelimit
from apps.platform_bot.tests.test_t830_initdata import _ref_hash
from apps.promotions.models import Customer
from apps.telegram.models import TelegramBot, TelegramLink
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
TOKEN = "777:SHOP-BOT-TOKEN"
UID = 4242001


@pytest.fixture(autouse=True)
def _env(settings, monkeypatch):
    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr(ratelimit, "cache", LocMemCache(f"rl-tg-login-{uuid.uuid4()}", {}))
    TelegramBot.objects.create(token=TOKEN, bot_username="shop_bot", is_active=True)


def _init_data(uid=UID, token=TOKEN, auth_date=None, name="Lena"):
    fields = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": uuid.uuid4().hex,
        "user": json.dumps({"id": uid, "first_name": name, "username": "lena_x"}),
    }
    fields["hash"] = _ref_hash(fields, token)
    return urlencode(fields)


def _req(init_data, ip="10.91.0.1"):
    req = RequestFactory().post("/konto/telegram/", {"init_data": init_data})
    req.META["REMOTE_ADDR"] = ip
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.session.save()
    req.tenant = TenantFactory.build(business_type="restaurant")
    return req


def test_new_telegram_user_gets_customer_with_name_only():
    req = _req(_init_data())
    old_key = req.session.session_key
    resp = views.telegram_login(req)
    assert resp.status_code == 302
    customer = auth.current_customer(req)
    assert customer is not None and customer.name == "Lena" and customer.email == ""
    assert TelegramLink.objects.get(customer=customer).chat_id == str(UID)
    assert req.session.session_key != old_key  # фиксация сессии исключена


def test_existing_link_logs_into_its_customer():
    c = Customer.objects.create(name="Max", email="max@test.de")
    TelegramLink.objects.create(customer=c, link_token="tok1", chat_id=str(UID))
    req = _req(_init_data())
    views.telegram_login(req)
    assert auth.current_customer(req).pk == c.pk
    assert Customer.objects.count() == 1


def test_repeat_login_reuses_customer():
    views.telegram_login(_req(_init_data()))
    views.telegram_login(_req(_init_data()))
    assert Customer.objects.count() == 1


def test_earliest_link_wins_when_chat_is_linked_twice():
    a = Customer.objects.create(name="A", email="a@test.de")
    b = Customer.objects.create(name="B", email="b@test.de")
    TelegramLink.objects.create(customer=a, link_token="t-a", chat_id=str(UID))
    TelegramLink.objects.create(customer=b, link_token="t-b", chat_id=str(UID))
    req = _req(_init_data())
    views.telegram_login(req)
    assert auth.current_customer(req).pk == a.pk


def test_foreign_bot_signature_is_rejected():
    req = _req(_init_data(token="999:OTHER-BOT"))
    resp = views.telegram_login(req)
    assert resp.status_code == 403
    assert auth.current_customer(req) is None
    assert Customer.objects.count() == 0


def test_stale_init_data_is_rejected():
    req = _req(_init_data(auth_date=int(time.time()) - 2 * 3600))
    assert views.telegram_login(req).status_code == 403


def test_init_data_opened_long_ago_still_works_within_an_hour():
    req = _req(_init_data(auth_date=int(time.time()) - 20 * 60))
    assert views.telegram_login(req).status_code == 302


def test_no_active_bot_is_404():
    from django.http import Http404

    TelegramBot.objects.update(is_active=False)
    with pytest.raises(Http404):
        views.telegram_login(_req(_init_data()))


def test_rate_limit_says_so():
    for _ in range(views.TG_RL_LIMIT):
        ratelimit.hit("acct_tg_ip", "10.91.0.9", limit=99, window=600)
    resp = views.telegram_login(_req(_init_data(), ip="10.91.0.9"))
    assert resp.status_code == 429
    assert Customer.objects.count() == 0


def test_view_keeps_csrf_protection():
    assert not getattr(views.telegram_login, "csrf_exempt", False)


def test_login_page_offers_hidden_telegram_button():
    req = RequestFactory().get("/konto/login/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(business_type="restaurant")
    html = views.login_view(req).content.decode()
    assert "data-tg-login" in html and 'name="init_data"' in html
    assert "Mit Telegram anmelden" in html


# --- DSGVO: клиент без e-mail тоже может выгрузить и удалить данные ----------------------


def test_telegram_only_customer_can_export():
    req = _req(_init_data())
    views.telegram_login(req)
    req2 = _req("")
    req2.session = req.session
    resp = views.export_data(req2)
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["customers"][0]["name"] == "Lena"


def test_telegram_only_customer_can_delete_and_link_goes():
    req = _req(_init_data())
    views.telegram_login(req)
    customer = auth.current_customer(req)
    req2 = _req("")
    req2.session = req.session
    resp = views.delete_account(req2)
    assert resp.status_code == 302
    customer.refresh_from_db()
    assert customer.name != "Lena"
    assert not TelegramLink.objects.filter(customer=customer).exists()


def test_privacy_text_mentions_telegram_login_only_with_active_bot():
    tenant = TenantFactory.build(business_type="restaurant")
    assert "Telegram-ID" in tenant.privacy_text()
    TelegramBot.objects.update(is_active=False)
    assert "Telegram" not in tenant.privacy_text()
