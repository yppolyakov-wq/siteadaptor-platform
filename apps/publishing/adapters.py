"""Адаптеры каналов: type → publish/remove.

`log` — внутренний (ничего наружу не шлёт). `google_business` — Google Business
Profile (Track B1): акция публикуется локальным постом (Google Posts, classic
v4 API) с CTA-ссылкой на страницу акции; настройка и получение доступа —
docs/gbp-setup.md. Остальные внешние адаптеры (Instagram и т.п.) — Phase 2
(P2.9). Адаптер возвращает external_ref при publish и бросает исключение при
ошибке (задача переведёт публикацию в failed + last_error).
"""

import logging

import requests
from django.conf import settings
from django.db import connection
from django_tenants.utils import schema_context

logger = logging.getLogger("publishing")

# --- log (внутренний) --------------------------------------------------------


def _log_publish(publication) -> str:
    logger.info("publish promo=%s channel=%s", publication.promotion_id, publication.channel_id)
    return f"log:{publication.promotion_id}:{publication.channel_id}"


def _log_remove(publication) -> None:
    logger.info("remove promo=%s channel=%s", publication.promotion_id, publication.channel_id)


# --- google_business (Google Posts) ------------------------------------------

_GBP_API = "https://mybusiness.googleapis.com/v4"
_GBP_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GBP_SUMMARY_LIMIT = 1500  # лимит Google на текст localPost


def _promo_public_url(promotion) -> str:
    """Абсолютная ссылка на страницу акции (домен арендатора из public-схемы)."""
    from apps.tenants.models import Domain

    schema = connection.schema_name
    with schema_context("public"):
        domain = (
            Domain.objects.filter(tenant__schema_name=schema, is_primary=True).first()
            or Domain.objects.filter(tenant__schema_name=schema).first()
        )
    return f"https://{domain.domain}/p/{promotion.id}/" if domain else ""


def _gbp_access_token(config) -> str:
    response = requests.post(
        _GBP_TOKEN_URL,
        data={
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "refresh_token": config["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _gbp_publish(publication) -> str:
    config = publication.channel.config or {}
    missing = [key for key in ("location", "refresh_token") if not config.get(key)]
    if missing:
        raise RuntimeError(f"GBP nicht konfiguriert: {', '.join(missing)} fehlt")

    promotion = publication.promotion
    summary = promotion.title_text
    if promotion.description_text:
        summary = f"{summary}\n\n{promotion.description_text}"
    body = {
        "languageCode": "de",
        "topicType": "STANDARD",
        "summary": summary[:_GBP_SUMMARY_LIMIT],
    }
    promo_url = _promo_public_url(promotion)
    if promo_url:
        body["callToAction"] = {"actionType": "LEARN_MORE", "url": promo_url}

    token = _gbp_access_token(config)
    response = requests.post(
        f"{_GBP_API}/{config['location']}/localPosts",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("name", "")


def _gbp_remove(publication) -> None:
    config = publication.channel.config or {}
    # нет поста или канал разобран — снятие считаем выполненным (идемпотентно)
    if not publication.external_ref or not config.get("refresh_token"):
        return
    token = _gbp_access_token(config)
    response = requests.delete(
        f"{_GBP_API}/{publication.external_ref}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    if response.status_code != 404:  # 404 = пост уже удалён
        response.raise_for_status()


# type → (publish, remove)
_ADAPTERS = {
    "log": (_log_publish, _log_remove),
    "google_business": (_gbp_publish, _gbp_remove),
}


def publish(publication) -> str:
    """Опубликовать в канал; вернуть external_ref. Бросает при ошибке."""
    pub_fn, _ = _ADAPTERS[publication.channel.type]
    return pub_fn(publication) or ""


def remove(publication) -> None:
    """Снять из канала. Бросает при ошибке."""
    _, rm_fn = _ADAPTERS[publication.channel.type]
    rm_fn(publication)
