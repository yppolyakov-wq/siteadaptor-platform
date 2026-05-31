from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Customer, Promotion, Reservation


@admin.register(Customer)
class CustomerAdmin(ModelAdmin):
    list_display = ("__str__", "email", "phone", "created_at")
    search_fields = ("name", "email", "phone")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Promotion)
class PromotionAdmin(ModelAdmin):
    list_display = ("__str__", "promo_type", "status", "available_quantity", "starts_at", "ends_at")
    list_filter = ("status", "promo_type")
    autocomplete_fields = ("product",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Reservation)
class ReservationAdmin(ModelAdmin):
    list_display = ("reference_code", "promotion", "customer", "quantity", "status", "expires_at")
    list_filter = ("status",)
    search_fields = ("reference_code",)
    raw_id_fields = ("promotion", "customer")
    readonly_fields = ("created_at", "updated_at")
