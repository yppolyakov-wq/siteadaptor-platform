"""Стенд: dev-настройки БЕЗ django-debug-toolbar.

Зачем: toolbar регистрирует свои URL только под главным URLconf. На субдомене
тенанта работает `urls_tenant`, namespace `djdt` там отсутствует, и КАЖДАЯ
страница витрины отдаёт 500 («'djdt' is not a registered namespace») — при
браузерном стенде это выглядит как поломка витрины, хотя ломается только
toolbar. Для сверки внешнего вида она не нужна.

Использование:

    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand

Модуль ничем не импортируется — на CI и в проде не участвует.
"""

from config.settings.development import *  # noqa: F401,F403

INSTALLED_APPS = [a for a in INSTALLED_APPS if a != "debug_toolbar"]  # noqa: F405
MIDDLEWARE = [m for m in MIDDLEWARE if "debug_toolbar" not in m]  # noqa: F405

# Стенд хранит медиа на диске (development) — раздаёт их сам, даже если в окружении
# задан ключ S3 (иначе картинки на стенде отдают 404).
SERVE_MEDIA = True

# FB-33 M5a: `handler404` Django зовёт только при DEBUG=False (иначе — отладочная 404), поэтому
# стенд страницы 404 поднимает сервер с `STAND_DEBUG=0` (и `runserver --insecure` — статика).
# Без переменной стенд прежний (DEBUG=True) — остальным стендам ничего не меняется.
import os as _os  # noqa: E402

if _os.environ.get("STAND_DEBUG") == "0":
    DEBUG = False
    # без DEBUG манифестное хранилище статики требует `collectstatic` — стенду хватает простого
    STORAGES = {  # noqa: F405
        **STORAGES,  # noqa: F405
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
