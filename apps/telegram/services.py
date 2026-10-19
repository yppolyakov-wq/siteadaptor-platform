"""Telegram Bot API (M23/TG1): getMe / sendMessage / set-deleteWebhook + базовый URL.

Внешние вызовы изолированы здесь (в тестах застаблены). Webhook ставится на
домен арендатора (public-схема), как и публичные ссылки в publishing.adapters.
"""

import json

import requests
from django.db import connection
from django_tenants.utils import schema_context

_API = "https://api.telegram.org"


def _endpoint(token: str, method: str) -> str:
    return f"{_API}/bot{token}/{method}"


def get_me(token: str) -> dict:
    response = requests.get(_endpoint(token, "getMe"), timeout=15)
    response.raise_for_status()
    return response.json().get("result", {})


def leave_chat(token: str, chat_id) -> None:
    """T-8.10h: выйти из группы/канала (общий бот работает только в личных чатах).
    Ошибка не всплывает: в её тексте URL с токеном бота."""
    try:
        requests.post(_endpoint(token, "leaveChat"), data={"chat_id": chat_id}, timeout=10)
    except Exception:  # noqa: BLE001
        pass


def send_message(token: str, chat_id, text: str, reply_markup=None) -> dict:
    data = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup)
    response = requests.post(_endpoint(token, "sendMessage"), data=data, timeout=20)
    response.raise_for_status()
    return response.json().get("result", {})


def get_file_url(token: str, file_id: str) -> str:
    """Ссылка на скачивание файла из Telegram (MT-3b: фото/документы из группы).

    Bot API отдаёт файлы до 20 МБ; на больший файл вернём "" — вызывающий
    сохранит запись без вложения, а не потеряет сообщение целиком.
    """
    try:
        response = requests.get(
            _endpoint(token, "getFile"), params={"file_id": file_id}, timeout=20
        )
        response.raise_for_status()
        path = (response.json().get("result") or {}).get("file_path") or ""
    except Exception:  # noqa: BLE001 — мост не должен ронять приём апдейта
        return ""
    return f"{_API}/file/bot{token}/{path}" if path else ""


def set_webhook(token: str, url: str, secret_token: str) -> dict:
    response = requests.post(
        _endpoint(token, "setWebhook"),
        data={
            "url": url,
            "secret_token": secret_token,
            # T-8.10b: callback_query — нажатия кнопок превью акции (✅/❌).
            "allowed_updates": '["message", "my_chat_member", "callback_query"]',
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def answer_callback_query(token: str, callback_id: str, text: str = "") -> None:
    """Снять «часики» с кнопки (Telegram ждёт ответа на каждый callback)."""
    data = {"callback_query_id": callback_id}
    if text:
        data["text"] = text[:200]
    try:
        requests.post(_endpoint(token, "answerCallbackQuery"), data=data, timeout=10)
    except Exception:  # noqa: BLE001 — нажатие обработаем и без ответа на «часики»
        pass


def edit_message_reply_markup(token: str, chat_id, message_id, reply_markup=None) -> None:
    """Убрать (или заменить) кнопки под сообщением превью."""
    data = {"chat_id": chat_id, "message_id": message_id}
    data["reply_markup"] = json.dumps(reply_markup or {"inline_keyboard": []})
    try:
        requests.post(_endpoint(token, "editMessageReplyMarkup"), data=data, timeout=10)
    except Exception:  # noqa: BLE001 — кнопки останутся, повторное нажатие идемпотентно
        pass


CAPTION_MAX = 1024


def send_photo(token: str, chat_id, file_id: str, caption: str, reply_markup=None) -> dict:
    """Фото по `file_id` (без повторной загрузки) с подписью ≤ 1024 символов."""
    data = {"chat_id": chat_id, "photo": file_id, "caption": caption[:CAPTION_MAX]}
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup)
    response = requests.post(_endpoint(token, "sendPhoto"), data=data, timeout=20)
    response.raise_for_status()
    return response.json().get("result", {})


DOWNLOAD_MAX = 10 * 1024 * 1024


def download_file(token: str, file_id: str, max_bytes: int = DOWNLOAD_MAX) -> bytes | None:
    """Байты файла из Telegram (фото акции) или None. Хост — константа API (SSRF
    неприменим); URL файла содержит токен бота — в лог его НЕ пишем."""
    try:
        meta = requests.get(_endpoint(token, "getFile"), params={"file_id": file_id}, timeout=20)
        meta.raise_for_status()
        result = meta.json().get("result") or {}
        if int(result.get("file_size") or 0) > max_bytes:
            return None
        path = result.get("file_path") or ""
        if not path:
            return None
        with requests.get(f"{_API}/file/bot{token}/{path}", stream=True, timeout=30) as resp:
            resp.raise_for_status()
            chunks, size = [], 0
            for chunk in resp.iter_content(64 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    return None
                chunks.append(chunk)
        return b"".join(chunks)
    except Exception:  # noqa: BLE001 — без URL/трейсбэка: в них токен бота
        return None


def delete_webhook(token: str) -> dict:
    response = requests.post(_endpoint(token, "deleteWebhook"), timeout=20)
    response.raise_for_status()
    return response.json()


def tenant_base_url() -> str:
    """https://<домен арендатора> (для URL вебхука). '' если домена нет."""
    from apps.tenants.models import Domain

    schema = connection.schema_name
    with schema_context("public"):
        domain = (
            Domain.objects.filter(tenant__schema_name=schema, is_primary=True).first()
            or Domain.objects.filter(tenant__schema_name=schema).first()
        )
    return f"https://{domain.domain}" if domain else ""
