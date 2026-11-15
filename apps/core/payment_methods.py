"""SH-23 (фидбэк владельца 2026-09-03): «для каждого типа заказа всех архетипов
по желанию нужна оплата онлайн, при получении или на месте или выставить счёт
как юрлицо; видимо нужен выбор — юрлицо покупает или физлицо».

Реестр способов оплаты — ОДИН на все виды сделок. До этой волны способ знал
только заказ (`Order.payment_method`), а бронь/номер/билет/заявка имели лишь
«сколько списать Stripe». Здесь: коды способов, тип покупателя и правила
доступности (`available`), которые уважают и настройки бизнеса, и решения
владельца §9 плана `docs/order-feedback-plan-2026-09-03.md`.

Решения владельца, зашитые в правила:
* Р-3 «Rechnung» (Kauf auf Rechnung) — ТОЛЬКО фирмам; частному лицу остаются
  Vorkasse, оплата на месте и онлайн.
* Р-2 срок оплаты счёта по умолчанию 14 дней (`Tenant.invoice_terms_days`).
* Р-4 удержание места без оплаты: до срока счёта, 3 дня для Vorkasse
  (`Tenant.vorkasse_hold_days`), «на месте» — без удержания.
* Р-5 отель со 100 % предоплатой принимает и банковский перевод, не только карту.
"""

from __future__ import annotations

from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

# Коды способов. Совпадают с `Order.PAYMENT_METHODS` (легаси-значения целы) плюс
# «invoice» — счёт юрлицу.
ON_SITE = "on_site"
STRIPE = "stripe"
VORKASSE = "vorkasse"
INVOICE = "invoice"

METHOD_LABELS = {
    ON_SITE: _("Barzahlung bei Abholung"),
    STRIPE: _("Online-Zahlung"),
    VORKASSE: _("Vorkasse (Überweisung)"),
    INVOICE: _("Kauf auf Rechnung"),
}
METHODS = tuple(METHOD_LABELS)
# Для `choices` доменных моделей (порядок реестра = порядок в админке/формах).
METHOD_CHOICES = [(code, label) for code, label in METHOD_LABELS.items()]

# Тип покупателя: частное лицо или фирма (Р-3 — от него зависит доступность счёта).
PRIVATE = "private"
COMPANY = "company"
CUSTOMER_TYPES = [
    (PRIVATE, _("Private")),
    (COMPANY, _("Company")),
]

# Виды сделок, у которых есть способ оплаты (kind контракта Transaction).
KINDS = ("order", "booking", "stay", "ticket", "job")


# FB-30.12: подпись «оплаты на месте» по виду сделки. Текст `METHOD_LABELS` записан в
# `choices` миграций пяти приложений — его не трогаем, меняется только эта подпись.
_ON_SITE_BY_KIND = {
    "order": _("Zahlung bei Abholung/Lieferung"),
    "booking": _("Zahlung vor Ort"),
    "stay": _("Zahlung bei Anreise"),
    "ticket": _("Zahlung an der Abendkasse"),
    "job": _("Zahlung nach Auftrag"),
}
_ON_SITE_BY_FULFILLMENT = {
    "pickup": _("Zahlung bei Abholung"),
    "delivery": _("Zahlung bei Lieferung"),
}
_ON_SITE_SUFFIX = {
    "cash": _("bar"),
    "card": _("Karte"),
    "both": _("bar oder Karte"),
}


def on_site_settings(tenant) -> dict:
    """`site_config["payment_on_site"]` с дефолтами (нет ключа → прежнее поведение)."""
    from apps.tenants.siteconfig import normalize_payment_on_site

    raw = (getattr(tenant, "site_config", None) or {}).get("payment_on_site")
    return normalize_payment_on_site(raw) or {"kind": "", "delivery": True}


def label(code: str, kind: str = "", *, fulfillment: str = "", tenant=None):
    """Человеческая подпись способа (неизвестный код → сам код).

    Без вида сделки — прежний текст реестра (старые вызовы не меняются). С видом —
    «оплата на месте» называется по сделке (запись — «vor Ort», номер — «bei Anreise»)
    и, если бизнес указал подвид, с уточнением «(bar)/(Karte)/(bar oder Karte)».
    """
    if code != ON_SITE or kind not in _ON_SITE_BY_KIND:
        return METHOD_LABELS.get(code, code)
    base = _ON_SITE_BY_KIND[kind]
    if kind == "order" and fulfillment in _ON_SITE_BY_FULFILLMENT:
        base = _ON_SITE_BY_FULFILLMENT[fulfillment]
    suffix = _ON_SITE_SUFFIX.get(on_site_settings(tenant)["kind"]) if tenant else None
    if not suffix:
        return base
    return format_lazy("{} ({})", base, suffix)


def _stripe_ready(tenant) -> bool:
    from apps.billing import connect

    return bool(
        getattr(tenant, "payments_enabled", False) and connect.is_connect_configured()
    ) and bool(getattr(tenant, "stripe_connect_id", ""))


def invoice_enabled(tenant) -> bool:
    """Счёт юрлицу включён у бизнеса (Р-1: счёт выпускается автоматически)."""
    return bool(getattr(tenant, "invoice_b2b_enabled", False))


def available(
    tenant, kind: str = "order", *, customer_type: str = PRIVATE, fulfillment: str = ""
) -> list[str]:
    """Способы оплаты для вида сделки и типа покупателя.

    Порядок = порядок пикера, первый — дефолт. Правила:
    * онлайн — при подключённом Stripe-Connect (у заказов дополнительно тумблер
      предоплаты, как в E7-2 — прежнее поведение чекаута корзины);
    * Vorkasse — при тумблере и заполненном IBAN;
    * счёт — только фирме и только при `invoice_b2b_enabled` (Р-3);
    * оплата на месте — всегда (последний, как раньше); FB-30.12: у заказа с
      доставкой бизнес может её выключить, но только если остаётся онлайн или
      Vorkasse — ноль способов на чекауте не бывает (счёт частному лицу не положен).
    """
    methods: list[str] = []
    if kind == "order":
        stripe_ok = _stripe_ready(tenant) and getattr(tenant, "orders_prepay", False)
    else:
        stripe_ok = _stripe_ready(tenant)
    if stripe_ok:
        methods.append(STRIPE)
    if getattr(tenant, "vorkasse_enabled", False) and getattr(tenant, "bank_iban", ""):
        methods.append(VORKASSE)
    if customer_type == COMPANY and invoice_enabled(tenant):
        methods.append(INVOICE)
    if on_site_allowed(tenant, kind, fulfillment=fulfillment, others=methods):
        methods.append(ON_SITE)
    return methods


def on_site_allowed(tenant, kind: str, *, fulfillment: str, others: list[str]) -> bool:
    """Предлагать ли «оплату на месте» (FB-30.12). Выключается только у заказа с
    доставкой при снятом флажке и при наличии способа для частного лица."""
    if kind != "order" or fulfillment != "delivery":
        return True
    if on_site_settings(tenant)["delivery"]:
        return True
    return not any(m in (STRIPE, VORKASSE) for m in others)


ON_SITE_REFUSED = _(
    "Bei Lieferung ist Zahlung vor Ort nicht möglich. Bitte wählen Sie eine andere Zahlungsart."
)


def on_site_refused(tenant, code: str, kind: str = "order", *, fulfillment: str = "") -> str:
    """FB-30.12: покупатель выбрал «на месте», а при доставке бизнес её выключил →
    текст ошибки (заказ не создаётся; молча подменять способ оплаты нельзя — это
    деньги). Иначе пустая строка."""
    if (code or "").strip() != ON_SITE:
        return ""
    if on_site_allowed(tenant, kind, fulfillment=fulfillment, others=_others(tenant, kind)):
        return ""
    return str(ON_SITE_REFUSED)


def hidden_for_delivery(tenant, kind: str = "order") -> bool:
    """Пикер витрины прячет «vor Ort», когда покупатель выбрал доставку (FB-30.12b);
    сервер всё равно отказывает сам (`on_site_refused`)."""
    return not on_site_allowed(tenant, kind, fulfillment="delivery", others=_others(tenant, kind))


def picker_rows(tenant, methods: list[str], kind: str = "order") -> list[dict]:
    """Строки пикера оплаты: код, подпись по виду сделки, «скрыть при доставке»."""
    hide = ON_SITE in methods and hidden_for_delivery(tenant, kind)
    return [
        {
            "code": m,
            "label": label(m, kind, tenant=tenant),
            "no_delivery": hide and m == ON_SITE,
        }
        for m in methods
    ]


def _others(tenant, kind: str) -> list[str]:
    return [m for m in available(tenant, kind) if m != ON_SITE]


def normalize(
    code: str,
    tenant,
    kind: str = "order",
    *,
    customer_type: str = PRIVATE,
    fulfillment: str = "",
) -> str:
    """Выбранный способ или первый доступный (мусор/недоступное → дефолт).

    Тот же fail-safe, что был у чекаута корзины: подмена поля не даёт способа,
    которого бизнес не предлагает.
    """
    allowed = available(tenant, kind, customer_type=customer_type, fulfillment=fulfillment)
    code = (code or "").strip()
    return code if code in allowed else allowed[0]


def clean_vat_id(raw: str) -> str:
    """Ревью безопасности CO-2: USt-IdNr с витрины — только формат «2 буквы + 2–13
    знаков» (иначе в официальный счёт уходил бы произвольный текст посетителя)."""
    import re

    value = re.sub(r"[\s.\-/]", "", (raw or "").upper())
    return value if re.fullmatch(r"[A-Z]{2}[0-9A-Z]{2,14}", value) else ""


def offline_payment(deal) -> bool:
    """CO-2d: покупатель выбрал оплату переводом (Rechnung/Vorkasse) — депозит/предоплату
    через Stripe не требуем: выбор покупателя сильнее настройки тарифа."""
    return getattr(deal, "payment_method", "") in (INVOICE, VORKASSE)


def customer_type_of(raw: str) -> str:
    """Тип покупателя из POST; мусор → частное лицо (fail-closed для счёта)."""
    return COMPANY if (raw or "").strip() == COMPANY else PRIVATE


def hold_days(tenant, method: str) -> int:
    """Р-4: сколько держать место/номер/билет без оплаты.

    Счёт — до срока оплаты счёта (по умолчанию 14 дней), Vorkasse — 3 дня,
    оплата на месте и онлайн-оплата удержания не требуют (0 = не ограничиваем).
    """
    if method == INVOICE:
        return int(getattr(tenant, "invoice_terms_days", 0) or 14)
    if method == VORKASSE:
        return int(getattr(tenant, "vorkasse_hold_days", 0) or 3)
    return 0


def picker_context(tenant, kind="order", *, customer_type=PRIVATE) -> dict:
    """Данные для партиалов `_payment_picker.html` и `_billing_party.html`.

    Список считаем ДЛЯ ФИРМЫ (счёт должен быть в разметке, чтобы переключатель
    «Privat/Firma» мог его включить без перезагрузки) — сервер всё равно
    пересчитывает по фактическому типу покупателя.
    """
    methods = available(
        tenant, kind, customer_type=COMPANY if invoice_enabled(tenant) else customer_type
    )
    return {
        "payment_methods": (picker_rows(tenant, methods, kind) if len(methods) > 1 else []),
        "billing_party_enabled": invoice_enabled(tenant),
    }
