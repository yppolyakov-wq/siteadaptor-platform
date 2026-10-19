from django.apps import AppConfig


class PlatformBotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.platform_bot"
    label = "platform_bot"
    verbose_name = "Telegram-Bot der Plattform"
