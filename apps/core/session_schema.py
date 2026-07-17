"""HIGH-10: привязка Django-сессии к схеме тенанта, в которой создан логин.

`django.contrib.auth` — TENANT-приложение: у каждой схемы свой `auth_user` с
независимым автоинкрементом, поэтому owner A pk=1 ≠ owner B pk=1. Сессии лежат в
ОБЩЕМ Redis и несут лишь `_auth_user_id`. Сегодня изоляцию держит host-only cookie
(`SESSION_COOKIE_DOMAIN` не задан). Если его когда-нибудь расширят до
`.siteadaptor.de` (частая правка ради SSO между субдоменами), кука owner A уйдёт на
субдомен B и `AuthenticationMiddleware` аутентифицирует её как owner B (тот же pk).

Защита (defense-in-depth): на логине штампуем текущую схему в сессию
(`user_logged_in`), а `SessionSchemaGuardMiddleware` сбрасывает сессию, пришедшую на
ДРУГУЮ схему. Легаси-сессии без штампа не трогаем — они проставятся при следующем
логине, а host-only cookie их и так изолирует. Инвариант «не задавать
SESSION_COOKIE_DOMAIN» дополнительно защищён system-check'ом (apps/core/checks.py).
"""

from django.contrib.auth.signals import user_logged_in
from django.db import connection

SESSION_SCHEMA_KEY = "_schema"


def stamp_session_schema(sender, request, user, **kwargs):
    """`user_logged_in`-приёмник: записать схему логина в сессию."""
    session = getattr(request, "session", None)
    if session is not None:
        session[SESSION_SCHEMA_KEY] = connection.schema_name


def connect():
    user_logged_in.connect(stamp_session_schema, dispatch_uid="core.stamp_session_schema")
