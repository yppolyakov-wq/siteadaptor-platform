"""SEC-E-M5 (аудит 2026-11-01): «проверенный отзыв» доказывается ссылкой из письма.

Раньше достаточно было ввести e-mail любого клиента (часто его знают соседи и
конкуренты): отзыв получал отметку «проверенный покупатель», а `update_or_create`
переписывал НАСТОЯЩИЙ отзыв этого клиента. Теперь доказательство — одно из двух:

- подписанная ссылка из письма «Wie war's?» (`?t=`; вид × сущность × клиент, 180 дней):
  GET кладёт разрешение в сессию и ведёт на форму;
- вход в личный кабинет клиента с этим e-mail.

E-mail отзыва берётся из доказательства, а не из поля формы.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.core import signing

SALT = "review-link"
MAX_AGE = 180 * 24 * 3600
SESSION_KEY = "review_grants"


def token(kind: str, entity_id, customer_pk) -> str:
    """Подписанный токен: вид × сущность × клиент (pk, не e-mail — ревью волны 3:
    подпись не шифрует, адрес читался бы из логов и пересланных писем)."""
    return signing.dumps({"k": kind, "i": str(entity_id), "c": str(customer_pk)}, salt=SALT)


def with_token(url: str, kind: str, entity_id, customer) -> str:
    """URL отзыва с токеном (для писем). Без клиента — URL как есть."""
    if not url or customer is None or not getattr(customer, "email", ""):
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{urlencode({'t': token(kind, entity_id, customer.pk)})}"


def _key(kind: str, entity_id) -> str:
    return f"{kind}:{entity_id}"


def grant_from_request(request, kind: str, entity_id) -> bool:
    """GET с `?t=`: верный токен для этой сущности → разрешение в сессии."""
    raw = request.GET.get("t") or ""
    if not raw or not hasattr(request, "session"):
        return False
    try:
        data = signing.loads(raw, salt=SALT, max_age=MAX_AGE)
    except signing.BadSignature:
        return False
    if data.get("k") != kind or data.get("i") != str(entity_id) or not data.get("c"):
        return False
    from apps.promotions.models import Customer

    email = Customer.objects.filter(pk=data["c"]).values_list("email", flat=True).first() or ""
    if not email:
        return False
    grant(request, kind, entity_id, email)
    return True


def grant(request, kind: str, entity_id, email: str):
    """Записать в сессию право на проверенный отзыв (после проверки токена)."""
    grants = dict(request.session.get(SESSION_KEY) or {})
    grants[_key(kind, entity_id)] = email.strip().lower()
    request.session[SESSION_KEY] = grants
    return request


def proven_email(request, kind: str, entity_id) -> str:
    """E-mail, которым посетитель доказал право на отзыв об этой сущности, или ''."""
    from apps.account import auth as account_auth

    # Вход в ЛК сильнее разрешения из ссылки: подброшенная ссылка (GET без CSRF) не
    # подменяет вошедшего клиента чужим адресом.
    customer = account_auth.current_customer(request)
    account_email = (getattr(customer, "email", "") or "").strip().lower()
    if account_email:
        return account_email
    grants = (getattr(request, "session", None) or {}).get(SESSION_KEY) or {}
    return grants.get(_key(kind, entity_id)) or ""
