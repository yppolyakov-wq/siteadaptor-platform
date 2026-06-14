"""Зашифрованные платформенные секреты (SHARED), управляемые из админки.

Ключи интеграций (Google OAuth, Meta App, Stripe-вебхук и т.п.) хранятся
зашифрованными (Fernet) в public-схеме и редактируются в unfold-админке без
правки .env/кода. Значение никогда не отдаётся в UI (маскируется). Чтение —
через apps.secrets.store.get/get_or_setting (с фолбэком на settings/.env, чтобы
ничего не ломалось, пока секрет не задан в админке).
"""

from django.db import models

from apps.core.models import TimestampedModel

from . import crypto


class PlatformSecret(TimestampedModel):
    key = models.CharField(max_length=100, unique=True)  # напр. "google_oauth_client_secret"
    value_encrypted = models.TextField(blank=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return self.key

    def set_value(self, raw: str) -> None:
        self.value_encrypted = crypto.encrypt(raw or "")

    def get_value(self) -> str:
        return crypto.decrypt(self.value_encrypted)

    @property
    def is_set(self) -> bool:
        return bool(self.value_encrypted)
