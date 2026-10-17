from django.apps import AppConfig


class PromotionsConfig(AppConfig):
    name = "apps.promotions"
    label = "promotions"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Д1 (T-8.10a): задача ИИ регистрируется при старте — её видят и веб, и Celery
        # (контракт AI-0: регистрация в ready(), не при импорте вьюхи).
        from . import (
            ai_draft,  # noqa: F401
            ai_text_check,  # noqa: F401 — D2a-3 «Text prüfen lassen»
        )
