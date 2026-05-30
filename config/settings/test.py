"""Настройки для тестов (pytest).

Проблема: django-tenants держит TENANT_APPS только в схемах арендаторов, а
pytest-django мигрирует public-БД → таблицы TENANT-приложений (catalog и т.д.)
в тестах отсутствуют. Роутер при этом обязателен (django-tenants падает без
него на старте).

Решение: в тестах объявляем ВСЕ приложения как SHARED (TENANT_APPS ⊆
SHARED_APPS). Тогда стандартный migrate создаёт все таблицы в public-схеме,
роутер остаётся на месте, а модели TENANT-приложений доступны напрямую.

Тесты изоляции арендаторов (transaction=True) всё равно поднимают реальные
схемы через auto_create_schema и проверяют разделение данных.
"""

from .development import *  # noqa: F401, F403
from .development import SHARED_APPS, TENANT_APPS

# Все tenant-приложения видны и как shared → их таблицы создаются в public.
SHARED_APPS = list(SHARED_APPS) + [a for a in TENANT_APPS if a not in SHARED_APPS]
INSTALLED_APPS = list(SHARED_APPS)
