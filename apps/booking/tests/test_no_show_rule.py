"""KA-12 E6.4c: «Anzahlung nach Nichterscheinen».

Правило владельца: ≥ N неявок по e-mail за окно → онлайн-запись только с
депозитом; Stripe не готов / офлайн-оплата / группа слотов → запись не создаётся,
нейтральная просьба позвонить. Решение — ДО брони; правило выключено — прежний
путь байт-в-байт. Тексты не называют причину (не оракул)."""

import uuid
from datetime import timedelta

import pytest
import stripe
from django.contrib.messages import get_messages
from django.core.cache.backends.locmem import LocMemCache
from django.utils import timezone

from apps.booking import availability, no_show_rule, public_views, services
from apps.booking.models import Booking, Pass
from apps.booking.tests.test_public import _req
from apps.booking.tests.test_services import _future_day, _resource, _rule, _service
from apps.tenants.siteconfig import normalize, normalize_booking
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

RULE = {"booking": {"no_show_deposit": {"after": 2, "days": 365}}}


@pytest.fixture(autouse=True)
def _env(monkeypatch, settings):
    from apps.core import ratelimit

    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr(ratelimit, "cache", LocMemCache(f"rl-noshow-{uuid.uuid4()}", {}))


def _tenant(rule=True, stripe=True, phone="0211 123"):
    return TenantFactory.build(
        business_type="friseur",
        site_config=dict(RULE) if rule else {},
        payments_enabled=stripe,
        stripe_connect_id="acct_1" if stripe else "",
        contact_phone=phone,
    )


@pytest.fixture
def stripe_on(monkeypatch):
    from apps.billing import connect

    calls = []
    monkeypatch.setattr(connect, "is_connect_configured", lambda: True)
    monkeypatch.setattr(
        public_views.payments,
        "deposit_checkout_url",
        lambda b, t, **kw: calls.append(b) or "https://stripe.test/dep",
    )
    return calls


def _past_no_show(email, n=2, days_ago=30):
    resource = _resource()
    for i in range(n):
        start = timezone.now() - timedelta(days=days_ago + i)
        b = services.book(
            resource, start=start, end=start + timedelta(hours=1), name="X", email=email
        )
        Booking.objects.filter(pk=b.pk).update(status="no_show")


def _service_setup(**svc):
    resource = _resource(type="staff")
    day = _future_day()
    _rule(resource, day, "09:00", "18:00")
    service = _service(duration_minutes=60, price_cents=5000, **svc)
    return service, availability.service_slots(service, day)


def _post_service(tenant, service, starts, email="anna@web.de", ip=None, **extra):
    data = {"start": [s.isoformat() for s in starts], "name": "Anna", "email": email}
    data.update(extra)
    request = _req("post", f"/termin/leistung/{service.pk}/buchen/", data, tenant=tenant)
    if ip:
        request.META["REMOTE_ADDR"] = ip
    response = public_views.service_book(request, pk=service.pk)
    return response, [str(m) for m in get_messages(request)]


# --- нормализация -----------------------------------------------------------------


def test_normalize_booking_clamps_and_drops_garbage():
    assert normalize_booking(None) == {}
    assert normalize_booking({"no_show_deposit": "x"}) == {}
    assert normalize_booking({"no_show_deposit": {}}) == {
        "no_show_deposit": {"after": 2, "days": 365}
    }
    out = normalize_booking({"no_show_deposit": {"after": 99, "days": 1, "cents": -5}})
    assert out == {"no_show_deposit": {"after": 10, "days": 30}}
    assert (
        normalize_booking({"no_show_deposit": {"cents": "1500"}})["no_show_deposit"]["cents"]
        == 1500
    )


def test_normalize_keeps_key_only_when_enabled():
    assert "booking" not in normalize({})
    assert normalize(RULE)["booking"] == RULE["booking"]


# --- подсчёт ------------------------------------------------------------------------


def test_count_window_mailbox_and_plus_address():
    _past_no_show("anna@web.de", n=1)
    _past_no_show("Anna+salon@WEB.de", n=1)
    _past_no_show("anna@web.de", n=1, days_ago=400)  # вне окна
    assert no_show_rule.recent_no_shows_for_email("anna+x@web.de", 365) == 2
    assert no_show_rule.recent_no_shows_for_email("other@web.de", 365) == 0
    assert no_show_rule.recent_no_shows_for_email("", 365) == 0


def test_count_is_one_query(django_assert_num_queries):
    with django_assert_num_queries(1):
        no_show_rule.recent_no_shows_for_email("anna@web.de", 365)


def test_cancelled_does_not_count():
    resource = _resource()
    start = timezone.now() - timedelta(days=3)
    for _ in range(3):
        b = services.book(
            resource, start=start, end=start + timedelta(hours=1), name="X", email="c@web.de"
        )
        Booking.objects.filter(pk=b.pk).update(status="cancelled")
        start -= timedelta(days=1)
    assert no_show_rule.recent_no_shows_for_email("c@web.de", 365) == 0


# --- витрина: услуга ------------------------------------------------------------------


def test_rule_off_is_unchanged(stripe_on):
    _past_no_show("anna@web.de", n=5)
    service, slots = _service_setup()
    response, _msgs = _post_service(_tenant(rule=False), service, slots[:1])
    booking = Booking.objects.get(service=service)
    assert response.url == f"/t/{booking.reference_code}/"
    assert booking.deposit_cents == 0 and not stripe_on


def test_flagged_forced_deposit_to_stripe(stripe_on):
    _past_no_show("anna@web.de")
    service, slots = _service_setup()
    response, _msgs = _post_service(_tenant(), service, slots[:1])
    booking = Booking.objects.get(service=service)
    assert response.url == "https://stripe.test/dep"
    assert booking.payment_state == Booking.PAYMENT_PENDING
    assert booking.deposit_cents == 5000  # нет депозита услуги/правила → вся цена (В-A1)


def test_forced_deposit_uses_service_deposit_then_rule_amount(stripe_on):
    _past_no_show("anna@web.de")
    service, slots = _service_setup(deposit_cents=1500)
    _post_service(_tenant(), service, slots[:1])
    assert Booking.objects.get(service=service).deposit_cents == 1500

    service2, slots2 = _service_setup()
    tenant = _tenant()
    tenant.site_config = {"booking": {"no_show_deposit": {"after": 2, "days": 365, "cents": 2000}}}
    _post_service(tenant, service2, slots2[:1])
    assert Booking.objects.get(service=service2).deposit_cents == 2000


def test_not_flagged_is_normal(stripe_on):
    _past_no_show("anna@web.de", n=1)
    service, slots = _service_setup()
    response, _msgs = _post_service(_tenant(), service, slots[:1])
    booking = Booking.objects.get(service=service)
    assert response.url == f"/t/{booking.reference_code}/" and not stripe_on


def test_flagged_without_stripe_creates_no_booking_and_says_call():
    _past_no_show("anna@web.de")
    service, slots = _service_setup()
    response, msgs = _post_service(_tenant(stripe=False), service, slots[:1])
    assert not Booking.objects.filter(service=service).exists()
    assert response.status_code == 302 and "/buchen" not in response.url
    text = " ".join(msgs)
    assert "0211 123" in text
    for leak in ("nicht erschienen", "Nichterscheinen", "anna@web.de", "E-Mail"):
        assert leak not in text


def test_call_text_is_identical_for_all_call_reasons(stripe_on):
    """Оракул: причина «call» не различима по тексту."""
    _past_no_show("anna@web.de")
    service, slots = _service_setup()
    _r1, no_stripe = _post_service(_tenant(stripe=False), service, slots[:1])
    _r2, group = _post_service(_tenant(), service, [slots[0], slots[2]])
    assert no_stripe == group and no_stripe


def test_group_of_slots_is_call(stripe_on):
    """Ревью C2: депозит одной брони не держит N слотов — группа идёт через звонок."""
    _past_no_show("anna@web.de")
    service, slots = _service_setup()
    _post_service(_tenant(), service, [slots[0], slots[2]])
    assert not Booking.objects.filter(service=service).exists() and not stripe_on


def test_email_required_when_rule_on(stripe_on):
    service, slots = _service_setup()
    for bad in ("", "x"):
        _post_service(_tenant(), service, slots[:1], email=bad)
    assert not Booking.objects.filter(service=service).exists()


def test_email_optional_when_rule_off():
    service, slots = _service_setup()
    _post_service(_tenant(rule=False), service, slots[:1], email="")
    assert Booking.objects.filter(service=service).exists()


def test_garbage_pass_code_does_not_bypass(stripe_on):
    """Ревью C1: мусорный код карты раньше уводил мимо любого депозита."""
    _past_no_show("anna@web.de")
    service, slots = _service_setup()
    response, _msgs = _post_service(_tenant(), service, slots[:1], pass_code="NOPE")
    assert response.url == "https://stripe.test/dep"
    assert Booking.objects.get(service=service).payment_state == Booking.PAYMENT_PENDING


def test_valid_pass_skips_rule(stripe_on):
    _past_no_show("anna@web.de")
    service, slots = _service_setup()
    from apps.promotions.models import Customer

    card = Pass.objects.create(
        customer=Customer.objects.create(name="A"), code="K-AAAAAA", credits_total=5
    )
    response, _msgs = _post_service(_tenant(), service, slots[:1], pass_code=card.code)
    booking = Booking.objects.get(service=service)
    assert response.url.startswith(f"/t/{booking.reference_code}/")
    assert booking.card_id == card.pk and not stripe_on


def test_stripe_failure_cancels_without_mail(monkeypatch):
    from apps.billing import connect
    from apps.booking import notifications

    sent = []
    monkeypatch.setattr(notifications, "notify", lambda **kw: sent.append(kw))
    monkeypatch.setattr(connect, "is_connect_configured", lambda: True)

    def boom(*a, **k):
        raise ValueError("no connect id")

    monkeypatch.setattr(public_views.payments, "deposit_checkout_url", boom)
    _past_no_show("anna@web.de")
    sent.clear()
    service, slots = _service_setup()
    response, msgs = _post_service(_tenant(), service, slots[:1])
    booking = Booking.objects.get(service=service)
    assert booking.status == "cancelled"
    assert "0211 123" in " ".join(msgs)
    assert not [m for m in sent if "anna" in str(m.get("recipient", "")) or "anna" in str(m)]
    # слот снова свободен
    assert slots[0] in availability.service_slots(service, slots[0].date())


def test_success_sends_created_mail_once(stripe_on, monkeypatch):
    from apps.booking import notifications

    sent = []
    monkeypatch.setattr(notifications, "notify", lambda **kw: sent.append(kw["type"]))
    _past_no_show("anna@web.de")
    sent.clear()
    service, slots = _service_setup()
    _post_service(_tenant(), service, slots[:1])
    assert sent.count("booking_created") == 1


def test_mailbox_rate_limit(monkeypatch):
    monkeypatch.setattr(public_views, "RL_LIMIT", 1000)  # проверяем лимит ящика, не IP
    service, slots = _service_setup()
    tenant = _tenant(stripe=False)
    codes = set()
    msgs = []
    for _ in range(no_show_rule.RL_EMAIL_LIMIT + 2):
        response, m = _post_service(
            tenant, service, slots[:1], email="probe+x@web.de", ip="10.7.7.7"
        )
        codes.add(response.status_code)
        msgs.extend(m)
        Booking.objects.filter(service=service).delete()
    assert codes == {302}  # не пустая 429-страница: редирект с нейтральным текстом
    assert any("0211 123" in m for m in msgs)


# --- витрина: ресурс (Tisch/Platz) ----------------------------------------------------


def _post_resource(tenant, resource, **extra):
    start, end = availability.free_slots(resource, _future_day())[0]
    data = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "name": "Anna",
        "email": "anna@web.de",
    }
    data.update(extra)
    request = _req("post", f"/termin/{resource.pk}/buchen/", data, tenant=tenant)
    return public_views.termin_book(request, pk=resource.pk)


def test_resource_forced_deposit(stripe_on):
    _past_no_show("anna@web.de")
    resource = _resource(deposit_cents=1000)
    _rule(resource, _future_day())
    response = _post_resource(_tenant(), resource)
    assert response.url == "https://stripe.test/dep"
    assert (
        Booking.objects.get(resource=resource, customer__email="anna@web.de").deposit_cents == 1000
    )


def test_resource_without_amount_is_call(stripe_on):
    _past_no_show("anna@web.de")
    resource = _resource()
    _rule(resource, _future_day())
    _post_resource(_tenant(), resource)
    assert not Booking.objects.filter(resource=resource).exists()


@pytest.mark.parametrize("method", ["invoice", "vorkasse"])
def test_offline_payment_is_call(stripe_on, monkeypatch, method):
    """Ревью H2: Rechnung/Vorkasse не обходят депозит по правилу."""
    from apps.core import payment_methods

    monkeypatch.setattr(payment_methods, "normalize", lambda *a, **k: method)
    _past_no_show("anna@web.de")
    resource = _resource(deposit_cents=1000)
    _rule(resource, _future_day())
    _post_resource(_tenant(), resource, payment=method)
    assert not Booking.objects.filter(resource=resource).exists() and not stripe_on


# --- кабинет --------------------------------------------------------------------------


def _cab(user_role, data):
    from django.contrib.auth.models import AnonymousUser  # noqa: F401
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.tenants.models import Tenant

    tenant = Tenant.objects.filter(schema_name="public").first() or TenantFactory(
        schema_name=f"t_{uuid.uuid4().hex[:8]}", auto_create_schema=False
    )
    tenant.site_config = {"presence": {"mode": "on"}}
    tenant.save(update_fields=["site_config"])
    request = RequestFactory().post("/dashboard/booking/nichterscheinen/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    request._messages = FallbackStorage(request)
    request.tenant = tenant
    request.user = type(
        "U",
        (),
        {"is_authenticated": True, "is_active": True, "pk": 1, "get_username": lambda self: "u"},
    )()
    return request, tenant


@pytest.mark.parametrize("allowed", [True, False])
def test_cabinet_save_roles_and_targeted_write(monkeypatch, allowed):
    from django.core.exceptions import PermissionDenied

    from apps.booking import views

    monkeypatch.setattr(views, "_can_edit_policy", lambda user: allowed)
    request, tenant = _cab(
        "owner", {"enabled": "1", "after": "3", "days": "180", "amount": "12,50"}
    )
    if not allowed:
        with pytest.raises(PermissionDenied):
            views.no_show_rule_save.__wrapped__.__wrapped__(request)
        tenant.refresh_from_db()
        assert "booking" not in tenant.site_config
        return
    views.no_show_rule_save.__wrapped__.__wrapped__(request)
    tenant.refresh_from_db()
    assert tenant.site_config["booking"] == {
        "no_show_deposit": {"after": 3, "days": 180, "cents": 1250}
    }
    assert tenant.site_config["presence"] == {"mode": "on"}  # чужой ключ цел (W6)

    request2, _t = _cab("owner", {"after": "3"})
    request2.tenant = tenant
    tenant.site_config = {**tenant.site_config}
    views.no_show_rule_save.__wrapped__.__wrapped__(request2)
    tenant.refresh_from_db()
    assert "booking" not in tenant.site_config  # выключено → ключа нет


def test_save_requires_login_and_post():
    from apps.booking import views

    assert hasattr(views.no_show_rule_save, "__wrapped__")


def test_buybox_shows_policy_line_only_when_rule_on():
    service, slots = _service_setup()
    data = {"tag": slots[0].date().isoformat(), "slot": slots[0].isoformat()}

    def body(tenant):
        req = _req(path=f"/termin/leistung/{service.pk}/", data=data, tenant=tenant)
        return public_views.service_slots(req, pk=service.pk).content.decode()

    on, off = body(_tenant()), body(_tenant(rule=False))
    assert "data-no-show-terms" in on and "data-no-show-terms" not in off
    assert 'id="id_email" name="email" type="email" required' in on
    assert 'id="id_email" name="email" type="email" required' not in off


def test_privacy_paragraph_only_when_rule_on():
    assert _tenant()._privacy_no_show_paragraph()
    assert _tenant(rule=False)._privacy_no_show_paragraph() == ""


# --- ревью кода (2026-10-25) ----------------------------------------------------------


@pytest.mark.parametrize("amount", ["abc", "1,2,3", "-5", "5000"])
def test_cabinet_rejects_bad_amount_without_500(monkeypatch, amount):
    from apps.booking import views

    monkeypatch.setattr(views, "_can_edit_policy", lambda user: True)
    request, tenant = _cab("owner", {"enabled": "1", "amount": amount})
    response = views.no_show_rule_save.__wrapped__.__wrapped__(request)
    assert response.status_code == 302
    tenant.refresh_from_db()
    assert "booking" not in tenant.site_config


def test_cabinet_amount_rounds_half_up(monkeypatch):
    from apps.booking import views

    monkeypatch.setattr(views, "_can_edit_policy", lambda user: True)
    request, tenant = _cab("owner", {"enabled": "1", "amount": "0,105"})
    views.no_show_rule_save.__wrapped__.__wrapped__(request)
    tenant.refresh_from_db()
    assert tenant.site_config["booking"]["no_show_deposit"]["cents"] == 11


def test_disable_keeps_sibling_booking_rules(monkeypatch):
    from apps.booking import views

    monkeypatch.setattr(views, "_can_edit_policy", lambda user: True)
    request, tenant = _cab("owner", {})
    tenant.site_config = {"booking": {"other": 1, "no_show_deposit": {"after": 2}}}
    tenant.save(update_fields=["site_config"])
    views.no_show_rule_save.__wrapped__.__wrapped__(request)
    tenant.refresh_from_db()
    assert tenant.site_config["booking"] == {"other": 1}


def test_stripe_failure_records_no_deal_and_no_doi(monkeypatch):
    from apps.aggregator import conversions
    from apps.billing import connect
    from apps.promotions import newsletter

    counted, doi = [], []
    monkeypatch.setattr(conversions, "count", lambda *a, **k: counted.append(1))
    monkeypatch.setattr(newsletter, "maybe_send_doi", lambda *a, **k: doi.append(1))
    monkeypatch.setattr(connect, "is_connect_configured", lambda: True)

    def boom(*a, **k):
        raise stripe.error.APIConnectionError("down")

    monkeypatch.setattr(public_views.payments, "deposit_checkout_url", boom)
    _past_no_show("anna@web.de")
    service, slots = _service_setup()
    _post_service(_tenant(), service, slots[:1], marketing="on")
    booking = Booking.objects.get(service=service)
    assert booking.status == "cancelled"
    assert booking.payment_state == Booking.PAYMENT_NONE and booking.deposit_cents == 0
    assert not counted and not doi


def test_success_records_deal_once(stripe_on, monkeypatch):
    from apps.aggregator import conversions

    counted = []
    monkeypatch.setattr(conversions, "count", lambda *a, **k: counted.append(1))
    _past_no_show("anna@web.de")
    service, slots = _service_setup()
    _post_service(_tenant(), service, slots[:1])
    assert counted == [1]


def test_pass_race_falls_back_to_deposit(stripe_on, monkeypatch):
    """Гейт пропустил по карте, но погасить не вышло (гонка) — правило в силе."""
    _past_no_show("anna@web.de")
    monkeypatch.setattr(no_show_rule, "pass_covers", lambda *a, **k: True)
    service, slots = _service_setup()
    response, _m = _post_service(_tenant(), service, slots[:1], pass_code="K-GONE00")
    assert response.url == "https://stripe.test/dep"
    booking = Booking.objects.get(service=service)
    assert booking.payment_state == Booking.PAYMENT_PENDING and booking.card_id is None


def test_mailbox_limit_is_per_ip_not_global():
    """Чужой IP не может заблокировать запись владельцу адреса."""
    k1 = no_show_rule.email_rate_key("a@b.de", ip="1.1.1.1", schema="s")
    k2 = no_show_rule.email_rate_key("a@b.de", ip="2.2.2.2", schema="s")
    k3 = no_show_rule.email_rate_key("a+x@b.de", ip="1.1.1.1", schema="s")
    assert k1 != k2 and k1 == k3


def test_pass_race_sends_created_once(stripe_on, monkeypatch):
    from apps.booking import notifications

    sent = []
    monkeypatch.setattr(notifications, "notify", lambda **kw: sent.append(kw["type"]))
    _past_no_show("anna@web.de")
    sent.clear()
    monkeypatch.setattr(no_show_rule, "pass_covers", lambda *a, **k: True)
    service, slots = _service_setup()
    _post_service(_tenant(), service, slots[:1], pass_code="K-GONE00")
    assert sent.count("booking_created") == 1
