"""Allauth-адаптер аккаунта: закрывает открытую саморегистрацию.

Регистрация бизнеса идёт ТОЛЬКО через `BusinessSignupView` (`/registrieren/` на
public-схеме → `create_business`, который заводит владельца с ролью Owner). Штатная
открытая регистрация allauth (`/accounts/signup/`) была смонтирована и на каждом
субдомене тенанта (`config/urls_tenant.py`), что позволяло анониму создать `User`
ВНУТРИ схемы тенанта и попасть в кабинет владельца (единственный гейт кабинета —
`@login_required`). Поэтому глушим `is_open_for_signup` на всех схемах; логин,
сброс пароля и подтверждение e-mail продолжают работать штатно.
"""

from allauth.account.adapter import DefaultAccountAdapter


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False
