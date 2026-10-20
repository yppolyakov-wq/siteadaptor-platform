"""T-8.7: сводка «Folgen» — одно письмо жителю в день (или в неделю) + мгновенный режим.

План — docs/t8-7-folgen-plan-2026-10-15.md §4.2. Правила:

* Пустых писем не бывает: нет новинок — нет письма, `last_sent_at` не двигается.
* Дедуп периода — строка `FollowDigest(user, period_key)` вставляется ДО отправки
  (unique): второй прогон того же часа выходит по IntegrityError; при сбое SMTP строка
  удаляется и следующий прогон повторит.
* «Новое» = `created_at > since` (с последнего письма, не раньше подтверждения, не глубже
  окна «Neu»); ключи источника, уже показанные за `recent_sent_days`, не повторяются —
  синк пересоздаёт строку листинга при паузе/реактивации акции.
* Расписание «час + гейт»: beat раз в час, письмо уходит в первый прогон после 08:00
  местного времени, в который есть что показать; пропущенный час не теряет письмо (в
  отличие от crontab). Житель без новинок остаётся кандидатом до конца дня — осознанно:
  новинка в 10:00 уйдёт в 11:00, а не завтра; цена — лёгкие выборки раз в час.
* Featured в письме не отмечается и не продвигается — порядок по новизне (UWG §5a).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.template.loader import render_to_string
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from . import follow
from .models import FollowDigest, FollowSubscription, PortalChat, PortalUser

log = logging.getLogger(__name__)

ITEMS_PER_FOLLOW = 5
MAX_FOLLOWS_PER_MAIL = 20
MAX_ITEM_KEYS = 200
RECENT_SENT_DAYS = 15  # ≥ NEW_DAYS: глубже since_for не заглядывает
OVERFETCH = 50  # строк на подписку: отсеять уже показанное без LIMIT «по числу seen»
DAILY_HOUR = 8
QUIET_HOURS = (21, 7)  # мгновенные письма копятся с 21:00 до 07:00
INSTANT_SLOT_MINUTES = 15


def _cfg(key: str, default):
    return getattr(settings, "AGGREGATOR_FOLLOW", {}).get(key, default)


# --- периоды ------------------------------------------------------------------------------


def _local(now=None) -> datetime:
    return timezone.localtime(now or timezone.now())


def period_key_daily(now=None) -> str:
    return f"d:{_local(now).date().isoformat()}"


def period_key_instant(now=None) -> str:
    local = _local(now)
    minute = local.minute - local.minute % INSTANT_SLOT_MINUTES
    return f"i:{local:%Y-%m-%dT%H}:{minute:02d}"


def daily_due(now=None) -> bool:
    return _local(now).hour >= int(_cfg("daily_hour", DAILY_HOUR))


def _week_start(now) -> datetime:
    """Понедельник 08:00 текущей ISO-недели (местное время, aware)."""
    local = _local(now)
    monday = (local - timedelta(days=local.weekday())).replace(
        hour=int(_cfg("daily_hour", DAILY_HOUR)), minute=0, second=0, microsecond=0
    )
    return monday


def weekly_due(sub: FollowSubscription, now=None) -> bool:
    now = now or timezone.now()
    start = _week_start(now)
    if _local(now) < start:
        return False
    # Подписка, подтверждённая на этой неделе, ждёт следующего понедельника — иначе
    # «еженедельно» дало бы письмо уже на следующий день.
    anchor = max(sub.confirmed_at, sub.last_sent_at or sub.confirmed_at)
    return anchor < start


def in_quiet_hours(now=None) -> bool:
    start, end = _cfg("quiet_hours", QUIET_HOURS)
    hour = _local(now).hour
    if start > end:  # через полночь
        return hour >= start or hour < end
    return start <= hour < end


# --- сборка -------------------------------------------------------------------------------


@dataclass
class Section:
    sub: FollowSubscription
    title: str
    items: list
    total: int
    more_url: str
    unsubscribe_url: str


@dataclass
class Digest:
    user: PortalUser
    sections: list[Section] = field(default_factory=list)
    manage_url: str = ""
    unsubscribe_all_url: str = ""
    portal: object = None

    @property
    def item_keys(self) -> list[str]:
        keys: list[str] = []
        for section in self.sections:
            keys.extend(follow.item_key(item) for item in section.items)
        return keys[:MAX_ITEM_KEYS]


_CTRL = re.compile(r"[\x00-\x1f\x7f\u2028\u2029]+")
TITLE_MAX = 120


def _clean_line(value) -> str:
    """Текст бизнеса в письме платформы — одной строкой, без управляющих символов
    (иначе владелец тенанта дописал бы в plain-text письмо свои строки и ссылки)."""
    return " ".join(_CTRL.sub(" ", str(value or "")).split())[:TITLE_MAX]


def _prepare(item) -> bool:
    """Поля для письма; False — элемент без годной http(s)-ссылки не показываем."""
    url = item.with_channel("digest")
    if not url.lower().startswith(("https://", "http://")):
        return False
    item.digest_url = url
    item.digest_title = _clean_line(item.title_text)
    item.digest_business = _clean_line(item.business_name)
    # В2: условие цены одной строкой (текст владельца — без управляющих символов).
    item.digest_condition = _clean_line(item.price_condition_label)
    return True


def recently_sent_keys(user: PortalUser, now=None) -> set[str]:
    """Ключи источников, уже показанных жителю за окно — ОДИН запрос."""
    now = now or timezone.now()
    since = now - timedelta(days=int(_cfg("recent_sent_days", RECENT_SENT_DAYS)))
    out: set[str] = set()
    for keys in FollowDigest.objects.filter(user=user, sent_at__gte=since).values_list(
        "item_keys", flat=True
    ):
        out.update(k for k in (keys or []) if isinstance(k, str))
    return out


def build_digest(user: PortalUser, subs: list[FollowSubscription], *, now=None) -> Digest | None:
    """Секции по подпискам; None, если показать нечего."""
    now = now or timezone.now()
    seen = recently_sent_keys(user, now)
    per_follow = int(_cfg("items_per_follow", ITEMS_PER_FOLLOW))
    portal = next((s.portal for s in subs if s.portal_id), None)
    digest = Digest(user=user, portal=portal)
    # T-8.10d: узкое первым — компания, затем поиски, затем раздел/район: предложение,
    # совпавшее с несколькими подписками, встаёт под самую точную подпись (и один раз).
    order = {
        FollowSubscription.TARGET_BUSINESS: 0,
        FollowSubscription.TARGET_QUERY: 1,
    }
    subs = sorted(subs, key=lambda s: order.get(s.target_kind, 2))
    for sub in subs[:MAX_FOLLOWS_PER_MAIL]:
        since = follow.since_for(sub, now)
        qs = follow.items_for(sub, since=since, now=now)
        window = list(qs[:OVERFETCH])  # одна выборка на подписку
        fresh = [item for item in window if follow.item_key(item) not in seen and _prepare(item)]
        if not fresh:
            continue
        shown = fresh[:per_follow]
        seen |= {follow.item_key(item) for item in shown}  # дедуп внутри одного письма
        # Точное «Alle anzeigen (N)» — только если окно срезано; иначе N = число свежих.
        total = qs.count() - (len(window) - len(fresh)) if len(window) == OVERFETCH else len(fresh)
        digest.sections.append(
            Section(
                sub=sub,
                title=follow.describe(sub),
                items=shown,
                total=max(total, len(fresh)),
                more_url=follow.scope_url(sub),
                unsubscribe_url=follow.unsubscribe_url(sub),
            )
        )
    if not digest.sections:
        return None
    digest.manage_url = follow.manage_url(user, portal)
    digest.unsubscribe_all_url = follow.unsubscribe_all_url(user, portal)
    return digest


def render(digest: Digest, *, locale: str = "") -> tuple[str, str, str]:
    """(subject, text, html) в языке жителя."""
    locale = follow.normalize_locale(locale or digest.user.locale)
    portal = digest.portal
    ctx = {
        "digest": digest,
        "sections": digest.sections,
        "portal": portal,
        "portal_name": portal.title_text if portal is not None else settings.TENANT_DOMAIN_BASE,
        "manage_url": digest.manage_url,
        "unsubscribe_url": digest.unsubscribe_all_url,
    }
    with translation.override(locale):
        # Тема — одной строкой: перевод строки в названии портала дал бы BadHeaderError.
        subject = " ".join(render_to_string("emails/follow_digest_subject.txt", ctx).split())
        text = render_to_string("emails/follow_digest.txt", ctx)
        html = render_to_string("emails/follow_digest.html", ctx)
    return subject, text, html


class BotUnavailable(Exception):
    """Бот портала выключен — сводку отложить, а не пометить отправленной."""


TELEGRAM_MAX = 3900  # запас до лимита сообщения Telegram (4096)


def render_telegram(digest: Digest, *, locale: str = "") -> str:
    """T-8.28: сводка одним сообщением Telegram (простой текст, без разметки)."""
    locale = follow.normalize_locale(locale or digest.user.locale)
    portal = digest.portal
    name = portal.title_text if portal is not None else settings.TENANT_DOMAIN_BASE
    with translation.override(locale):
        parts = ["🔔 " + _("Neu für Sie — %(name)s") % {"name": _clean_line(name)}]
        for section in digest.sections:
            block = [f"\n{_clean_line(section.title)}"]
            for item in section.items:
                line = f"• {item.digest_title}"
                if item.digest_condition:
                    line += f" — {item.digest_condition}"
                block.append(f"{line}\n  {item.digest_business}\n  {item.digest_url}")
            if section.total > len(section.items) and section.more_url:
                block.append(
                    _("Alle anzeigen (%(n)s): %(url)s")
                    % {
                        "n": section.total,
                        "url": section.more_url,
                    }
                )
            candidate = "\n".join([*parts, *block])
            if len(candidate) > TELEGRAM_MAX:
                break
            parts.extend(block)
        parts.append("\n" + _("Abos verwalten: /folgen"))
    return "\n".join(parts)[:TELEGRAM_MAX]


def _send_telegram(digest: Digest) -> bool:
    """True — ушло; False — чат недоступен (бот заблокирован/выключен). Иное — исключение."""
    import requests

    from apps.telegram import services

    chat = getattr(digest.user, "portal_chat", None)
    if chat is None or chat.blocked_at is not None:
        return False
    bot = chat.bot
    if not bot.is_active or not bot.token:
        raise BotUnavailable  # бот выключен временно: период не сжигаем
    try:
        services.send_message(bot.token, chat.chat_id, render_telegram(digest, locale=chat.locale))
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (400, 403):  # бот заблокирован / чат удалён («chat not found»)
            PortalChat.objects.filter(pk=chat.pk).update(blocked_at=timezone.now())
            return False
        # Текст любой ошибки requests несёт URL с токеном бота — наружу только тип/код.
        raise RuntimeError(f"telegram {status or type(exc).__name__}") from None
    return True


def send(digest: Digest, *, period_key: str, now=None) -> bool:
    """Отправить сводку ровно один раз за период (Р-П8)."""
    now = now or timezone.now()
    # Заявка на период — ДО отправки (unique = второй прогон выходит); ключи элементов —
    # ПОСЛЕ успешной отправки: иначе жёсткий сбой между insert и send пометил бы их
    # «показанными», и житель не увидел бы их до конца окна дедупа. Остаточный риск v1:
    # сбой процесса между insert и send пропускает письмо этого периода (не элементы).
    try:
        with transaction.atomic():
            row = FollowDigest.objects.create(user=digest.user, period_key=period_key, item_keys=[])
    except IntegrityError:
        return False
    if not digest.user.email:  # T-8.28: житель из Telegram-бота портала
        try:
            sent = _send_telegram(digest)
        except BotUnavailable:
            sent = False
        except Exception:  # noqa: BLE001 — сеть/429: строку снять, следующий прогон повторит
            log.warning("follow digest telegram failed user=%s", digest.user.pk)
            FollowDigest.objects.filter(pk=row.pk).delete()
            raise
        if not sent:
            # Период не сжигаем: чат вернётся (разблокировка, бот включён) — сводка дойдёт.
            # Заблокированные чаты в кандидаты и так не попадают.
            FollowDigest.objects.filter(pk=row.pk).delete()
            return False
        # Остаточный риск (как у письма): сбой между отправкой и этой строкой — сообщение
        # ушло, а ключи элементов не записаны; следующий период может их повторить.
        FollowDigest.objects.filter(pk=row.pk).update(item_keys=digest.item_keys)
        FollowSubscription.objects.filter(pk__in=[s.sub.pk for s in digest.sections]).update(
            last_sent_at=now, updated_at=now
        )
        return True
    subject, text, html = render(digest)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[digest.user.email],
        headers={
            "List-Unsubscribe": f"<{digest.unsubscribe_all_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
    message.attach_alternative(html, "text/html")
    try:
        message.send()
    except Exception:  # noqa: BLE001 — SMTP упал: строку снять, следующий прогон повторит
        log.exception("follow digest send failed user=%s", digest.user.pk)
        FollowDigest.objects.filter(pk=row.pk).delete()
        raise
    FollowDigest.objects.filter(pk=row.pk).update(item_keys=digest.item_keys)
    FollowSubscription.objects.filter(pk__in=[s.sub.pk for s in digest.sections]).update(
        last_sent_at=now, updated_at=now
    )
    return True


# --- прогоны ------------------------------------------------------------------------------


def _channel(user) -> str:
    """Канал жителя: почта — e-mail; житель бота портала (без почты) — Telegram."""
    return FollowSubscription.CHANNEL_EMAIL if user.email else FollowSubscription.CHANNEL_TELEGRAM


def _email_subs(user, frequencies) -> list[FollowSubscription]:
    return list(
        FollowSubscription.objects.filter(
            user=user, channel=_channel(user), frequency__in=frequencies
        ).select_related("portal")
    )


def _reachable():
    """Жители, до которых можно достучаться: с почтой или с живым чатом бота портала."""
    return (Q(email__isnull=False) & ~Q(email="")) | Q(
        portal_chat__blocked_at__isnull=True,
        portal_chat__bot__is_active=True,
    )


def digest_for_user(user: PortalUser, *, now=None) -> bool:
    """Дневная сводка одному жителю: daily + созревшие weekly. True — письмо ушло."""
    now = now or timezone.now()
    if not daily_due(now) or not user.is_active:
        return False
    period = period_key_daily(now)
    if FollowDigest.objects.filter(user=user, period_key=period).exists():
        return False
    subs = [
        s
        for s in _email_subs(user, (FollowSubscription.FREQ_DAILY, FollowSubscription.FREQ_WEEKLY))
        if s.frequency == FollowSubscription.FREQ_DAILY or weekly_due(s, now)
    ]
    if not subs:
        return False
    digest = build_digest(user, subs, now=now)
    if digest is None:
        return False
    return send(digest, period_key=period, now=now)


def daily_candidates(now=None):
    """Жители, которым сегодня ещё не писали и у кого есть e-mail-подписки сводкой."""
    now = now or timezone.now()
    period = period_key_daily(now)
    subs = FollowSubscription.objects.filter(
        user=OuterRef("pk"),
        frequency__in=(FollowSubscription.FREQ_DAILY, FollowSubscription.FREQ_WEEKLY),
    )
    done = FollowDigest.objects.filter(user=OuterRef("pk"), period_key=period)
    # Exists вместо JOIN+DISTINCT: оба подзапроса идут по индексам (FK; unique user+period).
    return (
        PortalUser.objects.filter(is_active=True)
        .filter(_reachable())
        .filter(Exists(subs))
        .exclude(Exists(done))
        .order_by()
    )


def run_daily(now=None) -> int:
    """Beat раз в час: гейт 08:00, по жителю — отдельная задача (fan-out)."""
    now = now or timezone.now()
    if not daily_due(now):
        return 0
    from .tasks import send_follow_digest_user

    period = period_key_daily(now)
    hour = _local(now).hour
    queued = 0
    for user_id in daily_candidates(now).values_list("pk", flat=True):
        # Ключ дедупа — на ЧАС, не на день: lock_timeout idempotent_task = интервалу beat,
        # и дневной ключ то пропускал бы, то пускал следующий прогон по джиттеру; после
        # сбоя отправки следующий час повторяет попытку, период держит unique-строка.
        send_follow_digest_user.delay(
            dedupe_key=f"follow:{user_id}:{period}:{hour}", user_id=user_id
        )
        queued += 1
    return queued


def instant_for_user(user: PortalUser, *, now=None) -> bool:
    """Мгновенные подписки на бизнес: новинки с последнего письма одним письмом."""
    now = now or timezone.now()
    if in_quiet_hours(now) or not user.is_active:
        return False
    subs = _email_subs(user, (FollowSubscription.FREQ_INSTANT,))
    if not subs:
        return False
    digest = build_digest(user, subs, now=now)
    if digest is None:
        return False
    return send(digest, period_key=period_key_instant(now), now=now)


def instant_candidates():
    subs = FollowSubscription.objects.filter(
        user=OuterRef("pk"),
        frequency=FollowSubscription.FREQ_INSTANT,
    )
    return (
        PortalUser.objects.filter(is_active=True)
        .filter(_reachable())
        .filter(Exists(subs))
        .order_by()
    )


def run_instant(now=None) -> int:
    """Beat раз в 15 минут: по жителю — отдельная задача (как run_daily), чтобы обход
    не перерастал интервал beat; повторный прогон того же слота гасит unique-строка."""
    now = now or timezone.now()
    if in_quiet_hours(now):
        return 0
    from .tasks import send_follow_instant_user

    slot = period_key_instant(now)
    queued = 0
    for user_id in instant_candidates().values_list("pk", flat=True):
        send_follow_instant_user.delay(dedupe_key=f"follow-i:{user_id}:{slot}", user_id=user_id)
        queued += 1
    return queued


def purge(now=None) -> int:
    now = now or timezone.now()
    days = int(_cfg("digest_retention_days", 90))
    count, _ = FollowDigest.objects.filter(sent_at__lt=now - timedelta(days=days)).delete()
    return int(count)
