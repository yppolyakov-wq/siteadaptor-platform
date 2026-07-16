"""Открытая allauth-регистрация закрыта (CRITICAL-1).

Регистрация бизнеса — только через BusinessSignupView (create_business). Штатный
allauth-signup на субдомене позволял анониму создать User в схеме тенанта → кабинет.
"""

from django.test import RequestFactory

from apps.tenants.adapters import AccountAdapter


def test_signup_is_closed():
    req = RequestFactory().get("/accounts/signup/")
    assert AccountAdapter().is_open_for_signup(req) is False
