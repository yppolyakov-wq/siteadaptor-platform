"""Настройки локального стенда (Playwright): dev без debug_toolbar."""

from .development import *  # noqa: F403

INSTALLED_APPS = [a for a in INSTALLED_APPS if "debug_toolbar" not in a]  # noqa: F405
MIDDLEWARE = [m for m in MIDDLEWARE if "debug_toolbar" not in m]  # noqa: F405
