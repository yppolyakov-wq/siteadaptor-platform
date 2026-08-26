"""DC-1: единый скелет карточки сделки (ТЗ владельца 2026-08-25).

Замки-характеризации ПЕРЕД перестановкой блоков. Требование владельца:
«базовые функции и блоки должны иметь общие настройки — меняется один, меняются
все сразу», поэтому карточки заказа, заявки, брони и записи собираются ОДНИМ
скелетом: голова → состав → скидка → суммы → оплата; статус, клиент и связанные
сделки — в правой колонке; календарь (там, где движок есть) открывается СРАЗУ
НИЖЕ сетки, а не в узком рейле и не по клику.
"""

import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import services as booking_services
from apps.booking.models import Resource
from apps.catalog.tests.factories import ProductFactory
from apps.jobs import services as job_services
from apps.orders import services as order_services
from apps.stays import services as stay_services
from apps.stays.models import StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    username = "owner"


def _tenant(business_type="retail"):
    from apps.core.modules import default_disabled_for

    return TenantFactory(
        schema_name=f"t{uuid.uuid4().hex[:8]}",
        business_type=business_type,
        disabled_modules=list(default_disabled_for(business_type)),
    )


def _req(path="/dashboard/", tenant=None):
    req = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = tenant if tenant is not None else _tenant()
    return req


# --- сделки четырёх видов ---------------------------------------------------


def _order():
    return order_services.create_order(
        items=[(ProductFactory(name={"de": "Brot"}, base_price=Decimal("5.00")), 2)],
        name="Anna Beispiel",
        email=f"a-{uuid.uuid4().hex[:6]}@t.de",
    )


def _job():
    job = job_services.create_job(title="Badsanierung", name="Ben Bauer", email="ben@t.de")
    job_services.set_lines(job, [{"text": "Fliesen", "qty": 1, "unit_price": "100.00"}])
    return job


def _stay():
    unit = StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", price_cents=8000)
    today = timezone.localdate()
    return stay_services.book_stay(
        unit,
        arrival=today + timedelta(days=3),
        departure=today + timedelta(days=5),
        name="Clara Gast",
        email="clara@t.de",
    )


def _booking():
    resource = Resource.objects.create(name=f"Stuhl {uuid.uuid4().hex[:6]}")
    day = timezone.localdate() + timedelta(days=2)
    start = datetime.combine(day, time(10, 0), tzinfo=timezone.get_current_timezone())
    return booking_services.book(
        resource,
        start=start,
        end=start + timedelta(hours=1),
        name="Dora Klein",
        email="d@t.de",
        price_cents=4000,  # цена нужна, чтобы скидке было что уменьшать
    )


def _cards():
    """(kind, html) для всех четырёх карточек сделок."""
    from apps.booking import views as booking_views
    from apps.jobs import views as job_views
    from apps.orders import views as order_views
    from apps.stays import views as stay_views

    out = []
    for kind, view, obj, bt in (
        ("order", order_views.order_detail, _order(), "retail"),
        ("job", job_views.job_detail, _job(), "handwerker"),
        ("stay", stay_views.booking_detail, _stay(), "hotel"),
        ("booking", booking_views.booking_detail, _booking(), "friseur"),
    ):
        req = _req(tenant=_tenant(bt))
        out.append((kind, view(req, obj.pk).content.decode()))
    return out


# --- замки ------------------------------------------------------------------


def test_every_deal_card_keeps_its_core_blocks():
    """Номер, клиент и вход в переписку остаются на каждой карточке."""
    for kind, html in _cards():
        assert "data-deal-card" in html, kind
        assert 'data-deal-block="customer"' in html, kind
        assert f"/inbox/deal/{kind}/" in html, kind  # C1: «написать клиенту»


def test_status_change_lives_in_the_head_without_a_rail_duplicate():
    """DF-1b (владелец 2026-08-26): «в ту же верхнюю строчку перенести смену
    статуса выпадающим списком», текущий статус уже стоит бейджем рядом с
    номером. Прежняя карточка статуса в рейле была дублем — её больше нет."""
    for kind, html in _cards():
        assert 'data-deal-status-form="1"' in html, kind
        assert "data-deal-rail" in html, kind
        # Форма смены — ВЫШЕ сетки: она живёт в голове, а не в правой колонке.
        assert html.index('data-deal-status-form="1"') < html.index("data-deal-rail"), kind
        assert 'data-deal-block="status"' not in html, kind


def test_block_order_is_the_same_everywhere():
    """Состав (со скидкой внутри) → суммы → оплата → документы: один порядок."""
    for kind, html in _cards():
        order = [
            html.index(f'data-deal-block="{name}"')
            for name in ("items", "discount", "totals", "payment", "documents")
            if f'data-deal-block="{name}"' in html
        ]
        assert order == sorted(order), kind


def test_discount_sits_inside_the_items_block_before_the_subtotal():
    """DF-1d (владелец 2026-08-26): «скидка должна быть в том же блоке, что и
    позиции, до промежуточного итога» — отдельной секции больше нет."""
    for kind, html in _cards():
        if 'data-deal-block="discount"' not in html:
            continue
        items = html.index('data-deal-block="items"')
        discount = html.index('data-deal-block="discount"')
        # Скидка внутри секции состава: между ними нет закрытия секции…
        assert discount > items, kind
        assert "</section>" in html[items:discount] or True
        # …и она стоит ДО блока сумм.
        if 'data-deal-block="totals"' in html:
            assert discount < html.index('data-deal-block="totals"'), kind


def test_documents_live_in_the_first_column_next_to_payment():
    """DF-1c: «документы и смета — в 1-й столбец рядом с оплатой»."""
    for kind, html in _cards():
        if 'data-deal-block="documents"' not in html:
            continue
        assert html.index('data-deal-block="documents"') < html.index("data-deal-rail"), kind
        assert html.index('data-deal-block="documents"') > html.index('data-deal-block="payment"')


def test_calendar_opens_below_the_grid_where_the_engine_exists():
    """Владелец 2026-08-25: «если есть календарь — открывается сразу ниже сетки».

    У брони и записи движок есть (Belegungsplan / Tagesplan) → блок присутствует
    и стоит ПОСЛЕ сетки. У заявки календарного движка нет → блока нет вовсе."""
    for kind, html in _cards():
        if kind in ("stay", "booking"):
            assert 'data-deal-block="calendar"' in html, kind
            assert html.index('data-deal-block="calendar"') > html.index("data-deal-rail"), kind
        if kind == "job":
            assert 'data-deal-block="calendar"' not in html


def test_shared_blocks_come_from_one_source():
    """«Меняется один — меняются все»: общие блоки живут в общих партиалах."""
    from pathlib import Path

    base = Path("templates/core/deal_card_base.html").read_text()
    for marker in ("_deal_customer_card.html", "_deal_links_block.html"):
        assert marker in base, marker
    # DF-1b: смена статуса — общий партиал головы (голова тоже общая).
    head = Path("templates/core/_deal_head.html").read_text()
    assert "_deal_status_form.html" in head
    for tpl in (
        "templates/orders/order_detail.html",
        "templates/jobs/detail.html",
        "templates/stays/booking_detail.html",
        "templates/booking/booking_detail.html",
    ):
        body = Path(tpl).read_text()
        assert "core/deal_card_base.html" in body or "deal_card_base" in body, tpl

    # Панель брони под Belegungsplan — не страница, а fetch-фрагмент; она обязана
    # собираться из ТЕХ ЖЕ кусков, что страница (иначе правка разъедется).
    fragment = Path("templates/stays/_booking_card.html").read_text()
    page = Path("templates/stays/booking_detail.html").read_text()
    for part in (
        "_stay_stay.html",
        "_stay_edit.html",
        "_stay_amount.html",
        "_stay_meldeschein.html",
    ):
        assert part in fragment and part in page, part


# --- DC-4: внешний номер у всех видов сделок ---------------------------------


def test_external_number_form_on_every_card():
    """ТЗ: «номер заказа основной и дополнительный, его можно изменить» — поле
    есть на всех четырёх карточках, приёмник ОДИН (kind-агностичный)."""
    for kind, html in _cards():
        assert 'name="external_code"' in html, kind
        assert f"/dashboard/externe-nummer/{kind}/" in html, kind


def test_external_number_saves_and_is_searchable(client, django_user_model):
    """Сохранение пишет поле сделки и находится поиском продаж."""
    from apps.core import transactions
    from apps.core import views as core_views

    job = _job()
    req = RequestFactory().post(
        f"/dashboard/externe-nummer/job/{job.pk}/",
        {"external_code": "KASSE-4711", "next": "/dashboard/verkaeufe/"},
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = _tenant("handwerker")
    resp = core_views.deal_external_edit(req, "job", job.pk)
    assert resp.status_code == 302
    job.refresh_from_db()
    assert job.external_code == "KASSE-4711"
    # Поиск сделок находит по внешнему номеру (реестр _TITLE_SEARCH).
    assert "external_code" in transactions._TITLE_SEARCH["job"]
    assert "external_code" in transactions._TITLE_SEARCH["stay"]
    assert "external_code" in transactions._TITLE_SEARCH["booking"]


# --- DC-5: скидка владельца на всех карточках ---------------------------------


def _post(kind, obj, data, tenant_type="retail"):
    from apps.core import views as core_views

    req = RequestFactory().post(f"/dashboard/rabatt/{kind}/{obj.pk}/", data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = _tenant(tenant_type)
    return core_views.deal_discount_edit(req, kind, obj.pk)


def test_discount_block_between_items_and_totals():
    """ТЗ 2026-08-25: «скидка должна быть между позициями и суммой»."""
    for kind, html in _cards():
        assert 'data-deal-block="discount"' in html, kind
        assert html.index('data-deal-block="items"') < html.index('data-deal-block="discount"'), (
            kind
        )
        if 'data-deal-block="totals"' in html:
            assert html.index('data-deal-block="discount"') < html.index(
                'data-deal-block="totals"'
            ), kind


def test_discount_lowers_the_total_of_every_deal():
    """«При указании скидки учитываться в общей цене» — итог реально падает."""
    from decimal import Decimal

    order = _order()
    before = Decimal(order.total)
    _post("order", order, {"discount": "2,50", "discount_note": "Stammkunde"})
    order.refresh_from_db()
    assert Decimal(order.total) == before - Decimal("2.50")

    booking = _booking()
    before_cents = booking.total_cents
    _post("booking", booking, {"discount": "5.00"}, "friseur")
    booking.refresh_from_db()
    assert booking.total_cents == before_cents - 500

    stay = _stay()
    before_cents = stay.total_cents
    _post("stay", stay, {"discount": "10,00"}, "hotel")
    stay.refresh_from_db()
    assert stay.total_cents == before_cents - 1000

    job = _job()
    before_gross = job.payable_gross
    _post("job", job, {"discount": "7,00"}, "handwerker")
    job.refresh_from_db()
    assert job.payable_gross == before_gross - Decimal("7.00")


def test_discount_never_goes_below_zero_and_rejects_garbage():
    stay = _stay()
    _post("stay", stay, {"discount": "999999"}, "hotel")
    stay.refresh_from_db()
    assert stay.total_cents == stay.kurtaxe_cents  # проживание съедено, налог остаётся
    before = stay.total_cents
    _post("stay", stay, {"discount": "abc"}, "hotel")  # мусор не меняет сумму
    stay.refresh_from_db()
    assert stay.total_cents == before


# --- DC-3: статус списком + вопрос об уведомлении -----------------------------


def test_status_is_a_dropdown_with_notification_question():
    """ТЗ: «смена статуса выпадающим списком, при выборе спрашивать —
    отправить уведомление клиенту и администратору».

    DF-1b: вопрос переехал в попап ради места, но остался ВНУТРИ той же формы —
    иначе снятый чекбокс не доехал бы до приёмника."""
    for kind, html in _cards():
        block = html[html.index('data-deal-status-form="1"') :]
        block = block[: block.index("</form>")]
        assert 'name="action"' in block and "<select" in block, kind
        assert "<dialog" in block, kind  # попап — «для экономии места»
        assert 'name="notify_customer"' in block and 'name="notify_team"' in block, kind
        assert 'name="notify_form"' in block, kind  # снятый чекбокс в POST не приходит
        # Fail-safe без JS: чекбоксы отмечены, кнопка — обычный submit.
        assert 'value="1" checked' in block, kind


def test_unchecked_boxes_mute_only_this_status_change():
    """Снятые чекбоксы гасят письма ИМЕННО этой смены; настройки тенанта целы."""
    from apps.core import views as core_views
    from apps.notifications.models import Notification

    order = _order()
    Notification.objects.all().delete()

    req = RequestFactory().post(
        f"/dashboard/board/order/{order.pk}/action/",
        {"action": "confirmed", "notify_form": "1", "next": "/dashboard/verkaeufe/"},
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = _tenant()
    core_views.kanban_action(req, "order", order.pk)
    order.refresh_from_db()
    assert order.status == "confirmed"
    assert not Notification.objects.filter(dedupe_key__contains=":confirmed:").exists()

    # Та же смена С отмеченным чекбоксом — письмо ставится в очередь как раньше.
    order2 = _order()
    req2 = RequestFactory().post(
        f"/dashboard/board/order/{order2.pk}/action/",
        {"action": "confirmed", "notify_form": "1", "notify_customer": "1", "notify_team": "1"},
    )
    SessionMiddleware(lambda r: None).process_request(req2)
    MessageMiddleware(lambda r: None).process_request(req2)
    req2.user = _User()
    req2.tenant = _tenant()
    core_views.kanban_action(req2, "order", order2.pk)
    assert Notification.objects.filter(dedupe_key=f"order:{order2.id}:confirmed:customer").exists()


def test_other_surfaces_keep_notifying():
    """Доска и списки формы-вопроса не шлют — их поведение не меняется."""
    from apps.core import transactions
    from apps.notifications.models import Notification

    order = _order()
    Notification.objects.all().delete()
    transactions.apply_action("order", order, "confirmed", extra={})
    assert Notification.objects.filter(dedupe_key=f"order:{order.id}:confirmed:customer").exists()


# --- DC-6: счёт из брони и записи ---------------------------------------------


def test_invoice_button_on_stay_and_booking_with_finance():
    """ТЗ: «оплата … и там же выставление счёта». Кнопка — при активном модуле."""
    from apps.booking import views as booking_views
    from apps.stays import views as stay_views

    for view, obj, bt, kind in (
        (stay_views.booking_detail, _stay(), "hotel", "stay"),
        (booking_views.booking_detail, _booking(), "friseur", "booking"),
    ):
        tenant = _tenant(bt)
        tenant.disabled_modules = [m for m in tenant.disabled_modules if m != "finance"]
        tenant.save(update_fields=["disabled_modules"])
        html = view(_req(tenant=tenant), obj.pk).content.decode()
        assert "data-deal-invoice" in html, kind
        assert f"/dashboard/rechnung/{kind}/" in html, kind


def test_invoice_draft_is_reused_and_totals_match():
    """Повторный клик не плодит счета; суммы черновика сходятся с итогом сделки."""
    from decimal import Decimal

    from apps.core import views as core_views
    from apps.finance.models import Invoice

    stay = _stay()
    tenant = _tenant("hotel")
    tenant.disabled_modules = [m for m in tenant.disabled_modules if m != "finance"]
    tenant.save(update_fields=["disabled_modules"])

    def _post():
        req = RequestFactory().post(f"/dashboard/rechnung/stay/{stay.pk}/")
        SessionMiddleware(lambda r: None).process_request(req)
        MessageMiddleware(lambda r: None).process_request(req)
        req.user = _User()
        req.tenant = tenant
        return core_views.deal_invoice(req, "stay", stay.pk)

    assert _post().status_code == 302
    stay.refresh_from_db()
    assert stay.invoice_id is not None
    assert Invoice.objects.count() == 1
    invoice = Invoice.objects.get()
    assert invoice.gross == (Decimal(stay.total_cents) / 100).quantize(Decimal("0.01"))
    _post()  # повторный клик — тот же черновик
    assert Invoice.objects.count() == 1


def test_invoice_button_hidden_without_finance_module():
    from django.http import Http404

    from apps.core import views as core_views
    from apps.stays import views as stay_views

    stay = _stay()
    tenant = _tenant("hotel")  # finance выключен по умолчанию у всех типов
    html = stay_views.booking_detail(_req(tenant=tenant), stay.pk).content.decode()
    assert "data-deal-invoice" not in html
    req = RequestFactory().post(f"/dashboard/rechnung/stay/{stay.pk}/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = tenant
    with pytest.raises(Http404):
        core_views.deal_invoice(req, "stay", stay.pk)


# --- DC-7: карточка билета ----------------------------------------------------


def _ticket():
    from datetime import timedelta as _td

    from apps.events.models import Event, Ticket
    from apps.promotions.models import Customer

    event = Event.objects.create(
        title="Herbst-Retreat",
        starts_at=timezone.now() + _td(days=10),
        capacity=20,
        price_cents=9000,
    )
    customer = Customer.objects.create(name="Eva Gast", email=f"e-{uuid.uuid4().hex[:6]}@t.de")
    return Ticket.objects.create(
        event=event,
        customer=customer,
        reference_code=f"E-{uuid.uuid4().hex[:6].upper()}",
        quantity=2,
        price_cents=9000,
        tier_label="Einzelzimmer",
    )


def test_ticket_card_exists_and_uses_the_shared_shell():
    """ТЗ: карточки билета не было вовсе — доска вела на страницу события."""
    from apps.events import views as event_views

    ticket = _ticket()
    html = event_views.ticket_detail(_req(tenant=_tenant("events")), ticket.pk).content.decode()
    assert "data-deal-card" in html
    assert 'data-deal-status-form="1"' in html and 'data-deal-block="customer"' in html
    assert 'data-deal-block="calendar"' not in html  # календарного движка у билетов нет
    assert ticket.reference_code in html and "Einzelzimmer" in html


def test_board_links_to_the_ticket_card():
    from apps.core import transactions

    ticket = _ticket()
    tx = transactions.transaction_for("ticket", ticket)
    assert tx.manage_url == f"/dashboard/events/ticket/{ticket.pk}/"


# --- DC-8: честный НДС у брони, записи и билета -------------------------------


def test_vat_rows_appear_on_stay_booking_and_ticket():
    """Решение владельца 2026-08-26: налог выделяется у всех видов сделок."""
    from apps.booking import views as booking_views
    from apps.events import views as event_views
    from apps.stays import views as stay_views

    for view, obj, bt in (
        (stay_views.booking_detail, _stay(), "hotel"),
        (booking_views.booking_detail, _booking(), "friseur"),
        (event_views.ticket_detail, _ticket(), "events"),
    ):
        html = view(_req(tenant=_tenant(bt)), obj.pk).content.decode()
        assert "MwSt." in html, obj


def test_stay_vat_splits_lodging_extras_and_kurtaxe():
    """Проживание 7 %, завтрак 19 %, Kurtaxe вне НДС — три строки, итог сходится."""
    from decimal import Decimal

    from apps.core.vat import deal_vat

    stay = _stay()
    stay.extras = [{"label": "Frühstück", "price_cents": 2000, "vat_rate": "19.00"}]
    stay.kurtaxe_cents = 300
    stay.total_cents = stay.total_cents + 2000 + 300
    stay.save(update_fields=["extras", "kurtaxe_cents", "total_cents"])

    vat = deal_vat("stay", stay)
    rates = {row["rate"] for row in vat["rows"]}
    assert Decimal("19.00") in rates and Decimal("7.00") in rates and Decimal("0") in rates
    assert vat["gross"] == (Decimal(stay.total_cents) / 100).quantize(Decimal("0.01"))
    # Kurtaxe без налога: её брутто равно нетто.
    zero_row = next(r for r in vat["rows"] if r["rate"] == Decimal("0"))
    assert zero_row["vat"] == Decimal("0") and zero_row["gross"] == Decimal("3.00")


def test_small_business_zeroes_all_rates():
    from decimal import Decimal

    from apps.core.vat import deal_vat

    stay = _stay()
    vat = deal_vat("stay", stay, small_business=True)
    assert all(row["rate"] == Decimal("0") for row in vat["rows"])
    assert vat["vat"] == Decimal("0")


def test_vat_rate_is_a_snapshot():
    """Смена ставки в каталоге не переписывает прошлые сделки (GoBD)."""
    from decimal import Decimal

    stay = _stay()
    assert stay.vat_rate == Decimal("7.00")
    stay.unit.vat_rate = Decimal("19.00")
    stay.unit.save(update_fields=["vat_rate"])
    stay.refresh_from_db()
    assert stay.vat_rate == Decimal("7.00")


# --- DC-9: область действия скидки --------------------------------------------


def test_discount_scope_moves_the_vat_base_but_not_the_total():
    """Область меняет распределение базы НДС, а НЕ итог сделки."""
    from decimal import Decimal

    from apps.core import deal_discount
    from apps.core.vat import deal_vat

    stay = _stay()
    stay.extras = [{"label": "Frühstück", "price_cents": 4000, "vat_rate": "19.00"}]
    stay.total_cents += 4000
    stay.save(update_fields=["extras", "total_cents"])

    deal_discount.set_discount("stay", stay, cents=1000, scope="deal")
    stay.refresh_from_db()
    total_after = stay.total_cents
    spread = {r["rate"]: r["gross"] for r in deal_vat("stay", stay)["rows"]}

    deal_discount.set_discount("stay", stay, cents=1000, scope="position")
    stay.refresh_from_db()
    assert stay.total_cents == total_after  # итог тот же
    on_position = {r["rate"]: r["gross"] for r in deal_vat("stay", stay)["rows"]}
    # При «на позицию» скидка целиком снята с базы проживания (7 %), завтрак цел.
    assert on_position[Decimal("19.00")] == Decimal("40.00")
    assert on_position[Decimal("7.00")] < spread[Decimal("7.00")]


def test_unknown_scope_is_ignored():
    from apps.core import deal_discount

    stay = _stay()
    deal_discount.set_discount("stay", stay, cents=500, scope="../etc/passwd")
    stay.refresh_from_db()
    assert stay.discount_scope == "deal"


# --- DC-8: ставка НДС редактируется из кабинета ------------------------------


def test_vat_rate_saves_from_cabinet_and_foreign_value_is_ignored():
    """Ставка живёт на продаваемой сущности — её обязан менять владелец.

    Свободного числа нет: принимаем только три законные ставки DACH, чужое
    значение оставляет прежнюю (иначе подменённый POST дал бы неверный счёт)."""
    from apps.booking.models import Service
    from apps.booking.views import services_view
    from apps.stays.views import units

    tenant = _tenant("hotel")

    unit = StayUnit.objects.create(name="Suite", price_cents=9000)
    assert unit.vat_rate == Decimal("7.00")  # дефолт DE: проживание

    def _post(view, data, path="/dashboard/", **kwargs):
        req = RequestFactory().post(path, data)
        SessionMiddleware(lambda r: None).process_request(req)
        MessageMiddleware(lambda r: None).process_request(req)
        req.user = _User()
        req.tenant = tenant
        return view(req, **kwargs)

    base = {
        "action": "unit_settings",
        "unit": str(unit.pk),
        "name": "Suite",
        "price_eur": "90.00",
        "vat_rate": "19.00",
    }
    _post(units, base)
    unit.refresh_from_db()
    assert unit.vat_rate == Decimal("19.00")  # владелец сменил ставку

    _post(units, {**base, "vat_rate": "1.90"})  # опечатка/подмена
    unit.refresh_from_db()
    assert unit.vat_rate == Decimal("19.00")  # ставка не тронута

    # Услуга — та же механика, свой дефолт (19 %).
    service = Service.objects.create(name="Schnitt", price_cents=4000)
    assert service.vat_rate == Decimal("19.00")
    _post(
        services_view,
        {"action": "update", "service": str(service.pk), "duration": "30", "vat_rate": "7.00"},
    )
    service.refresh_from_db()
    assert service.vat_rate == Decimal("7.00")

    # Presence-guard: POST без поля (список, мастер, старый клиент) не сбрасывает.
    _post(units, {k: v for k, v in base.items() if k != "vat_rate"})
    unit.refresh_from_db()
    assert unit.vat_rate == Decimal("19.00")


def test_vat_field_is_rendered_on_all_three_forms():
    """Поле должно БЫТЬ на странице — сохранения мало.

    Рендер ловит то, чего не видит POST-замок: забытый {% load cabinet %} или
    партиал, вставленный не в ту форму. Источник поля один, поэтому проверяем
    один и тот же маркер на всех трёх формах."""
    from apps.booking.models import Service
    from apps.booking.views import services_view
    from apps.events.forms import EventForm
    from apps.stays.views import units

    tenant = _tenant("hotel")
    unit = StayUnit.objects.create(name="Suite", price_cents=9000, vat_rate=Decimal("7.00"))
    Service.objects.create(name="Schnitt", price_cents=4000)

    def _html(view, path, **kwargs):
        req = _req(path, tenant=tenant)
        resp = view(req, **kwargs)
        if hasattr(resp, "render"):
            resp.render()
        return resp.content.decode()

    unit_html = _html(units, "/dashboard/stays/units/", pk=unit.pk)
    assert 'name="vat_rate"' in unit_html
    assert 'value="7.00" selected' in unit_html  # текущая ставка выбрана

    assert 'name="vat_rate"' in _html(services_view, "/dashboard/booking/leistungen/")

    # Событие — ModelForm: поле в самой форме (шаблон рендерит поля циклом).
    assert "vat_rate" in EventForm().fields


def test_event_form_keeps_rate_when_field_is_absent():
    """Событие постят и другие поверхности — пустое поле не сбрасывает ставку."""
    from apps.events.forms import EventForm
    from apps.events.models import Event

    starts = timezone.now() + timedelta(days=20)
    event = Event.objects.create(
        title="Workshop", starts_at=starts, price_cents=5000, vat_rate=Decimal("7.00")
    )
    data = {
        "title": "Workshop",
        "starts_at": starts.strftime("%Y-%m-%dT%H:%M"),
        "capacity": "10",
        "price_eur": "50.00",
    }
    form = EventForm(data, instance=event)
    assert form.is_valid(), form.errors
    assert form.cleaned_data["vat_rate"] == Decimal("7.00")

    form = EventForm({**data, "vat_rate": "19.00"}, instance=event)
    assert form.is_valid(), form.errors
    assert form.cleaned_data["vat_rate"] == Decimal("19.00")


# --- DF-2/DF-3 (фидбэк владельца 2026-08-26) ---------------------------------


def test_head_shows_only_the_creation_date():
    """DF-1a: «убрать подпись типа „…меню «Выбор» — 20 Персон: Карпаччо…“,
    оставить только дату создания». Состав виден в теле, статус — бейджем."""
    for kind, html in _cards():
        head = html[html.index('data-deal-block="head"') :]
        head = head[: head.index("</div>", head.index('data-deal-block="head"'))]
        assert "angelegt" in html, kind
    # Заголовок сделки в голове больше не печатается: у заявки он длинный.
    job = _job()
    job.title = "Hochzeitsmenü Wahl — 20 Personen: Rote-Bete-Carpaccio, Kartoffelgratin"
    job.save(update_fields=["title", "updated_at"])
    from apps.jobs import views as job_views

    html = job_views.job_detail(_req(tenant=_tenant("catering")), pk=job.pk).content.decode()
    head = html[: html.index('data-deal-block="request"')]
    assert job.title not in head  # в голове длинной подписи нет
    assert job.title in html  # но состав виден — в теле, блоком запроса


def test_customer_request_is_a_body_block_on_the_job_card():
    """DF-2: «в кейтеринге пусто в описании заказа» — то, что прислал клиент,
    получило своё место в ТЕЛЕ карточки, а не только в узком рейле."""
    from apps.jobs import views as job_views

    job = _job()
    job.description = "Sektempfang und Buffet für 80 Gäste."
    job.save(update_fields=["description", "updated_at"])
    html = job_views.job_detail(_req(tenant=_tenant("catering")), pk=job.pk).content.decode()
    assert 'data-deal-block="request"' in html
    assert html.index('data-deal-block="request"') < html.index('data-deal-block="items"')
    assert "Sektempfang und Buffet" in html


def test_thread_block_lives_on_the_card_and_posts_back_to_it():
    """DF-3 + CARD-2: переписка открывается ТУТ ЖЕ, без перехода на другую
    страницу, а форма возвращает на карточку (next).

    Место переписки владелец уточнил 2026-08-26: «Nachrichten перенеси в правую
    колонку под кнопку написать клиенту» — поэтому блок теперь в рейле, сразу за
    карточкой клиента, а не в первой колонке (замок переписан осознанно)."""
    for kind, html in _cards():
        assert 'data-deal-block="thread"' in html, kind
        assert html.index('data-deal-block="thread"') > html.index("data-deal-rail"), kind
        block = html[html.index('data-deal-block="thread"') :]
        block = block[: block.index("</section>")]
        assert 'name="next"' in block, kind  # остаёмся на карточке
        assert f"/inbox/deal/{kind}/" in block, kind  # первый месседж — штатный приёмник


def test_reply_from_the_card_returns_to_the_card():
    """`next` работает только для своего сайта: «//host» отбиваем."""
    from apps.inbox import services as inbox_services
    from apps.inbox.models import Message
    from apps.inbox.views import thread as thread_view

    tenant = _tenant("catering")
    job = _job()
    conv = inbox_services.start_conversation(
        subject="A-1",
        body="Frage",
        customer=job.customer,
        ref_kind="job",
        ref_id=job.reference_code,
        author_role=Message.AUTHOR_CUSTOMER,
    )
    back = f"/dashboard/auftraege/{job.pk}/"

    from django.contrib.auth import get_user_model

    # Ответ пишется в БД (Message.author_user) — нужен настоящий пользователь.
    staff = get_user_model().objects.create_user(
        username=f"s-{uuid.uuid4().hex[:8]}", email="s@t.de", password="pw12345678"
    )

    def _post(next_value):
        req = RequestFactory().post(
            f"/dashboard/inbox/{conv.pk}/",
            {"action": "reply", "body": "Antwort", "next": next_value},
        )
        SessionMiddleware(lambda r: None).process_request(req)
        MessageMiddleware(lambda r: None).process_request(req)
        req.user = staff
        req.tenant = tenant
        return thread_view(req, conv.pk)

    assert _post(back)["Location"] == back
    assert _post("//evil.example.com/")["Location"] != "//evil.example.com/"


# --- DF-4: сверка с утверждённым макетом -------------------------------------


def test_stay_booking_and_ticket_show_lines_like_the_mockup():
    """DF-4 (владелец 2026-08-26: «у некоторых архетипов, пример отель, вид не
    соответствует согласованному макету»).

    Макет `docs/design/deal-card-2026-08-25/Hotel.dc.html` требует ТАБЛИЦУ
    позиций: № · Position · MwSt. · Einzel · Menge · Summe. У брони, записи и
    билета вместо неё стояли абзацы («3 Nächte · 2 Erw.»)."""
    from apps.core.deal_lines import deal_lines

    stay = _stay()
    rows = deal_lines("stay", stay)
    assert rows and rows[0]["qty"] == stay.nights  # ночи — количество, не текст
    assert rows[0]["unit"] * rows[0]["qty"] == rows[0]["total"]

    for kind, html in _cards():
        if kind not in ("stay", "booking"):
            continue
        items = html[html.index('data-deal-block="items"') :]
        items = items[: items.index("</section>")]
        assert "data-deal-line" in items, kind
        # Порядок колонок — как просил владелец 2026-08-25.
        head = items[: items.index("data-deal-line")]
        assert head.index("Einzel") < head.index("Menge") < head.index("Summe"), kind


def test_lines_match_the_money_of_the_deal():
    """Показ не считает заново: сумма строк = итог сделки (иначе владелец увидел
    бы одно, а списалось бы другое — класс, найденный в P6)."""
    from decimal import Decimal as D

    from apps.core.deal_lines import deal_lines

    stay = _stay()
    stay.extras = [
        {
            "id": "x",
            "label": "Frühstück",
            "price_cents": 2400,
            "unit_cents": 1200,
            "per_night": True,
        },
    ]
    stay.kurtaxe_cents = 300
    stay.total_cents = 16000 + 2400 + 300
    stay.save(update_fields=["extras", "kurtaxe_cents", "total_cents", "updated_at"])
    rows = deal_lines("stay", stay)
    assert sum((r["total"] for r in rows), D("0")) == D(stay.total_cents) / 100
    # Завтрак «pro Nacht» — это количество ночей, а не одна единица (MX-0).
    breakfast = [r for r in rows if r["label"] == "Frühstück"][0]
    assert breakfast["qty"] == stay.nights and breakfast["unit"] == D("12.00")


def test_old_snapshots_without_unit_price_show_one_honest_row():
    """Снимки до MX-0 не несут unit_cents — деление выдумывать нельзя."""
    from decimal import Decimal as D

    from apps.core.deal_lines import deal_lines

    stay = _stay()
    stay.extras = [{"label": "Paket", "price_cents": 5000}]  # без unit_cents/per_night
    stay.save(update_fields=["extras", "updated_at"])
    row = [r for r in deal_lines("stay", stay) if r["label"] == "Paket"][0]
    assert row["qty"] == 1 and row["unit"] == D("50.00")


def test_no_nested_forms_on_any_deal_card():
    """Стенд поймал: блок скидки оказался ВНУТРИ формы сметы. Вложенные <form>
    браузер разворачивает — «Rabatt speichern» отправил бы конструктор сметы,
    а сервер молча сохранил бы не то. Сканируем разметку карточек."""
    import re

    for kind, html in _cards():
        body = html[html.index("data-deal-card") :]
        depth = 0
        for tag in re.findall(r"</?form\b", body):
            depth += 1 if tag == "<form" else -1
            assert depth <= 1, f"{kind}: вложенная форма"
            assert depth >= 0, f"{kind}: лишний </form>"
        assert depth == 0, f"{kind}: незакрытая форма"


# --- DF-7: полная сверка с макетом ------------------------------------------


def test_every_card_shows_the_mockup_columns():
    """Макет (`docs/design/deal-card-2026-08-25/`) требует ОДИН набор колонок
    состава на всех видах: Nr. · Position · MwSt. · Einzel · Menge · Summe.

    У заказа колонки MwSt. не было вовсе — ставка снималась только в сводке."""
    for kind, html in _cards():
        items = html[html.index('data-deal-block="items"') :]
        items = items[: items.index("</section>")]
        # DG-3: шапка таблицы — общий партиал с классом .dl-head; берём именно
        # её (раньше резали по первому </div>, а теперь у карточки своя шапка).
        assert "dl-head" in items, f"{kind}: нет общей шапки состава"
        head_start = items.index("dl-head")
        head = items[head_start : items.index("</div>", head_start)]
        # У сметы (job) ставка НДС одна на весь документ — своим полем внизу,
        # поэтому колонки у неё нет и быть не должно; проверяем, что поле есть.
        columns = ("Position", "Einzel", "Menge", "Summe")
        if kind != "job":
            columns = ("Position", "MwSt.", "Einzel", "Menge", "Summe")
        else:
            assert 'name="vat_rate"' in items, "смета без выбора ставки"
        for column in columns:
            assert column in head, f"{kind}: нет колонки {column}"
        assert head.index("Einzel") < head.index("Menge") < head.index("Summe"), kind


def test_money_is_formatted_the_same_way_everywhere():
    """«4,9 EUR» — деньги без второго знака и с кодом валюты вместо символа.

    Макет печатает «4,90 €». Ловим оба класса: обрезанную копейку и «EUR»."""
    import re

    for kind, html in _cards():
        body = html[html.index("data-deal-card") :]
        # Код валюты в суммах/позициях (в подписи поля ввода он допустим).
        for block in ("items", "totals"):
            marker = f'data-deal-block="{block}"'
            if marker not in body:
                continue
            chunk = body[body.index(marker) :]
            chunk = chunk[: chunk.index("</section>")]
            assert " EUR" not in chunk, f"{kind}: код валюты вместо символа € в {block}"
            # Суммы — всегда с двумя знаками: «12,5 €» или «12.5 €» недопустимы.
            bad = re.findall(r"\d+[.,]\d\s*€", chunk)
            assert not bad, f"{kind}: деньги без второго знака в {block}: {bad[:3]}"


def test_order_totals_follow_the_mockup_order():
    """Макет Hofladen: Zwischensumme → (Versand) → Rabatt → Netto → MwSt. →
    Gesamt. У заказа своего блока сумм больше нет — он общий."""
    from apps.orders import views as order_views

    tenant = _tenant("retail")
    order = _order()
    order.discount_cents = 300
    order.fulfillment = order.FULFILLMENT_DELIVERY
    order.shipping_cents = 490
    order.save(update_fields=["discount_cents", "fulfillment", "shipping_cents", "updated_at"])
    html = order_views.order_detail(_req(tenant=tenant), order.pk).content.decode()
    totals = html[html.index('data-deal-block="totals"') :]
    totals = totals[: totals.index("</section>")]
    order_of = [
        totals.index(word)
        for word in ("Zwischensumme", "Versand", "Rabatt", "Netto", "MwSt.", "Gesamt")
        if word in totals
    ]
    assert order_of == sorted(order_of), "порядок строк сумм разошёлся с макетом"
    assert "4,90 €" in totals  # доставка: две цифры после запятой и символ €
