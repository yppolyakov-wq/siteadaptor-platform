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
            "allowed_updates": '["message", "my_chat_member"]',
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


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
