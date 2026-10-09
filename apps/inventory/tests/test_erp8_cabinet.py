"""ERP-8b: Mängelanzeige в кабинете «Einkauf» — создание, решение, PDF-бланк, отправка.

План — `docs/erp8-maengelanzeige-plan-2026-10-09.md` §5 (замки 7–9).
"""

from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory
from django.utils import translation

from apps.catalog.tests.factories import ProductFactory
from apps.core import documents
from apps.core.tests.test_documents_i18n import pdf_text as _raw_pdf_text
from apps.inventory import maengel, purchasing
from apps.inventory.models import Bestellung, Maengelanzeige
from apps.inventory.pdf import build_maengel_pdf
from apps.inventory.views_purchasing import maengel_pdf, purchasing_view
from apps.notifications.models import Notification
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def pdf_text(data: bytes) -> str:
    """Текст PDF с раскрытыми восьмеричными escape (`\\337` → «ß»): умлауты бланка."""
    import re

    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), _raw_pdf_text(data))


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    username = "chef"


def _req(method="get", data=None, query="", path="/dashboard/purchasing/"):
    req = getattr(RequestFactory(), method)(f"{path}{query}", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = TenantFactory.build(name="Backhaus Krume", address="Markt 3", city="Hilden")
    return req


def _received(email="einkauf@mueller.example"):
    supplier = purchasing.Lieferant.objects.create(
        name="Großhandel Müller", email=email, customer_number="K-77"
    )
    po = purchasing.create_po(supplier=supplier)
    product = ProductFactory(name={"de": "Weizenmehl 25 kg"}, cost_price=Decimal("12.00"))
    line = purchasing.add_po_line(po, product=product, qty=10)
    purchasing.set_po_status(po, Bestellung.STATUS_ORDERED)
    purchasing.receive_po_line(line)
    po.refresh_from_db()
    line.refresh_from_db()
    return po, line


def _create_via_view(po, line):
    return purchasing_view(
        _req(
            "post",
            {
                "action": "create_maengel",
                "po": str(po.pk),
                "carrier": "DHL Freight",
                "delivery_note_ref": "LS-4711",
                "delivery_date": "2026-10-08",
                "result": "Zwei Säcke durchnässt.",
                f"m_qty_{line.pk}": "2",
                f"m_types_{line.pk}": ["packaging", "quality"],
                f"m_desc_{line.pk}": "Säcke nass, Mehl verklumpt",
            },
        )
    )


# ───────────────────────────── 9: кабинет ─────────────────────────────


def test_create_resolve_and_list_badge_via_cabinet():
    po, line = _received()
    resp = _create_via_view(po, line)
    assert resp.status_code == 302 and f"?po={po.pk}" in resp["Location"]
    anzeige = Maengelanzeige.objects.get()
    mangel = anzeige.maengel.get()
    assert mangel.qty == 2 and mangel.defect_types == ["packaging", "quality"]
    assert anzeige.carrier == "DHL Freight" and anzeige.delivery_note_ref == "LS-4711"
    assert str(anzeige.delivery_date) == "2026-10-08" and anzeige.inspected_by == "chef"

    detail = purchasing_view(_req(query=f"?po={po.pk}")).content.decode()
    assert anzeige.reference in detail and "Verpackungsschaden" in detail
    overview = purchasing_view(_req()).content.decode()
    assert "data-maengel-open" in overview  # бейдж открытых рекламаций в списке заказов

    purchasing_view(
        _req(
            "post",
            {
                "action": "resolve_mangel",
                "po": str(po.pk),
                "mangel": str(mangel.pk),
                "decision": "discount",
                "discount": "7,50",
            },
        )
    )
    mangel.refresh_from_db()
    assert mangel.decision == "discount" and mangel.discount == Decimal("7.50")
    assert "data-maengel-open" not in purchasing_view(_req()).content.decode()


def test_create_without_affected_lines_creates_nothing():
    po, line = _received()
    purchasing_view(_req("post", {"action": "create_maengel", "po": str(po.pk)}))
    assert not Maengelanzeige.objects.exists()


def test_resolve_of_a_line_from_another_order_is_refused():
    po, line = _received()
    other_po, other_line = _received()
    anzeige = maengel.create_anzeige(other_po, lines=[{"position": other_line, "qty": 1}])
    mangel = anzeige.maengel.get()
    purchasing_view(
        _req(
            "post",
            {
                "action": "resolve_mangel",
                "po": str(po.pk),
                "mangel": str(mangel.pk),
                "decision": "return",
            },
        )
    )
    mangel.refresh_from_db()
    assert mangel.resolved_at is None


def test_pdf_view_returns_pdf_and_404_for_unknown():
    po, line = _received()
    anzeige = maengel.create_anzeige(po, lines=[{"position": line, "qty": 1}])
    resp = maengel_pdf(_req(path=f"/dashboard/purchasing/maengel/{anzeige.pk}.pdf"), pk=anzeige.pk)
    assert resp.status_code == 200 and resp["Content-Type"] == "application/pdf"
    assert anzeige.reference in resp["Content-Disposition"]
    with pytest.raises(Http404):
        maengel_pdf(_req(), pk=po.pk)  # чужой uuid


def test_pdf_view_requires_login():
    from django.contrib.auth.models import AnonymousUser

    po, line = _received()
    anzeige = maengel.create_anzeige(po, lines=[{"position": line, "qty": 1}])
    req = _req()
    req.user = AnonymousUser()
    assert maengel_pdf(req, pk=anzeige.pk).status_code == 302


# ───────────────────────────── 7: PDF ─────────────────────────────


def test_pdf_carries_form_fields_and_legal_reference(monkeypatch):
    monkeypatch.setattr(documents, "unicode_fonts_available", lambda: False)
    po, line = _received()
    anzeige = maengel.create_anzeige(
        po,
        lines=[
            {
                "position": line,
                "qty": 2,
                "defect_types": ["packaging"],
                "description": "Säcke nass",
            }
        ],
        actor="Anna",
        carrier="DHL Freight",
        delivery_note_ref="LS-4711",
    )
    with translation.override("de"):
        text = pdf_text(build_maengel_pdf(anzeige, TenantFactory.build(name="Backhaus Krume")))
    for needle in (
        "Mängelanzeige",
        anzeige.reference,
        po.reference,
        "LS-4711",
        "DHL Freight",
        "377 HGB",
        "Verpackungsschaden",
        "Weizenmehl 25 kg",
        "Großhandel Müller",
    ):
        assert needle in text, needle


def test_pdf_builds_in_cyrillic_with_unicode_font():
    po, line = _received()
    anzeige = maengel.create_anzeige(po, lines=[{"position": line, "qty": 1}])
    with translation.override("ru"):
        assert build_maengel_pdf(anzeige, TenantFactory.build())[:4] == b"%PDF"


# ───────────────────────────── 8: отправка ─────────────────────────────


def test_send_mails_the_pdf_once_per_click_and_marks_notified():
    po, line = _received()
    anzeige = maengel.create_anzeige(po, lines=[{"position": line, "qty": 1}])
    tenant = TenantFactory.build(name="Backhaus Krume")
    assert maengel.send_to_supplier(anzeige, tenant)
    anzeige.refresh_from_db()
    assert anzeige.notified_at is not None and anzeige.sent_count == 1
    mail = Notification.objects.get()
    assert mail.recipient == "einkauf@mueller.example"
    assert anzeige.reference in mail.subject
    att = mail.payload["attachments"][0]
    assert att["mime"] == "application/pdf" and anzeige.reference in att["name"]
    # повтор после правки — новое письмо; дубль одного клика гасит dedupe
    assert maengel.send_to_supplier(anzeige, tenant)
    assert Notification.objects.count() == 2


def test_send_without_supplier_email_is_refused_and_manual_mark_works():
    po, line = _received(email="")
    anzeige = maengel.create_anzeige(po, lines=[{"position": line, "qty": 1}])
    assert not maengel.send_to_supplier(anzeige, TenantFactory.build())
    assert not Notification.objects.exists()
    purchasing_view(
        _req("post", {"action": "maengel_notified", "po": str(po.pk), "anzeige": str(anzeige.pk)})
    )
    anzeige.refresh_from_db()
    assert anzeige.notified_at is not None


# ───────────────────────────── 10: демо ─────────────────────────────


@pytest.mark.parametrize(
    "key",
    sorted(
        k
        for k, kit in __import__("apps.tenants.demo_kits", fromlist=["KITS"]).KITS.items()
        if kit.categories
    ),
)
def test_every_goods_kit_gets_the_purchasing_demo(key):
    """Фидбэк владельца: рекламация нужна не только пекарне — всем, кто продаёт товары.
    Демо-закупки (и рекламация в них) — у каждого кита товарного типа, а не только у
    китов с партиями; у гастро-китов (меню блюд) закупать «блюда» оптом — абсурд."""
    from apps.tenants import demo_kits

    kit = demo_kits.KITS[key]
    expected = kit.business_type in demo_kits.PURCHASING_DEMO_TYPES or kit.enable_lots
    assert demo_kits._purchasing_demo_on(kit) is expected
    goods = {"retail", "clothing", "online_shop", "grocery", "bakery", "butcher"}
    if kit.business_type in goods:
        assert expected, key


@pytest.mark.parametrize("key", ["bakery", "shop"])
def test_demo_purchasing_kit_shows_a_settled_and_an_open_complaint(key):
    """Пищевой (с партиями) и непищевой магазин: рекламация с решённой строкой и
    открытой — бейдж «⚠» в списке и обе ветки строки видны в демо."""
    from apps.tenants import demo_kits

    tenant = TenantFactory(slug=f"erp8-demo-{key}", name="Demo")
    assert demo_kits.apply_kit(tenant, key) is True
    anzeige = Maengelanzeige.objects.get()
    rows = list(anzeige.maengel.order_by("created_at"))
    assert rows[0].decision == "discount" and rows[0].resolved_at is not None
    assert rows[1].resolved_at is None
    assert anzeige.status == maengel.STATUS_OPEN and anzeige.notified_at is not None
    assert anzeige.bestellung.status == Bestellung.STATUS_RECEIVED
    # строки заказа — складские сущности: у товара с вариантами — вариант
    for line in anzeige.bestellung.positions.all():
        assert line.variant_id or not line.product.has_variants


def test_complaint_status_is_not_the_unpaid_homonym_in_russian():
    """Стенд: «offen» уже занят «Offene Posten» (ru «не оплачено») — у статуса рекламации
    свой контекст перевода, иначе открытая рекламация читалась как неоплаченная."""
    po, line = _received()
    maengel.create_anzeige(po, lines=[{"position": line, "qty": 1}])
    with translation.override("ru"):
        html = purchasing_view(_req(query=f"?po={po.pk}")).content.decode()
    section = html[html.index("data-maengel>") :]
    assert "открыта" in section and "не оплачено" not in section
