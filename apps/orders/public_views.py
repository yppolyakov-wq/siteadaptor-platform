"""Витрина Click & Collect (Track D / D2a): корзина-сессия + оформление самовывоза.

Корзина — dict {product_id: qty} в сессии (без аккаунта, как бронь акций).
Защита формы — как у брони: honeypot (website) + rate-limit по IP
(apps.core.ratelimit). Если модуль orders у бизнеса выключен — всех страниц
просто нет (404), кнопка на витрине тоже скрыта.
"""

import stripe
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.billing import connect
from apps.core import ratelimit

from . import payments as order_payments
from .models import Order
from .services import EmptyOrder, OutOfStock, create_order, delivery_quote

CART_SESSION_KEY = "cart"
RL_LIMIT = 5  # оформлений на IP
RL_WINDOW = 600  # за 10 минут
MAX_QTY = 50  # на позицию — защита от мусора


def _require_orders_active(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or not tenant.is_module_active("orders"):
        raise Http404


def _cart(request) -> dict:
    cart = request.session.get(CART_SESSION_KEY)
    return cart if isinstance(cart, dict) else {}


def _split_key(key):
    """Ключ корзины «pid:vid:o1-o2» → (pid, vid, [option_ids]).

    Сегменты опциональны (обратная совместимость): «pid», «pid:vid», «pid:vid:».
    """
    parts = key.split(":")
    pid = parts[0]
    vid = parts[1] if len(parts) > 1 else ""
    # Разделитель опций — запятая (НЕ дефис: UUID содержит дефисы).
    opt_ids = parts[2].split(",") if len(parts) > 2 and parts[2] else []
    return pid, vid, opt_ids


def _cart_key(product, variant, options) -> str:
    """«pid:vid» или «pid:vid:o1-o2» — разные наборы Extras = разные позиции.

    Без опций третий сегмент не добавляем (совместимость со старыми ключами).
    """
    base = f"{product.pk}:{variant.pk if variant else ''}"
    if not options:
        return base
    return base + ":" + ",".join(sorted(str(o.pk) for o in options))


def _cart_items(request):
    """[(product, variant|None, [options], qty), …]; мёртвые позиции отбрасываем.

    Ключ корзины — «pid:vid:o1-o2» (vid пустой = без варианта; третий сегмент —
    выбранные опции модификаторов, A4b). Старые ключи «pid»/«pid:vid» читаются.
    """
    from apps.catalog.models import Product, ProductVariant
    from apps.catalog.modifiers import options_from_ids

    cart = _cart(request)
    parsed = [(*_split_key(key), qty) for key, qty in cart.items()]
    products = {
        str(p.pk): p
        for p in Product.objects.filter(
            pk__in={pid for pid, _v, _o, _q in parsed}, is_active=True
        ).prefetch_related("modifier_groups__options")
    }
    variant_ids = {vid for _p, vid, _o, _q in parsed if vid}
    variants = {
        str(v.pk): v for v in ProductVariant.objects.filter(pk__in=variant_ids, is_active=True)
    }
    items = []
    for pid, vid, opt_ids, qty in parsed:
        product = products.get(pid)
        if product is None:
            continue
        variant = variants.get(vid) if vid else None
        if vid and (variant is None or variant.product_id != product.pk):
            continue  # вариант исчез/чужой — позицию отбрасываем
        options = options_from_ids(product, opt_ids) if opt_ids else []
        items.append((product, variant, options, qty))
    return items


def _line_price(product, variant, options=()):
    from apps.catalog.modifiers import options_delta

    base = variant.price_value if variant is not None else product.base_price
    return base + options_delta(options)


# --- Комбо-наборы (A4) в корзине -------------------------------------------------

COMBO_SESSION_KEY = "combo_cart"


def _combo_cart(request) -> dict:
    cc = request.session.get(COMBO_SESSION_KEY)
    return cc if isinstance(cc, dict) else {}


def _combo_key(combo, options) -> str:
    """«comboid» или «comboid|o1,o2» — разные наборы опций = разные позиции."""
    base = str(combo.pk)
    if not options:
        return base
    return base + "|" + ",".join(sorted(str(o.pk) for o in options))


def _split_combo_key(key):
    parts = key.split("|")
    opt_ids = parts[1].split(",") if len(parts) > 1 and parts[1] else []
    return parts[0], opt_ids


def _combo_items(request):
    """[(combo, [options], qty)] из сессии; мёртвые/невалидные ключи отбрасываем."""
    from apps.catalog.combos import get_active, options_from_ids

    out = []
    for key, qty in _combo_cart(request).items():
        cid, opt_ids = _split_combo_key(key)
        try:
            combo = get_active(cid)
        except (ValueError, ValidationError):
            combo = None
        if combo is None:
            continue
        out.append((combo, options_from_ids(combo, opt_ids), qty))
    return out


def quick_add_form(request, pk):
    """T2c: фрагмент модалки быстрого заказа (размер+ингредиенты) для карточки.

    Загружается vanilla-fetch'ем по клику «+» на карточке; форма постит в
    cart_add (как со страницы товара). Гейтинг модуля orders — 404 иначе.
    """
    _require_orders_active(request)
    from apps.catalog.models import Product

    product = get_object_or_404(
        Product.objects.prefetch_related("modifier_groups__options", "variants"),
        pk=pk,
        is_active=True,
    )
    return render(request, "storefront/_quick_add.html", {"product": product})


def combo_list_public(request):
    """Витрина комбо-наборов (A4): /kombi/. Гейтинг orders → 404."""
    _require_orders_active(request)
    from apps.catalog.combos import active_combos

    return render(request, "storefront/combos.html", {"combos": active_combos()})


def combo_detail_public(request, pk):
    """Конфигуратор набора (выбор напитка/гарнира) → POST в combo_add."""
    _require_orders_active(request)
    from apps.catalog.combos import get_active

    combo = get_active(pk)
    if combo is None:
        raise Http404
    return render(request, "storefront/combo_detail.html", {"combo": combo})


@require_POST
def combo_add(request):
    _require_orders_active(request)
    from apps.catalog.combos import get_active, validate_selection

    combo = get_active(request.POST.get("combo"))
    if combo is None:
        raise Http404
    options, error = validate_selection(combo, request.POST.getlist("opt"))
    if error:
        messages.error(request, error)
        return redirect("storefront-combo", pk=combo.pk)
    try:
        qty = max(1, min(int(request.POST.get("qty", "1")), MAX_QTY))
    except (TypeError, ValueError):
        qty = 1
    key = _combo_key(combo, options)
    cc = _combo_cart(request)
    cc[key] = min(cc.get(key, 0) + qty, MAX_QTY)
    request.session[COMBO_SESSION_KEY] = cc
    messages.success(request, _("Added to your order."))
    return redirect("storefront-cart")


@require_POST
def combo_remove(request):
    _require_orders_active(request)
    cc = _combo_cart(request)
    cc.pop(request.POST.get("item", ""), None)
    request.session[COMBO_SESSION_KEY] = cc
    return redirect("storefront-cart")


PROMO_SESSION_KEY = "promo_code"


@require_POST
def cart_apply_code(request):
    """A4: применить промокод (Voucher со скидкой) к корзине — в сессию."""
    _require_orders_active(request)
    from apps.promotions.models import Voucher

    code = (request.POST.get("code") or "").strip().upper()[:12]
    voucher = Voucher.objects.filter(code=code).first() if code else None
    if voucher is None or not voucher.has_order_discount or not voucher.is_redeemable:
        request.session.pop(PROMO_SESSION_KEY, None)
        messages.error(request, _("This code is invalid or expired."))
    else:
        request.session[PROMO_SESSION_KEY] = code
        messages.success(request, _("Code applied."))
    return redirect("storefront-cart")


@require_POST
def cart_remove_code(request):
    _require_orders_active(request)
    request.session.pop(PROMO_SESSION_KEY, None)
    return redirect("storefront-cart")


def _cart_discount(request, subtotal):
    """(voucher, скидка Decimal) для применённого промокода на subtotal (Decimal)."""
    from decimal import Decimal

    from apps.promotions.models import Voucher

    code = request.session.get(PROMO_SESSION_KEY, "")
    if not code:
        return None, Decimal("0")
    voucher = Voucher.objects.filter(code=code).first()
    if voucher is None or not voucher.has_order_discount:
        return None, Decimal("0")
    return voucher, Decimal(voucher.discount_for(int(subtotal * 100))) / 100


@require_POST
def reorder(request, code):
    """CA4: «Nochmal bestellen» — товарные позиции заказа обратно в корзину.

    Восстанавливаем product+variant по снимку (модификаторы/комбо v1 не
    переносим — у снимка нет id опций; клиент донастроит). Заказ ищем по коду.
    """
    _require_orders_active(request)
    order = get_object_or_404(Order.objects.prefetch_related("items"), reference_code=code)
    cart = _cart(request)
    added = 0
    for item in order.items.all():
        if item.product_id is None:  # комбо-позиция — пропускаем
            continue
        key = f"{item.product_id}:{item.variant_id or ''}"
        cart[key] = min(cart.get(key, 0) + item.qty, MAX_QTY)
        added += 1
    request.session[CART_SESSION_KEY] = cart
    if added:
        messages.success(request, _("Added to your order."))
    return redirect("storefront-cart")


def _is_ajax(request) -> bool:
    return request.headers.get("X-Requested-With") == "fetch"


def _cart_total_count(request) -> int:
    total = 0
    for key in (CART_SESSION_KEY, COMBO_SESSION_KEY):
        d = request.session.get(key)
        if isinstance(d, dict):
            total += sum(v for v in d.values() if isinstance(v, int))
    return total


def _added_response(request):
    """R1: AJAX → JSON со счётчиком (без перехода); иначе — редирект в корзину."""
    if _is_ajax(request):
        from django.http import JsonResponse

        return JsonResponse({"ok": True, "count": _cart_total_count(request)})
    messages.success(request, _("Added to your order."))
    return redirect("storefront-cart")


def _add_error(request, msg, *, product_pk=None, fallback="storefront-cart"):
    if _is_ajax(request):
        from django.http import JsonResponse

        return JsonResponse({"ok": False, "error": str(msg)}, status=400)
    messages.error(request, msg)
    if product_pk is not None:
        return redirect("storefront-product", pk=product_pk)
    return redirect(fallback)


@require_POST
def cart_add(request):
    _require_orders_active(request)

    from apps.catalog.models import Product, ProductVariant

    product = get_object_or_404(Product, pk=request.POST.get("product"), is_active=True)
    variant = None
    if product.has_variants:
        vid = (request.POST.get("variant") or "").strip()
        try:
            variant = (
                ProductVariant.objects.filter(pk=vid, product=product, is_active=True).first()
                if vid
                else None
            )
        except (ValidationError, ValueError):
            variant = None
        if variant is None:
            return _add_error(request, _("Please choose an option."), product_pk=product.pk)
    # Модификаторы/Extras (A4b): валидируем выбор по правилам групп на сервере.
    options = []
    if product.has_modifiers:
        from apps.catalog.modifiers import validate_selection

        options, error = validate_selection(product, request.POST.getlist("mod"))
        if error:
            return _add_error(request, error, product_pk=product.pk)
    try:
        qty = max(1, min(int(request.POST.get("qty", "1")), MAX_QTY))
    except (TypeError, ValueError):
        qty = 1
    key = _cart_key(product, variant, options)
    cart = _cart(request)
    cart[key] = min(cart.get(key, 0) + qty, MAX_QTY)
    request.session[CART_SESSION_KEY] = cart
    return _added_response(request)


@require_POST
def cart_remove(request):
    _require_orders_active(request)
    cart = _cart(request)
    cart.pop(request.POST.get("item", ""), None)
    request.session[CART_SESSION_KEY] = cart
    return redirect("storefront-cart")


def cart_view(request):
    _require_orders_active(request)
    from decimal import Decimal

    items = _cart_items(request)
    rows = [
        {
            "product": product,
            "variant": variant,
            "options": options,
            "qty": qty,
            "key": _cart_key(product, variant, options),
            "unit_price": _line_price(product, variant, options),
            "line_total": _line_price(product, variant, options) * qty,
        }
        for product, variant, options, qty in items
    ]
    # Комбо-наборы (A4): отдельные строки корзины со снимком состава.
    from apps.catalog.combos import combo_price

    combo_rows = [
        {
            "combo": combo,
            "options": options,
            "qty": qty,
            "key": _combo_key(combo, options),
            "unit_price": combo_price(combo, options),
            "line_total": combo_price(combo, options) * qty,
        }
        for combo, options, qty in _combo_items(request)
    ]
    total = sum((r["line_total"] for r in rows + combo_rows), start=Decimal("0"))
    tenant = getattr(request, "tenant", None)
    delivery_enabled = getattr(tenant, "delivery_enabled", False)
    currency = (
        items[0][0].currency
        if items
        else (combo_rows[0]["combo"].currency if combo_rows else "EUR")
    )
    # A4 промокод: скидка на subtotal (товары+комбо), итог к оплате.
    voucher, discount = _cart_discount(request, total)
    ctx = {
        "rows": rows,
        "combo_rows": combo_rows,
        "total": total,
        "discount": discount,
        "grand_total": total - discount,
        "promo_code": request.session.get(PROMO_SESSION_KEY, ""),
        "promo_min_not_met": bool(voucher and discount == 0 and voucher.min_order_cents),
        "currency": currency,
    }
    # T1 upsell «Passt dazu»: товары не из корзины, рекомендованные вперёд.
    if rows:
        from apps.catalog.models import Product

        in_cart_ids = {r["product"].pk for r in rows}
        ctx["upsell"] = list(
            Product.objects.filter(is_active=True)
            .exclude(pk__in=in_cart_ids)
            .order_by("-is_featured", "-created_at")[:4]
        )
    if delivery_enabled:
        ctx["delivery_enabled"] = True
        ctx["delivery_fee_eur"] = f"{getattr(tenant, 'delivery_fee_cents', 0) / 100:.2f}"
        ctx["delivery_free_eur"] = f"{getattr(tenant, 'delivery_free_cents', 0) / 100:.2f}"
        ctx["delivery_free_cents"] = getattr(tenant, "delivery_free_cents", 0)
        ctx["delivery_min_eur"] = f"{getattr(tenant, 'delivery_min_cents', 0) / 100:.2f}"
        ctx["delivery_min_cents"] = getattr(tenant, "delivery_min_cents", 0)
        ctx["delivery_area"] = getattr(tenant, "delivery_area", "")
    return render(request, "storefront/cart.html", ctx)


@require_POST
def checkout(request):
    _require_orders_active(request)
    if request.POST.get("website"):  # honeypot
        return redirect("storefront-cart")
    # hit() == True → лимит превышен (см. apps.core.ratelimit)
    if ratelimit.hit("order", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
        return HttpResponse(status=429)

    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, _("Please tell us your name."))
        return redirect("storefront-cart")

    # G4/A2a: способ получения. delivery только если бизнес включил доставку.
    tenant = getattr(request, "tenant", None)
    from decimal import Decimal

    items = _cart_items(request)
    from apps.catalog.combos import combo_price

    combo_items = _combo_items(request)
    subtotal = sum((_line_price(p, v, o) * q for p, v, o, q in items), Decimal("0"))
    subtotal += sum((combo_price(c, o) * q for c, o, q in combo_items), Decimal("0"))
    subtotal_cents = int(subtotal * 100)
    delivery = request.POST.get("fulfillment") == "delivery" and getattr(
        tenant, "delivery_enabled", False
    )
    shipping_cents = 0
    shipping_address = ""
    if delivery:
        street = request.POST.get("street", "").strip()
        plz = request.POST.get("plz", "").strip()
        city = request.POST.get("city", "").strip()
        if not (street and plz and city):
            messages.error(request, _("Please enter your full delivery address."))
            return redirect("storefront-cart")
        quote = delivery_quote(tenant, subtotal_cents, plz)
        if not quote["deliverable"]:
            messages.error(
                request,
                _("Sorry, we don't deliver to postal code %(plz)s.") % {"plz": plz},
            )
            return redirect("storefront-cart")
        if quote["min_cents"] and subtotal_cents < quote["min_cents"]:
            messages.error(
                request,
                _("Minimum order for delivery is %(min)s €.")
                % {"min": f"{quote['min_cents'] / 100:.2f}".replace(".", ",")},
            )
            return redirect("storefront-cart")
        shipping_cents = quote["fee_cents"]
        shipping_address = f"{street}\n{plz} {city}"
    else:
        pickup_min = getattr(tenant, "pickup_min_cents", 0) or 0
        if pickup_min and subtotal_cents < pickup_min:
            messages.error(
                request,
                _("Minimum order for pickup is %(min)s €.")
                % {"min": f"{pickup_min / 100:.2f}".replace(".", ",")},
            )
            return redirect("storefront-cart")

    # _cart_items даёт (product, variant, options, qty); create_order ждёт
    # (product, variant, qty, options) — переставляем.
    order_items = [(p, v, q, o) for p, v, o, q in _cart_items(request)]
    order_combos = [(c, o, q) for c, o, q in combo_items]
    try:
        order = create_order(
            items=order_items,
            combos=order_combos,
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            note=request.POST.get("note", "").strip()[:2000],
            table_number="" if delivery else request.session.get("table", ""),
            source_channel=(request.GET.get("ch") or "")[:50],
            fulfillment=Order.FULFILLMENT_DELIVERY if delivery else Order.FULFILLMENT_PICKUP,
            shipping_address=shipping_address,
            shipping_cents=shipping_cents,
            voucher_code=request.session.get(PROMO_SESSION_KEY, ""),
        )
    except EmptyOrder:
        messages.error(request, _("Your order is empty."))
        return redirect("storefront-cart")
    except OutOfStock as exc:
        messages.error(
            request,
            _("Sorry, “%(item)s” is no longer available in this quantity.") % {"item": exc.title},
        )
        return redirect("storefront-cart")
    request.session[CART_SESSION_KEY] = {}
    request.session[COMBO_SESSION_KEY] = {}
    request.session.pop(PROMO_SESSION_KEY, None)

    # Онлайн-предоплата (P2.5c): если включена у бизнеса и оплата подключена — на
    # Stripe Checkout (на счёт бизнеса). Иначе — оплата при получении (как раньше).
    tenant = getattr(request, "tenant", None)
    if (
        getattr(tenant, "orders_prepay", False)
        and getattr(tenant, "payments_enabled", False)
        and connect.is_connect_configured()
        and order.total > 0
    ):
        order_url = request.build_absolute_uri(
            reverse("storefront-order", args=[order.reference_code])
        )
        try:
            return redirect(
                order_payments.order_checkout_url(
                    order, tenant, success_url=order_url + "?paid=1", cancel_url=order_url
                )
            )
        except stripe.error.StripeError:
            pass  # оплата временно недоступна — заказ остаётся (оплата при получении)
    return redirect("storefront-order", code=order.reference_code)


def order_confirmation(request, code):
    _require_orders_active(request)
    order = get_object_or_404(Order, reference_code=code)
    from apps.telegram.notify import deep_link

    return render(
        request,
        "storefront/order_confirmation.html",
        {
            "order": order,
            "just_paid": request.GET.get("paid") == "1",
            # TG3: кнопка привязки к Telegram-боту (пусто, если бот не настроен).
            "telegram_link": deep_link(order.customer),
        },
    )
