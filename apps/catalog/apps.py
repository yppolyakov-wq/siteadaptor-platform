from django.apps import AppConfig


class CatalogConfig(AppConfig):
    name = "apps.catalog"
    label = "catalog"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # §11 PAngV (M1): лог цен при сохранении товара/варианта (админка, формы,
        # импорт, сидер — один путь через post_save; запись только при изменении).
        # Ресиверы — модульного уровня (weak-ссылки сигналов собирают локальные).
        from django.db.models.signals import post_save

        from apps.catalog import price_history
        from apps.catalog.models import Product, ProductVariant

        post_save.connect(
            price_history._on_product_save, sender=Product, dispatch_uid="pricelog_product"
        )
        post_save.connect(
            price_history._on_variant_save, sender=ProductVariant, dispatch_uid="pricelog_variant"
        )
