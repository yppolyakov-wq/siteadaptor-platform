"""In-app OAuth подключения каналов (OAuth-A): GBP + Pinterest.

Каркас: из кабинета арендатора уводим на провайдера (authorize_url с подписанным
state→схема), провайдер возвращает на ЕДИНЫЙ callback на основном домене
(обходит проблему redirect-URI на субдоменах, master-plan §8). Callback меняет
code на токен и кладёт его в Channel.config зашифрованным (apps.secrets).

Client-credentials провайдера — из зашифрованного стора (apps.secrets) с фолбэком
на settings/.env. Meta (FB/IG) — отдельно (OAuth-B): нужен обмен на page-токен.
"""

from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core import signing

from apps.secrets import store as secret_store

_STATE_SALT = "channel-oauth"
_STATE_MAX_AGE = 600  # 10 минут на прохождение OAuth

PROVIDERS = {
    "google_business": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/business.manage",
        "client_id": ("google_oauth_client_id", "GOOGLE_OAUTH_CLIENT_ID"),
        "client_secret": ("google_oauth_client_secret", "GOOGLE_OAUTH_CLIENT_SECRET"),
        "config_field": "refresh_token",  # куда в config кладём секрет
        "token_field": "refresh_token",  # какое поле ответа токена берём
        "authorize_extra": {"access_type": "offline", "prompt": "consent"},
        "token_auth": "params",
    },
    "pinterest": {
        "authorize_url": "https://www.pinterest.com/oauth/",
        "token_url": "https://api.pinterest.com/v5/oauth/token",
        "scope": "boards:read,pins:read,pins:write",
        "client_id": ("pinterest_client_id", "PINTEREST_CLIENT_ID"),
        "client_secret": ("pinterest_client_secret", "PINTEREST_CLIENT_SECRET"),
        "config_field": "access_token",
        "token_field": "access_token",
        "authorize_extra": {},
        "token_auth": "basic",
    },
}


def supports(provider: str) -> bool:
    return provider in PROVIDERS


def _cred(pair) -> str:
    key, settings_attr = pair
    return (
        secret_store.get_or_setting(key, settings_attr) if settings_attr else secret_store.get(key)
    )


def callback_base() -> str:
    return getattr(settings, "OAUTH_CALLBACK_BASE", "") or f"https://{settings.TENANT_DOMAIN_BASE}"


def redirect_uri(provider: str) -> str:
    # Фиксированный путь (без reverse): callback живёт в urls_public, а authorize
    # строится под urls_tenant — reverse там бы не нашёл имя.
    return f"{callback_base()}/oauth/{provider}/callback/"


def make_state(schema: str, provider: str) -> str:
    return signing.dumps({"s": schema, "p": provider}, salt=_STATE_SALT)


def read_state(state: str, provider: str) -> str | None:
    """Вернуть схему арендатора из state или None (битый/просроченный/чужой провайдер)."""
    try:
        data = signing.loads(state, salt=_STATE_SALT, max_age=_STATE_MAX_AGE)
    except (signing.BadSignature, signing.SignatureExpired):
        return None
    return data.get("s") if data.get("p") == provider else None


def authorize_url(provider: str, schema: str) -> str:
    cfg = PROVIDERS[provider]
    params = {
        "client_id": _cred(cfg["client_id"]),
        "redirect_uri": redirect_uri(provider),
        "response_type": "code",
        "scope": cfg["scope"],
        "state": make_state(schema, provider),
        **cfg["authorize_extra"],
    }
    return f"{cfg['authorize_url']}?{urlencode(params)}"


def exchange_code(provider: str, code: str) -> str:
    """Обменять authorization code на секретный токен (refresh/access)."""
    cfg = PROVIDERS[provider]
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(provider),
    }
    kwargs = {"timeout": 20}
    if cfg["token_auth"] == "basic":
        kwargs["auth"] = (_cred(cfg["client_id"]), _cred(cfg["client_secret"]))
    else:
        data["client_id"] = _cred(cfg["client_id"])
        data["client_secret"] = _cred(cfg["client_secret"])
    response = requests.post(cfg["token_url"], data=data, **kwargs)
    response.raise_for_status()
    return response.json().get(cfg["token_field"], "")


def store_token(provider: str, schema: str, token: str) -> None:
    """Положить токен в Channel.config (зашифрованным) в схеме арендатора + включить."""
    from django_tenants.utils import schema_context

    from apps.secrets import crypto

    from .models import Channel

    with schema_context(schema):
        channel, _ = Channel.objects.get_or_create(type=provider)
        config = dict(channel.config or {})
        config[PROVIDERS[provider]["config_field"]] = crypto.encrypt(token)
        channel.config = config
        channel.save(update_fields=["config", "updated_at"])


def tenant_channels_url(schema: str) -> str:
    """Абсолютный URL страницы каналов арендатора (для возврата после OAuth)."""
    from django_tenants.utils import schema_context

    from apps.tenants.models import Domain

    with schema_context("public"):
        domain = (
            Domain.objects.filter(tenant__schema_name=schema, is_primary=True).first()
            or Domain.objects.filter(tenant__schema_name=schema).first()
        )
    return f"https://{domain.domain}/dashboard/channels/" if domain else ""
