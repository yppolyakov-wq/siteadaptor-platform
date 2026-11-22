"""FB-33 C5: вкладка «Felder» у строки формы корзины (`cart/form`) в окне блока.

План — scratchpad стопки 6 (раздел C5). Поля оформления (`form_fields.checkout`) правятся тем
же движком, что форма заявки (M2i-5): правка — в черновик страницы «Warenkorb»
(`draft["form"]` на хосте `cart`), «Abbrechen» возвращает черновик байт-в-байт, «Speichern»
пишет только `form_fields.checkout` через `form_spec.put` под блокировкой строки бизнеса. Имя
закреплено (🔒), событийных полей и «Branchen-Vorlage» нет, порядок системных полей —
фиксированный. Подсказки части (`apps/core/checkout_window.py`): онлайн-оплата и столик.
"""

import copy
import json
import re

import pytest
from django.utils import translation

from apps.core import aufbau_draft, block_window, form_spec, site_schema
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
WOPEN = "openC5"
WINDOW = "?seite=cart&block=form&tab=felder"
STRIPE_HINT = "Die Bestätigung kommt an die E-Mail aus der Zahlung"
TABLE_HINT = "Bei Bestellung am Tisch (QR-Code) fragen wir nur"
EMAIL_HINT_ID = "ff-email-pay-hint"

QUESTIONS = [
    {"id": "q1", "type": "text", "label": "Allergien", "mode": "req"},
    {"id": "q2", "type": "bool", "label": "Geschenkpapier"},
]
#: заявка с настройкой — её черновик и сохранённое не должны меняться от правки корзины
ANFRAGE = {"form_fields": {"anfrage": {"mode": {"phone": "req"}}}}


def _tenant(cfg=None, business_type="cafe", **kw):
    return TenantFactory(
        business_type=business_type,
        disabled_modules=[],
        site_config=copy.deepcopy(cfg if cfg is not None else {}),
        **kw,
    )


def _shop(cfg=None, **kw):
    """Магазин без столиков и без онлайн-оплаты — подсказок нет."""
    return _tenant(cfg, business_type="online_shop", **kw)


def _edit(b, seite="cart", **fields):
    data = {"seite": seite, "ref": "form", "op": "update", "panel_present": "1"}
    data.setdefault("wopen", WOPEN)
    data.update({f"f_{k}": v for k, v in fields.items()})
    return b.post(**data)


def _drafts(b):
    return copy.deepcopy((b.session or {}).get(aufbau_draft.SESSION_KEY) or {})


def _saved(tenant):
    return Tenant.objects.get(pk=tenant.pk).site_config


def _part(html):
    start = html.index('id="bw-form-formfields"')
    return html[start : html.index("</form>", start)]


# ───────────── 1: вкладка у строки формы корзины ─────────────


def test_1_cart_form_opens_on_tab_felder_with_checkout_fields():
    html = Browser(_shop()).get(WINDOW)
    assert 'data-window-part="formfields"' in html
    assert 'id="schema-tab-felder"' in html
    part = _part(html)
    keys = re.findall(r'data-form-field="([a-z_]+)"', part)
    assert keys == ["name", "email", "phone", "note"]  # порядок фиксирован
    name = part[part.index('data-form-field="name"') :]
    name = name[: name.index("</div>")]
    assert "🔒" in name and "f_mode_name" not in part
    for key in ("email", "phone", "note"):
        for mode in ("off", "opt", "req"):
            assert f'name="f_mode_{key}" value="{mode}"' in part
    # без событий и без «Branchen-Vorlage» (пресета корзины нет — место под M2i-6)
    assert "f_event_types" not in part and "data-form-preset" not in part
    assert "Anfrage-Form" not in part
    assert 'name="ref" value="form"' in part and 'name="seite" value="cart"' in part


def test_1_no_online_payment_no_email_hint_but_table_hint():
    part = _part(Browser(_shop()).get(WINDOW))
    assert STRIPE_HINT not in part and EMAIL_HINT_ID not in part
    assert TABLE_HINT in part  # столик (?tisch=) — у любого бизнеса с заказами


def test_1b_email_hint_sits_under_the_email_field(settings):
    from apps.orders.tests.test_payment_methods import _configure

    _configure(settings)
    stripe = _shop(orders_prepay=True, payments_enabled=True, stripe_connect_id="acct_1")
    part = _part(Browser(stripe).get(WINDOW))
    start = part.index('data-form-field="email"')
    fieldset = part[part.rindex("<fieldset", 0, start) : part.index("</fieldset>", start)]
    assert f'aria-describedby="{EMAIL_HINT_ID}"' in fieldset
    assert f'id="{EMAIL_HINT_ID}"' in fieldset and STRIPE_HINT in fieldset
    assert part.count(f'id="{EMAIL_HINT_ID}"') == 1 and part.count(STRIPE_HINT) == 1
    # прочие поля без неё
    phone = part[part.index('data-form-field="phone"') :]
    assert "aria-describedby" not in phone[: phone.index(">")]


def test_1e_hints_keys_and_table_by_orders_module():
    from apps.core import checkout_window

    shop = _shop()
    assert [k for k, _t in checkout_window.hints(shop)] == ["table"]
    shop.disabled_modules = ["orders"]
    shop.save(update_fields=["disabled_modules"])
    assert checkout_window.hints(shop) == []


def test_1f_payment_methods_error_is_logged(monkeypatch, caplog):
    from apps.core import checkout_window
    from apps.orders import payments

    def boom(*a, **kw):
        raise RuntimeError("x")

    monkeypatch.setattr(payments, "available_methods", boom)
    caplog.set_level("WARNING")
    assert checkout_window.stripe_available(_shop()) is False
    assert "checkout window" in caplog.text and "RuntimeError" in caplog.text


@pytest.mark.xfail(strict=True, reason="FB-33 M2i-6: замок до кода")
def test_1c_presets_are_per_form():
    """FB-33 M2i-6: замок перевёрнут осознанно — у корзины гастро-типов пресет появился
    (было `preset_for(…, form="checkout") == {}` у всех)."""
    from apps.jobs.anfrage_presets import preset_for

    assert preset_for("catering")  # заявка — прежний пресет
    assert preset_for("catering", form="anfrage") == preset_for("catering")
    assert preset_for("catering", form="checkout") == {}  # пресет заявки в корзину не течёт
    assert preset_for("bakery", form="checkout")
    assert preset_for("bakery", form="anfrage") == {}  # и обратно
    assert preset_for("retail", form="checkout") == {}


# ───────────── 2: черновик на хосте cart, заявка байт-в-байт ─────────────


def test_2_edit_goes_to_cart_draft_and_anfrage_draft_stays():
    tenant = _tenant(ANFRAGE)
    before = json.dumps(_saved(tenant), sort_keys=True)
    b = Browser(tenant)
    _edit(b, seite="anfrage", wopen="openA1", mode_description="req")
    b.post(seite="anfrage", ref="form", op="window_done", wopen="openA1")
    anfrage = _drafts(b)["anfrage"]
    resp, msgs = _edit(b, mode_email="off", mode_note="req")
    assert resp.status_code == 302 and "block=form" in resp["Location"] and msgs == []
    drafts = _drafts(b)
    assert drafts["anfrage"] == anfrage  # черновик заявки байт-в-байт
    assert drafts["cart"]["form"]["mode"] == {"email": "off", "phone": "opt", "note": "req"}
    assert "event_types" not in drafts["cart"]["form"] or not drafts["cart"]["form"]["event_types"]
    assert json.dumps(_saved(tenant), sort_keys=True) == before  # на сайт — ни байта
    req = b._request("get")
    assert aufbau_draft.info(req, siteconfig.normalize(tenant.site_config), "cart")["count"] == 1


# ───────────── 3: Speichern / Abbrechen ─────────────


def test_3_save_writes_only_checkout_through_put_under_lock(monkeypatch):
    from django.db import connection

    tenant = _shop(ANFRAGE)
    before = siteconfig.normalize(_saved(tenant))
    calls = []
    real = form_spec.put

    def spy(config, form, state):
        calls.append((form, connection.in_atomic_block))
        return real(config, form, state)

    monkeypatch.setattr(form_spec, "put", spy)
    b = Browser(tenant)
    _edit(b, mode_phone="req", do="add", new_label="Allergien", new_req="1")
    calls.clear()  # показ черновика тоже идёт через `put` (на копии)
    resp, msgs = b.post(seite="cart", op="save")
    assert resp.status_code == 302 and msgs
    assert ("checkout", True) in calls and all(form == "checkout" for form, _a in calls)
    after = siteconfig.normalize(_saved(tenant))
    entry = after["form_fields"].pop("checkout")
    assert entry["mode"] == {"phone": "req"}
    assert entry["custom"] == [{"id": "q1", "type": "text", "label": "Allergien", "mode": "req"}]
    assert entry["next_id"] == 1
    assert after == before  # остальное (и заявка) — как было
    assert _drafts(b) == {}


def test_3b_cancel_returns_cart_draft_byte_for_byte():
    b = Browser(_shop())
    b.get(WINDOW)
    _edit(b, mode_email="req")
    resp, msgs = b.post(seite="cart", ref="form", op="revert", wopen=WOPEN)
    assert resp.status_code == 302 and msgs
    assert _drafts(b) == {}
    _edit(b, wopen="openB1", mode_note="off")
    b.post(seite="cart", ref="form", op="window_done", wopen="openB1")
    before = _drafts(b)
    _edit(b, mode_note="req", do="add", new_label="Neu")
    b.post(seite="cart", ref="form", op="revert", wopen=WOPEN)
    assert _drafts(b) == before


# ───────────── 4: трёхстороннее слияние ─────────────


def test_4_change_saved_meanwhile_merges_three_way():
    tenant = _shop({"form_fields": {"checkout": {"custom": QUESTIONS, "next_id": 2}}})
    b = Browser(tenant)
    _edit(b, mode_email="off")
    # между правкой и записью настройку корзины изменили в другом месте (телефон, вопрос)
    cfg = siteconfig.normalize(_saved(tenant))
    cfg["form_fields"]["checkout"]["mode"] = {"phone": "req"}
    cfg["form_fields"]["checkout"]["custom"] = QUESTIONS[:1]
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)
    resp, msgs = b.post(seite="cart", op="save")
    assert not any("anderer Stelle" in m for m in msgs), msgs
    site = siteconfig.normalize(_saved(tenant))
    assert form_spec.mode_of(site, "checkout", "email") == "off"  # из черновика
    assert form_spec.mode_of(site, "checkout", "phone") == "req"  # из другого места
    assert [q["id"] for q in site["form_fields"]["checkout"]["custom"]] == ["q1"]


# ───────────── 5: оба контакта «Nicht fragen» у корзины можно ─────────────


def test_5_both_contacts_off_is_fine_for_checkout():
    tenant = _shop()
    b = Browser(tenant)
    _resp, msgs = _edit(b, mode_email="off", mode_phone="off")
    assert not any("Telefon" in m for m in msgs), msgs
    b.post(seite="cart", op="save")
    site = siteconfig.normalize(_saved(tenant))
    assert form_spec.mode_of(site, "checkout", "email") == "off"
    assert form_spec.mode_of(site, "checkout", "phone") == "off"


# ───────────── 6: переводы подписей ─────────────


def test_6_label_translation_goes_to_checkout():
    tenant = _shop()
    tenant.enabled_locales = ["de", "en"]
    tenant.save(update_fields=["enabled_locales"])
    b = Browser(tenant)
    part = _part(b.get(WINDOW))
    assert 'name="f_label_email_en"' in part
    _edit(b, label_email="E-Mail für Rückfragen", label_email_en="Email for questions")
    b.post(seite="cart", op="save")
    site = siteconfig.normalize(_saved(tenant))
    entry = site["form_fields"]["checkout"]
    assert entry["labels"] == {"email": "E-Mail für Rückfragen"}
    assert entry[form_spec.LABELS_I18N] == {"email": {"en": "Email for questions"}}
    assert form_spec.view(site, "checkout", "en")["email"].label == "Email for questions"


# ───────────── 7: право ─────────────


def test_7_staff_without_website_edit_gets_403(settings):
    from apps.core.models import Membership
    from apps.core.tests.test_staff_walk import _open, _user

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _shop()
    before = json.dumps(_saved(tenant), sort_keys=True)
    user = _user(Membership.ROLE_STAFF)
    Membership.objects.filter(user=user).update(permissions={"remove": ["website.edit"]})
    data = {
        "seite": "cart",
        "ref": "form",
        "op": "update",
        "panel_present": "1",
        "f_mode_email": "off",
    }
    assert _open("/dashboard/site/aufbau/", tenant, user, "post", data).status_code == 403
    data["op"] = "save"
    assert _open("/dashboard/site/aufbau/", tenant, user, "post", data).status_code == 403
    assert json.dumps(_saved(tenant), sort_keys=True) == before
    owner = _user(Membership.ROLE_OWNER)  # контроль: с правом запрос доходит до вьюхи
    data["op"] = "update"
    assert _open("/dashboard/site/aufbau/", tenant, owner, "post", data).status_code == 302


# ───────────── 8: матрица окна M3-0 у cart/form ─────────────


def test_8_window_matrix_for_cart_form():
    from apps.core.tests.test_fb33_m3_window import _nonempty, _sections
    from apps.core.tests.test_fb33_m3_window_before import _capture, _panel

    tenant = _shop()
    known = set(block_window.PANEL_KEYS) | block_window.ROW_KEYS
    html, view, selected = _capture(Browser(tenant), "?seite=cart&block=form")
    assert _nonempty(selected) <= known, _nonempty(selected) - known
    found = block_window.parts(selected, view)
    assert found == ["formfields"]
    tabs = block_window.tabs(selected, view)
    assert [t["key"] for t in tabs] == ["felder"] and tabs[0]["active"]
    panel = _panel(html)
    sections = _sections(panel)
    assert panel.count('data-window-part="formfields"') == 1
    assert 'data-window-part="formfields"' in sections["felder"][2]
    # без блока и у итога корзины окно прежнее: итог — «Hier werden keine Angaben abgefragt»
    _html, _view, summary = _capture(Browser(tenant), "?seite=cart&block=summary")
    assert "form_spec" not in summary and summary.get("noinput")


def test_8b_anfrage_form_row_is_unchanged():
    """Строка формы заявки — прежняя модель (форма `anfrage`, без подсказок корзины)."""
    tenant = _tenant(ANFRAGE)
    rows = site_schema.blocks_for(siteconfig.normalize(tenant.site_config), "anfrage", "anfrage")
    panel = next(r for r in rows if r["ref"] == "form")[form_spec.PANEL_KEY]
    assert panel["form"] == "anfrage" and "hints" not in panel


def test_8c_anfrage_window_has_no_cart_hints(settings):
    from apps.orders.tests.test_payment_methods import _configure

    _configure(settings)
    tenant = _tenant(ANFRAGE, orders_prepay=True, payments_enabled=True, stripe_connect_id="a_1")
    part = _part(Browser(tenant).get("?seite=anfrage&block=form&tab=felder"))
    assert "data-form-hint" not in part and EMAIL_HINT_ID not in part
    assert STRIPE_HINT not in part and TABLE_HINT not in part


def test_5b_cart_and_anfrage_drafts_side_by_side():
    tenant = _tenant(ANFRAGE)
    saved = siteconfig.normalize(_saved(tenant))
    b = Browser(tenant)
    _edit(b, seite="anfrage", wopen="openA1", mode_description="req")
    _edit(b, mode_email="off")
    anfrage = _drafts(b)["anfrage"]
    b.post(seite="cart", op="save")
    after = siteconfig.normalize(_saved(tenant))
    assert _drafts(b) == {"anfrage": anfrage}  # черновик заявки цел
    assert after["form_fields"]["anfrage"] == saved["form_fields"]["anfrage"]
    assert after.get("anfrage") == saved.get("anfrage")
    assert form_spec.mode_of(after, "checkout", "email") == "off"
    b.post(seite="anfrage", op="save")
    final = siteconfig.normalize(_saved(tenant))
    assert final["form_fields"]["checkout"] == after["form_fields"]["checkout"]
    assert form_spec.mode_of(final, "anfrage", "description") == "req"


def test_5c_preset_button_on_cart_changes_nothing():
    tenant = _tenant()  # кафе — у заявки пресета нет, у корзины его нет вовсе
    tenant.business_type = "catering"
    tenant.save(update_fields=["business_type"])
    before = json.dumps(_saved(tenant), sort_keys=True)
    b = Browser(tenant)
    resp, _msgs = _edit(b, do="preset")
    assert resp.status_code == 302
    assert aufbau_draft.get(b._request("get"), "cart") is None
    assert json.dumps(_saved(tenant), sort_keys=True) == before


# ───────────── 9: Vorschau — поля из черновика ─────────────


def test_9_preview_shows_draft_checkout_fields():
    tenant = _shop()
    b = Browser(tenant)
    _edit(b, mode_email="off", do="add", new_label="Allergien")
    draft = aufbau_draft.get(b._request("get"), "cart")
    shown = siteconfig.normalize(
        aufbau_draft.overlay(siteconfig.normalize(tenant.site_config), draft)
    )
    view = form_spec.view(shown, "checkout")
    assert not view["email"].on
    assert [q["label"] for q in view["custom"]] == ["Allergien"]
    assert form_spec.EDIT_KEY not in shown and "anfrage" not in (shown.get("form_fields") or {})
    rows = site_schema.blocks_for(aufbau_draft.overlay(tenant.site_config, draft), "cart", "cart")
    panel = next(r for r in rows if r["ref"] == "form")[form_spec.PANEL_KEY]
    assert panel["form"] == "checkout" and panel["custom"][-1]["new"]


# ───────────── 10: /warenkorb/ по настройке ─────────────


def test_10_cart_page_follows_the_saved_tab(settings):
    from apps.orders.tests.test_fb33_m2i34_checkout import _cart, _checkout_form

    tenant = _shop()
    b = Browser(tenant)
    _edit(b, mode_email="off", mode_note="req", do="add", new_label="Allergien")
    b.post(seite="cart", op="save")
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant.refresh_from_db()
    with translation.override("de"):
        form = _checkout_form(_cart(tenant))
    assert 'name="email"' not in form
    assert 'name="phone"' in form and 'name="note"' in form
    assert "Allergien" in form


def test_1d_hints_and_intro_are_translated(settings):
    """ru-кабинет: подсказки и вводная вкладки — без немецких строк."""
    from apps.orders.tests.test_payment_methods import _configure

    _configure(settings)
    tenant = _tenant(orders_prepay=True, payments_enabled=True, stripe_connect_id="acct_1")
    with translation.override("ru"):
        part = _part(Browser(tenant).get(WINDOW))
    assert "Подтверждение придёт на e-mail из оплаты" in part
    assert "При заказе за столиком (QR-код) мы спрашиваем только" in part
    assert "Что корзина спрашивает при заказе" in part
    assert STRIPE_HINT not in part and TABLE_HINT not in part
