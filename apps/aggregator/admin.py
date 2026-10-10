"""Unfold-админка порталов агрегатора (P2.1d).

Django admin живёт только на public (config/urls_public.py). Внимание: портал
отдаётся по хосту только при наличии строки Domain(host → public tenant) —
команда `create_portal` создаёт обе записи разом; при создании портала через
админку строку Domain нужно добавить вручную (см. docs/portal-setup.md).
"""

from django import forms
from django.contrib import admin, messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from .models import (
    AggregatorListing,
    AggregatorPortal,
    BusinessReview,
    ListingReport,
    PortalBot,
)


class HiddenFilter(admin.SimpleListFilter):
    title = _("Moderation")
    parameter_name = "verborgen"

    def lookups(self, request, model_admin):
        return [("ja", _("Verborgen")), ("nein", _("Sichtbar"))]

    def queryset(self, request, queryset):
        if self.value() == "ja":
            return queryset.filter(hidden_at__isnull=False)
        if self.value() == "nein":
            return queryset.filter(hidden_at__isnull=True)
        return queryset


@admin.register(AggregatorListing)
class AggregatorListingAdmin(ModelAdmin):
    """Листинги: продажа продвижения вручную (P2.4a) — выставить featured_until.

    Карточные поля редактировать незачем — их перезаписывает sync_listing;
    featured_until синк не трогает.
    """

    list_display = (
        "business_name",
        "city",
        "business_type",
        "featured_until",
        "is_active",
        "hidden_at",
        "open_reports",
    )
    search_fields = ("business_name", "city", "tenant_slug")
    list_filter = ("is_active", "business_type", HiddenFilter)
    fields = (
        "business_name",
        "city",
        "business_type",
        "detail_url",
        "featured_until",
        "hidden_at",
        "hidden_reason",
    )
    readonly_fields = ("business_name", "city", "business_type", "detail_url", "hidden_at")
    ordering = ("-updated_at",)
    actions = ("hide_listings", "unhide_listings")

    def has_add_permission(self, request):
        return False  # листинги создаёт только sync_listing

    @admin.display(description=_("Offene Meldungen"))
    def open_reports(self, obj):
        return obj.reports.filter(status=ListingReport.STATUS_OPEN).count()

    @admin.action(description=_("Im Stadtportal verbergen"))
    def hide_listings(self, request, queryset):
        n = queryset.filter(hidden_at__isnull=True).update(
            hidden_at=timezone.now(), hidden_reason=_("Moderation")
        )
        messages.success(request, _("%(n)s verborgen.") % {"n": n})

    @admin.action(description=_("Wieder anzeigen (Meldungen erledigt)"))
    def unhide_listings(self, request, queryset):
        n = queryset.update(hidden_at=None, hidden_reason="")
        ListingReport.objects.filter(listing__in=queryset).update(
            status=ListingReport.STATUS_RESOLVED
        )
        messages.success(request, _("%(n)s wieder sichtbar.") % {"n": n})


@admin.register(ListingReport)
class ListingReportAdmin(ModelAdmin):
    """T-8.6: очередь жалоб «Melden» (постмодерация, автоскрытие при 3 голосах)."""

    list_display = ("created_at", "listing", "reason", "status", "listing_hidden")
    list_filter = ("status", "reason")
    search_fields = ("listing__business_name", "message")
    readonly_fields = ("listing", "reason", "message", "created_at")
    fields = ("listing", "reason", "message", "status", "created_at")
    ordering = ("status", "-created_at")
    actions = ("resolve_keep", "resolve_hide")

    def has_add_permission(self, request):
        return False

    @admin.display(boolean=True, description=_("Verborgen"))
    def listing_hidden(self, obj):
        return obj.listing.hidden_at is not None

    @admin.action(description=_("Erledigt — Angebot bleibt sichtbar"))
    def resolve_keep(self, request, queryset):
        ids = list(queryset.values_list("listing_id", flat=True))
        AggregatorListing.objects.filter(pk__in=ids).update(hidden_at=None, hidden_reason="")
        ListingReport.objects.filter(listing_id__in=ids).update(
            status=ListingReport.STATUS_RESOLVED
        )

    @admin.action(description=_("Erledigt — Angebot verbergen"))
    def resolve_hide(self, request, queryset):
        ids = list(queryset.values_list("listing_id", flat=True))
        AggregatorListing.objects.filter(pk__in=ids, hidden_at__isnull=True).update(
            hidden_at=timezone.now(), hidden_reason=_("Moderation")
        )
        ListingReport.objects.filter(listing_id__in=ids).update(
            status=ListingReport.STATUS_RESOLVED
        )


@admin.register(BusinessReview)
class BusinessReviewAdmin(ModelAdmin):
    """Модерация отзывов (G8): супер-админ скрывает абьюз (status=hidden).

    После смены статуса агрегат пересчитывается (save_model)."""

    list_display = ("business_name", "rating", "status", "created_at")
    search_fields = ("business_name", "tenant_slug", "comment")
    list_filter = ("status", "rating")
    readonly_fields = ("tenant_schema", "tenant_slug", "business_name", "author", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False  # отзывы создают клиенты на порталах

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from .reviews import recompute_rating

        recompute_rating(obj.tenant_schema)


@admin.register(AggregatorPortal)
class AggregatorPortalAdmin(ModelAdmin):
    list_display = ("host", "kind", "city", "business_type", "show_demo", "is_active", "updated_at")
    search_fields = ("host", "city")
    list_filter = ("kind", "is_active", "business_type")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("host",)

    fieldsets = (
        (None, {"fields": ("host", "kind", "is_active")}),
        ("Filters", {"fields": ("city", "business_type", "show_demo")}),
        ("Branding", {"fields": ("title", "tagline", "intro", "logo_url", "primary_color")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


class PortalBotForm(forms.ModelForm):
    token_input = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label="Bot token",
        help_text="From @BotFather. Leave blank to keep current. Save, then run «Connect».",
    )

    class Meta:
        model = PortalBot
        fields = ("portal",)

    def save(self, commit=True):
        obj = super().save(commit=False)
        raw = self.cleaned_data.get("token_input")
        if raw:
            obj.token = raw
        if commit:
            obj.save()
        return obj


@admin.register(PortalBot)
class PortalBotAdmin(ModelAdmin):
    """Telegram-бот портала (TG4): задать токен → действие «Connect» ставит webhook."""

    form = PortalBotForm
    list_display = ("portal", "bot_username", "is_active", "updated_at")
    readonly_fields = ("bot_username", "is_active", "created_at", "updated_at")
    actions = ("connect_selected", "disconnect_selected")

    @admin.action(description="Connect bot (verify token + set webhook)")
    def connect_selected(self, request, queryset):
        from .telegram_bot import connect_bot

        for bot in queryset:
            try:
                connect_bot(bot)
                self.message_user(request, f"{bot.portal.host}: connected.", messages.SUCCESS)
            except Exception as exc:  # noqa: BLE001 — показать ошибку в админке
                self.message_user(request, f"{bot.portal.host}: {exc}", messages.ERROR)

    @admin.action(description="Disconnect bot (remove webhook)")
    def disconnect_selected(self, request, queryset):
        from .telegram_bot import disconnect_bot

        for bot in queryset:
            disconnect_bot(bot)
        self.message_user(request, "Disconnected.", messages.SUCCESS)
