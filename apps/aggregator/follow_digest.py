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
  местного времени; пропущенный час не теряет письмо (в отличие от crontab).
* Featured в письме не отмечается и не продвигается — порядок по новизне (UWG §5a).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import timezone, translation

from . import follow
from .models import FollowDigest, FollowSubscription, PortalUser

log = logging.getLogger(__name__)

ITEMS_PER_FOLLOW = 5
MAX_FOLLOWS_PER_MAIL = 20
MAX_ITEM_KEYS = 200
RECENT_SENT_DAYS = 30
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
    for sub in subs[:MAX_FOLLOWS_PER_MAIL]:
        since = follow.since_for(sub, now)
        qs = follow.items_for(sub, since=since, now=now)
        fresh = [
            item for item in qs[: per_follow * 4 + len(seen)] if follow.item_key(item) not in seen
        ]
        if not fresh:
            continue
        for item in fresh:
            item.digest_url = item.with_channel("digest")
        total = qs.count() - (len(qs[: per_follow * 4 + len(seen)]) - len(fresh))
        digest.sections.append(
            Section(
                sub=sub,
                title=follow.describe(sub),
                items=fresh[:per_follow],
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
        subject = render_to_string("emails/follow_digest_subject.txt", ctx).strip()
        text = render_to_string("emails/follow_digest.txt", ctx)
        html = render_to_string("emails/follow_digest.html", ctx)
    return subject, text, html


def send(digest: Digest, *, period_key: str, now=None) -> bool:
    """Отправить сводку ровно один раз за период (Р-П8)."""
    now = now or timezone.now()
    try:
        with transaction.atomic():
            row = FollowDigest.objects.create(
                user=digest.user, period_key=period_key, item_keys=digest.item_keys
            )
    except IntegrityError:
        return False
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
    FollowSubscription.objects.filter(pk__in=[s.sub.pk for s in digest.sections]).update(
        last_sent_at=now, updated_at=now
    )
    return True


# --- прогоны ------------------------------------------------------------------------------


def _email_subs(user, frequencies) -> list[FollowSubscription]:
    return list(
        FollowSubscription.objects.filter(
            user=user, channel=FollowSubscription.CHANNEL_EMAIL, frequency__in=frequencies
        ).select_related("portal")
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
    return (
        PortalUser.objects.filter(
            is_active=True,
            follows__channel=FollowSubscription.CHANNEL_EMAIL,
            follows__frequency__in=(FollowSubscription.FREQ_DAILY, FollowSubscription.FREQ_WEEKLY),
        )
        .exclude(follow_digests__period_key=period)
        .distinct()
    )


def run_daily(now=None) -> int:
    """Beat раз в час: гейт 08:00, по жителю — отдельная задача (fan-out)."""
    now = now or timezone.now()
    if not daily_due(now):
        return 0
    from .tasks import send_follow_digest_user

    period = period_key_daily(now)
    queued = 0
    for user_id in daily_candidates(now).values_list("pk", flat=True):
        send_follow_digest_user.delay(dedupe_key=f"follow:{user_id}:{period}", user_id=user_id)
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


def run_instant(now=None) -> int:
    now = now or timezone.now()
    if in_quiet_hours(now):
        return 0
    sent = 0
    users = PortalUser.objects.filter(
        is_active=True,
        follows__channel=FollowSubscription.CHANNEL_EMAIL,
        follows__frequency=FollowSubscription.FREQ_INSTANT,
    ).distinct()
    for user in users:
        try:
            if instant_for_user(user, now=now):
                sent += 1
        except Exception:  # noqa: BLE001 — один житель не валит обход
            log.exception("follow instant failed user=%s", user.pk)
    return sent


def purge(now=None) -> int:
    now = now or timezone.now()
    days = int(_cfg("digest_retention_days", 90))
    count, _ = FollowDigest.objects.filter(sent_at__lt=now - timedelta(days=days)).delete()
    return int(count)
