"""T-8.10f F-4: «Zurücklegen» и «Coupon» из ассистента — с подтверждением по e-mail.

План — docs/t8-10f-f4-plan-2026-10-19.md. Ассистент ничего не создаёт сам: инструмент
кладёт «ожидающее действие» в кэш и отправляет человеку письмо со ссылкой; резерв или
купон появляются только после клика человека на странице бизнеса (POST).

* Токен — случайный, одноразовый. В кэше лежит запись под sha256 токена, данные
  человека зашифрованы (Fernet, ключи секретов); ни токена, ни адреса в ключах нет.
* Срок — не дольше `MCP_ACTION_TTL` (24 ч) и не дольше конца акции.
* Одноразовость: `claim()` — `cache.add`; итог запоминается в `finish()` на срок
  записи, повторный клик показывает тот же итог, а не второе действие.
* Предпроверка (`precheck`) не трогает данные человека: до клика в БД бизнеса ни
  клиента, ни уведомления.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

OP_RESERVE = "reserve"
OP_COUPON = "coupon"
OPS = (OP_RESERVE, OP_COUPON)

PAYLOAD_VERSION = 1
_PENDING = "mcp:pending:"
_CLAIM = "mcp:claim:"
_DONE = "mcp:done:"

#: Коды отказа предпроверки — то, что видит ассистент (без деталей о человеке).
NOT_FOUND = "not_found"
NOT_RESERVABLE = "not_reservable"
NOT_COUPON = "not_coupon"
SOLD_OUT = "sold_out"
LIMIT = "limit"
UNAVAILABLE = "unavailable"
#: Отказ по АДРЕСУ (лимит, повтор, «это не я»): ассистент получает тот же ответ, что
#: при отправке, а письмо не уходит — иначе код выдаёт, знают ли адрес (Д-10).
SILENT = "silent"

#: Сколько штук можно отложить через ассистента за раз.
QTY_MAX = 10
NAME_MAX = 80
#: Сколько держится «занято» на время исполнения (не сутки: упавший процесс не должен
#: запирать ссылку человека до конца срока).
CLAIM_TTL = 120

#: Почтовые бэкенды, которые письмо человеку НЕ доставляют (Д-9).
_FAKE_BACKENDS = ("console", "dummy", "filebased")


def mail_ready() -> bool:
    """Настоящая почта: Resend/SMTP (и locmem в тестах). Console/dummy — нет."""
    backend = (getattr(settings, "EMAIL_BACKEND", "") or "").lower()
    return bool(backend) and not any(fake in backend for fake in _FAKE_BACKENDS)


def enabled() -> bool:
    """Действия доступны ассистенту: переключатель включён и почта настоящая."""
    return bool(getattr(settings, "MCP_ACTIONS_ENABLED", False)) and mail_ready()


def _hash(token: str) -> str:
    return hashlib.sha256(str(token).encode()).hexdigest()


def _valid_token(token) -> bool:
    return isinstance(token, str) and 20 <= len(token) <= 100


def ttl_for(ends_at, now=None) -> int:
    """Срок ссылки в секундах: не дольше `MCP_ACTION_TTL` и не дольше конца акции."""
    ttl = int(getattr(settings, "MCP_ACTION_TTL", 86400))
    if ends_at is not None:
        now = now or timezone.now()
        ttl = min(ttl, int((ends_at - now).total_seconds()))
    return max(ttl, 0)


def clean_input(email, name="", qty=1) -> tuple[str, str, int]:
    """Проверка того, что передал ассистент → (email, name, qty). ValueError — мусор."""
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    email = str(email or "").strip().lower()
    if not email or len(email) > 254:
        raise ValueError("email")
    try:
        validate_email(email)
    except ValidationError:
        raise ValueError("email") from None
    name = " ".join("".join(ch for ch in str(name or "") if ch.isprintable()).split())
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        raise ValueError("qty") from None
    if not 1 <= qty <= QTY_MAX:
        raise ValueError("qty")
    return email, name[:NAME_MAX], qty


def create_pending(
    *,
    op: str,
    schema: str,
    promo_id,
    listing_id: int,
    portal_id: int | None,
    email: str,
    name: str = "",
    qty: int = 1,
    lang: str = "de",
    ends_at=None,
    is_demo: bool = False,
) -> tuple[str, int] | None:
    """Положить ожидающее действие → (токен, срок в секундах). None — акция уже кончилась
    или кэш недоступен (вызывающий честно отказывает, а не обещает письмо)."""
    if op not in OPS:
        raise ValueError(op)
    email, name, qty = clean_input(email, name, qty)
    ttl = ttl_for(ends_at)
    if ttl <= 0:
        return None
    from apps.secrets import crypto

    token = secrets.token_urlsafe(32)
    payload = {
        "v": PAYLOAD_VERSION,
        "op": op,
        "schema": schema,
        "promo_id": str(promo_id),
        "listing_id": int(listing_id),
        "portal_id": portal_id,
        "qty": int(qty),
        "lang": lang,
        "demo": bool(is_demo),
        "created": timezone.now().isoformat(),
        # человек — только зашифрованным
        "who": crypto.encrypt(json.dumps({"email": email, "name": name})),
    }
    try:
        cache.set(_PENDING + _hash(token), payload, ttl)
    except Exception as exc:  # noqa: BLE001 — нет кэша: честный отказ выше
        logger.warning("mcp pending store failed: %s", type(exc).__name__)
        return None
    return token, ttl


def load_pending(token) -> dict | None:
    """Запись по токену с расшифрованными `email`/`name`; None — нет/протухла/битая."""
    if not _valid_token(token):
        return None
    try:
        payload = cache.get(_PENDING + _hash(token))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict) or payload.get("v") != PAYLOAD_VERSION:
        return None
    from apps.secrets import crypto

    try:
        who = json.loads(crypto.decrypt(payload.get("who") or "") or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(who, dict) or not who.get("email"):
        return None
    out = {k: v for k, v in payload.items() if k != "who"}
    out["email"] = who["email"]
    out["name"] = who.get("name") or ""
    return out


def claim(token) -> bool:
    """Занять токен для исполнения. False — уже занят (двойной клик/гонка)."""
    if not _valid_token(token):
        return False
    try:
        return bool(cache.add(_CLAIM + _hash(token), 1, CLAIM_TTL))
    except Exception:  # noqa: BLE001 — без кэша исполнять нельзя: одноразовость не гарантирована
        return False


def release(token) -> None:
    """Снять занятость после сбоя ДО действия — человек может нажать ещё раз."""
    try:
        cache.delete(_CLAIM + _hash(token))
    except Exception:  # noqa: BLE001
        pass


def finish(token, outcome: dict) -> None:
    """Запомнить итог (на повторный клик) и удалить ожидающую запись с адресом."""
    ttl = int(getattr(settings, "MCP_ACTION_TTL", 86400))
    key = _hash(token)
    try:
        cache.set(_DONE + key, dict(outcome), ttl)
    except Exception as exc:  # noqa: BLE001 — итог потерян: повтор найдёт запись в БД
        logger.error("mcp finish: outcome not stored: %s", type(exc).__name__)
    try:
        cache.delete(_PENDING + key)
    except Exception as exc:  # noqa: BLE001
        logger.error("mcp finish: pending not deleted: %s", type(exc).__name__)


def outcome(token) -> dict | None:
    if not _valid_token(token):
        return None
    try:
        found = cache.get(_DONE + _hash(token))
    except Exception:  # noqa: BLE001
        return None
    return found if isinstance(found, dict) else None


# --- предпроверка --------------------------------------------------------------------


class PrecheckError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Checked:
    tenant: object
    promo_id: str
    title: str
    ends_at: object
    is_demo: bool


def _refused(op: str) -> str:
    return NOT_RESERVABLE if op == OP_RESERVE else NOT_COUPON


def precheck(listing, op: str, qty: int = 1) -> Checked:
    """Можно ли предложить человеку это действие — без его данных, один `schema_context`.

    Те же условия, что у кнопки на витрине: акция активна, отклик совпадает
    (`response_for`), цель не услуга/номер, остаток есть, бизнес в каталоге."""
    from django_tenants.utils import schema_context

    from apps.promotions import response
    from apps.tenants.models import Tenant

    from .. import visibility
    from ..models import AggregatorListing

    if not isinstance(qty, int) or not 1 <= qty <= QTY_MAX:
        raise PrecheckError(LIMIT)
    if listing is None or listing.listing_kind != AggregatorListing.KIND_PROMOTION:
        raise PrecheckError(NOT_FOUND)
    try:
        ref = uuid.UUID(str(listing.source_ref))
    except (TypeError, ValueError, AttributeError):
        raise PrecheckError(NOT_FOUND) from None
    tenant = (
        Tenant.objects.filter(schema_name=listing.tenant_schema)
        .exclude(schema_name="public")
        .first()
    )
    if tenant is None or not visibility.listable(tenant):
        raise PrecheckError(NOT_FOUND)
    with schema_context(tenant.schema_name):
        from apps.promotions.models import Promotion

        promo = Promotion.objects.filter(pk=ref).first()
        if promo is None or promo.status != "active":
            raise PrecheckError(NOT_FOUND)
        if promo.ends_at is not None and promo.ends_at <= timezone.now():
            raise PrecheckError(NOT_FOUND)
        if promo.target_kind in ("service", "stay"):
            raise PrecheckError(_refused(op))
        if response.response_for(promo, tenant) != op:
            raise PrecheckError(_refused(op))
        if promo.available_quantity is not None and promo.available_quantity < qty:
            raise PrecheckError(SOLD_OUT)
        if op == OP_RESERVE and promo.max_per_customer and qty > promo.max_per_customer:
            raise PrecheckError(LIMIT)
        return Checked(
            tenant=tenant,
            promo_id=str(promo.pk),
            title=promo.title_text or "",
            ends_at=promo.ends_at,
            is_demo=bool(getattr(tenant, "is_demo", False)),
        )


# --- лимиты --------------------------------------------------------------------------


def _limit(name: str, default: int) -> int:
    return int(getattr(settings, name, default))


_GMAIL = ("gmail.com", "googlemail.com")


def canonical_email(email: str) -> str:
    """Один почтовый ящик = один ключ лимита: без `+метки`, у Gmail ещё и без точек."""
    local, _at, domain = str(email or "").strip().lower().rpartition("@")
    local = local.split("+", 1)[0]
    if domain in _GMAIL:
        local, domain = local.replace(".", ""), "gmail.com"
    return f"{local}@{domain}"


def address_key(email: str) -> str:
    """Ключ адреса в лимитах: HMAC, а не голый sha256 — по утечке кэша адрес не подобрать."""
    secret = settings.SECRET_KEY.encode()
    return hmac.new(secret, canonical_email(email).encode(), hashlib.sha256).hexdigest()


def _windows(email: str, listing_id: int):
    """(scope, ident, предел, окно, код отказа) — всё, что считает отправленные письма."""
    mail = address_key(email)
    day = 60 * 60 * 24
    return (
        ("mcp-act-email-offer", f"{mail}:{listing_id}", 1, day, SILENT),
        ("mcp-act-email", mail, _limit("MCP_ACTION_RATE_EMAIL", 3), day, SILENT),
        ("mcp-act-offer", str(listing_id), _limit("MCP_ACTION_RATE_OFFER", 50), day, LIMIT),
        ("mcp-act-global", "all", _limit("MCP_ACTION_RATE_GLOBAL", 300), 3600, LIMIT),
    )


def _used(scope: str, ident: str) -> int:
    from apps.core import ratelimit

    try:
        return int(ratelimit.cache.get(f"rl:{scope}:{ident}") or 0)
    except Exception:  # noqa: BLE001 — кэш недоступен: fail-open, как ratelimit.hit
        return 0


def hit_ip(request) -> bool:
    """Предохранитель на адрес запроса (дёшево, первым). True — отказ."""
    from apps.core import ratelimit

    limit = _limit("MCP_ACTION_RATE_IP", 20)
    return ratelimit.hit("mcp-act-ip", ratelimit.client_ip(request), limit=limit, window=600)


def check_limits(*, email: str, listing_id: int) -> str | None:
    """Можно ли отправить письмо (Д-11) — БЕЗ расхода квот: счётчики увеличивает только
    `consume_limits` после реальной отправки, отказ дальше по цепочке квоту не сжигает.

    Отказ по адресу (повтор, лимит, «это не я») — `SILENT`: ассистенту тот же ответ,
    что при отправке. Отказ по предложению или общему потолку — честный `LIMIT`."""
    if is_suppressed(email):
        return SILENT
    for scope, ident, limit, _window, code in _windows(email, listing_id):
        if _used(scope, ident) >= limit:
            return code
    return None


def consume_limits(*, email: str, listing_id: int) -> None:
    """Засчитать отправленное письмо во все окна."""
    from apps.core import ratelimit

    for scope, ident, limit, window, _code in _windows(email, listing_id):
        ratelimit.hit(scope, ident, limit=limit, window=window)


SUPPRESS_TTL = 60 * 60 * 24 * 30
_SUPPRESS = "mcp:suppress:"


def suppress(email: str) -> None:
    """«Das war ich nicht»: 30 дней на этот ящик писем от ассистентов не отправляем."""
    try:
        cache.set(_SUPPRESS + address_key(email), 1, SUPPRESS_TTL)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp suppress failed: %s", type(exc).__name__)


def is_suppressed(email: str) -> bool:
    try:
        return bool(cache.get(_SUPPRESS + address_key(email)))
    except Exception:  # noqa: BLE001
        return False


def confirm_url(tenant, promo_id, token) -> str:
    """Ссылка подтверждения на основном домене бизнеса (tenant-urlconf явно, урок T-8.5)."""
    from django.urls import reverse

    from apps.promotions.notifications import _base_url

    base = _base_url(tenant.schema_name)
    if not base:
        return ""
    path = reverse(
        "storefront-assistant-confirm",
        kwargs={"pk": promo_id, "token": token},
        urlconf="config.urls_tenant",
    )
    return base + path
