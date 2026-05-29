from django.apps import AppConfig


class WebhooksConfig(AppConfig):
    name = "apps.integrations.webhooks"
    label = "webhooks"
    default_auto_field = "django.db.models.BigAutoField"
