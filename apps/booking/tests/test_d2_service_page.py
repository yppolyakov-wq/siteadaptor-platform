"""UX-D D2.4: страница услуги — шапка + вкладки (макет ServiceEdit).

Grundlagen / Buchungsregeln / Beschreibung & FAQ — ОДНА форма (action=update пишет
цену/длительность/описание всегда: формы по вкладкам обнулили бы чужие поля, W0);
«Preise & Varianten» — свои мини-формы. `tab` возвращает на ту же вкладку."""

import re
import uuid
from html.parser import HTMLParser
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from apps.booking import views
from apps.booking.models import Service
from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "templates/booking/service_page.html"


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, role=Membership.ROLE_OWNER):
    req = getattr(RequestFactory(), method)("/dashboard/booking/leistungen/x/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(disabled_modules=[], business_type="friseur")
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": role})
    return req


def _svc(**kw):
    defaults = {
        "name": "Haarschnitt",
        "price_cents": 3500,
        "duration_minutes": 45,
        "description": "Waschen, Schneiden, Föhnen",
        "attributes": ["Inkl. Pflege"],
        "faq": [{"q": "Dauer?", "a": "45 Minuten"}],
        "buffer_after_minutes": 10,
        "cancel_window_hours": 24,
        "deposit_cents": 1000,
    }
    defaults.update(kw)
    return Service.objects.create(**defaults)


def _page(svc, **get):
    return views.services_view(_req(data=get), pk=svc.pk).content.decode()


class _FormFields(HTMLParser):
    """Поля формы #svc-form (имя → значение), как их отправит браузер."""

    def __init__(self):
        super().__init__()
        self.depth = 0  # вложенность внутри #svc-form
        self.fields: list[tuple[str, str]] = []
        self.nested_forms = 0
        self._textarea = None
        self._select = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            if self.depth:
                self.nested_forms += 1
            elif a.get("id") == "svc-form":
                self.depth = 1
            return
        if not self.depth or "form" in a:
            return
        name = a.get("name")
        if tag == "input" and name:
            kind = a.get("type", "text")
            if kind in ("checkbox", "radio") and "checked" not in a:
                return
            if kind == "file":
                return
            self.fields.append((name, a.get("value", "")))
        elif tag == "textarea" and name:
            self._textarea = [name, ""]
        elif tag == "select" and name:
            self._select = [name, None, None]
        elif tag == "option" and self._select is not None:
            if self._select[2] is None:
                self._select[2] = a.get("value", "")
            if "selected" in a:
                self._select[1] = a.get("value", "")

    def handle_data(self, data):
        if self._textarea is not None:
            self._textarea[1] += data

    def handle_endtag(self, tag):
        if tag == "form" and self.depth:
            self.depth = 0
        elif tag == "textarea" and self._textarea is not None:
            self.fields.append(tuple(self._textarea))
            self._textarea = None
        elif tag == "select" and self._select is not None:
            name, sel, first = self._select
            self.fields.append((name, sel if sel is not None else first))
            self._select = None


def _form_post(html):
    parser = _FormFields()
    parser.feed(html)
    data = {}
    for name, value in parser.fields:
        data.setdefault(name, []).append(value)
    return data, parser


def test_page_has_four_tabs_and_one_main_form():
    html = _page(_svc())
    for tab in ("grund", "preise", "regeln", "text"):
        assert f'data-pf-tab="{tab}"' in html and f'data-pf-panel="{tab}"' in html
    assert html.count('id="svc-form"') == 1
    data, parser = _form_post(html)
    assert parser.nested_forms == 0  # мини-формы цен — вне главной формы
    # все поля бывшей строки списка — в одной форме (W0)
    for name in (
        "name",
        "price_eur",
        "duration",
        "description",
        "attributes",
        "attributes_present",
        "faq_present",
        "booking_rules_present",
        "buffer_after_minutes",
        "cancel_policy_present",
        "deposit_present",
        "pricing_mode_present",
        "is_video_present",
        "hide_in_city_present",
    ):
        assert name in data, name


def test_saving_the_rendered_form_unchanged_keeps_every_value():
    svc = _svc(vat_rate="7.00", pricing_mode="per_person", hide_in_city=True)
    data, _ = _form_post(_page(svc))
    before = Service.objects.values().get(pk=svc.pk)
    resp = views.services_view(_req("post", data), pk=svc.pk)
    assert resp.status_code == 302
    after = Service.objects.values().get(pk=svc.pk)
    for key in ("updated_at", "confirmed_at"):
        before.pop(key), after.pop(key)
    assert after == before


@pytest.mark.parametrize("tab", ["grund", "preise", "regeln", "text"])
def test_tab_param_selects_the_tab(tab):
    html = _page(_svc(), tab=tab)
    assert re.search(rf'data-pf-tab="{tab}"[^>]*aria-selected="true"', html)
    panel = re.search(rf'data-pf-panel="{tab}" class="([^"]*)"', html).group(1)
    assert "hidden" not in panel.split()


def test_junk_tab_falls_back_to_basics():
    html = _page(_svc(), tab="<script>")
    assert re.search(r'data-pf-tab="grund"[^>]*aria-selected="true"', html)
    assert "&lt;script&gt;" not in html.split("data-svc-tab")[0][-200:]


@pytest.mark.parametrize(
    "tab, suffix", [("regeln", "?tab=regeln"), ("grund", ""), ("evil", ""), (None, "")]
)
def test_save_returns_to_the_same_tab(tab, suffix):
    svc = _svc()
    data = {"action": "update", "service": str(svc.pk), "price_eur": "40", "duration": "30"}
    if tab:
        data["tab"] = tab
    resp = views.services_view(_req("post", data), pk=svc.pk)
    assert resp["Location"] == reverse("booking:service-edit", args=[svc.pk]) + suffix


def test_season_form_returns_to_prices_tab():
    svc = _svc()
    resp = views.services_view(
        _req(
            "post",
            {
                "action": "season_add",
                "service": str(svc.pk),
                "tab": "preise",
                "start_date": "2026-12-01",
                "end_date": "2026-12-31",
                "price_eur": "50",
            },
        ),
        pk=svc.pk,
    )
    assert resp["Location"].endswith("?tab=preise")
    assert svc.season_rates.count() == 1


def test_mini_forms_carry_the_prices_tab():
    svc = _svc()
    svc.season_rates.create(start_date="2026-12-01", end_date="2026-12-31", price_cents=5000)
    svc.variants.create(name="Lang", price_delta_cents=500)
    html = _page(svc)
    section = html[html.index('data-pf-panel="preise"') :]
    assert section.count('name="tab" value="preise"') == section.count("<form ")


def _update(svc, role=Membership.ROLE_OWNER, **extra):
    data = {
        "action": "update",
        "service": str(svc.pk),
        "price_eur": "35,00",
        "duration": "45",
        "description": svc.description,
        "deposit_present": "1",
        **extra,
    }
    req = _req("post", data, role=role)
    views.services_view(req, pk=svc.pk)
    svc.refresh_from_db()
    return [str(m) for m in get_messages(req)]


def test_owner_edits_deposit_on_rules_tab():
    svc = _svc()
    _update(svc, deposit_eur="12,50")
    assert svc.deposit_cents == 1250


def test_empty_deposit_means_no_deposit():
    svc = _svc()
    _update(svc, deposit_eur="")
    assert svc.deposit_cents == 0


@pytest.mark.parametrize("raw", ["abc", "-5", "1e999"])
def test_bad_deposit_is_rejected_and_kept(raw):
    svc = _svc()
    msgs = _update(svc, deposit_eur=raw)
    assert svc.deposit_cents == 1000
    assert any("Betrag" in m for m in msgs)
    assert "Service saved." not in msgs  # нет зелёного «сохранено» рядом с ошибкой


def test_deposit_above_price_is_capped_with_a_warning():
    svc = _svc()
    msgs = _update(svc, deposit_eur="99")
    assert svc.deposit_cents == svc.price_cents == 3500
    assert any("begrenzt" in m for m in msgs)


def test_lowering_price_caps_deposit_even_for_staff():
    """Ревью D2.4: сотрудник без права на предоплату снижает цену ниже неё."""
    svc = _svc()
    _update(svc, role=Membership.ROLE_STAFF, price_eur="5")
    assert svc.price_cents == 500 and svc.deposit_cents == 500


@pytest.mark.parametrize("raw", ["zwölf", "abc", "1e999", "-3"])
def test_garbage_price_keeps_old_price_not_free(raw):
    """Ревью D2.4: кривая цена раньше молча делала услугу бесплатной."""
    svc = _svc()
    msgs = _update(svc, price_eur=raw)
    assert svc.price_cents == 3500
    assert any("Betrag" in m for m in msgs) and "Service saved." not in msgs


def test_link_to_inactive_master_survives_save():
    from apps.booking.models import Resource

    svc = _svc()
    a = Resource.objects.create(name="Anna")
    b = Resource.objects.create(name="Ben")
    gone = Resource.objects.create(name="Alt", is_active=False)
    svc.resources.set([a, gone])
    _update(svc, resources_present="1", resources=[str(b.pk)])
    assert set(svc.resources.all()) == {b, gone}


def test_skills_checkboxes_do_not_query_per_master(django_assert_max_num_queries):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.booking.models import Resource

    svc = _svc()
    for i in range(2):
        svc.resources.add(Resource.objects.create(name=f"R{i}"))
    with CaptureQueriesContext(connection) as small:
        _page(svc)
    for i in range(8):
        Resource.objects.create(name=f"S{i}")
    with CaptureQueriesContext(connection) as big:
        html = _page(svc)
    assert html.count('name="resources"') == 10
    assert len(big) <= len(small) + 1, (len(small), len(big))


def test_staff_cannot_change_deposit():
    svc = _svc()
    _update(svc, role=Membership.ROLE_STAFF, deposit_eur="1")
    assert svc.deposit_cents == 1000


def test_tabs_and_panels_are_wired_for_assistive_tech():
    js = (ROOT / "templates/tenant/_i18n_switch.html").read_text()
    assert "aria-controls" in js and '"tabpanel"' in js and "aria-labelledby" in js


def test_staff_sees_rules_read_only_without_deposit_field():
    svc = _svc()
    req = _req(role=Membership.ROLE_STAFF)
    html = views.services_view(req, pk=svc.pk).content.decode()
    assert "data-service-cancel-readonly" in html
    assert 'name="deposit_eur"' not in html and 'name="deposit_present"' not in html


def test_existing_booking_keeps_its_deposit_snapshot():
    from datetime import timedelta

    from django.utils import timezone

    from apps.booking.models import Booking, Resource
    from apps.crm.models import Customer

    svc = _svc()
    start = timezone.now() + timedelta(days=3)
    booking = Booking.objects.create(
        resource=Resource.objects.create(name="Anna"),
        customer=Customer.objects.create(name="Gast", email="g@example.com"),
        service=svc,
        start=start,
        end=start + timedelta(minutes=45),
        deposit_cents=1000,
    )
    _update(svc, deposit_eur="20")
    booking.refresh_from_db()
    assert svc.deposit_cents == 2000 and booking.deposit_cents == 1000


def test_header_links_to_storefront_and_back_to_list():
    svc = _svc()
    html = _page(svc)
    assert reverse("booking:services") in html
    assert reverse("storefront-service-detail", args=[svc.pk]) in html
    inactive = _svc(name="Alt", is_active=False)
    assert reverse("storefront-service-detail", args=[inactive.pk]) not in _page(inactive)


def test_template_has_no_inline_handlers():
    text = TEMPLATE.read_text()
    assert "<script" not in text and not re.search(r"\son[a-z]+=", text)


def test_tab_sync_script_lives_in_cabinet_js():
    js = (ROOT / "static/js/cabinet.js").read_text()
    assert "// ---- booking/service_page.html ----" in js and "data-svc-tab" in js


def test_d7_page_shows_customer_preview_card():
    """UX-D D7.3: справа — настоящая карточка витрины, неактивная."""
    html = _page(_svc())
    aside = html.split("data-object-preview", 1)[1].split("</aside>", 1)[0]
    assert "Haarschnitt" in aside and "inert" in aside
    assert "Noch nicht auf der Website" not in aside
    html = _page(_svc(name="Bart", is_active=False))
    assert "Noch nicht auf der Website" in html.split("data-object-preview", 1)[1]
