from django.apps import AppConfig


class InboxConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inbox"

    def ready(self):
        # T-8.10g: задача ИИ регистрируется при старте — и в Celery-воркере.
        from . import ai_reply  # noqa: F401
