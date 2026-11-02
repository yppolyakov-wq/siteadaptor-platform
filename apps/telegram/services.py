"""Telegram Bot API (M23/TG1): getMe / sendMessage / set-deleteWebhook + базовый URL.

Внешние вызовы изолированы здесь (в тестах застаблены). Webhook ставится на
домен арендатора (public-схема), как и публичные ссылки в publishing.adapters.

SEC-A1 (аудит безопасности 2026-11-01): URL каждого вызова содержит токен бота, а текст
`requests.HTTPError`/`ConnectionError` — этот URL. Поэтому наружу из модуля уходит ТОЛЬКО
`TelegramAPIError` без URL и без цепочки исключений (`from None`); у ошибки есть `.status`
и `.response` (объект ответа, его `str()` — `<Response [403]>`). Любой `logger.exception`
вокруг вызовов Telegram по-прежнему запрещён замком (`test_sec_a_token_leak`).
"""

import json
import re
from types import SimpleNamespace

import requests
from django.db import connection
from django_tenants.utils import schema_context

_API = "https://api.telegram.org"
_TOKEN_RE = re.compile(r"bot\d+:[A-Za-z0-9_-]+")


def scrub(text) -> str:
    """Замаскировать токен бота в произвольном тексте (логи, last_error, Sentry)."""
    return _TOKEN_RE.sub("bot<token>", str(text or ""))


class TelegramAPIError(requests.RequestException):
    """Ошибка Bot API без URL (= без токена). `status` — HTTP-код или None (сеть/таймаут)."""

    def __init__(self, method: str, status: int | None = None, kind: str = "", response=None):
        self.method = method
        self.status = status
        self.kind = kind
        super().__init__(f"telegram {method} failed ({status or kind or 'error'})")
        # requests.RequestException.__init__ кладёт response/request в атрибуты только из
        # kwargs; URL в объекте ответа есть, но в текст исключения он не попадает.
        self.response = response
        self.request = None


def header_secret(path_secret: str) -> str:
    """SEC-A4 (аудит 2026-11-01): секрет заголовка X-Telegram-Bot-Api-Secret-Token —
    производный от секрета пути, а не он сам. Путь вебхука виден в логах прокси/404;
    раньше этого было достаточно, чтобы подделать запрос от Telegram."""
    import base64
    import hashlib
    import hmac

    from django.conf import settings

    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        b"tg-webhook-header:" + str(path_secret or "").encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def header_ok(header: str, path_secret: str) -> bool:
    """Заголовок вебхука верен: производный секрет; до перерегистрации вебхуков
    (`telegram_resync_webhooks --apply`) — и прежний (= путь), пока включён
    `TELEGRAM_WEBHOOK_LEGACY_HEADER`."""
    import hmac

    from django.conf import settings

    got = str(header or "").encode("utf-8")
    if not path_secret or not got:
        return False
    if hmac.compare_digest(got, header_secret(path_secret).encode("utf-8")):
        return True
    legacy = getattr(settings, "TELEGRAM_WEBHOOK_LEGACY_HEADER", True)
    return bool(legacy) and hmac.compare_digest(got, str(path_secret).encode("utf-8"))


def _endpoint(token: str, method: str) -> str:
    return f"{_API}/bot{token}/{method}"


def _call(http, token: str, method: str, **kwargs):
    """HTTP-вызов Bot API; любая ошибка → TelegramAPIError без URL и без контекста."""
    error = None
    try:
        response = http(_endpoint(token, method), **kwargs)
        response.raise_for_status()
    except requests.HTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        # Живой Response несёт URL с токеном (response.url, request.url) — наружу только код.
        error = TelegramAPIError(
            method, status=status, response=SimpleNamespace(status_code=status)
        )
    except requests.RequestException as exc:
        error = TelegramAPIError(method, kind=type(exc).__name__)
    if error is not None:
        # Поднимаем ВНЕ `except`: иначе Python положит исходное исключение (с URL и
        # токеном) в `__context__`, и трейсбэк/Sentry всё равно его напечатают.
        raise error
    return response


def get_me(token: str) -> dict:
    return _call(requests.get, token, "getMe", timeout=15).json().get("result", {})


def leave_chat(token: str, chat_id) -> None:
    """T-8.10h: выйти из группы/канала (общий бот работает только в личных чатах).
    Ошибка не всплывает."""
    try:
        _call(requests.post, token, "leaveChat", data={"chat_id": chat_id}, timeout=10)
    except Exception:  # noqa: BLE001
        pass


def send_message(token: str, chat_id, text: str, reply_markup=None) -> dict:
    data = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup)
    return (
        _call(requests.post, token, "sendMessage", data=data, timeout=20).json().get("result", {})
    )


def set_webhook(token: str, url: str, secret_token: str) -> dict:
    return _call(
        requests.post,
        token,
        "setWebhook",
        data={
            "url": url,
            "secret_token": secret_token,
            # T-8.10b: callback_query — нажатия кнопок превью акции (✅/❌).
            "allowed_updates": '["message", "my_chat_member", "callback_query"]',
        },
        timeout=20,
    ).json()


def answer_callback_query(token: str, callback_id: str, text: str = "") -> None:
    """Снять «часики» с кнопки (Telegram ждёт ответа на каждый callback)."""
    data = {"callback_query_id": callback_id}
    if text:
        data["text"] = text[:200]
    try:
        _call(requests.post, token, "answerCallbackQuery", data=data, timeout=10)
    except Exception:  # noqa: BLE001 — нажатие обработаем и без ответа на «часики»
        pass


def edit_message_reply_markup(token: str, chat_id, message_id, reply_markup=None) -> None:
    """Убрать (или заменить) кнопки под сообщением превью."""
    data = {"chat_id": chat_id, "message_id": message_id}
    data["reply_markup"] = json.dumps(reply_markup or {"inline_keyboard": []})
    try:
        _call(requests.post, token, "editMessageReplyMarkup", data=data, timeout=10)
    except Exception:  # noqa: BLE001 — кнопки останутся, повторное нажатие идемпотентно
        pass


CAPTION_MAX = 1024


def send_document(token: str, chat_id, filename: str, content: bytes, caption: str = "") -> dict:
    """T-8.10h H-7i: файл в чат (выгрузка данных Art. 15/20). Telegram хранит файл у себя —
    это сказано пользователю в тексте рядом."""
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption[:CAPTION_MAX]
    response = _call(
        requests.post,
        token,
        "sendDocument",
        data=data,
        files={"document": (filename, content, "application/json")},
        timeout=30,
    )
    return response.json().get("result", {})


def send_photo(token: str, chat_id, file_id: str, caption: str, reply_markup=None) -> dict:
    """Фото по `file_id` (без повторной загрузки) с подписью ≤ 1024 символов."""
    data = {"chat_id": chat_id, "photo": file_id, "caption": caption[:CAPTION_MAX]}
    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup)
    return _call(requests.post, token, "sendPhoto", data=data, timeout=20).json().get("result", {})


DOWNLOAD_MAX = 10 * 1024 * 1024


def download_file(token: str, file_id: str, max_bytes: int = DOWNLOAD_MAX) -> bytes | None:
    """Байты файла из Telegram (фото акции) или None. Хост — константа API (SSRF
    неприменим); URL файла содержит токен бота — в лог его НЕ пишем."""
    try:
        meta = _call(requests.get, token, "getFile", params={"file_id": file_id}, timeout=20)
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


def set_my_commands(token: str, commands: list[dict], language_code: str = "") -> None:
    """Меню команд бота (T-8.10h H-6); описания — на языке пользователя Telegram."""
    data = {"commands": json.dumps(commands)}
    if language_code:
        data["language_code"] = language_code
    _call(requests.post, token, "setMyCommands", data=data, timeout=5)


def set_chat_menu_button(token: str, *, url: str, text: str) -> None:
    """T-8.30: кнопка меню всех личных чатов бота — открывает Mini App (web_app)."""
    button = {"type": "web_app", "text": text, "web_app": {"url": url}}
    _call(
        requests.post,
        token,
        "setChatMenuButton",
        data={"menu_button": json.dumps(button)},
        timeout=5,
    )


def get_webhook_info(token: str, timeout: int = 15) -> dict:
    return _call(requests.get, token, "getWebhookInfo", timeout=timeout).json().get("result", {})


def delete_webhook(token: str) -> dict:
    return _call(requests.post, token, "deleteWebhook", timeout=20).json()


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
