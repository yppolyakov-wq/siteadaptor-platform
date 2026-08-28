"""G6 / F2: кабинет Aufträge — ручная заявка, конструктор сметы, переходы
статусов, Angebot-PDF, создание Rechnung из сметы."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.finance.models import Invoice
from apps.jobs import services, views
from apps.jobs.models import Job
from apps.jobs.state_machine import JobSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/dashboard/auftraege/", data=None, tenant=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    request.tenant = tenant if tenant is not None else TenantFactory.build()
    return request


def _job(**kwargs):
    kwargs.setdefault("title", "Bad streichen")
    kwargs.setdefault("name", "Kunde")
    return services.create_job(**kwargs)


# --- список / ручная заявка -------------------------------------------------------


def test_manual_request_creates_job():
    """X2c (осознанная переписка): приёмник ручной заявки переехал со списка
    на экран создания `jobs:new` — список схлопнут в единую поверхность
    продаж (конвенция X6-1: «＋» открывает форму)."""
    resp = views.job_new(
        _req("post", data={"title": "Zaun bauen", "name": "Herr Meyer", "email": "m@t.de"})
    )
    assert resp.status_code == 302
    job = Job.objects.get(title="Zaun bauen")
    assert job.status == "new" and job.source_channel == "manual"
    assert str(job.pk) in resp.url


def test_new_screen_renders_form():
    body = views.job_new(_req()).content.decode()
    assert 'name="title"' in body and 'name="name"' in body


def test_legacy_list_redirects_to_sales_tab():
    """X2c: легаси-список заявок → 302 на вкладку продаж с GET-carry
    (?status= живёт на цели — фильтр статуса generic-Liste закрыл паритет)."""
    resp = views.job_list(_req(data={"status": "new"}))
    assert resp.status_code == 302
    assert resp.url.startswith("/dashboard/verkaeufe/")
    assert "tab=job" in resp.url and "status=new" in resp.url


def test_detail_renders_with_lines():
    job = _job()
    services.set_lines(job, [{"text": "Arbeit", "qty": 2, "unit_price": "40.00"}])
    body = views.job_detail(_req(), pk=job.pk).content.decode()
    assert job.title in body and "Arbeit" in body


# --- конструктор сметы ------------------------------------------------------------


def test_save_lines_computes_totals():
    job = _job()
    resp = views.job_detail(
        _req(
            "post",
            data={
                "action": "save_lines",
                "line_text_1": "Arbeit",
                "line_qty_1": "8",
                "line_price_1": "50,00",
                "line_text_2": "Material",
                "line_qty_2": "1",
                "line_price_2": "120,00",
                "vat_rate": "19.00",
                "valid_until": "2026-12-31",
            },
        ),
        pk=job.pk,
    )
    assert resp.status_code == 302
    job.refresh_from_db()
    assert job.net == Decimal("520.00") and job.gross == Decimal("618.80")
    assert job.lines.count() == 2
    assert str(job.valid_until) == "2026-12-31"


# --- VK-9/10 (фидбэк владельца 2026-08-20): смета ----------------------------------


def test_qty_survives_reload_in_german_locale():
    """«В предварительной при указании числа оно пропадает»: Decimal в немецкой
    локали рендерился как «2,50», а input[type=number] принимает только точку —
    браузер показывал поле ПУСТЫМ, и сохранённое количество выглядело потерянным."""
    from django.utils import translation

    job = _job()
    services.set_lines(job, [{"text": "Arbeit", "qty": "2.5", "unit_price": "40.00"}])
    with translation.override("de"):
        body = views.job_detail(_req(), pk=job.pk).content.decode()
    assert 'name="line_qty_1" type="number" min="0.01" step="0.01" data-qt-qty value="2.50"' in body
    assert 'value="2,50"' not in body  # запятая = невалидное значение для type=number


def test_line_total_column_rendered():
    """п.10: итог позиции (кол-во × цена) — в самой строке, а не только внизу."""
    job = _job()
    services.set_lines(job, [{"text": "Arbeit", "qty": 2, "unit_price": "40.00"}])
    from django.utils import translation

    with translation.override("de"):
        body = views.job_detail(_req(), pk=job.pk).content.decode()
    assert "data-qt-sum" in body and "80,00 €" in body
    # цена и итог — в одном (немецком) формате; приёмник понимает и точку, и запятую
    assert 'data-qt-price value="40,00"' in body


def test_line_with_price_but_no_text_is_reported_not_swallowed():
    """Второй способ «потерять число»: строка без описания молча отбрасывалась."""
    job = _job()
    req = _req(
        "post",
        data={
            "action": "save_lines",
            "line_text_1": "Arbeit",
            "line_qty_1": "1",
            "line_price_1": "50,00",
            "line_qty_2": "3",
            "line_price_2": "20,00",  # описания нет — строка не сохранится
            "vat_rate": "19.00",
        },
    )
    views.job_detail(req, pk=job.pk)
    job.refresh_from_db()
    assert job.lines.count() == 1
    texts = [str(m) for m in req._messages]
    assert any("ohne Beschreibung" in t for t in texts)


# --- G11b: пикер расходников из каталога -------------------------------------------


def test_detail_shows_part_picker():
    """VF-9b (осознанная переписка): селект каталога больше НЕ в каждой строке —
    один пикер у «＋ Position» (data-qt-addpick, как у заказа); привязку строки
    держит hidden line_part_i (без него Save снял бы связь — класс W0)."""
    product = ProductFactory(base_price="49.00", stock_quantity=5)
    job = _job()
    body = views.job_detail(_req(), pk=job.pk).content.decode()
    assert "data-qt-addpick" in body  # пикер у «＋ Position»
    assert f"p:{product.pk}" in body  # ассортимент в опциях
    assert 'type="hidden" name="line_part_1"' in body  # привязка строки — hidden
    assert "data-qt-part" not in body  # строчного селекта больше нет
    assert "data-qt-clear" in body  # «✕» очистки строки (иначе привязанную не удалить)


def test_detail_hides_ek_field_but_preserves_value():
    """VF-9b «закупка — это раздел ERP»: видимого поля EK на странице продажи
    нет, значение едет hidden'ом — Save не стирает введённые ставки (W0),
    снимок EK для строк каталога по-прежнему делает сервер (ERP-6)."""
    job = _job()
    services.set_lines(
        job,
        [{"text": "Montage", "qty": 2, "unit_price": "80.00", "cost_rate": "38.50"}],
        vat_rate=19,
    )
    body = views.job_detail(_req(), pk=job.pk).content.decode()
    i = body.index('name="line_cost_1"')
    assert 'type="hidden"' in body[i - 60 : i]  # поле есть, но скрыто
    # круговой Save (значение из hidden уходит обратно) держит ставку
    views.job_detail(
        _req(
            "post",
            data={
                "action": "save_lines",
                "line_part_1": "",
                "line_text_1": "Montage",
                "line_qty_1": "2",
                "line_price_1": "80,00",
                "line_cost_1": "38,50",
                "vat_rate": "19.00",
            },
        ),
        pk=job.pk,
    )
    assert job.lines.get().cost_rate == Decimal("38.50")


def test_combo_in_picker_and_snapshot():
    """VF-9b «товар или комбо просто выбираем из каталога»: комбо-наборы в
    пикере сметы (k:<pk>), выбор без текста → снимок имени/цены (FK нет —
    как у услуги)."""
    from apps.catalog.models import Combo
    from apps.catalog.picker import _catalog_parts

    combo = Combo.objects.create(name="Buffet-Paket", price=Decimal("450.00"))
    values = [p["value"] for p in _catalog_parts(include_combos=True)]
    assert f"k:{combo.pk}" in values
    assert f"k:{combo.pk}" not in [p["value"] for p in _catalog_parts()]  # заказ не знает k:

    job = _job()
    views.job_detail(
        _req(
            "post",
            data={
                "action": "save_lines",
                "line_part_1": f"k:{combo.pk}",
                "line_text_1": "",
                "line_price_1": "",
                "line_qty_1": "1",
                "vat_rate": "19.00",
            },
        ),
        pk=job.pk,
    )
    line = job.lines.get()
    assert line.text == "Buffet-Paket" and line.unit_price == Decimal("450.00")
    assert line.product_id is None  # снимок, не FK


def test_save_lines_links_part_and_snapshots():
    product = ProductFactory(base_price="49.00", stock_quantity=10)
    job = _job()
    views.job_detail(
        _req(
            "post",
            data={
                "action": "save_lines",
                "line_part_1": f"p:{product.pk}",
                "line_text_1": "",  # пусто → снимок названия
                "line_price_1": "",  # пусто → снимок цены
                "line_qty_1": "2",
                "vat_rate": "19.00",
            },
        ),
        pk=job.pk,
    )
    line = job.lines.get()
    assert line.product_id == product.id
    assert line.text == product.name_text and line.unit_price == Decimal("49.00")
    assert line.qty == 2


def test_save_lines_links_variant():
    product = ProductFactory(base_price="10.00")
    variant = ProductVariant.objects.create(
        product=product, label="M", price="14.00", stock_quantity=3
    )
    job = _job()
    views.job_detail(
        _req(
            "post",
            data={
                "action": "save_lines",
                "line_part_1": f"v:{variant.pk}",
                "line_qty_1": "1",
                "vat_rate": "19.00",
            },
        ),
        pk=job.pk,
    )
    line = job.lines.get()
    assert line.variant_id == variant.id and line.unit_price == Decimal("14.00")


# --- статусы + Rechnung -----------------------------------------------------------


def test_status_transitions_set_timestamps():
    job = _job()
    views.job_detail(_req("post", data={"action": "quoted"}), pk=job.pk)
    job.refresh_from_db()
    assert job.status == "quoted" and job.quoted_at is not None
    views.job_detail(_req("post", data={"action": "accepted"}), pk=job.pk)
    job.refresh_from_db()
    assert job.status == "accepted" and job.accepted_at is not None


def test_create_invoice_from_done_job():
    job = _job()
    services.set_lines(job, [{"text": "Pauschale", "qty": 1, "unit_price": "500.00"}])
    sm = JobSM()
    for dst in ("quoted", "accepted", "done"):
        sm.apply(job, dst)

    resp = views.job_detail(_req("post", data={"action": "invoice"}), pk=job.pk)
    assert resp.status_code == 302
    job.refresh_from_db()
    assert job.status == "invoiced" and job.invoice_id is not None
    invoice = Invoice.objects.get(pk=job.invoice_id)
    assert invoice.gross == Decimal("595.00")  # 500 + 19 %
    assert f"/dashboard/finance/rechnungen/{invoice.pk}/" in resp.url


def test_invoice_blocked_before_done():
    job = _job()
    services.set_lines(job, [{"text": "X", "qty": 1, "unit_price": "10.00"}])
    JobSM().apply(job, "quoted")  # ещё не done
    views.job_detail(_req("post", data={"action": "invoice"}), pk=job.pk)
    job.refresh_from_db()
    assert job.status == "quoted" and job.invoice_id is None
    assert not Invoice.objects.exists()


# --- PDF + удаление ---------------------------------------------------------------


def test_angebot_pdf_renders():
    job = _job()
    services.set_lines(job, [{"text": "Arbeit", "qty": 2, "unit_price": "40.00"}])
    resp = views.job_pdf(_req(), pk=job.pk)
    assert resp["Content-Type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_delete_new_job():
    job = _job()
    resp = views.job_delete(_req("post"), pk=job.pk)
    assert resp.status_code == 302
    assert not Job.objects.filter(pk=job.pk).exists()


def test_vehicle_field_on_create_and_save():
    """A9 Werkstatt: Fahrzeug/Kennzeichen на заявке (создание + правка в кабинете)."""
    job = services.create_job(title="Inspektion", name="Kunde", vehicle="VW Golf · M-AB 1234")
    assert job.vehicle == "VW Golf · M-AB 1234"
    # правка через форму сметы (_save_lines)
    views.job_detail(
        _req("post", data={"action": "save_lines", "vat_rate": "19.00", "vehicle": "BMW · K-XY 9"}),
        pk=job.pk,
    )
    job.refresh_from_db()
    assert job.vehicle == "BMW · K-XY 9"


def test_service_due_date_saved_and_rearms_reminder():
    """A9: следующий TÜV/Service сохраняется формой сметы; смена даты сбрасывает
    service_reminder_sent_at (перезаряжает напоминание)."""
    from django.utils import timezone

    job = services.create_job(title="Inspektion", name="Kunde")
    job.service_reminder_sent_at = timezone.now()  # как будто напоминание уже ушло
    job.save(update_fields=["service_reminder_sent_at"])
    views.job_detail(
        _req(
            "post",
            data={"action": "save_lines", "vat_rate": "19.00", "service_due_date": "2027-03-15"},
        ),
        pk=job.pk,
    )
    job.refresh_from_db()
    assert str(job.service_due_date) == "2027-03-15"
    assert job.service_reminder_sent_at is None  # перезаряжено под новую дату


def test_link_and_unlink_booking():
    """A7d: привязка/отвязка выездного Termin к заявке."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.booking.models import Booking, Resource

    job = services.create_job(title="Reparatur", name="Kunde", email="k@t.de")
    resource = Resource.objects.create(name="Team")
    start = timezone.now() + timedelta(days=1)
    booking = Booking.objects.create(
        resource=resource,
        customer=job.customer,
        reference_code="T-AAA111",
        start=start,
        end=start + timedelta(hours=1),
        status="confirmed",
    )
    views.job_detail(
        _req("post", data={"action": "link_booking", "booking": str(booking.pk)}), pk=job.pk
    )
    job.refresh_from_db()
    assert job.booking_id == booking.pk

    views.job_detail(_req("post", data={"action": "unlink_booking"}), pk=job.pk)
    job.refresh_from_db()
    assert job.booking_id is None


# --- AF-1: панель «⚙️ Anfrage-Formular» (событийные поля публичной заявки) --------


def test_anfrage_form_settings_saves_and_preserves_other_keys():
    tenant = TenantFactory(
        disabled_modules=[], site_config={"notify": {"customer": {"email": True}}}
    )
    resp = views.anfrage_form_settings(
        _req(
            "post",
            path="/dashboard/auftraege/anfrage-formular/",
            data={
                "af_date": "on",
                "af_event_type": "on",
                "af_event_types": "Hochzeit\nFirmenfeier\n\n  Geburtstag  ",
            },
            tenant=tenant,
        )
    )
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.site_config["anfrage"] == {
        "fields": ["date", "event_type"],
        "event_types": ["Hochzeit", "Firmenfeier", "Geburtstag"],
    }
    # probe-ключ: targeted-write не затирает чужие ключи (инвариант W6)
    assert tenant.site_config["notify"] == {"customer": {"email": True}}


def test_anfrage_form_settings_unchecking_all_drops_key():
    tenant = TenantFactory(
        disabled_modules=[],
        site_config={"anfrage": {"fields": ["date"], "event_types": ["Hochzeit"]}},
    )
    views.anfrage_form_settings(
        _req("post", path="/dashboard/auftraege/anfrage-formular/", data={}, tenant=tenant)
    )
    tenant.refresh_from_db()
    assert "anfrage" not in tenant.site_config  # presence-minimal: выкл = ключа нет


def test_ablaeufe_renders_anfrage_form_panel_with_current_state():
    """X2c (осознанная переписка): панель «Anfrage-Formular» переехала со
    страницы заявок (она схлопывается в единую поверхность продаж) на
    «Abläufe» — там живут настройки процессов продаж. Разметка та же
    (общий партиал), приёмник POST прежний."""
    from apps.core import views as core_views

    tenant = TenantFactory.build(
        disabled_modules=[],
        site_config={"anfrage": {"fields": ["guests"], "event_types": ["Grillfest"]}},
    )
    body = core_views.ablaeufe_view(_req(tenant=tenant)).content.decode()
    assert 'name="af_guests" checked' in body
    assert "Grillfest" in body


# --- QF-батч (фидбэк владельца 2026-08-20 по странице сметы) ---------------------


def test_quote_shows_only_filled_rows_plus_one_spare():
    """п.1: двенадцать пустых строк были стеной полей. Видны заполненные + одна
    свободная; остальные лежат в DOM (индексы приёмника не меняются) и
    раскрываются кнопкой."""
    job = _job()
    services.set_lines(job, [{"text": "Buffet", "qty": 1, "unit_price": "480.00"}])
    body = views.job_detail(_req(), pk=job.pk).content.decode()
    # DG-1: считаем по САМОМУ маркеру строки — класс сетки теперь общий
    # (.dl-row) и может меняться; суть замка — число строк в DOM.
    rows = body.count('data-qt-row="1"')  # разметка, а не строки JS-селекторов
    assert rows == 12  # все строки остаются в DOM (индексы приёмника не меняются)
    # Скрытие — атрибутом И инлайновым display: класс .grid перебивает hidden
    # (стенд ловил, что все двенадцать строк остаются видимыми).
    assert body.count('hidden style="display:none"') == 10  # видны две: строка + запас
    assert "data-qt-add" in body  # кнопка «＋ Position»


def test_picker_carries_title_and_price_for_instant_fill():
    """п.5: колонка «Teil (Katalog)» выглядела пустой — теперь выбор сразу
    заполняет описание и цену (данные едут в data-атрибутах опции)."""
    # name у товара — i18n-словарь (см. ProductFactory), подпись берётся из name_text
    ProductFactory(name={"de": "Buffet Vegetarisch"}, base_price="24.00", stock_quantity=5)
    job = _job()
    body = views.job_detail(_req(), pk=job.pk).content.decode()
    assert 'data-title="Buffet Vegetarisch"' in body
    assert 'data-price="24' in body


def test_service_can_be_added_to_the_quote_as_snapshot():
    """п.1 («товар/услугу»): услуга попадает в смету снимком названия и цены —
    FK нет, поэтому правка каталога услуг не переписывает отправленную смету."""
    from apps.booking.models import Service

    svc = Service.objects.create(name="Personal & Aufbau", price_cents=48000)
    job = _job()
    views.job_detail(
        _req(
            "post",
            data={
                "action": "save_lines",
                "line_part_1": f"s:{svc.pk}",
                "line_qty_1": "1",
                "vat_rate": "19.00",
            },
        ),
        pk=job.pk,
    )
    line = job.lines.get()
    assert "Personal & Aufbau" in line.text
    assert line.unit_price == Decimal("480.00")
    assert line.product_id is None and line.variant_id is None  # снимок, не FK


def test_customer_data_editable_from_the_job_page():
    """п.4: контакты правятся со страницы заявки (общая карточка клиента)."""
    job = _job()
    resp = views.job_detail(
        _req(
            "post",
            data={
                "action": "customer",
                "cust_name": "Miriam Klein",
                "cust_email": "mk@example.de",
                "cust_phone": "+49 170 1234567",
                "site_address": "Rheinstr. 5, Düsseldorf",
            },
        ),
        pk=job.pk,
    )
    assert resp.status_code == 302
    job.refresh_from_db()
    job.customer.refresh_from_db()
    assert job.customer.name == "Miriam Klein"
    assert job.customer.email == "mk@example.de"
    assert job.customer.phone == "+49 170 1234567"
    assert job.site_address.startswith("Rheinstr.")


def test_customer_contacts_are_prominent_not_grey_fine_print():
    """п.3: контакты — крупной строкой со ссылками, а не мелким серым текстом."""
    job = _job(email="mk@example.de", phone="+49 170 1234567")
    body = views.job_detail(_req(), pk=job.pk).content.decode()
    assert 'href="mailto:mk@example.de"' in body
    assert 'href="tel:+49 170 1234567"' in body
    # DC-1: карточка клиента — общий партиал (имя, кликабельные контакты).
    assert 'data-deal-block="customer"' in body


def test_workshop_fields_hidden_for_non_workshop_but_data_never_lost():
    """QF-2: «Fahrzeug»/«Nächster TÜV» — поля мастерской, у кейтеринга это шум.
    Скрытие НЕ должно стирать данные при сохранении сметы (класс W0)."""
    from datetime import date

    from apps.tenants.tests.factories import TenantFactory

    catering = TenantFactory.build(business_type="catering")
    job = _job()
    job.service_due_date = date(2027, 3, 15)
    job.vehicle = "VW Golf"
    job.save(update_fields=["service_due_date", "vehicle", "updated_at"])

    req = _req(tenant=catering)
    body = views.job_detail(req, pk=job.pk).content.decode()
    assert 'name="service_due_date"' in body  # данные заполнены → поле показано

    # У чистой заявки кейтеринга полей нет…
    clean = _job(title="Ohne Fahrzeug")
    body2 = views.job_detail(_req(tenant=catering), pk=clean.pk).content.decode()
    assert 'name="vehicle"' not in body2

    # …и сохранение сметы без этих полей не стирает дату у другой заявки
    views.job_detail(
        _req("post", data={"action": "save_lines", "vat_rate": "19.00"}, tenant=catering),
        pk=job.pk,
    )
    job.refresh_from_db()
    assert job.service_due_date == date(2027, 3, 15)
    assert job.vehicle == "VW Golf"


# --- VF-9 (фидбэк 2026-08-24): карточка заявки — как у заказа/товара ---------
def test_detail_uses_rail_layout():
    """«Страница заявки должна быть такой же, как у заказов и товара»: смета —
    широкой колонкой, клиент/статус/связи — рейлом 340px (тот же грид, что у
    формы товара); карточки в тени R5. Состав сметы (строки line_*_i,
    data-qt-*) не тронут — его держат прежние замки."""
    job = _job()
    body = views.job_detail(_req(), pk=job.pk).content.decode()
    # DC-1 (2026-08-25): рейл даёт общий скелет карточки сделки.
    assert "xl:grid-cols-[minmax(0,1fr)_380px]" in body  # рейл-грид (макет: 380px)
    assert "data-deal-rail" in body
    assert "shadow-[0_6px_18px_rgba(22,24,29,0.05)]" in body  # тень R5
    # смета (форма) идёт РАНЬШЕ рейла: на мобильном позиции первыми — как у
    # заказа. Голый "<aside" ловит сайдбар кабинета — якоримся на классах рейла.
    rail_i = body.index("data-deal-rail")
    assert body.index('name="action" value="save_lines"') < rail_i
    # рейл несёт клиента; статус переехал в верхнюю строку (DF-1b, 2026-08-26)
    aside = body[rail_i:]
    assert "Kundendaten bearbeiten" in aside
    assert 'value="quoted"' in body[:rail_i]  # смена статуса — в голове карточки


# --- VF-15 (фидбэк 2026-08-25): блок «Zahlung» на карточке заявки ------------
def test_payment_card_and_mark_paid():
    """Блок «💳 Zahlung» (статус/депозит/Angebot-ссылка) + ручное «Als bezahlt
    markieren» — оплату на месте раньше было не отметить вовсе (payment_state
    писал только Stripe-вебхук). Идемпотентно. DC-1 (2026-08-25): по ТЗ владельца
    оплата — секция ЛЕВОЙ колонки, единая на все карточки сделок."""
    job = _job()
    services.set_lines(job, [{"text": "Buffet", "qty": 1, "unit_price": "100.00"}], vat_rate=19)
    body = views.job_detail(_req(), pk=job.pk).content.decode()
    pay = body[body.index('data-deal-block="payment"') : body.index("data-deal-rail")]
    assert "💳" in body and 'value="mark_paid"' in pay
    assert "/angebot/" not in pay  # ссылка только на quoted/accepted

    resp = views.job_detail(_req("post", data={"action": "mark_paid"}), pk=job.pk)
    assert resp.status_code == 302
    job.refresh_from_db()
    assert job.payment_state == "paid"
    views.job_detail(_req("post", data={"action": "mark_paid"}), pk=job.pk)  # идемпотентно
    job.refresh_from_db()
    assert job.payment_state == "paid"
    body = views.job_detail(_req(), pk=job.pk).content.decode()
    assert 'value="mark_paid"' not in body  # оплачено → кнопка честно скрыта

    # VF-16: ссылка на CRM-карточку клиента (crm у всех типов с VF-6)
    assert f"/crm/{job.customer.pk}/" in body or "crm" in body


def test_deposit_lives_in_the_payment_card_and_survives_quote_save():
    """Фидбэк владельца 2026-08-28: Anzahlung — свойство оплаты, а не состава.

    Поле уехало в карточку «Zahlung» и приходит своей формой; сохранение состава
    сметы его больше не видит — значит обязано НЕ трогать (иначе каждый Save
    обнулял бы депозит: класс дефекта W0)."""
    job = _job()
    views.job_detail(_req("post", data={"action": "deposit", "deposit_eur": "150,00"}), pk=job.pk)
    job.refresh_from_db()
    assert job.deposit_cents == 15000

    views.job_detail(
        _req(
            "post",
            data={
                "action": "save_lines",
                "line_text_1": "Arbeit",
                "line_price_1": "80",
                "line_qty_1": "1",
            },
        ),
        pk=job.pk,
    )
    job.refresh_from_db()
    assert job.deposit_cents == 15000  # состав сохранён, депозит цел


def test_quote_form_has_no_second_vat_control():
    """Ставка выбирается В СТРОКЕ (VAT-1); документный селект на том же экране
    противоречил ей — убран. Ставка документа остаётся дефолтом строк."""
    job = _job()
    body = views.job_detail(_req("get"), pk=job.pk).content.decode()
    assert 'name="line_vat_1"' in body  # ставка строки на месте
    assert 'name="vat_rate"' not in body  # второго, документного селекта нет

    before = job.vat_rate
    views.job_detail(
        _req(
            "post",
            data={
                "action": "save_lines",
                "line_text_1": "Arbeit",
                "line_price_1": "80",
                "line_qty_1": "1",
            },
        ),
        pk=job.pk,
    )
    job.refresh_from_db()
    assert job.vat_rate == before  # без поля в форме ставка документа не сбрасывается


def test_angebot_actions_live_only_in_the_documents_block():
    """Фидбэк владельца 2026-08-28: действия с самим документом (отправка, PDF,
    срок действия) — только в «Dokumente». В блоке состава остаётся сохранение
    позиций: это единственный submit формы, без него смету не сохранить.
    """
    job = _job()
    body = views.job_detail(_req("get"), pk=job.pk).content.decode()

    quote = body[body.index('data-deal-block="items"') :]
    quote = quote[: quote.index("</section>")]
    assert "Positionen speichern" in quote  # форма состава сохраняется
    assert "Angebot" not in quote  # но «Angebot» тут больше не действие

    docs = body[body.index('data-deal-block="documents"') :]
    docs = docs[: docs.index("</section>")]
    assert "Angebot senden" in docs  # отправка живёт в документах
