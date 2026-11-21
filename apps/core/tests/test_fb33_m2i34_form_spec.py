"""FB-33 M2i-34: форма оформления заказа (корзина) в ядре `form_spec` — режимы, подписи, проверка.

План — scratchpad `m2i34-plan.md` (C2). Подписи формы `checkout` = подписи витрины корзины
(«Note (optional)»), e-mail при доступной онлайн-оплате не выключается (минимум «Optional»),
у заказа за столиком контакты не спрашиваются; оба способа связи «нет» разрешены. Деньги
ответы не трогают: в `form_answers` нет денежного типа, расчёт заказа ядро форм не знает.
"""

import re
from pathlib import Path

import pytest
from django.utils import translation
from django.utils.translation import gettext

from apps.core import form_answers, form_spec

ROOT = Path(__file__).resolve().parents[3]


def _site(mode=None, labels=None, custom=None):
    entry = {}
    if mode:
        entry["mode"] = mode
    if labels:
        entry["labels"] = labels
    if custom:
        entry["custom"] = custom
        entry["next_id"] = len(custom)
    raw = {"checkout": entry}
    return {"form_fields": form_spec.normalize_all(raw)}


#: C2 ещё нет — поведение будущего (strict: ожил раньше — замок снять)
TODO_C2 = pytest.mark.xfail(strict=True, reason="FB-33 M2i-34 C2")


@TODO_C2
@pytest.mark.parametrize("lang", ["de", "ru"])
def test_checkout_labels_are_the_storefront_labels(lang):
    """Те же msgid, что рисует корзина (`storefront/cart.html`)."""
    with translation.override(lang):
        shown = form_spec.view({}, "checkout")
        got = [shown[k].label for k in ("name", "email", "phone", "note")]
        assert got == [gettext(m) for m in ("Name", "Email", "Phone", "Note (optional)")]
        req = form_spec.view(_site({"note": "req"}), "checkout")["note"].label
        assert req == gettext("Note")


def test_checkout_defaults_are_optional_and_name_is_pinned():
    shown = form_spec.view({}, "checkout")
    assert shown["name"].req and all(shown[k].mode == "opt" for k in ("email", "phone", "note"))
    assert form_spec.missing({}, "checkout", {}) == []


def test_both_contacts_off_are_allowed_in_checkout():
    """Заявке нужен способ связи; корзине — нет (обязательно только имя)."""
    site = _site({"email": "off", "phone": "off"})
    assert site["form_fields"]["checkout"]["mode"] == {"email": "off", "phone": "off"}
    assert form_spec.missing(site, "checkout", {}) == []


def test_required_fields_and_questions_are_checked():
    custom = [
        {"id": "q1", "type": "text", "label": "Allergien", "mode": "req"},
        {"id": "q2", "type": "number", "label": "Personen"},
    ]
    site = _site({"phone": "req", "note": "req"}, custom=custom)
    assert form_spec.missing(site, "checkout", {}) == ["phone", "note", "q1"]
    post = {"phone": "0171", "note": "Klingeln", "q1": "Nüsse", "q2": "zwei"}
    assert form_spec.missing(site, "checkout", post) == []


@TODO_C2
def test_stripe_keeps_email_at_least_optional():
    site = _site({"email": "off"})
    assert not form_spec.view(site, "checkout")["email"].on
    assert form_spec.view(site, "checkout", stripe=True)["email"].mode == "opt"
    req = _site({"email": "req"})
    assert form_spec.view(req, "checkout", stripe=True)["email"].req


@TODO_C2
def test_table_order_does_not_ask_for_contacts():
    site = _site({"email": "req", "phone": "req", "note": "req"})
    shown = form_spec.view(site, "checkout", table=True)
    assert not shown["email"].on and not shown["phone"].on and shown["note"].req
    assert form_spec.missing(site, "checkout", {}, table=True) == ["note"]
    assert form_spec.missing_labels(site, "checkout", ["note"], table=True) == str(
        shown["note"].label
    )


@TODO_C2
def test_required_email_must_be_an_email():
    site = _site({"email": "req"})
    assert form_spec.missing(site, "checkout", {"email": "kein-email"}) == ["email"]
    assert form_spec.missing(site, "checkout", {"email": "k@example.com"}) == []


def test_answers_have_no_money_type():
    assert not {"money", "price", "amount", "currency"} & set(form_answers.TYPES)


@pytest.mark.parametrize(
    "path",
    ["apps/core/money_contract.py", "apps/orders/services.py", "apps/orders/totals.py"],
)
def test_money_code_does_not_know_the_forms(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    assert not re.search(r"\bform_(spec|answers)\b", text), path


def test_order_plaque_does_not_promise_editable_fields():
    """Решение владельца: окна «Felder» у корзины ещё нет — плашка этого не обещает."""
    text = (ROOT / "apps/core/legal_buttons.py").read_text(encoding="utf-8")
    assert "Felder können Sie anpassen" not in text


def test_hidden_commit_button_of_felder_is_not_aria_hidden():
    """Невидимая «Übernehmen» (Enter в поле): sr-only и вне Tab, но не aria-hidden —
    скрытая от чтецов кнопка по умолчанию формы — нарушение (как у плашек M3-5c)."""
    tpl = (ROOT / "templates/tenant/_bw_formfields.html").read_text(encoding="utf-8")
    button = re.search(r'<button[^>]*name="f_commit_new"[^>]*>', tpl).group(0)
    assert 'class="sr-only"' in button and 'tabindex="-1"' in button
    assert "aria-hidden" not in button
