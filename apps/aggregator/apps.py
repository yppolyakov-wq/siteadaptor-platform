from django.apps import AppConfig


class AggregatorConfig(AppConfig):
    name = "apps.aggregator"
    label = "aggregator"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Сброс кэша резолвера host→портал при изменении AggregatorPortal.
        from django.db.models.signals import post_delete, post_save

        from .middleware import clear_portal_cache
        from .models import AggregatorPortal

        post_save.connect(
            clear_portal_cache, sender=AggregatorPortal, dispatch_uid="agg_portal_cache_save"
        )
        post_delete.connect(
            clear_portal_cache, sender=AggregatorPortal, dispatch_uid="agg_portal_cache_delete"
        )
