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
