"""FB-30.12b: вкладка «Zahlung» карточками (макет 7, `docs/fb30-plan-2026-11-15.md` §12b).

Карточка = вид оплаты из общего реестра `payment_methods`; включён ли он, считают те же
флаги `Tenant`, что и чекаут (`available`) — второго списка правил здесь нет. Поля карточек
пишут прежние сентинелы `sec_*` и новый `sec_on_site` (подвид «оплаты на месте»)."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core import payment_methods as pm

ARTS = (pm.ON_SITE, pm.STRIPE, pm.VORKASSE, pm.INVOICE)

_TITLES = {
    pm.ON_SITE: _("Zahlung vor Ort"),
    pm.STRIPE: _("Online-Zahlung"),
    pm.VORKASSE: _("Vorkasse (Überweisung)"),
    pm.INVOICE: _("Kauf auf Rechnung"),
}
_KIND_TEXT = {
    "": _("bar oder Karte – nach Ihrer Kasse"),
    "cash": _("nur bar"),
    "card": _("nur Karte am Terminal"),
    "both": _("bar oder Karte"),
}


def art_from(raw) -> str:
    """Вид из `?art=`; мусор → "" (ничего не раскрыто)."""
    return raw if raw in ARTS else ""


def _summary(tenant, code: str, ctx: dict) -> str:
    if code == pm.ON_SITE:
        cfg = pm.on_site_settings(tenant)
        text = str(_KIND_TEXT[cfg["kind"]])
        if ctx.get("orders_active") and not cfg["delivery"]:
            text = f"{text} · {_('nicht bei Lieferung')}"
        return text
    if code == pm.STRIPE:
        state = _("verbunden") if ctx.get("connected") else _("nicht verbunden")
        return f"{_('Anbieter')}: Stripe · {state}"
    if code == pm.VORKASSE:
        if ctx.get("vorkasse_enabled") and not ctx.get("bank_iban"):
            return str(_("IBAN fehlt – wird nicht angeboten"))
        return str(_("Kunde überweist vorab auf Ihr Konto"))
    terms = ctx.get("invoice_terms_days") or 14
    return str(_("nur für Firmen · Zahlungsziel %(days)s Tage") % {"days": terms})


def _is_on(tenant, code: str) -> bool:
    if code == pm.ON_SITE:
        return True
    if code == pm.STRIPE:
        return pm._stripe_ready(tenant)
    if code == pm.VORKASSE:
        return bool(tenant.vorkasse_enabled and tenant.bank_iban)
    return pm.invoice_enabled(tenant)


def cards_context(tenant, ctx: dict, art: str = "") -> dict:
    """Карточки (включённые сверху, порядок реестра внутри групп) и меню «＋ Zahlungsart»."""
    # Те же условия показа, что у прежних секций: Vorkasse — при заказах, Stripe — когда
    # платформа подключила Connect (иначе карточке нечего настроить).
    codes = [
        c
        for c in ARTS
        if (c != pm.VORKASSE or ctx.get("orders_active"))
        and (c != pm.STRIPE or ctx.get("connect_configured"))
    ]
    cards = [
        {
            "code": code,
            "title": _TITLES[code],
            "summary": _summary(tenant, code, ctx),
            "on": _is_on(tenant, code),
            "open": code == art,
        }
        for code in codes
    ]
    cards.sort(key=lambda c: not c["on"])
    others = [c for c in cards if c["on"] and c["code"] != pm.ON_SITE]
    return {
        "pay_cards": cards,
        "pay_addable": [c for c in cards if not c["on"]],
        "pay_art": art,
        "on_site_cfg": pm.on_site_settings(tenant),
        "on_site_kinds": [
            ("", _("Nicht angeben")),
            ("cash", _("Nur bar")),
            ("card", _("Nur Karte am Terminal")),
            ("both", _("Bar oder Karte")),
        ],
        # Выключение «vor Ort» при доставке работает, только если есть чем платить ещё.
        "on_site_switch_idle": not any(c["code"] in (pm.STRIPE, pm.VORKASSE) for c in others),
    }
