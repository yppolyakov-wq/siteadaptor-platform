"""FB-33 M2i-6: пресет полей корзины по типу бизнеса.

План — `docs/fb33-stack8-plan-2026-11-22.md` (срез B). Решение владельца 2026-11-22: пресет —
только режимы полей и подпись заметки, без своих вопросов; bakery / cafe / restaurant / butcher
— телефон «Pflicht», заметка «Allergien / Wünsche»; у остальных типов пресета корзины нет.
Кладётся при создании бизнеса и при СМЕНЕ типа — только при отсутствующем ключе
`form_fields.checkout` (ключ есть, даже пустой — «задано»); существующие бизнесы не трогаем.
Кнопка «Branchen-Vorlage laden» вкладки «Felder» корзины — через черновик окна.

Замки по таблице §2 плана: один реестр (2), запись только `form_spec.put` (1), настройка
владельца цела (6), подпись заметки переведена на языки тенанта (16, 17), заказ к столику без
телефона (29).
"""

import copy
import json
import uuid
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import translation

from apps.core import aufbau_draft, form_spec, setup_steps
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.jobs import anfrage_presets
from apps.jobs.anfrage_presets import preset_for
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.services import _new_tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

FOOD = ("bakery", "cafe", "restaurant", "butcher")
NOTE_DE = "Allergien / Wünsche"
NOTE = {
    "en": "Allergies / requests",
    "tr": "Alerjiler / istekler",
    "ru": "Аллергии / пожелания",
    "uk": "Алергії / побажання",
}
WOPEN = "openM2i6"
WINDOW = "?seite=cart&block=form&tab=felder"
#: то, что пресет кладёт бизнесу с языками de+en (фабрика и регистрация)
ENTRY_DE_EN = {
    "mode": {"phone": "req"},
    "labels": {"note": NOTE_DE},
    "labels_i18n": {"note": {"en": NOTE["en"]}},
}


def _new(business_type, slug="neu"):
    return _new_tenant(
        business_name="Neu", slug=slug, business_type=business_type, city="Köln", email="a@b.de"
    )


def _tenant(business_type="cafe", cfg=None, **kw):
    return TenantFactory(
        business_type=business_type,
        disabled_modules=[],
        site_config=copy.deepcopy(cfg if cfg is not None else {}),
        **kw,
    )


def _stored(tenant):
    return Tenant.objects.get(pk=tenant.pk).site_config


def _checkout(config):
    return (siteconfig.normalize(config).get("form_fields") or {}).get("checkout")


def _edit(b, **fields):
    data = {"seite": "cart", "ref": "form", "op": "update", "panel_present": "1", "wopen": WOPEN}
    data.update({f"f_{k}": v for k, v in fields.items()})
    return b.post(**data)


def _draft_form(b):
    drafts = (b.session or {}).get(aufbau_draft.SESSION_KEY) or {}
    return copy.deepcopy((drafts.get("cart") or {}).get("form"))


def _part(html):
    start = html.index('id="bw-form-formfields"')
    return html[start : html.index("</form>", start)]


# ───────────── реестр: один, у гастро-типов пресет, у остальных — нет ─────────────


def test_food_types_have_checkout_preset_others_do_not():
    for business_type in FOOD:
        preset = preset_for(business_type, form="checkout")
        assert preset["mode"] == {"phone": "req"}
        assert preset["labels"] == {"note": NOTE_DE}
        assert not preset.get("custom")  # решение владельца: без своих вопросов
    for business_type in ("retail", "online_shop", "catering", "handwerker", "hotel", "", None):
        assert preset_for(business_type, form="checkout") == {}
    assert preset_for("bakery") == {}  # у заявки пекарни пресета как не было, так и нет
    assert preset_for("catering")["fields"] == ["date", "guests", "event_type"]


def test_preset_note_is_translated_to_the_given_locales_only():
    preset = preset_for("bakery", form="checkout", locales=["en", "ru"])
    assert preset["labels_i18n"] == {"note": {"en": NOTE["en"], "ru": NOTE["ru"]}}
    assert not preset_for("bakery", form="checkout").get("labels_i18n")  # один язык — нет
    every = preset_for("cafe", form="checkout", locales=["de", "en", "tr", "ru", "uk", "xx"])
    assert every["labels_i18n"] == {"note": NOTE}  # основной и чужой язык — мимо
    # язык кабинета владельца на пресет не влияет: база — немецкая
    with translation.override("ru"):
        assert preset_for("bakery", form="checkout", locales=["en"]) == {
            "mode": {"phone": "req"},
            "labels": {"note": NOTE_DE},
            "labels_i18n": {"note": {"en": NOTE["en"]}},
        }


def test_one_registry_feeds_signup_type_switch_and_window(monkeypatch):
    """Второго списка нет: запись реестра меняет все три пути сразу."""
    monkeypatch.setitem(anfrage_presets.PRESETS["checkout"], "hotel", {"mode": {"email": "req"}})
    assert _checkout(_new("hotel").site_config) == {"mode": {"email": "req"}}
    switched = _tenant("retail")
    setup_steps.apply_business_type(switched, "hotel")
    assert _checkout(_stored(switched)) == {"mode": {"email": "req"}}
    b = Browser(_tenant("hotel"))
    assert "data-form-preset" in _part(b.get(WINDOW))
    _edit(b, do="preset")
    assert _draft_form(b)["mode"]["email"] == "req"


# ───────────── создание бизнеса ─────────────


def test_new_food_business_starts_with_checkout_preset():
    for i, business_type in enumerate(FOOD):
        tenant = _new(business_type, slug=f"neu-{i}")
        assert tenant.enabled_locales == ["de", "en"]
        assert _checkout(tenant.site_config) == ENTRY_DE_EN
        site = siteconfig.normalize(tenant.site_config)
        shown = form_spec.view(site, "checkout", "de")
        assert shown["phone"].req and shown["note"].label == NOTE_DE
        assert form_spec.view(site, "checkout", "en")["note"].label == NOTE["en"]
        assert shown["custom"] == []


def test_new_business_of_other_type_has_no_checkout_settings():
    assert "form_fields" not in _new("retail").site_config
    catering = _new("catering", slug="tafel").site_config
    assert "form_fields" not in catering and catering["anfrage"]  # заявка — прежний пресет


def test_signup_with_directions_and_wizard_keeps_the_preset():
    tenant = _new_tenant(
        business_name="Neu",
        slug="neu-v4",
        business_type="bakery",
        city="Köln",
        email="a@b.de",
        wizard_v4=True,
        directions=["products"],
    )
    assert _checkout(tenant.site_config) == ENTRY_DE_EN
    assert tenant.site_config["onboarding"]["flow"] == "v4"


# ───────────── смена типа: только при отсутствующем ключе ─────────────


def test_switch_to_food_type_adds_preset_and_keeps_other_keys():
    cfg = {"notify": {"x": 1}, "form_fields": {"anfrage": {"mode": {"phone": "req"}}}}
    tenant = _tenant("retail", cfg)
    setup_steps.apply_business_type(tenant, "restaurant")
    stored = _stored(tenant)
    assert stored["form_fields"].pop("checkout") == ENTRY_DE_EN
    assert stored == cfg  # заявка и чужие ключи — как были


def test_switch_translates_note_to_tenant_languages():
    tenant = _tenant("retail", enabled_locales=["de", "ru", "uk"])
    setup_steps.apply_business_type(tenant, "butcher")
    entry = _checkout(_stored(tenant))
    assert entry["labels_i18n"] == {"note": {"ru": NOTE["ru"], "uk": NOTE["uk"]}}
    site = siteconfig.normalize(_stored(tenant))
    assert form_spec.view(site, "checkout", "uk")["note"].label == NOTE["uk"]
    assert form_spec.view(site, "checkout", "en")["note"].label == NOTE_DE  # перевода нет

    single = _tenant("retail", enabled_locales=["de"])
    setup_steps.apply_business_type(single, "cafe")
    assert _checkout(_stored(single)) == {"mode": {"phone": "req"}, "labels": {"note": NOTE_DE}}


@pytest.mark.parametrize(
    "own",
    [
        {"mode": {"phone": "off"}},
        {"labels": {"note": "Wunschtext"}},
        {"custom": [{"id": "q1", "type": "text", "label": "Uhrzeit"}], "next_id": 1},
        {},  # ключ есть и пуст — «задано», не трогаем
    ],
)
def test_switch_never_touches_existing_checkout_key(own):
    cfg = {"form_fields": {"checkout": own}}
    tenant = _tenant("retail", cfg)
    Tenant.objects.filter(pk=tenant.pk).update(site_config=cfg)  # как лежит, без нормализации
    setup_steps.apply_business_type(tenant, "bakery")
    assert json.dumps(_stored(tenant), sort_keys=True) == json.dumps(cfg, sort_keys=True)
    assert Tenant.objects.get(pk=tenant.pk).business_type == "bakery"


def test_same_type_again_and_non_food_switch_add_nothing():
    old = _tenant("bakery", {"notify": {"x": 1}})  # существующий бизнес — без пресета
    setup_steps.apply_business_type(old, "bakery")
    assert _stored(old) == {"notify": {"x": 1}}
    other = _tenant("bakery")
    setup_steps.apply_business_type(other, "retail")
    assert "form_fields" not in _stored(other)


@pytest.mark.xfail(strict=True, reason="ревью стопки 8: пресет прежнего типа остаётся")
def test_untouched_preset_follows_the_type_but_owner_edits_stay():
    """Ревью стопки 8: пресет, который владелец не правил, уходит вместе с типом (пекарня →
    магазин: телефон «Pflicht» и «Allergien / Wünsche» магазину не нужны); правленный — остаётся."""
    shop = _tenant("retail")
    setup_steps.apply_business_type(shop, "bakery")
    assert _checkout(_stored(shop))["mode"] == {"phone": "req"}
    setup_steps.apply_business_type(shop, "retail")
    assert "checkout" not in (_stored(shop).get("form_fields") or {})

    food = _tenant("retail")
    setup_steps.apply_business_type(food, "bakery")
    before = copy.deepcopy(_checkout(_stored(food)))
    setup_steps.apply_business_type(food, "cafe")  # у обоих типов пресет один — остаётся
    assert _checkout(_stored(food)) == before

    own = _tenant("retail")
    setup_steps.apply_business_type(own, "bakery")
    cfg = _stored(own)
    cfg["form_fields"]["checkout"]["mode"] = {"phone": "opt"}  # владелец смягчил телефон
    Tenant.objects.filter(pk=own.pk).update(site_config=cfg)
    own.refresh_from_db()
    kept = copy.deepcopy(_checkout(_stored(own)))
    setup_steps.apply_business_type(own, "retail")
    assert _checkout(_stored(own)) == kept


# ───────────── запись — только через form_spec.put ─────────────


def test_preset_is_written_through_form_spec_put(monkeypatch):
    calls = []
    real = form_spec.put

    def spy(config, form, state):
        calls.append(form)
        return real(config, form, state)

    monkeypatch.setattr(form_spec, "put", spy)
    _new("bakery", slug="spy-1")
    assert calls == ["checkout"]
    calls.clear()
    tenant = _tenant("retail")
    setup_steps.apply_business_type(tenant, "cafe")
    assert calls == ["checkout"]
    calls.clear()
    _new("retail", slug="spy-2")
    assert calls == []  # пресета нет — писателя не зовут


def test_without_the_writer_nothing_is_stored(monkeypatch):
    """Мимо писателя записи нет: с «немым» `put` ключ не появляется ни одним путём."""
    assert _checkout(_new("bakery", slug="vor").site_config)  # с писателем — есть
    monkeypatch.setattr(form_spec, "put", lambda config, form, state: config)
    assert "form_fields" not in _new("bakery", slug="mute").site_config
    tenant = _tenant("retail")
    setup_steps.apply_business_type(tenant, "cafe")
    assert "form_fields" not in _stored(tenant)


# ───────────── окно: «Branchen-Vorlage laden» — через черновик ─────────────


def test_preset_button_only_for_types_with_checkout_preset():
    assert "data-form-preset" in _part(Browser(_tenant("cafe")).get(WINDOW))
    assert "data-form-preset" not in _part(Browser(_tenant("online_shop")).get(WINDOW))
    # у кейтеринга пресет есть только у заявки — в корзине кнопки нет
    assert "data-form-preset" not in _part(Browser(_tenant("catering")).get(WINDOW))


def test_window_preset_goes_to_draft_not_to_site_config():
    tenant = _tenant("cafe", {"notify": {"x": 1}})
    before = json.dumps(_stored(tenant), sort_keys=True)
    b = Browser(tenant)
    resp, msgs = _edit(b, do="preset")
    assert resp.status_code == 302 and any("Branchen-Vorlage" in m for m in msgs)
    state = _draft_form(b)
    assert state["mode"] == {"email": "opt", "phone": "req", "note": "opt"}
    assert state["labels"] == {"note": NOTE_DE}
    assert state["labels_i18n"] == {"note": {"en": NOTE["en"]}}  # языки бизнеса: de+en
    assert state["custom"] == []
    assert json.dumps(_stored(tenant), sort_keys=True) == before  # на сайт — ни байта

    # «Abbrechen» окна откатывает пресет
    b.post(seite="cart", ref="form", op="revert", wopen=WOPEN)
    assert _draft_form(b) is None
    assert json.dumps(_stored(tenant), sort_keys=True) == before


def test_window_preset_reaches_the_site_only_on_save_through_put(monkeypatch):
    tenant = _tenant("butcher", {"notify": {"x": 1}}, enabled_locales=["de", "tr"])
    calls = []
    real = form_spec.put

    def spy(config, form, state):
        calls.append(form)
        return real(config, form, state)

    monkeypatch.setattr(form_spec, "put", spy)
    b = Browser(tenant)
    _edit(b, do="preset")
    calls.clear()
    b.post(seite="cart", op="save")
    assert "checkout" in calls
    stored = _stored(tenant)
    assert _checkout(stored) == {
        "mode": {"phone": "req"},
        "labels": {"note": NOTE_DE},
        "labels_i18n": {"note": {"tr": NOTE["tr"]}},
    }
    assert stored["notify"] == {"x": 1}


def test_window_preset_replaces_modes_and_keeps_own_questions():
    own = {
        "mode": {"email": "off", "note": "req"},
        "labels": {"note": "Wunschtext", "email": "Mail"},
        "labels_i18n": {"note": {"en": "Wish"}},
        "custom": [{"id": "q1", "type": "text", "label": "Uhrzeit"}],
        "next_id": 1,
    }
    b = Browser(_tenant("bakery", {"form_fields": {"checkout": own}}))
    _edit(b, do="preset")
    state = _draft_form(b)
    assert state["mode"] == {"email": "opt", "phone": "req", "note": "opt"}  # «ersetzen»
    assert state["labels"] == {"note": NOTE_DE, "email": "Mail"}
    # подпись заметки сменилась — её прежний перевод снят, стоит перевод пресета
    assert state["labels_i18n"] == {"note": {"en": NOTE["en"]}}
    assert [q["label"] for q in state["custom"]] == ["Uhrzeit"]  # свои вопросы целы


def test_window_preset_without_template_says_so_and_changes_nothing():
    tenant = _tenant("online_shop")
    b = Browser(tenant)
    _resp, msgs = _edit(b, do="preset")  # запрос в обход кнопки
    assert any("keine Vorlage" in m for m in msgs)
    assert _draft_form(b) is None and "form_fields" not in _stored(tenant)


# ───────────── заказ к столику проходит без телефона ─────────────


def _order_req(tenant, data, session):
    request = RequestFactory().post("/warenkorb/", data)
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.session.update(session)
    request.tenant = tenant
    return request


def test_table_order_needs_no_phone_with_the_preset():
    site = siteconfig.normalize({"form_fields": {"checkout": copy.deepcopy(ENTRY_DE_EN)}})
    assert form_spec.missing(site, "checkout", {"name": "Kunde"}) == ["phone"]
    assert form_spec.missing(site, "checkout", {"name": "Kunde"}, table=True) == []
    assert not form_spec.view(site, "checkout", table=True)["phone"].on


def test_table_checkout_view_passes_without_phone_but_pickup_does_not(settings):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders import public_views
    from apps.orders.models import Order

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory.build(
        business_type="restaurant",
        site_config={"form_fields": {"checkout": copy.deepcopy(ENTRY_DE_EN)}},
    )
    product = ProductFactory(base_price=Decimal("8.00"))
    add = _order_req(tenant, {"product": str(product.pk), "qty": "1"}, {})
    public_views.cart_add(add)
    cart = add.session["cart"]

    public_views.checkout(_order_req(tenant, {"name": "Kunde"}, {"cart": cart}))
    assert not Order.objects.exists()  # самовывоз: телефон обязателен

    public_views.checkout(_order_req(tenant, {"name": "Kunde"}, {"cart": cart, "table": "7"}))
    order = Order.objects.get()
    assert order.table_number == "7" and not order.customer.phone
