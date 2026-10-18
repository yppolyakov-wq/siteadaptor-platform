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
from datetime import UTC, datetime, time
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
    complete: bool = True  # Google отдал все посты (иначе «удалено» не помечаем)
    updated: int = 0
    flagged_changed: int = 0
    flagged_gone: int = 0
    deferred: int = 0  # новые посты сверх лимита — придут следующим проходом


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


def _dt_key(value) -> str:
    """Дата для хеша — в UTC и до минуты: при импорте она в Europe/Berlin, из БД — в UTC, а
    поле формы `datetime-local` срезает секунды (23:59:59 → 23:59)."""
    if value is None:
        return ""
    return value.astimezone(UTC).replace(second=0, microsecond=0).isoformat()


def _text_key(value) -> dict:
    """Текст для хеша без шума формы: пустые локали отброшены (форма пишет все включённые
    языки), переводы строк \r\n → \n, пробелы по краям сняты."""
    if not isinstance(value, dict):
        return {}
    out = {}
    for locale, text in value.items():
        if isinstance(text, str):
            text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
            if text:
                out[str(locale)] = text
    return out


def content_hash(fields) -> str:
    """Отпечаток полей, которые может править владелец («Bei Google geändert»). Нормализован,
    чтобы пустой Save формы не делал черновик «правленым»."""
    payload = [
        _text_key(fields.get("title")),
        _text_key(fields.get("description")),
        _dt_key(fields.get("starts_at")),
        _dt_key(fields.get("ends_at")),
    ]
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _fields_of(promo) -> dict:
    return {
        "title": promo.title,
        "description": promo.description,
        "starts_at": promo.starts_at,
        "ends_at": promo.ends_at,
    }


def import_offers(channel, tenant, *, now=None) -> ImportResult:
    """Забрать Offer-посты локации: новые → черновики; изменённые → обновить нетронутый
    черновик или пометить; пропавшие (только при полном проходе) → пометить. Идемпотентно."""
    from apps.promotions.models import Promotion

    from .models import Publication
    from .secrets import decrypted_config

    now = now or timezone.now()
    config = decrypted_config(channel)
    v4, _v1 = gbp.location_ids(config)
    posts, complete = gbp.iter_local_posts(gbp.access_token(config), v4)
    result = ImportResult(complete=complete)
    dismissed = set(config.get("gbp_dismissed") or [])
    # Все имена ответа — любого типа и статуса: закончившийся или не-LIVE пост не «удалён».
    seen = {p["name"] for p in posts if isinstance(p, dict) and isinstance(p.get("name"), str)}
    imported = {
        pub.external_ref: pub.promotion_id
        for pub in Publication.objects.filter(
            channel=channel, dedupe_key__startswith=IMPORT_PREFIX
        ).only("external_ref", "promotion_id")
    }
    accepted = dict(
        Promotion.objects.filter(pk__in=imported.values()).values_list("pk", "metadata")
    )
    own = set(
        Publication.objects.filter(channel=channel, external_ref__in=seen)
        .exclude(dedupe_key__startswith=IMPORT_PREFIX)
        .values_list("external_ref", flat=True)
    )
    for post in posts:
        try:
            fields = post_to_draft_fields(post, tenant, now=now)
        except Exception as exc:  # noqa: BLE001 — один кривой пост не блокирует остальные
            logger.warning("gbp import: bad post skipped: %s", type(exc).__name__)
            fields = None
        if fields is None:
            continue
        name = fields["metadata"]["gbp_post"]
        if name in own or name in dismissed:
            result.skipped += 1
            continue
        if name in imported:
            if _unchanged(accepted.get(imported[name]), fields):
                continue  # та же версия поста и пометок нет — без блокировки строки
            outcome = _apply_change(imported[name], fields, now)
            if outcome == "updated":
                result.updated += 1
            elif outcome == "flagged":
                result.flagged_changed += 1
            continue
        if result.created >= MAX_CREATE_PER_RUN:
            result.deferred += 1  # лимит останавливает только создание, обход идёт дальше
            continue
        if _create(channel, name, fields):
            result.created += 1
        else:
            result.skipped += 1
    if complete:
        result.flagged_gone = _sync_gone(imported, seen, now)
    logger.info(
        "gbp import: posts=%s created=%s updated=%s changed=%s gone=%s deferred=%s complete=%s",
        len(posts),
        result.created,
        result.updated,
        result.flagged_changed,
        result.flagged_gone,
        result.deferred,
        complete,
    )
    return result


def _create(channel, name, fields) -> bool:
    from apps.promotions.models import Promotion

    from .models import Publication

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
        return False
    return True


_CHANGE_KEYS = ("gbp_changed", "gbp_changed_hash", "gbp_changed_at")
_IMPORT_KEYS = ("gbp_coupon_code", "gbp_redeem_url", "gbp_update_time")


def _unchanged(meta, fields) -> bool:
    """По снимку metadata (без блокировки): версия поста та же и пометок «изменено» нет."""
    if not isinstance(meta, dict):
        return False
    return meta.get("gbp_hash") == fields["metadata"]["gbp_hash"] and not any(
        k in meta for k in _CHANGE_KEYS
    )


def _apply_change(promotion_pk, fields, now) -> str:
    """Пост уже импортирован. Нетронутый владельцем черновик — обновить; правленый черновик и
    любая не-черновик акция — только пометка «Bei Google geändert» (содержимое не трогаем).
    Мягко удалённая акция не находится → «skip»."""
    from apps.promotions.models import Promotion

    new_hash = fields["metadata"]["gbp_hash"]
    with transaction.atomic():
        promo = Promotion.objects.select_for_update().filter(pk=promotion_pk).first()
        if promo is None:
            return "skip"
        meta = dict(promo.metadata) if isinstance(promo.metadata, dict) else {}
        accepted = meta.get("gbp_hash")
        if new_hash == accepted:
            if any(k in meta for k in _CHANGE_KEYS):  # Google вернул принятую версию
                for key in _CHANGE_KEYS:
                    meta.pop(key, None)
                Promotion.objects.filter(pk=promo.pk).update(metadata=meta)
            return "same"
        untouched = content_hash(_fields_of(promo)) == accepted
        if promo.status == "draft" and untouched:
            for key in (*_CHANGE_KEYS, *_IMPORT_KEYS):
                meta.pop(key, None)  # купон/ссылка, убранные в Google, уходят и у нас
            meta.update(fields["metadata"])
            for attr in ("title", "description", "starts_at", "ends_at"):
                setattr(promo, attr, fields[attr])
            promo.metadata = meta
            promo.save(
                update_fields=[
                    "title",
                    "description",
                    "starts_at",
                    "ends_at",
                    "metadata",
                    "updated_at",
                ]
            )
            return "updated"
        if new_hash == meta.get("gbp_ack_hash") or meta.get("gbp_changed_hash") == new_hash:
            return "same"
        meta.update(
            {"gbp_changed": True, "gbp_changed_hash": new_hash, "gbp_changed_at": now.isoformat()}
        )
        # .update(): без сигналов (активная акция не пересобирает листинги) и без updated_at.
        Promotion.objects.filter(pk=promo.pk).update(metadata=meta)
        return "flagged"


def _sync_gone(imported: dict, seen: set, now) -> int:
    """Только после ПОЛНОГО прохода: пометить импортированные акции, чьих постов больше нет у
    Google, и снять пометку у вернувшихся. Акция и пост у Google не удаляются (В-6)."""
    from apps.promotions.models import Promotion

    by_pk = {pk: name for name, pk in imported.items()}
    current = Promotion.objects.filter(pk__in=by_pk).values_list("pk", "metadata")
    # Один запрос на всё; блокировка — только у тех, чья пометка должна поменяться.
    todo = [
        pk
        for pk, meta in current
        if (by_pk[pk] not in seen) != bool(isinstance(meta, dict) and meta.get("gbp_gone"))
    ]
    flagged = 0
    for promotion_pk in todo:
        is_gone = by_pk[promotion_pk] not in seen
        with transaction.atomic():
            promo = Promotion.objects.select_for_update().filter(pk=promotion_pk).first()
            if promo is None:
                continue
            meta = dict(promo.metadata) if isinstance(promo.metadata, dict) else {}
            if is_gone and not meta.get("gbp_gone"):
                meta.update({"gbp_gone": True, "gbp_gone_at": now.isoformat()})
                flagged += 1
            elif not is_gone and meta.get("gbp_gone"):
                meta.pop("gbp_gone", None)
                meta.pop("gbp_gone_at", None)
            else:
                continue
            Promotion.objects.filter(pk=promo.pk).update(metadata=meta)
    return flagged


def ack_change(promotion_pk) -> None:
    """«Ausblenden»: скрыть пометку «Bei Google geändert» до следующей версии поста."""
    from apps.promotions.models import Promotion

    with transaction.atomic():
        promo = Promotion.objects.select_for_update().get(pk=promotion_pk)
        meta = dict(promo.metadata) if isinstance(promo.metadata, dict) else {}
        if meta.get("source") != "gbp":
            raise ValueError("not a gbp promotion")
        if meta.get("gbp_changed_hash"):
            meta["gbp_ack_hash"] = meta["gbp_changed_hash"]
        for key in _CHANGE_KEYS:
            meta.pop(key, None)
        Promotion.objects.filter(pk=promo.pk).update(metadata=meta)


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
