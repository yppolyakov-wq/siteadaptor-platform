"""Гейтинг подписки: при suspended/trial_expired кабинет владельца — read-only.

Блокирует небезопасные методы (POST/PUT/PATCH/DELETE) на путях кабинета, кроме
биллинга и аккаунта (чтобы можно было оплатить/выйти). Публичную витрину и
public-схему не трогает. Статус прокидывается в request для баннера
(см. context.subscription). Спецификация: roadmap §5.5, state-machine.md.
"""

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

from .state_machine import GATED_STATUSES

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
# Пути кабинета владельца, где блокируем запись при gated-статусе.
_CABINET_PREFIXES = ("/dashboard/", "/catalog/", "/imports/", "/promotions/")
# Остаются доступны даже при gated — оплата и выход из аккаунта.
_ALLOWED_WHILE_GATED = ("/dashboard/billing", "/accounts/")


class SubscriptionGatingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = getattr(request, "tenant", None)
        on_tenant = tenant is not None and getattr(tenant, "schema_name", "public") != "public"
        status = getattr(tenant, "subscription_status", "") if on_tenant else ""
        gated = status in GATED_STATUSES

        # Прокидываем для баннера и шаблонов (см. context.subscription).
        request.subscription_status = status
        request.subscription_gated = gated

        if (
            gated
            and request.method not in _SAFE_METHODS
            and request.path.startswith(_CABINET_PREFIXES)
            and not request.path.startswith(_ALLOWED_WHILE_GATED)
        ):
            messages.error(
                request,
                _("Ihr Abo ist inaktiv. Bitte aktivieren Sie es, um Änderungen vorzunehmen."),
            )
            return redirect("billing")

        return self.get_response(request)
