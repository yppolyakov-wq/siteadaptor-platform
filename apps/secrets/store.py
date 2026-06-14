"""Чтение платформенных секретов (с фолбэком на settings/.env).

Секреты лежат в public-схеме (SHARED), поэтому читаем в schema_context("public")
— аксессор безопасно вызывать и из схемы арендатора (адаптеры каналов и т.п.).
"""

from django.conf import settings
from django_tenants.utils import schema_context


def get(key: str, default: str = "") -> str:
    """Расшифрованное значение секрета по ключу или default, если не задан."""
    from .models import PlatformSecret

    with schema_context("public"):
        obj = PlatformSecret.objects.filter(key=key).first()
        if obj is not None and obj.is_set:
            return obj.get_value()
    return default


def get_or_setting(key: str, settings_attr: str) -> str:
    """Значение из админки, иначе из settings (.env). Не ломает прод до задания."""
    return get(key, default=getattr(settings, settings_attr, "") or "")
