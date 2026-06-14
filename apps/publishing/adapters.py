"""Адаптеры каналов: type → publish/remove.

`log` — внутренний (ничего наружу не шлёт). `google_business` — Google Business
Profile (Track B1): акция публикуется локальным постом (Google Posts, classic
v4 API) с CTA-ссылкой на страницу акции; настройка и получение доступа —
docs/gbp-setup.md. `facebook`/`instagram` (M23a) — соц-постинг через Meta Graph
API: акция → пост на странице Facebook / в Instagram, завершение акции → пост
снимается (FB удаляется, IG — no-op: Graph API не умеет удалять органические
посты); настройка — docs/meta-social-setup.md. Адаптер возвращает external_ref
при publish и бросает исключение при ошибке (задача переведёт публикацию в
failed + last_error).
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
    # Платформенные ключи Google OAuth — из зашифрованного стора (админка) с
    # фолбэком на settings/.env (apps.secrets); per-tenant refresh_token — в config.
    from apps.secrets import store as secret_store

    response = requests.post(
        _GBP_TOKEN_URL,
        data={
            "client_id": secret_store.get_or_setting(
                "google_oauth_client_id", "GOOGLE_OAUTH_CLIENT_ID"
            ),
            "client_secret": secret_store.get_or_setting(
                "google_oauth_client_secret", "GOOGLE_OAUTH_CLIENT_SECRET"
            ),
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


# --- Meta: Facebook Pages / Instagram (M23a, Graph API) ----------------------

_META_API = "https://graph.facebook.com"
_IG_CAPTION_LIMIT = 2200  # лимит Instagram на текст подписи


def _meta_version() -> str:
    return getattr(settings, "META_GRAPH_API_VERSION", "v21.0")


def _promo_caption(promotion) -> str:
    text = promotion.title_text
    if promotion.description_text:
        text = f"{text}\n\n{promotion.description_text}"
    return text


def _promo_image_url(promotion) -> str:
    """Абсолютный URL главного фото акции (для фетча Meta). '' если фото нет.

    Относительный `/media/...` достраиваем доменом арендатора (public-схема),
    как и ссылку на акцию.
    """
    img = promotion.primary_image
    url = img.get("url") if img else None
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url

    from apps.tenants.models import Domain

    schema = connection.schema_name
    with schema_context("public"):
        domain = (
            Domain.objects.filter(tenant__schema_name=schema, is_primary=True).first()
            or Domain.objects.filter(tenant__schema_name=schema).first()
        )
    return f"https://{domain.domain}{url}" if domain else ""


def _fb_publish(publication) -> str:
    config = publication.channel.config or {}
    missing = [key for key in ("page_id", "access_token") if not config.get(key)]
    if missing:
        raise RuntimeError(f"Facebook nicht konfiguriert: {', '.join(missing)} fehlt")

    promotion = publication.promotion
    version = _meta_version()
    token = config["access_token"]
    caption = _promo_caption(promotion)
    link = _promo_public_url(promotion)
    image = _promo_image_url(promotion)

    if image:
        # /photos не принимает link → ссылку добавляем в текст подписи
        message = f"{caption}\n\n{link}".strip() if link else caption
        endpoint = f"{_META_API}/{version}/{config['page_id']}/photos"
        data = {"url": image, "caption": message, "access_token": token}
    else:
        endpoint = f"{_META_API}/{version}/{config['page_id']}/feed"
        data = {"message": caption, "access_token": token}
        if link:
            data["link"] = link

    response = requests.post(endpoint, data=data, timeout=20)
    response.raise_for_status()
    payload = response.json()
    return payload.get("post_id") or payload.get("id", "")


def _fb_remove(publication) -> None:
    config = publication.channel.config or {}
    # нет поста или канал разобран — снятие идемпотентно
    if not publication.external_ref or not config.get("access_token"):
        return
    response = requests.delete(
        f"{_META_API}/{_meta_version()}/{publication.external_ref}",
        params={"access_token": config["access_token"]},
        timeout=20,
    )
    if response.status_code != 404:  # 404 = пост уже удалён
        response.raise_for_status()


def _ig_publish(publication) -> str:
    config = publication.channel.config or {}
    missing = [key for key in ("ig_user_id", "access_token") if not config.get(key)]
    if missing:
        raise RuntimeError(f"Instagram nicht konfiguriert: {', '.join(missing)} fehlt")

    promotion = publication.promotion
    image = _promo_image_url(promotion)
    if not image:
        raise RuntimeError("Instagram benötigt ein Bild für die Aktion")

    version = _meta_version()
    ig_user = config["ig_user_id"]
    token = config["access_token"]
    caption = _promo_caption(promotion)
    link = _promo_public_url(promotion)
    if link:  # IG-Captions ohne klickbaren Link — URL als Text
        caption = f"{caption}\n\n{link}"

    # 1) контейнер медиа
    create = requests.post(
        f"{_META_API}/{version}/{ig_user}/media",
        data={"image_url": image, "caption": caption[:_IG_CAPTION_LIMIT], "access_token": token},
        timeout=20,
    )
    create.raise_for_status()
    creation_id = create.json()["id"]

    # 2) публикация контейнера
    publish = requests.post(
        f"{_META_API}/{version}/{ig_user}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=20,
    )
    publish.raise_for_status()
    return publish.json().get("id", "")


def _ig_remove(publication) -> None:
    # Graph API не удаляет органические IG-посты → снятие no-op (идемпотентно).
    return


# --- Telegram-канал бизнеса (M23, Bot API) -----------------------------------

_TG_API = "https://api.telegram.org"


def _tg_publish(publication) -> str:
    """Пост в Telegram-канал бизнеса. Бот должен быть админом канала.

    external_ref = «chat_id:message_id» (для удаления). С фото → sendPhoto,
    иначе sendMessage; ссылка на акцию — в тексте (Telegram кликабелен).
    """
    config = publication.channel.config or {}
    missing = [key for key in ("bot_token", "chat_id") if not config.get(key)]
    if missing:
        raise RuntimeError(f"Telegram nicht konfiguriert: {', '.join(missing)} fehlt")

    promotion = publication.promotion
    text = _promo_caption(promotion)
    link = _promo_public_url(promotion)
    if link:
        text = f"{text}\n\n{link}"
    image = _promo_image_url(promotion)
    token, chat_id = config["bot_token"], config["chat_id"]

    if image:
        endpoint = f"{_TG_API}/bot{token}/sendPhoto"
        data = {"chat_id": chat_id, "photo": image, "caption": text}
    else:
        endpoint = f"{_TG_API}/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": text}
    response = requests.post(endpoint, data=data, timeout=20)
    response.raise_for_status()
    result = response.json().get("result", {})
    message_id = result.get("message_id", "")
    return f"{chat_id}:{message_id}" if message_id else ""


def _tg_remove(publication) -> None:
    config = publication.channel.config or {}
    if not publication.external_ref or not config.get("bot_token"):
        return
    chat_id, _, message_id = publication.external_ref.rpartition(":")
    if not message_id:
        return
    response = requests.post(
        f"{_TG_API}/bot{config['bot_token']}/deleteMessage",
        data={"chat_id": chat_id, "message_id": message_id},
        timeout=20,
    )
    # 400 = сообщение уже удалено/недоступно → идемпотентно
    if response.status_code not in (200, 400):
        response.raise_for_status()


# --- Pinterest (M23, API v5) -------------------------------------------------

_PINTEREST_API = "https://api.pinterest.com/v5"


def _pinterest_publish(publication) -> str:
    """Создать Pin (картинка + ссылка на акцию). Pinterest требует изображение."""
    config = publication.channel.config or {}
    missing = [key for key in ("access_token", "board_id") if not config.get(key)]
    if missing:
        raise RuntimeError(f"Pinterest nicht konfiguriert: {', '.join(missing)} fehlt")

    promotion = publication.promotion
    image = _promo_image_url(promotion)
    if not image:
        raise RuntimeError("Pinterest benötigt ein Bild für die Aktion")

    body = {
        "board_id": config["board_id"],
        "title": promotion.title_text[:100],
        "description": promotion.description_text[:800],
        "media_source": {"source_type": "image_url", "url": image},
    }
    link = _promo_public_url(promotion)
    if link:
        body["link"] = link
    response = requests.post(
        f"{_PINTEREST_API}/pins",
        json=body,
        headers={"Authorization": f"Bearer {config['access_token']}"},
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("id", "")


def _pinterest_remove(publication) -> None:
    config = publication.channel.config or {}
    if not publication.external_ref or not config.get("access_token"):
        return
    response = requests.delete(
        f"{_PINTEREST_API}/pins/{publication.external_ref}",
        headers={"Authorization": f"Bearer {config['access_token']}"},
        timeout=20,
    )
    if response.status_code != 404:  # 404 = пин уже удалён
        response.raise_for_status()


# type → (publish, remove)
_ADAPTERS = {
    "log": (_log_publish, _log_remove),
    "google_business": (_gbp_publish, _gbp_remove),
    "facebook": (_fb_publish, _fb_remove),
    "instagram": (_ig_publish, _ig_remove),
    "telegram": (_tg_publish, _tg_remove),
    "pinterest": (_pinterest_publish, _pinterest_remove),
}


def publish(publication) -> str:
    """Опубликовать в канал; вернуть external_ref. Бросает при ошибке."""
    pub_fn, _ = _ADAPTERS[publication.channel.type]
    return pub_fn(publication) or ""


def remove(publication) -> None:
    """Снять из канала. Бросает при ошибке."""
    _, rm_fn = _ADAPTERS[publication.channel.type]
    rm_fn(publication)
