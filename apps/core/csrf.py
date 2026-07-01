"""Диагностическая страница ошибки CSRF (403).

Штатный 403 CSRF непрозрачен без DEBUG. Здесь — прод-безопасная страница, которая
показывает ТОЧНУЮ причину отказа Django (`reason`) и сигналы запроса, по которым
`CsrfViewMiddleware` принимает решение: пришла ли кука `csrftoken`, заголовки
Origin/Referer, распознан ли HTTPS за прокси (`is_secure`), какой хост. Этого
достаточно, чтобы за один заход отличить «Origin не в trusted origins» от «кука не
пришла» / «токен не совпал» — и чинить прицельно, без DEBUG и без доступа к логам.

Подключается через `settings.CSRF_FAILURE_VIEW`. Причину дополнительно пишем в лог
`django.security.csrf` (WARNING) — как и штатное поведение Django.
"""

import logging

from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.http import HttpResponseForbidden
from django.utils.html import escape

logger = logging.getLogger("django.security.csrf")


def _request_diagnostics(request, reason: str) -> dict:
    try:
        host = request.get_host()
    except DisallowedHost:
        host = f"<disallowed: {request._get_raw_host()!r}>"
    cookie_name = settings.CSRF_COOKIE_NAME
    return {
        "reason": reason,
        "path": request.path,
        "method": request.method,
        "host": host,
        "is_secure": request.is_secure(),
        "x_forwarded_proto": request.META.get("HTTP_X_FORWARDED_PROTO", ""),
        "origin": request.META.get("HTTP_ORIGIN", "<none>"),
        "referer": request.META.get("HTTP_REFERER", "<none>"),
        "csrf_cookie_received": cookie_name in request.COOKIES,
        "csrf_cookie_name": cookie_name,
    }


def csrf_failure(request, reason=""):
    """Прод-безопасная замена стандартной 403-страницы CSRF с диагностикой причины."""
    diag = _request_diagnostics(request, reason)
    logger.warning("CSRF failure: %s", diag)
    rows = "".join(
        f"<tr><td style='padding:2px 12px 2px 0;color:#6b7280'>{escape(str(k))}</td>"
        f"<td style='font-family:monospace'>{escape(str(v))}</td></tr>"
        for k, v in diag.items()
    )
    html = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>403 — Sicherheitsprüfung</title></head>
<body style="font-family:system-ui,sans-serif;max-width:640px;margin:48px auto;padding:0 16px;color:#111">
<h1 style="font-size:20px">Sitzung abgelaufen</h1>
<p style="color:#374151">Aus Sicherheitsgründen wurde die Anfrage abgebrochen. Bitte laden Sie die
Seite neu und versuchen Sie es erneut. Löschen die Cookies für diese Seite, falls es weiterhin auftritt.</p>
<details style="margin-top:20px"><summary style="cursor:pointer;color:#6b7280;font-size:13px">Technische Details</summary>
<table style="margin-top:8px;font-size:13px;border-collapse:collapse">{rows}</table></details>
</body></html>"""
    return HttpResponseForbidden(html)
