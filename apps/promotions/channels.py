"""T-8.6: каналы привлечения акции — просмотры и воронка «канал → действие».

План — docs/t8-6-catalog-hygiene-plan-2026-10-10.md §1. Канал приходит из `?ch=`
(портал, флаер, витрина, QR в соцсетях) и живёт в сессии витрины (`_capture_channel`);
он же пишется в резерв (`Reservation.source_channel`) и купон (`Voucher.source_channel`).
"""

from __future__ import annotations

import re

from django.db import IntegrityError, transaction
from django.db.models import Count, F

DIRECT = "direkt"
_CLEAN = re.compile(r"[^a-z0-9_-]+")


def normalize(raw) -> str:
    """«Instagram Story» → instagram-story; пусто → «direkt» (≤30 символов)."""
    value = _CLEAN.sub("-", str(raw or "").strip().lower()).strip("-")[:30].strip("-")
    return value or DIRECT


def count_view(promotion, raw_channel) -> None:
    """Атомарно +1 просмотр по каналу (пара создаётся при первом просмотре)."""
    from .models import PromotionChannelView

    channel = normalize(raw_channel)
    rows = PromotionChannelView.objects.filter(promotion=promotion, channel=channel)
    if rows.update(views=F("views") + 1):
        return
    try:
        with transaction.atomic():
            PromotionChannelView.objects.create(promotion=promotion, channel=channel, views=1)
    except IntegrityError:  # параллельный первый просмотр создал строку раньше
        rows.update(views=F("views") + 1)


def funnel(promotion) -> list[dict]:
    """Строки «канал → просмотры → отложено → выдано → купоны → погашено».

    Порядок — по просмотрам, затем по действиям; каналы без единого события не
    показываются. Сырые значения резервов нормализуются тем же правилом.
    """
    from apps.loyalty.models import Voucher

    from .models import PromotionChannelView, Reservation

    rows: dict[str, dict] = {}

    def row(ch):
        return rows.setdefault(
            ch,
            {"channel": ch, "views": 0, "reserved": 0, "handed": 0, "coupons": 0, "redeemed": 0},
        )

    for v in PromotionChannelView.objects.filter(promotion=promotion):
        row(normalize(v.channel))["views"] += v.views
    for r in (
        Reservation.objects.filter(promotion=promotion)
        .values("source_channel", "status")
        .annotate(n=Count("id"))
    ):
        target = row(normalize(r["source_channel"]))
        target["reserved"] += r["n"]
        if r["status"] == "fulfilled":
            target["handed"] += r["n"]
    for c in Voucher.objects.filter(promotion=promotion).values("source_channel", "used_count"):
        target = row(normalize(c["source_channel"]))
        target["coupons"] += 1
        if c["used_count"]:
            target["redeemed"] += 1
    return sorted(
        rows.values(),
        key=lambda r: (-r["views"], -(r["reserved"] + r["coupons"]), r["channel"]),
    )
