from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Category, Product


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ("__str__", "slug", "parent", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("slug",)
    ordering = ("sort_order", "slug")


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ("__str__", "sku", "category", "base_price", "currency", "is_active")
    list_filter = ("is_active", "is_featured", "category")
    search_fields = ("sku",)
    autocomplete_fields = ("category",)
    readonly_fields = ("created_at", "updated_at")
