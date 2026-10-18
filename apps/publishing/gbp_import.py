"""Offer-посты Google Business Profile → черновики акций (Д3-3, план
docs/d3-gbp-sync-plan-2026-10-18.md §4).

Решения владельца: только черновик (активирует владелец), без миграции (В-8) — журнал импорта —
`Publication(dedupe_key="gbp-import:<имя поста>", status=published)`; он же не даёт повторно
запостить акцию при активации (`_do_publish` берёт только queued, `services._publish_all` не
возвращает такую публикацию в очередь) и не даёт удалить пост владельца при окончании (В-6).
Код купона и условия — текстом в описании и в metadata (В-9).

Текст Google — недоверенные ДАННЫЕ: без тегов, без управляющих и невидимых символов, с лимитами
длины, только автоэкранирование при выводе; в ИИ не передаётся. Цен и процентов не выдумываем:
у оффера Google их нет в структуре (PAngV — никакого «statt» из догадок)."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import unicodedata
from dataclasses import dataclass
from datetime import datetime, time
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.html import strip_tags

from . import gbp

logger = logging.getLogger("publishing")

TITLE_MAX = 200
DESCRIPTION_MAX = 4000
FALLBACK_TITLE_MAX = 80
DISMISS_MAX = 300
MAX_CREATE_PER_RUN = 50  # черновиков за одно нажатие; остальные — следующим проходом
YEAR_MIN, YEAR_MAX = 2000, 2100
BERLIN = ZoneInfo("Europe/Berlin")
IMPORT_PREFIX = "gbp-import:"


@dataclass
class ImportResult:
    created: int = 0
    skipped: int = 0
    complete: bool = True


def clean_text(value, limit: int) -> str:
    """Внешний текст → безопасная строка: без тегов, управляющих (кроме \\n) и форматирующих
    символов (нулевой ширины, переворот направления), NFC, с лимитом длины."""
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFC", strip_tags(value))
    text = "".join(
        ch for ch in text if ch == "\n" or unicodedata.category(ch) not in ("Cc", "Cf", "Co", "Cs")
    )
    lines = [" ".join(line.split()) for line in text.split("\n")]
    text = "\n".join(lines).strip()
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text[:limit].rstrip()


def _date_time(date, tod, *, end: bool) -> datetime | None:
    if not isinstance(date, dict):
        return None
    try:
        year, month, day_n = int(date["year"]), int(date["month"]), int(date["day"])
        if not YEAR_MIN <= year <= YEAR_MAX:
            return None
        day = datetime(year, month, day_n).date()
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    clock = time(23, 59, 59) if end else time(0, 0)
    if isinstance(tod, dict) and tod:
        try:
            hours, minutes = int(tod.get("hours", 0)), int(tod.get("minutes", 0))
            if 0 <= hours < 24 and 0 <= minutes < 60:
                clock = time(hours, minutes)
        except (TypeError, ValueError, OverflowError):
            pass
    return datetime.combine(day, clock, tzinfo=BERLIN)


def _public_url(url) -> str:
    """https-ссылка с обычным именем хоста или ''. Ссылка только показывается текстом и
    никогда не запрашивается сервером, поэтому без DNS (резолв 500 чужих имён в веб-запросе
    был бы дорог): отбрасываем не-https, userinfo, порты и IP-адреса."""
    if not isinstance(url, str) or len(url) > 500 or not url.startswith("https://"):
        return ""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return ""
    if not host or "@" in parts.netloc or port is not None or "." not in host:
        return ""
    try:
        ipaddress.ip_address(host)
        return ""  # голый IP — не адрес бизнеса
    except ValueError:
        pass
    if any(ch.isspace() or unicodedata.category(ch)[0] == "C" for ch in url):
        return ""
    return url


def _locale(post, tenant) -> str:
    raw = post.get("languageCode")
    code = raw.split("-")[0].lower() if isinstance(raw, str) else ""
    active = getattr(tenant, "active_locales", None) or []
    return code if code and code in active else settings.LANGUAGE_CODE


def post_to_draft_fields(post, tenant, *, now) -> dict | None:
    """Поля черновика из Offer-поста или None (не оффер, не LIVE, закончился, без имени)."""
    if (
        not isinstance(post, dict)
        or post.get("topicType") != "OFFER"
        or post.get("state") != "LIVE"
    ):
        return None
    name = post.get("name")
    if not isinstance(name, str) or not name or len(name) > 190:
        return None
    event = post.get("event") if isinstance(post.get("event"), dict) else {}
    schedule = event.get("schedule") if isinstance(event.get("schedule"), dict) else {}
    starts = _date_time(schedule.get("startDate"), schedule.get("startTime"), end=False)
    ends = _date_time(schedule.get("endDate"), schedule.get("endTime"), end=True)
    if ends is not None and ends <= now:
        return None
    if starts is not None and ends is not None and starts > ends:
        starts = None
    summary = clean_text(post.get("summary"), DESCRIPTION_MAX)
    title = " ".join(clean_text(event.get("title"), TITLE_MAX).split())  # заголовок — одна строка
    if not title:
        title = clean_text(summary.split("\n", 1)[0], FALLBACK_TITLE_MAX)
    if not title:
        return None
    offer = post.get("offer") if isinstance(post.get("offer"), dict) else {}
    terms = clean_text(offer.get("termsConditions"), 1000)
    coupon = clean_text(offer.get("couponCode"), 60)
    parts = [summary]
    if terms:
        parts.append(f"Bedingungen: {terms}")
    if coupon:
        parts.append(f"Code: {coupon}")
    description = "\n\n".join(p for p in parts if p)[:DESCRIPTION_MAX]
    lang = _locale(post, tenant)
    metadata = {
        "source": "gbp",
        "gbp_post": name,
        "gbp_update_time": clean_text(post.get("updateTime"), 40),
    }
    if coupon:
        metadata["gbp_coupon_code"] = coupon
    redeem = _public_url(offer.get("redeemOnlineUrl"))
    if redeem:
        metadata["gbp_redeem_url"] = redeem[:500]
    fields = {
        "title": {lang: title},
        "description": {lang: description} if description else {},
        "starts_at": starts,
        "ends_at": ends,
        "metadata": metadata,
    }
    metadata["gbp_hash"] = content_hash(fields)
    return fields


def content_hash(fields) -> str:
    """Отпечаток полей, которые может править владелец (для «Bei Google geändert», D3-4)."""
    payload = [
        fields.get("title"),
        fields.get("description"),
        str(fields.get("starts_at")),
        str(fields.get("ends_at")),
    ]
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def import_offers(channel, tenant, *, now=None) -> ImportResult:
    """Забрать Offer-посты локации и создать черновики для новых. Идемпотентно."""
    from apps.promotions.models import Promotion

    from .models import Publication
    from .secrets import decrypted_config

    now = now or timezone.now()
    config = decrypted_config(channel)
    v4, _v1 = gbp.location_ids(config)
    posts, complete = gbp.iter_local_posts(gbp.access_token(config), v4)
    result = ImportResult(complete=complete)
    dismissed = set(config.get("gbp_dismissed") or [])
    names = [p.get("name") for p in posts if isinstance(p, dict) and isinstance(p.get("name"), str)]
    known = set(
        Publication.objects.filter(channel=channel, external_ref__in=names).values_list(
            "external_ref", flat=True
        )
    )
    for post in posts:
        if result.created >= MAX_CREATE_PER_RUN:
            result.complete = False
            break
        try:
            fields = post_to_draft_fields(post, tenant, now=now)
        except Exception as exc:  # noqa: BLE001 — один кривой пост не блокирует остальные
            logger.warning("gbp import: bad post skipped: %s", type(exc).__name__)
            fields = None
        if fields is None:
            continue
        name = fields["metadata"]["gbp_post"]
        # Свой пост (опубликованный нами) или уже импортированный — не трогаем.
        if name in known or name in dismissed:
            result.skipped += 1
            continue
        try:
            with transaction.atomic():
                promo = Promotion.objects.create(
                    status="draft", promo_type=Promotion.DISCOUNT, **fields
                )
                Publication.objects.create(
                    promotion=promo,
                    channel=channel,
                    status="published",
                    external_ref=name,
                    dedupe_key=f"{IMPORT_PREFIX}{name}",
                )
        except IntegrityError:  # параллельный импорт успел раньше
            result.skipped += 1
            continue
        result.created += 1
    logger.info(
        "gbp import: posts=%s created=%s skipped=%s complete=%s",
        len(posts),
        result.created,
        result.skipped,
        complete,
    )
    return result


def is_imported(publication) -> bool:
    """Публикация — журнал импорта поста владельца, а не наш пост (её нельзя ни постить,
    ни удалять у Google). Единая проверка для services и adapters."""
    return bool((publication.dedupe_key or "").startswith(IMPORT_PREFIX))


def dismiss(channel_pk, promotion_pk) -> None:
    """«Nicht übernehmen»: черновик удаляется (мягко), пост больше не импортируется.
    Только черновик из Google — статус перепроверяется под блокировкой строки (владелец мог
    активировать его в соседней вкладке)."""
    from apps.promotions.models import Promotion

    from .models import Channel

    with transaction.atomic():
        promotion = Promotion.objects.select_for_update().get(pk=promotion_pk)
        meta = promotion.metadata if isinstance(promotion.metadata, dict) else {}
        name = meta.get("gbp_post")
        if promotion.status != "draft" or meta.get("source") != "gbp" or not name:
            raise ValueError("not a gbp draft")

        def mutate(config):
            names = [n for n in (config.get("gbp_dismissed") or []) if n != name]
            config["gbp_dismissed"] = (names + [name])[-DISMISS_MAX:]

        Channel.update_config(channel_pk, mutate)
        promotion.delete()
