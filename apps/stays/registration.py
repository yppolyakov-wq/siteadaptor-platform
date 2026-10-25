"""G6 / KA-12 Z-6: данные Meldeschein из формы — один разбор для онлайн-регистрации гостя
(`public_views.unterkunft_checkin`) и ввода со стойки (`views.stay_action`)."""

from datetime import date


def _parse_date(raw):
    try:
        return date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


def fill(reg, post) -> None:
    """Перенести поля формы в GuestRegistration (с обрезкой по длинам модели)."""
    reg.last_name = post.get("last_name", "").strip()[:120]
    reg.first_name = post.get("first_name", "").strip()[:120]
    reg.birth_date = _parse_date(post.get("birth_date"))
    reg.nationality = post.get("nationality", "").strip()[:80]
    reg.street = post.get("street", "").strip()[:200]
    reg.postal_code = post.get("postal_code", "").strip()[:20]
    reg.city = post.get("city", "").strip()[:120]
    reg.country = post.get("country", "").strip()[:80]
    reg.doc_type = post.get("doc_type", "").strip()[:40]
    reg.doc_number = post.get("doc_number", "").strip()[:60]
    try:
        reg.accompanying = max(0, min(int(post.get("accompanying", "0")), 50))
    except (TypeError, ValueError):
        reg.accompanying = 0
