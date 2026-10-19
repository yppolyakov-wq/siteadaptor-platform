"""T-8.10f F-4: подтверждение действия, начатого в ассистенте (план
docs/t8-10f-f4-plan-2026-10-19.md, Д-2…Д-8).

Ссылка из письма ведёт сюда, на поддомен бизнеса: GET только показывает, что будет
сделано (почтовые сканеры открывают ссылки сами), POST выполняет — теми же сервисами,
что кнопки на витрине (`reserve`, `issue_coupon`). Повторный клик показывает тот же
итог, а не второе действие.
"""

from __future__ import annotations

import logging

from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import translation
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from apps.aggregator.mcp import actions

from .models import Promotion

logger = logging.getLogger(__name__)

TEMPLATE = "storefront/assistant_confirm.html"
#: Запросов к странице подтверждения с одного адреса за 10 минут (перебор токенов).
RATE_LIMIT = 30


def _headers(response):
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


def _language(payload, tenant) -> str:
    lang = (payload or {}).get("lang") or ""
    try:
        allowed = list(tenant.active_locales)
    except Exception:  # noqa: BLE001 — стаб тенанта без локалей
        allowed = []
    return lang if lang in allowed else ""


def _mask(email: str) -> str:
    name, _at, domain = (email or "").partition("@")
    if not domain:
        return ""
    return f"{name[:1]}***@{domain}"


def _page(request, ctx, *, status=200):
    return _headers(render(request, TEMPLATE, ctx, status=status))


def _result_redirect(done: dict):
    if done.get("result") == "reserved" and done.get("code"):
        return _headers(redirect("storefront-confirmation", code=done["code"]))
    if done.get("result") == "coupon" and done.get("code"):
        return _headers(redirect("storefront-coupon", code=done["code"]))
    return None


@never_cache
@require_http_methods(["GET", "POST"])
def assistant_confirm(request, pk, token):
    from apps.core import ratelimit

    tenant = getattr(request, "tenant", None)
    if tenant is None:
        raise Http404
    if ratelimit.hit("mcp-confirm", ratelimit.client_ip(request), limit=RATE_LIMIT, window=600):
        return _page(request, {"state": "busy"}, status=429)
    done = actions.outcome(token)
    if done is not None:
        if done.get("schema") != tenant.schema_name or done.get("promo_id") != str(pk):
            raise Http404
        found = _result_redirect(done)
        if found is not None:
            return found
        with translation.override(done.get("lang") or translation.get_language()):
            return _page(request, {"state": done.get("result") or "invalid"})
    payload = actions.load_pending(token)
    if payload is None:
        return _page(request, {"state": "invalid"}, status=410)
    if payload.get("schema") != tenant.schema_name or payload.get("promo_id") != str(pk):
        raise Http404
    lang = _language(payload, tenant)
    with translation.override(lang or translation.get_language()):
        if request.method == "POST":
            return _confirm(request, tenant, pk, token, payload, lang)
        promo = Promotion.objects.filter(pk=pk).first()
        if not _usable(promo, payload["op"], tenant):
            # GET ничего не тратит: ссылку не гасим, просто честно говорим
            return _page(request, {"state": "unavailable"})
        return _page(
            request,
            {
                "state": "ask",
                "op": payload["op"],
                "promotion": promo,
                "qty": payload.get("qty") or 1,
                "email_masked": _mask(payload.get("email", "")),
                "is_demo": bool(getattr(tenant, "is_demo", False)),
            },
        )


def _usable(promo, op, tenant) -> bool:
    from django.utils import timezone

    from apps.aggregator import visibility

    from . import response

    return bool(
        promo is not None
        and promo.status == "active"
        and (promo.ends_at is None or promo.ends_at > timezone.now())
        and promo.target_kind not in ("service", "stay")
        and response.response_for(promo, tenant) == op
        and visibility.listable(tenant)
    )


def _recover(promo, payload) -> dict | None:
    """Итог потерян (сбой кэша в `finish`), а запись в БД есть — найти её, а не делать
    вторую. Ищем только среди сделок этого адреса по этой акции через ассистента."""
    from apps.loyalty.models import Voucher

    from .models import Reservation

    if promo is None:
        return None
    email = payload.get("email") or ""
    if payload["op"] == actions.OP_RESERVE:
        res = (
            Reservation.objects.filter(
                promotion=promo, source_channel="mcp", customer__email__iexact=email
            )
            .order_by("-created_at")
            .first()
        )
        return {"result": "reserved", "code": res.reference_code} if res else None
    voucher = Voucher.objects.filter(promotion=promo, customer__email__iexact=email).first()
    return {"result": "coupon", "code": voucher.code} if voucher else None


def _confirm(request, tenant, pk, token, payload, lang=""):
    base = {"schema": tenant.schema_name, "promo_id": str(pk), "lang": lang}
    promo = Promotion.objects.filter(pk=pk).first()
    if not actions.claim(token):
        # двойной клик: итог уже есть — тот же итог; запись в БД есть — она же;
        # иначе честное «läuft gerade»
        found = _result_redirect(actions.outcome(token) or {})
        if found is not None:
            return found
        recovered = _recover(promo, payload)
        if recovered is not None:
            actions.finish(token, {**base, **recovered})
            return _result_redirect(recovered)
        return _page(request, {"state": "busy"}, status=409)
    op = payload["op"]
    if not _usable(promo, op, tenant):
        actions.finish(token, {**base, "result": "unavailable"})
        return _page(request, {"state": "unavailable"})
    try:
        if op == actions.OP_RESERVE:
            return _do_reserve(request, tenant, promo, token, payload, base)
        return _do_coupon(request, tenant, promo, token, payload, base)
    except Exception:
        # `reserve` атомарен (письма — внутри его транзакции), купон идемпотентен по
        # адресу: после сбоя записи нет или повтор её найдёт — можно нажать ещё раз
        actions.release(token)
        raise


def _attribution(payload):
    from apps.core.attribution import Attribution

    return Attribution("mcp", payload.get("listing_id"))


def _do_reserve(request, tenant, promo, token, payload, base):
    from apps.aggregator import conversions
    from apps.notifications.prefs import muted

    from .services import OutOfStock, ReservationLimitReached, reserve

    try:
        # решение владельца (R1): владельцу ДЕМО-бизнеса письмо о сделке из ассистента
        # не уходит — адреса демо-владельцев не наши.
        with muted(owner=bool(getattr(tenant, "is_demo", False))):
            res = reserve(
                promo,
                name=payload.get("name") or payload["email"],
                email=payload["email"],
                phone="",
                quantity=int(payload.get("qty") or 1),
                source_channel="mcp",
            )
    except OutOfStock:
        actions.finish(token, {**base, "result": "sold_out"})
        return _page(request, {"state": "sold_out"})
    except ReservationLimitReached:
        actions.finish(token, {**base, "result": "limit"})
        return _page(request, {"state": "limit"})
    actions.finish(token, {**base, "result": "reserved", "code": res.reference_code})
    conversions.count(request, "deal", "reservation", res, attribution=_attribution(payload))
    return _headers(redirect("storefront-confirmation", code=res.reference_code))


def _do_coupon(request, tenant, promo, token, payload, base):
    from apps.aggregator import conversions

    from .public_views import _remember_coupon
    from .services import CouponUnavailable, issue_coupon

    try:
        voucher, created = issue_coupon(
            promo,
            name=payload.get("name") or "",
            email=payload["email"],
            source_channel="mcp",
        )
    except CouponUnavailable:
        actions.finish(token, {**base, "result": "sold_out"})
        return _page(request, {"state": "sold_out"})
    actions.finish(token, {**base, "result": "coupon", "code": voucher.code})
    if created:
        conversions.count(request, "deal", "coupon", voucher, attribution=_attribution(payload))
    try:
        _send_coupon_email(voucher, promo, payload["email"], _language(payload, tenant))
    except Exception as exc:  # noqa: BLE001 — купон уже выдан; письмо не смеет ронять ответ
        logger.warning("mcp coupon mail failed: %s", type(exc).__name__)
    return _headers(
        _remember_coupon(
            redirect("storefront-coupon", code=voucher.code), request, promo, voucher.code
        )
    )


def _send_coupon_email(voucher, promo, email, lang=""):
    """Д-8: купон нужен на кассе, а ссылку человек мог открыть на другом устройстве."""
    from django.db import connection
    from django.urls import reverse

    from apps.notifications.services import notify

    from .notifications import _base_url, _render

    base = _base_url(connection.schema_name)
    url = f"{base}{reverse('storefront-coupon', args=[voucher.code])}" if base else ""
    subject, body, html = _render(
        "coupon_issued",
        {"coupon": voucher, "promotion": promo, "coupon_url": url},
        locale=lang or None,
    )
    notify(
        dedupe_key=f"coupon:{voucher.pk}:mcp:customer",
        type="coupon_issued",
        recipient=email,
        subject=" ".join(subject.split()),  # заголовок без переводов строк
        body=body,
        html=html,
    )
