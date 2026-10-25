"""KA-12 E6.4c: «Anzahlung nach Nichterscheinen» — правило онлайн-записи.

Владелец включает правило (`site_config["booking"]["no_show_deposit"]`). Если по
e-mail гостя за `days` дней набралось ≥ `after` неявок, онлайн-запись требует
депозит через Stripe; когда Stripe не готов (или выбран офлайн-способ, или запись
на несколько времён, или сумма нулевая) — запись НЕ создаётся, гость видит
нейтральную просьбу позвонить. Решение принимается ДО создания брони.

Ревью безопасности плана (2026-10-25): ответ не называет причину; подсчёт идёт
одним и тем же запросом для любого e-mail; e-mail при включённом правиле обязателен
ВСЕМ (иначе правило обходится пустым полем); плюс-адреса (`a+x@b`) сводятся к
одному ящику; Mehrfachkarte пропускает правило только ПРОВЕРЕННАЯ заранее.
Телефон не используется никогда (KA-H7: на витрине клиента ищем только по e-mail).
"""

import hashlib
import logging
import re
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.utils.translation import gettext as _

from . import no_shows

logger = logging.getLogger(__name__)

NONE, DEPOSIT, CALL = "none", "deposit", "call"
# Гость с неявками, чью запись покрывает Mehrfachkarte: правило пропущено, но
# если карта не погасила все визиты (гонка) — откат на депозит.
PASS = "pass"
# Пробник «есть ли у этого адреса неявки» упирается в лимит по самому адресу.
RL_EMAIL_LIMIT = 10
RL_EMAIL_WINDOW = 3600


@dataclass(frozen=True)
class Decision:
    kind: str = NONE
    cents: int = 0

    @property
    def forced(self) -> bool:
        return self.kind == DEPOSIT


def rule(tenant) -> dict | None:
    """Нормализованное правило или None (выключено/мусор)."""
    from apps.tenants.siteconfig import normalize_booking

    cfg = getattr(tenant, "site_config", None)
    raw = cfg.get("booking") if isinstance(cfg, dict) else None
    return normalize_booking(raw).get("no_show_deposit")


def clean_email(raw) -> str:
    """Обрезанный адрес или "" (пусто/не адрес)."""
    email = (raw or "").strip()
    if not email:
        return ""
    try:
        validate_email(email)
    except ValidationError:
        return ""
    return email


def mailbox_pattern(email: str) -> str:
    """iregex «тот же ящик»: `anna+x@web.de` ≡ `anna@web.de` ≡ `Anna+y@WEB.de`."""
    local, _sep, domain = email.lower().rpartition("@")
    local = local.split("+", 1)[0]
    return rf"^{re.escape(local)}(\+[^@]*)?@{re.escape(domain)}$"


def email_rate_key(email: str, *, ip: str = "", schema: str = "") -> str:
    """Ключ лимита: ящик + IP + схема. Только по ящику — целевой DoS (чужой человек
    10 запросами блокировал бы запись владельцу адреса); перебор многих адресов с
    одного IP держит общий IP-лимит «termin»."""
    raw = f"{schema}|{ip}|{mailbox_pattern(email)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def recent_no_shows_for_email(email: str, days: int) -> int:
    """Неявки за окно по ВСЕМ карточкам этого ящика (дубли карточек не размывают
    счётчик). Один запрос; для пустого адреса — тоже ровно один (тайминг ровный)."""
    from datetime import timedelta

    from .models import Booking

    since = timezone.now() - timedelta(days=days)
    qs = Booking.objects.filter(status__in=no_shows.NO_SHOW_STATUSES, start__gte=since)
    if email:
        qs = qs.filter(customer__email__iregex=mailbox_pattern(email))
    else:
        qs = qs.none()
    return qs.order_by().count()


def stripe_ready(tenant) -> bool:
    from apps.billing import connect

    return bool(
        getattr(tenant, "payments_enabled", False)
        and getattr(tenant, "stripe_connect_id", "")
        and connect.is_connect_configured()
    )


def flagged(tenant, email: str) -> bool:
    cfg = rule(tenant)
    if not cfg:
        return False
    return recent_no_shows_for_email(email, cfg["days"]) >= cfg["after"]


def amount_cents(tenant, base_deposit_cents: int, payable_cents: int | None) -> int:
    """Сумма принудительного депозита: депозит услуги/ресурса → сумма из правила →
    вся цена (В-A1). Не больше к оплате (`payable_cents`; None — без капа, у
    ресурсной записи цены обычно нет, В-A3)."""
    cfg = rule(tenant) or {}
    cents = base_deposit_cents or cfg.get("cents", 0) or (payable_cents or 0)
    if payable_cents is not None:
        cents = min(cents, max(0, payable_cents))
    return max(0, int(cents))


def decide_before(
    tenant, *, is_flagged: bool, slots: int, offline: bool, estimate_cents: int
) -> Decision:
    """До брони: только то, что известно из формы. `deposit` здесь — «будет
    депозит», точная сумма считается по созданной брони (`amount_cents`)."""
    if not is_flagged:
        return Decision()
    if slots > 1 or offline or not stripe_ready(tenant) or estimate_cents <= 0:
        return Decision(CALL)
    return Decision(DEPOSIT, estimate_cents)


def call_message(tenant) -> str:
    """Нейтральный текст: без причины и без упоминания адреса (не оракул)."""
    phone = (getattr(tenant, "contact_phone", "") or "").strip()
    if phone:
        return _("Für diese Buchung bitten wir um einen kurzen Anruf: %(phone)s") % {"phone": phone}
    return _("Für diese Buchung bitten wir um einen kurzen Anruf.")


def pass_covers(code: str, *, service=None, slots: int = 1) -> bool:
    """Mehrfachkarte пропускает правило, только если она ДЕЙСТВИТЕЛЬНО покроет
    все периоды (ревью C1: мусорный код раньше обходил любой депозит)."""
    from .models import Pass

    code = (code or "").strip()
    if not code:
        return False
    card = Pass.objects.filter(code__iexact=code, is_active=True).first()
    if card is None or not card.is_valid or card.credits_left < slots:
        return False
    return not (card.service_id and service is not None and card.service_id != service.pk)
