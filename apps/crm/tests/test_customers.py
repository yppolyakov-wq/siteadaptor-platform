"""Track C3: CRM-минимум «Клиенты» — список/поиск, карточка, теги, заметки."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.crm import views
from apps.crm.models import CustomerNote
from apps.promotions.models import Customer
from apps.promotions.services import reserve
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/crm/", data=None):
    import uuid

    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"o{uuid.uuid4().hex[:10]}", email="o@test.de", password="pw12345678"
    )
    return request


def test_list_and_search():
    Customer.objects.create(name="Anna Schmidt", email="anna@test.de")
    Customer.objects.create(name="Boris Müller", phone="+49 170 1", tags=["vip"])

    body = views.customer_list(_req()).content.decode()
    assert "Anna Schmidt" in body
    assert "Boris Müller" in body

    body = views.customer_list(_req(data={"q": "anna"})).content.decode()
    assert "Anna Schmidt" in body
    assert "Boris Müller" not in body

    body = views.customer_list(_req(data={"q": "vip"})).content.decode()  # поиск по тегу
    assert "Boris Müller" in body
    assert "Anna Schmidt" not in body


def test_create_customer_with_tags():
    data = {
        "name": "Clara Neu",
        "email": "clara@test.de",
        "phone": "",
        "note": "",
        "tags_input": "VIP, stammkunde, vip,  ",
    }
    resp = views.customer_create(_req("post", "/crm/new/", data))
    assert resp.status_code == 302
    customer = Customer.objects.get(name="Clara Neu")
    assert customer.tags == ["vip", "stammkunde"]  # lower + dedupe + trim


def test_detail_updates_and_shows_reservations():
    promo = PromotionFactory(status="active", available_quantity=5, title={"de": "KartenBrot"})
    res = reserve(promo, name="Dora", email="dora@test.de", quantity=1)
    customer = Customer.objects.get(email="dora@test.de")

    body = views.customer_detail(_req(path=f"/crm/{customer.pk}/"), pk=customer.pk)
    body = body.content.decode()
    assert "KartenBrot" in body
    assert res.reference_code in body

    data = {
        "name": "Dora Lang",
        "email": "dora@test.de",
        "phone": "",
        "note": "",
        "tags_input": "stammkunde",
    }
    resp = views.customer_detail(_req("post", f"/crm/{customer.pk}/", data), pk=customer.pk)
    assert resp.status_code == 302
    customer.refresh_from_db()
    assert customer.name == "Dora Lang"
    assert customer.tags == ["stammkunde"]


def test_note_add_and_render():
    customer = Customer.objects.create(name="Emil")
    resp = views.note_add(
        _req("post", f"/crm/{customer.pk}/notes/", {"text": "Mag Roggenbrot."}), pk=customer.pk
    )
    assert resp.status_code == 302
    assert CustomerNote.objects.filter(customer=customer, text="Mag Roggenbrot.").exists()

    body = views.customer_detail(_req(path=f"/crm/{customer.pk}/"), pk=customer.pk)
    assert "Mag Roggenbrot." in body.content.decode()


def test_customer_without_reservation_is_fine():
    customer = Customer.objects.create(name="Frei Stehend")
    body = views.customer_detail(_req(path=f"/crm/{customer.pk}/"), pk=customer.pk)
    assert body.status_code == 200
    assert "Frei Stehend" in body.content.decode()


def test_manual_create_sets_source_and_consent():
    """D1: ручное создание помечается manual; согласие — только явной галкой."""
    data = {
        "name": "Greta Optin",
        "email": "greta@test.de",
        "phone": "",
        "note": "",
        "tags_input": "",
        "marketing_opt_in": "on",
    }
    resp = views.customer_create(_req("post", "/crm/new/", data))
    assert resp.status_code == 302
    customer = Customer.objects.get(name="Greta Optin")
    assert customer.created_source == Customer.SOURCE_MANUAL
    assert customer.marketing_opt_in is True

    # Клиент из брони — источник по умолчанию reservation, без согласия.
    promo = PromotionFactory(status="active", available_quantity=5)
    reserve(promo, name="Hans", email="hans@test.de", quantity=1)
    hans = Customer.objects.get(email="hans@test.de")
    assert hans.created_source == Customer.SOURCE_RESERVATION
    assert hans.marketing_opt_in is False

    # Бейджи на карточке: источник и согласие видны владельцу.
    body = views.customer_detail(_req(path=f"/crm/{customer.pk}/"), pk=customer.pk)
    body = body.content.decode()
    assert "Marketing" in body and "Manual" in body


def test_detail_shows_loyalty_cards():
    """D1b: карточка 360° — карты лояльности клиента (readonly)."""
    from apps.loyalty.models import LoyaltyCard, LoyaltyProgram

    customer = Customer.objects.create(name="Ines Stempel")
    program = LoyaltyProgram.objects.create(
        label="Kaffee-Karte", stamps_required=10, reward_label="Gratis Kaffee"
    )
    LoyaltyCard.objects.create(program=program, customer=customer, stamps=4, rewards_earned=1)

    body = views.customer_detail(_req(path=f"/crm/{customer.pk}/"), pk=customer.pk)
    body = body.content.decode()
    assert "Kaffee-Karte" in body
    assert "🎁 1" in body


def test_issue_voucher_to_customer():
    """D1: ваучер из карточки клиента привязывается к нему (360°)."""
    from apps.loyalty.models import Voucher

    customer = Customer.objects.create(name="Lena Gutschein")
    resp = views.customer_detail(
        _req(
            "post",
            f"/crm/{customer.pk}/",
            {"action": "issue_voucher", "label": "−10 %", "max_uses": "3"},
        ),
        pk=customer.pk,
    )
    assert resp.status_code == 302
    voucher = Voucher.objects.get(customer=customer)
    assert voucher.label == "−10 %" and voucher.max_uses == 3 and voucher.code.startswith("V-")


def test_card_shows_customer_vouchers():
    from apps.promotions.services import generate_vouchers

    customer = Customer.objects.create(name="Mara")
    generate_vouchers(label="Gratis Kaffee", count=1, customer=customer)
    body = views.customer_detail(_req(path=f"/crm/{customer.pk}/"), pk=customer.pk).content.decode()
    assert "Gratis Kaffee" in body


def test_export_csv_respects_filter():
    """D1c: CSV-экспорт уважает поисковый фильтр и содержит поля D1."""
    Customer.objects.create(name="Jana Vip", email="jana@test.de", tags=["vip"])
    Customer.objects.create(name="Karl Ohne", email="karl@test.de", marketing_opt_in=True)

    resp = views.customer_export_csv(_req(path="/crm/export.csv"))
    assert resp["Content-Type"].startswith("text/csv")
    body = resp.content.decode()
    assert "Jana Vip" in body and "Karl Ohne" in body
    assert body.splitlines()[0].startswith("name,email,phone,tags,marketing_opt_in")
    assert "yes" in body  # согласие Karl

    resp = views.customer_export_csv(_req(path="/crm/export.csv", data={"q": "vip"}))
    body = resp.content.decode()
    assert "Jana Vip" in body and "Karl Ohne" not in body


def test_list_cards_show_batch_ltv():
    """ST-5c: карточный грид (без classic_ui) + LTV батчем на страницу —
    сумма и число покупок на карточке; клиент без выручки — без LTV-строки."""
    from decimal import Decimal

    from apps.finance.models import RevenueEntry

    anna = Customer.objects.create(name="Anna Schmidt", email="anna@test.de")
    Customer.objects.create(name="Boris Müller", phone="+49 170 1")
    RevenueEntry.objects.create(amount=Decimal("30.00"), customer=anna)
    RevenueEntry.objects.create(amount=Decimal("12.50"), customer=anna)

    body = views.customer_list(_req()).content.decode()
    assert "grid sm:grid-cols-2" in body  # карточный грид
    assert ("42,50" in body or "42.50" in body) and "2×" in body
    assert body.count("×") == 1  # у Boris LTV-строки нет


def test_list_classic_keeps_row_list():
    """ST-5c: classic_ui=True — прежний divide-y список (Р7)."""
    from apps.tenants.tests.factories import TenantFactory

    Customer.objects.create(name="Anna Schmidt", email="anna@test.de")
    req = _req()
    req.tenant = TenantFactory(slug="crmcls", name="CrmCls", site_config={"classic_ui": True})
    body = views.customer_list(req).content.decode()
    assert "divide-y divide-gray-100" in body
    assert "grid sm:grid-cols-2" not in body
