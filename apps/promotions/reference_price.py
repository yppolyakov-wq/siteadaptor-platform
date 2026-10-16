"""SF-7 (§11 PAngV): цена сравнения у акции — от низшей цены 30 дней ДО её старта.

EuGH C-330/23 «Aldi Süd» (26.09.2024) и BGH I ZR 183/24 (09.10.2025): при объявлении
снижения цены товара и зачёркнутая цена, и процент («−30 %») считаются от низшей цены,
которую продавец применял в последние 30 дней ПЕРЕД снижением. Раньше процент шёл от
`compare_at_price`/текущей цены товара, а 30-дневный минимум только печатался рядом —
«Mondpreis» (поднял цену перед акцией) и повтор недельной акции подряд давали
незаконное «−X %», которое каталог города разносил на портал, фид и ИИ.

Что входит в минимум (`prior_low`):
* `PriceLog` базовой цены товара в окне [старт − 30 дн, старт) + цена, действовавшая
  на начало окна (семантика `catalog.price_history.lowest_price_30d`, но окно
  привязано к старту АКЦИИ, а не к «сейчас» — иначе своя же акция сдвигала бы окно);
* цены прошлых акций на ТОТ ЖЕ товар/набор, действовавших в окне — наш `PriceLog`
  промо-цены не пишет, а для потребителя это тоже «применённая цена».

Только товары и наборы (§11 PAngV — Waren). Услуги/номера/свободные акции → `None`,
прежнее поведение. Цена прошлой акции — её `new_price` по ТЕКУЩИМ данным (у
`price_override` — точная; у процентной от изменившейся базы — приближение).

Батч: `attach(promos)` — один запрос `PriceLog` + один запрос акций на всю страницу.
"""

from collections import defaultdict
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

WINDOW_DAYS = 30
# Черновик и запланированная никогда не были видны покупателю — их цена
# «применённой» не считается. Мягко удалённые — считаются (`all_objects`):
# удаление прошлой дешёвой акции не должно поднимать цену сравнения.
_NEVER_LIVE = ("draft", "scheduled")


def start_of(promo):
    """Момент снижения: старт акции, иначе создание, иначе сейчас."""
    return promo.starts_at or promo.created_at or timezone.now()


def _is_goods(promo) -> bool:
    return bool(promo.product_id or promo.combo_id)


def exemption_enabled() -> bool:
    """SF-8b: выключатель исключения § 11 Abs. 4 (settings/env, default True)."""
    from django.conf import settings

    return bool(getattr(settings, "PANGV_PERISHABLE_EXEMPTION", True))


def is_perishable(promo) -> bool:
    """Флаг владельца «schnell verderblich / kurze Haltbarkeit» (metadata, без миграции)
    — действует только при включённом исключении."""
    meta = promo.metadata if isinstance(getattr(promo, "metadata", None), dict) else {}
    # Только Waren (товар/набор): у услуги/номера/свободной акции флаг инертен — иначе
    # подпись «wegen kurzer Haltbarkeit» была бы ложным публичным заявлением (UWG).
    return bool(meta.get("perishable")) and _is_goods(promo) and exemption_enabled()


def attach(promos) -> list:
    """Проставить `_prior_low` (Decimal | None) всем акциям списка; вернуть список."""
    from apps.catalog.models import PriceLog

    from .models import Promotion

    promos = [p for p in promos if p is not None]
    todo = [p for p in promos if not hasattr(p, "_prior_low")]
    goods = []
    for p in todo:
        # SF-8b: § 11 Abs. 4 — у скоропортящегося минимум не считается вовсе
        # (цена сравнения = обычная цена, как у услуг).
        if _is_goods(p) and not is_perishable(p):
            goods.append(p)
        else:
            p._prior_low = None
    if not goods:
        return promos

    starts = {id(p): start_of(p) for p in goods}
    lo = min(starts.values()) - timedelta(days=WINDOW_DAYS)
    hi = max(starts.values())
    product_ids = {p.product_id for p in goods if p.product_id}
    combo_ids = {p.combo_id for p in goods if p.combo_id}

    # 1) История базовой цены: окно [lo, hi) целиком + последняя запись до lo.
    logs = defaultdict(list)
    before = {}
    if product_ids:
        base = PriceLog.objects.filter(product_id__in=product_ids, variant__isnull=True)
        for pid, at, price in (
            base.filter(created_at__gte=lo, created_at__lt=hi)
            .order_by("created_at")
            .values_list("product_id", "created_at", "price")
        ):
            logs[pid].append((at, price))
        for pid, price in (
            base.filter(created_at__lt=lo)
            .order_by("product_id", "-created_at")
            .distinct("product_id")
            .values_list("product_id", "price")
        ):
            before[pid] = price

    # 2) Прошлые акции на те же товары/наборы, пересекающие общее окно.
    target_q = Q()
    if product_ids:
        target_q |= Q(product_id__in=product_ids)
    if combo_ids:
        target_q |= Q(combo_id__in=combo_ids)
    others = list(
        Promotion.all_objects.filter(target_q)
        .exclude(status__in=_NEVER_LIVE)
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=lo))
        .select_related("product", "combo")
    )

    for p in goods:
        start = starts[id(p)]
        since = start - timedelta(days=WINDOW_DAYS)
        cands = []
        if p.product_id:
            series = logs.get(p.product_id, [])
            cands += [price for at, price in series if since <= at < start]
            at_since = None
            for at, price in series:
                if at < since:
                    at_since = price
            if at_since is None:
                at_since = before.get(p.product_id)
            if at_since is not None:
                cands.append(at_since)
        for o in others:
            if o.pk == p.pk:
                continue
            same = (p.product_id and o.product_id == p.product_id) or (
                p.combo_id and o.combo_id == p.combo_id
            )
            if not same or not (start_of(o) < start):
                continue
            if o.ends_at is not None and o.ends_at <= since:
                continue
            price = o.new_price
            if price is not None:
                cands.append(price)
        p._prior_low = min(cands) if cands else None
    return promos


def prior_low(promo):
    """Низшая цена 30 дней до старта акции (Decimal | None) — с кэшем на объекте."""
    if not hasattr(promo, "_prior_low"):
        attach([promo])
    return promo._prior_low
