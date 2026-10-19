"""T-8.10g (G-1): факты для черновика ответа клиенту — только из базы.

План — docs/t8-10g-reply-draft-plan-2026-10-19.md §2. Черновик ИИ опирается на эти
строки, а постпроверка (`ai_reply.check_reply`) пропускает в ответе только числа,
ссылки и утверждения, которые здесь есть (или были в переписке).

Правила:
- `ref_label`/`subject` треда пишет клиент — фактами они НЕ считаются;
- факты сделки — только если клиент треда совпадает с клиентом сделки (О-1):
  ссылку на чужой заказ можно подставить в публичную форму;
- не берём внутренние поля (EK `cost_price`, ставки сметы `cost_rate`), контакты,
  адрес доставки и оплату клиента, имена сотрудников;
- формат дат «Mo 19.10.», время «18:00», год отдельным словом: `core.pii.scrub`
  считает 7+ цифр подряд телефоном и вырезал бы «19.10.2026» из промпта.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone
from django.utils.html import strip_tags

DESCRIPTION_MAX = 600
LINES_MAX = 12

WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
WEEKDAYS_LONG = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

DEAL_KINDS = ("order", "booking", "stay", "ticket", "job", "reservation")


@dataclass
class Facts:
    lines: list[str] = field(default_factory=list)
    urls: set[str] = field(default_factory=set)
    # True — у товара заполнена декларация аллергенов (LMIV: пустой список =
    # «неизвестно», О-3); иначе упоминать аллергены черновику нельзя.
    allergens_declared: bool = False
    # Источник утверждений «vegan/bio/glutenfrei…» — только поля, не вопрос клиента.
    claims_text: str = ""
    # Подписи задекларированных аллергенов на всех языках кабинета (casefold):
    # черновик может назвать аллерген, только если он здесь.
    allergen_text: str = ""
    # Названия (товар, строки сделки, событие, бизнес): их слова не считаются
    # упоминанием аллергена («Roggenbrot», «Käsekuchen»).
    name_text: str = ""
    # Контекст для модели («сегодня», текущий час) — в промпт и в digest, но НЕ в
    # набор разрешённых чисел: иначе «bis 14 Uhr» проходило бы ровно в 14:xx.
    context: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Доверенные факты из базы — источник разрешённых чисел, цен, ссылок."""
        return "\n".join(self.lines)

    @property
    def prompt_text(self) -> str:
        return "\n".join([*self.lines, *self.context])


# --- форматирование -----------------------------------------------------------------------


def money(value, currency: str = "EUR") -> str:
    if value in (None, ""):
        return ""
    try:
        d = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        return ""
    s = f"{d:.2f}".replace(".", ",")
    return f"{s} €" if (currency or "EUR") == "EUR" else f"{s} {currency}"


def day(value) -> str:
    """«Mo 19.10.» (с временем — «Mo 19.10. 18:00»); год не пишем — см. докстринг."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        local = timezone.localtime(value) if timezone.is_aware(value) else value
        return f"{WEEKDAYS[local.weekday()]} {local:%d.%m.} {local:%H:%M}"
    if isinstance(value, date):
        return f"{WEEKDAYS[value.weekday()]} {value:%d.%m.}"
    return ""


def _qty(value) -> str:
    try:
        d = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        return "1"
    return str(int(d)) if d == d.to_integral() else f"{d}".replace(".", ",")


def _one_line(text, limit: int = 200) -> str:
    return " ".join(strip_tags(str(text or "")).split())[:limit]


# --- сделка -------------------------------------------------------------------------------


def _find_deal(kind: str, ref_id: str):
    from apps.core import transactions

    model = transactions.model_for(kind)
    obj = model.objects.filter(reference_code=ref_id).first()
    if obj is None:
        try:
            obj = model.objects.filter(pk=uuid.UUID(ref_id)).first()
        except (ValueError, TypeError):
            obj = None
    return obj


def _deal_lines(kind: str, obj) -> list[str]:
    """Состав сделки строками «2× Roggenbrot à 3,20 €» — без EK и ставок."""
    out = []
    if kind == "order":
        for item in obj.items.all()[:LINES_MAX]:
            name = _one_line(item.title_snapshot, 120)
            if item.variant_label:
                name = f"{name} ({_one_line(item.variant_label, 60)})"
            out.append(f"{item.qty}× {name} à {money(item.unit_price, obj.currency)}")
    elif kind == "job":
        for line in obj.lines.all()[:LINES_MAX]:
            out.append(f"{_qty(line.qty)}× {_one_line(line.text, 120)} à {money(line.unit_price)}")
    elif kind in ("stay", "booking", "ticket"):
        from apps.core.deal_lines import deal_lines

        for row in deal_lines(kind, obj)[:LINES_MAX]:
            out.append(f"{_qty(row['qty'])}× {_one_line(row['label'], 120)} à {money(row['unit'])}")
    return out


def _deal_facts(kind: str, obj, facts: Facts) -> None:
    from apps.core import transactions
    from apps.inbox.deal_threads import KIND_WORD

    tx = transactions.transaction_for(kind, obj)
    facts.lines.append(f"Deal: {KIND_WORD.get(kind, kind)} {obj.reference_code}")
    # Тему заявки (Job.title) пишет клиент на /anfrage/ — фактом она не считается
    # (ревью T-8.10g): иначе «Pauschalpreis 1 €» из темы разрешил бы эту цену.
    if kind != "job":
        facts.lines.append(f"- Title: {_one_line(tx.title)}")
    facts.lines.append(f"- Status: {tx.status_label}")
    if tx.when:
        facts.lines.append(f"- Date: {day(tx.when)}")
    if tx.deadline:
        facts.lines.append(f"- Valid until: {day(tx.deadline)}")
    if tx.subtotal_display:
        facts.lines.append(f"- Total: {tx.subtotal_display}")
    for line in _deal_lines(kind, obj):
        facts.lines.append(f"- {line}")
        facts.name_text += f" {line}"


# --- продаваемая сущность -----------------------------------------------------------------


def _absolute(base: str, path: str) -> str:
    if not base or not path or not path.startswith("/"):
        return ""
    return base + path


def _product_facts(obj, facts: Facts, base: str) -> None:
    from apps.catalog.food import allergen_labels, diet_badges
    from apps.core.sellable import display_fields
    from apps.promotions.models import Promotion

    d = display_fields("product", obj)
    facts.lines.append(f"Item: {_one_line(d['name'])}")
    facts.name_text += f" {d['name']}"
    if not obj.is_active:
        facts.lines.append("- no longer offered")
        return
    if d.get("price_display"):
        facts.lines.append(f"- Price: {d['price_display']}")
    facts.lines.append(f"- Available: {'yes' if obj.in_stock else 'no'}")
    if d.get("description"):
        facts.lines.append(f"- Description: {_one_line(d['description'], DESCRIPTION_MAX)}")
    allergens = [a for a in (obj.allergens or []) if a]
    if allergens:
        facts.allergens_declared = True
        labels = ", ".join(str(a) for a in allergen_labels(allergens))
        facts.lines.append(f"- Allergens (complete declaration): {labels}")
        facts.allergen_text = _labels_all_languages(allergens)
    else:
        facts.lines.append("- Allergens: not declared (customer must ask in the shop)")
    diets = ", ".join(str(b["label"]) for b in diet_badges(obj.diets or []))
    if diets:
        facts.lines.append(f"- Diet: {diets}")
    facts.claims_text += f" {d['name']} {d.get('description') or ''} {diets}"
    promo = Promotion.objects.filter(Promotion.on_sale_q(), product=obj).order_by("ends_at").first()
    if promo is not None:
        if promo.discount_style == "mystery":
            # SF-9: секретная цена не раскрывается нигде, и в ответе тоже.
            facts.lines.append(
                f"- Offer: {_one_line(promo.title_text)} (secret price, only in the shop)"
            )
        else:
            price = money(promo.new_price, promo.currency) if promo.new_price else ""
            facts.lines.append(
                f"- Offer: {_one_line(promo.title_text)}"
                + (f", offer price {price}" if price else "")
            )
        if promo.ends_at:
            facts.lines.append(f"- Offer ends: {day(promo.ends_at)}")
    url = _absolute(base, obj.get_absolute_url())
    if url:
        facts.urls.add(url)
        facts.lines.append(f"- Link: {url}")


def _labels_all_languages(codes) -> str:
    """Подписи аллергенов на всех языках кабинета: черновик пишется на языке
    клиента, проверка должна узнать «Sesam», «sesame» и «кунжут» одинаково."""
    from django.conf import settings
    from django.utils import translation

    from apps.catalog.food import allergen_labels

    out = [" ".join(codes)]
    for code in getattr(settings, "CABINET_LANGUAGES", None) or [settings.LANGUAGE_CODE]:
        with translation.override(code):
            out.append(" ".join(str(a) for a in allergen_labels(codes)))
    return " ".join(out).casefold()


def _event_facts(obj, facts: Facts) -> None:
    if not obj.is_published:
        return  # неопубликованное событие не раскрываем (ревью T-8.10g)
    facts.lines.append(f"Event: {_one_line(obj.title_localized())}")
    facts.name_text += f" {obj.title_localized()}"
    facts.lines.append(f"- Starts: {day(obj.starts_at)}")
    if obj.location:
        facts.lines.append(f"- Place: {_one_line(obj.location)}")
    left = obj.seats_left
    if left is not None:
        facts.lines.append(f"- Free seats: {left}")
    facts.claims_text += f" {obj.title_localized()}"


def _stay_unit_facts(obj, facts: Facts) -> None:
    from apps.core.sellable import display_fields

    if not obj.is_active:
        return
    d = display_fields("stay", obj)
    facts.lines.append(f"Accommodation: {_one_line(d['name'])}")
    facts.name_text += f" {d['name']}"
    if d.get("price_display"):
        facts.lines.append(f"- Price: {d['price_display']}")
    if d.get("description"):
        facts.lines.append(f"- Description: {_one_line(d['description'], DESCRIPTION_MAX)}")
    facts.claims_text += f" {d['name']} {d.get('description') or ''}"


def _entity_facts(kind: str, ref_id: str, facts: Facts, base: str) -> None:
    try:
        pk = uuid.UUID(ref_id)
    except (ValueError, TypeError):
        return
    if kind == "product":
        from apps.catalog.models import Product

        obj = Product.objects.filter(pk=pk).first()
        if obj is not None:
            _product_facts(obj, facts, base)
    elif kind == "event":
        from apps.events.models import Event

        obj = Event.objects.filter(pk=pk).first()
        if obj is not None:
            _event_facts(obj, facts)
    elif kind == "stay":
        from apps.stays.models import StayUnit

        obj = StayUnit.objects.filter(pk=pk).first()
        if obj is not None:
            _stay_unit_facts(obj, facts)
    elif kind == "tour":
        from apps.events.models import Tour

        obj = Tour.objects.filter(pk=pk, is_published=True).first()
        if obj is not None:
            facts.lines.append(f"Tour: {_one_line(obj.title_localized())}")
            facts.name_text += f" {obj.title_localized()}"
            facts.claims_text += f" {obj.title_localized()}"


# --- бизнес -------------------------------------------------------------------------------


def _business_facts(tenant, facts: Facts) -> None:
    # Час, а не минуты: строка входит в digest кэша черновика (1 ч), минуты
    # делали бы каждый повтор промахом.
    now = timezone.localtime()
    facts.lines.append(f"Business: {_one_line(getattr(tenant, 'name', ''))}")
    facts.name_text += f" {getattr(tenant, 'name', '')}"
    address = ", ".join(
        p.strip() for p in str(getattr(tenant, "address", "") or "").splitlines() if p.strip()
    )
    if address:
        facts.lines.append(f"- Address: {_one_line(address)}")
    if getattr(tenant, "city", ""):
        facts.lines.append(f"- City: {tenant.city}")
    hours = ""
    try:
        hours = tenant.opening_hours_localized(None)
    except Exception:  # noqa: BLE001 — часы необязательны
        hours = ""
    hours = "; ".join(p.strip() for p in str(hours or "").splitlines() if p.strip())
    if hours:
        facts.lines.append(f"- Opening hours: {_one_line(hours, 400)}")
    facts.context.append(
        f"- Today: {WEEKDAYS_LONG[now.weekday()]} {now:%d.%m.}, year {now:%Y}, "
        f"current hour {now:%H}"
    )


def _deal_link_trusted(conversation) -> bool:
    """Привязку треда к сделке поставил НЕ клиент: тред начат владельцем (C1),
    системой (C2/предложение) или сервисом сделки. Публичная форма принимает
    ref и e-mail без проверки владения адресом (Customer ищется по e-mail) —
    тред, начатый клиентом с ref на сделку, мог открыть кто угодно, знающий
    чужой e-mail и код (ревью T-8.10g). Такому треду факты сделки не даём."""
    first = conversation.messages.order_by("created_at").values_list("author_role", flat=True)
    return first.first() not in (None, "customer")


def facts_for(conversation, tenant) -> Facts:
    """Факты треда: сделка/сущность по ref (если применимо) + данные бизнеса.
    Подписи — на базовом языке: факты одинаковы при любом языке кабинета."""
    from django.conf import settings
    from django.utils import translation

    with translation.override(settings.LANGUAGE_CODE):
        return _facts_for(conversation, tenant)


def _facts_for(conversation, tenant) -> Facts:
    facts = Facts()
    kind = (conversation.ref_kind or "").strip()
    ref_id = (conversation.ref_id or "").strip()
    base = ""
    if kind == "product":
        from apps.promotions.notifications import _base_url

        base = _base_url(getattr(tenant, "schema_name", ""))
    if kind and ref_id:
        deal = _find_deal(kind, ref_id) if kind in DEAL_KINDS else None
        if deal is not None:
            customer_id = conversation.customer_id
            if (
                customer_id
                and getattr(deal, "customer_id", None) == customer_id
                and _deal_link_trusted(conversation)
            ):
                _deal_facts(kind, deal, facts)
        elif kind in ("product", "event", "stay", "tour"):
            _entity_facts(kind, ref_id, facts, base)
    _business_facts(tenant, facts)
    return facts
