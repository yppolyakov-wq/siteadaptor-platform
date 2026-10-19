"""T-8.10f F-4c: инструменты ассистента «Zurücklegen» и «Coupon» (план
docs/t8-10f-f4-plan-2026-10-19.md, Д-7…Д-12).

Инструмент ничего не создаёт: проверяет акцию (`actions.precheck`), лимиты и отправляет
человеку письмо со ссылкой подтверждения на страницу бизнеса. Резерв или купон
появляются только после клика человека (`promotions.assistant_views`).

Ответ ассистенту не зависит от того, знаком ли адрес: отказ по адресу (повтор, лимит,
«это не я») выглядит как отправка (Д-10). В ответе нет ни адреса, ни ссылки, ни токена —
иначе ассистент подтвердил бы сам.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone, translation
from django.utils.translation import gettext as _

from . import actions
from .handlers import _LANG_PROP, _lang, _pool
from .tools import Context, Tool, ToolError, register

logger = logging.getLogger(__name__)

_EMAIL_PROP = {"type": "string", "maxLength": 254, "description": "The person's e-mail."}

RESERVE_INPUT = {
    "type": "object",
    "properties": {
        "offer_id": {"type": "integer", "minimum": 1},
        "email": _EMAIL_PROP,
        "name": {"type": "string", "maxLength": 200},
        "quantity": {"type": "integer", "minimum": 1, "maximum": actions.QTY_MAX},
        "language": _LANG_PROP,
    },
    "required": ["offer_id", "email"],
    "additionalProperties": False,
}

COUPON_INPUT = {
    "type": "object",
    "properties": {
        "offer_id": {"type": "integer", "minimum": 1},
        "email": _EMAIL_PROP,
        "language": _LANG_PROP,
    },
    "required": ["offer_id", "email"],
    "additionalProperties": False,
}

ACTION_OUTPUT = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["confirmation_sent"]},
        "expires_at": {"type": "string"},
        "offer": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "title": {"type": "string"},
                "business": {"type": "string"},
            },
            "required": ["id", "title", "business"],
        },
        "demo": {"type": "boolean"},
        "message": {"type": "string"},
    },
    "required": ["status", "expires_at", "offer", "demo", "message"],
    "additionalProperties": False,
}

_ACTION = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}


def _refusal(code: str) -> str:
    return {
        actions.NOT_FOUND: _("Angebot nicht gefunden."),
        actions.NOT_RESERVABLE: _("Dieses Angebot kann man nicht zurücklegen lassen."),
        actions.NOT_COUPON: _("Für dieses Angebot gibt es keinen Coupon."),
        actions.SOLD_OUT: _("Leider ausverkauft."),
        actions.LIMIT: _("Diese Menge ist für dieses Angebot nicht möglich."),
    }.get(code, _("Diese Aktion ist gerade nicht verfügbar."))


def _unavailable(listing=None) -> ToolError:
    msg = _("Diese Aktion ist gerade nicht verfügbar.")
    url = ""
    if listing is not None:
        lang = translation.get_language() or ""
        url = listing.with_channel("mcp", lang=lang, listing_ref=True) or listing.detail_url
    if url:
        msg += " " + _("Die Person kann sie auf der Seite des Angebots ausführen: %(url)s") % {
            "url": url
        }
    return ToolError(msg)


def _request(op: str, args: dict, ctx: Context) -> dict:
    from ..tasks import send_mcp_confirm_email

    if actions.hit_ip(ctx.request):  # дёшево и первым — до любых запросов к БД
        raise ToolError(_("Zu viele Anfragen — bitte kurz warten."))
    lang = _lang(args)
    listing = _pool(ctx.portal).filter(pk=args["offer_id"]).first()
    if not actions.enabled():
        raise _unavailable(listing)
    try:
        email, name, qty = actions.clean_input(
            args.get("email"), args.get("name", ""), args.get("quantity", 1)
        )
    except ValueError:
        raise ToolError(_("Bitte eine gültige E-Mail-Adresse angeben.")) from None
    try:
        checked = actions.precheck(listing, op, qty)
    except actions.PrecheckError as err:
        raise ToolError(_refusal(err.code)) from None
    business = getattr(checked.tenant, "name", "") or ""
    ttl = actions.ttl_for(checked.ends_at)
    code = actions.reserve_slot(email=email, listing_id=listing.pk)
    if code == actions.LIMIT:
        raise ToolError(_("Zu viele Anfragen — bitte kurz warten."))
    if code is None:
        created = actions.create_pending(
            op=op,
            schema=checked.tenant.schema_name,
            promo_id=checked.promo_id,
            listing_id=listing.pk,
            portal_id=getattr(ctx.portal, "pk", None),
            email=email,
            name=name,
            qty=qty,
            lang=lang,
            ends_at=checked.ends_at,
            is_demo=checked.is_demo,
            title=checked.title,
            business=business,
        )
        if created is None:
            actions.release_slot(email=email, listing_id=listing.pk)
            raise _unavailable(listing)
        token, ttl = created
        try:
            # письмо — задачей: ответ одинаково быстрый при отправке и при «молчании»
            # (Д-10), рабочий процесс не ждёт почтовый сервер; в очереди только токен
            send_mcp_confirm_email.delay(
                dedupe_key=f"mcp-confirm:{actions._hash(token)}", token=token
            )
        except Exception as exc:  # noqa: BLE001 — очередь недоступна: квоту вернуть
            logger.warning("mcp confirm enqueue failed: %s", type(exc).__name__)
            actions.discard(token)
            actions.release_slot(email=email, listing_id=listing.pk)
            raise _unavailable(listing) from None
    # code == SILENT: ответ тот же, письмо не уходит (Д-10)
    expires = timezone.now() + timedelta(seconds=ttl)
    return {
        "status": "confirmation_sent",
        "expires_at": expires.isoformat(),
        "offer": {"id": listing.pk, "title": checked.title, "business": business},
        "demo": checked.is_demo,
        "message": _(
            "Wir haben eine E-Mail mit einem Bestätigungslink gesendet. Erledigt ist es erst "
            "nach dem Klick auf den Link."
        ),
    }


def _unavailable_text(args: dict, ctx: Context) -> str:
    """Скрытый инструмент вызвали напрямую (`tools.call_tool`) — отказ со ссылкой на
    страницу предложения: человек сделает то же сам."""
    with translation.override(_lang(args)):
        listing = _pool(ctx.portal).filter(pk=args.get("offer_id") or 0).first()
        return str(_unavailable(listing))


def request_reservation(args: dict, ctx: Context) -> dict:
    return _request(actions.OP_RESERVE, args, ctx)


def request_coupon(args: dict, ctx: Context) -> dict:
    return _request(actions.OP_COUPON, args, ctx)


def _with_language(handler):
    def wrapped(args: dict, ctx: Context) -> dict:
        with translation.override(_lang(args)):
            return handler(args, ctx)

    return wrapped


for _tool in (
    Tool(
        name="request_reservation",
        title="Ask to set an offer aside",
        description=(
            "Ask the business to set aside (reserve) an offer whose next_step.type is "
            "'reserve'. Sends the person an e-mail with a confirmation link; nothing is "
            "reserved until they click it. Use only with the person's own e-mail and consent."
        ),
        input_schema=RESERVE_INPUT,
        output_schema=ACTION_OUTPUT,
        handler=_with_language(request_reservation),
        annotations=_ACTION,
        available=actions.enabled,
        unavailable=_unavailable_text,
    ),
    Tool(
        name="request_coupon",
        title="Ask for a coupon",
        description=(
            "Ask for the coupon of an offer whose next_step.type is 'coupon'. Sends the "
            "person an e-mail with a confirmation link; the coupon is issued only after they "
            "click it. Use only with the person's own e-mail and consent."
        ),
        input_schema=COUPON_INPUT,
        output_schema=ACTION_OUTPUT,
        handler=_with_language(request_coupon),
        annotations=_ACTION,
        available=actions.enabled,
        unavailable=_unavailable_text,
    ),
):
    register(_tool)
