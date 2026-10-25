"""KA-12 E6.7g: ДОСТУП к контактам клиентов (e-mail, телефон) — по праву «Kontaktdaten der Kunden
sehen» (`kunden.kontakte`).

Решение владельца 2026-10-25: право по умолчанию у всех ролей (admin/staff), владелец
снимает его точечно. Без права контакты МАСКИРУЮТСЯ на всех поверхностях кабинета
(«•••@domain.de», «•••12»), поиск по ним не работает, а формы, где они правятся, их не
затирают (поля не показываются, сервер сохраняет прежние значения — инвариант W0).
"""

from apps.core import permissions
from apps.core.palette_search import mask_email, mask_phone

KEY = "kunden.kontakte"

__all__ = ["KEY", "can_see", "mask_email", "mask_phone", "kept"]


def can_see(user) -> bool:
    """Видит ли пользователь контакты. Не член команды — True (кабинет его не пускает)."""
    return permissions.chrome_allows(user, KEY)


def kept(user, customer, field: str, new_value: str) -> str:
    """Значение поля контакта для сохранения: без права — прежнее (форма поле не показывала)."""
    if can_see(user):
        return new_value
    return getattr(customer, field, "") or ""
