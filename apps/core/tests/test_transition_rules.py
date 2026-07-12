"""FB-3: правила переходов статусов (кабинет-конфигуратор поверх FSM).

Инвариант: FSM/apply() — жёсткий пол; конфиг только СКРЫВАЕТ не-danger переходы из
ОТОБРАЖЕНИЯ; danger/отмена (cancel) не прячется никогда. Хранение presence-minimal.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.core import pipeline, transactions, transition_rules
from apps.core.views import transitions_save
from apps.orders.state_machine import OrderSM
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _post(data, tenant):
    req = RequestFactory().post("/x", data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    req.user = get_user_model()(is_active=True)
    return req


def _make_order():
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal("8.00"))
    return create_order(items=[(product, 1)], name="Max", email="max@test.de")


def _all_nondanger_checked(kind="order"):
    """POST со ВСЕМИ не-danger переходами включёнными (= дефолт, ничего не скрыто)."""
    sm = OrderSM()
    data = {}
    for src in siteconfig.status_label_statuses(kind):
        for dst in sm.allowed_targets(src):
            if not pipeline.is_danger(dst):
                data[f"t_{src}_{dst}"] = "on"
    return data


# --- pure read (без DB) ------------------------------------------------------


def test_keep_target_danger_always_kept():
    subset = {"new": []}  # скрыть все не-danger из new
    assert transition_rules.keep_target("new", "cancelled", subset) is True  # danger
    assert transition_rules.keep_target("new", "confirmed", subset) is False
    assert transition_rules.keep_target("confirmed", "ready", {}) is True  # нет правила → да


def test_allowed_actions_hides_nondanger_keeps_danger():
    full = {a["target"] for a in transactions.allowed_actions_for("order", "new")}
    assert full == {"confirmed", "cancelled"}
    hidden = {a["target"] for a in transactions.allowed_actions_for("order", "new", {"new": []})}
    assert hidden == {"cancelled"}  # confirmed скрыт, cancel (danger) остался


# --- save (DB) ---------------------------------------------------------------


def test_save_stores_only_when_hidden_and_presence_minimal():
    t = TenantFactory(site_config={"foo": 1})
    data = _all_nondanger_checked()
    del data["t_new_confirmed"]  # скрыть один переход new→confirmed
    transition_rules.save(t, "order", _post(data, t))
    t.refresh_from_db()
    assert t.site_config["transitions"]["order"] == {"new": []}
    assert t.site_config["foo"] == 1  # прочие ключи целы
    # всё включено обратно → правило снимается (presence-minimal), ключ уходит
    transition_rules.save(t, "order", _post(_all_nondanger_checked(), t))
    t.refresh_from_db()
    assert "transitions" not in t.site_config


def test_editor_rows_structure_and_danger_flag():
    rows = transition_rules.editor_rows(TenantFactory(site_config={}), "order")
    srcs = {r["src"] for r in rows}
    assert "new" in srcs  # у new есть не-danger переход (confirmed)
    assert "picked_up" not in srcs  # picked_up→returned только danger → строки нет
    new_row = next(r for r in rows if r["src"] == "new")
    tgts = {x["dst"]: x for x in new_row["targets"]}
    assert tgts["confirmed"]["enabled"] and not tgts["confirmed"]["danger"]
    assert tgts["cancelled"]["danger"]  # danger-флаг у отмены


# --- board (кабинет) vs клиентский аккаунт -----------------------------------


def test_transaction_for_applies_transitions_only_when_passed():
    order = _make_order()  # статус new
    full = {a["target"] for a in transactions.transaction_for("order", order).allowed_actions}
    assert "confirmed" in full  # без subset — дефолт
    hidden = transactions.transaction_for("order", order, transitions={"new": []}).allowed_actions
    tgts = {a["target"] for a in hidden}
    assert "confirmed" not in tgts and "cancelled" in tgts  # скрыт, danger остался


# --- normalize ---------------------------------------------------------------


def test_normalize_transitions_whitelist_and_presence():
    out = siteconfig.normalize_transitions(
        {
            "order": {"new": ["confirmed", "bogus"], "unknownsrc": ["x"]},
            "stay": {"confirmed": []},  # пустой список осмыслен → материализуется
            "nope": {"a": ["b"]},
        }
    )
    assert out == {"order": {"new": ["confirmed"]}, "stay": {"confirmed": []}}
    assert siteconfig.normalize_transitions({}) == {}


def test_normalize_preserves_transitions_key():
    out = siteconfig.normalize({"transitions": {"order": {"new": []}}})
    assert out["transitions"] == {"order": {"new": []}}
    # без ключа — не появляется (golden-паритет)
    assert "transitions" not in siteconfig.normalize({})


# --- view --------------------------------------------------------------------


def test_transitions_save_view_saves_and_404():
    t = TenantFactory(site_config={})
    data = _all_nondanger_checked()
    del data["t_new_confirmed"]
    data["next"] = "/dashboard/orders/"
    resp = transitions_save(_post(data, t), "order")
    assert resp.status_code == 302 and resp.url == "/dashboard/orders/"
    t.refresh_from_db()
    assert t.site_config["transitions"]["order"] == {"new": []}
    with pytest.raises(Http404):
        transitions_save(_post({}, t), "nope")
