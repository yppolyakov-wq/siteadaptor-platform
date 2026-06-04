from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import (
    Customer,
    LoyaltyCard,
    LoyaltyProgram,
    Promotion,
    Reservation,
    Voucher,
    WaitlistEntry,
)


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


@admin.register(WaitlistEntry)
class WaitlistEntryAdmin(ModelAdmin):
    list_display = ("email", "name", "promotion", "notified", "created_at")
    list_filter = ("notified",)
    search_fields = ("email", "name")
    raw_id_fields = ("promotion",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Voucher)
class VoucherAdmin(ModelAdmin):
    list_display = ("code", "label", "used_count", "max_uses", "is_active", "expires_at")
    list_filter = ("is_active",)
    search_fields = ("code", "label")
    readonly_fields = ("created_at", "updated_at")


@admin.register(LoyaltyProgram)
class LoyaltyProgramAdmin(ModelAdmin):
    list_display = ("label", "stamps_required", "reward_label", "is_active")
    list_filter = ("is_active",)
    search_fields = ("label", "reward_label")
    readonly_fields = ("created_at", "updated_at")


@admin.register(LoyaltyCard)
class LoyaltyCardAdmin(ModelAdmin):
    list_display = ("customer", "program", "stamps", "rewards_earned")
    raw_id_fields = ("program", "customer")
    readonly_fields = ("created_at", "updated_at", "token")
