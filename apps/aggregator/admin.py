"""Unfold-админка порталов агрегатора (P2.1d).

Django admin живёт только на public (config/urls_public.py). Внимание: портал
отдаётся по хосту только при наличии строки Domain(host → public tenant) —
команда `create_portal` создаёт обе записи разом; при создании портала через
админку строку Domain нужно добавить вручную (см. docs/portal-setup.md).
"""

import csv
from datetime import timedelta

from django import forms
from django.contrib import admin, messages
from django.db.models import F, Sum
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from .models import (
    AggregatorListing,
    AggregatorPortal,
    BusinessReview,
    FollowSubscription,
    ListingReport,
    PortalBot,
    PortalStat,
    PortalUser,
    SearchQueryLog,
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


class ReportSourceFilter(admin.SimpleListFilter):
    """D2b-1: машинные пометки «Text-Check» отдельно от жалоб людей."""

    title = _("Quelle")
    parameter_name = "quelle"

    def lookups(self, request, model_admin):
        return [("auto", _("Automatisch")), ("meldung", _("Meldung"))]

    def queryset(self, request, queryset):
        if self.value() == "auto":
            return queryset.filter(ip_hash=ListingReport.AUTO_MARKER)
        if self.value() == "meldung":
            return queryset.exclude(ip_hash=ListingReport.AUTO_MARKER)
        return queryset


@admin.register(ListingReport)
class ListingReportAdmin(ModelAdmin):
    """T-8.6: очередь жалоб «Melden» (постмодерация, автоскрытие при 3 голосах)."""

    list_display = ("created_at", "listing", "reason", "status", "listing_hidden")
    list_filter = ("status", "reason", ReportSourceFilter)
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
        # D2b: машинная пометка решается сама по себе — скрытие людьми и их жалобы
        # она не трогает (иначе «Erledigt» по авто-пометке молча снимал бы скрытие).
        queryset.filter(ip_hash=ListingReport.AUTO_MARKER).update(
            status=ListingReport.STATUS_RESOLVED
        )
        human = queryset.exclude(ip_hash=ListingReport.AUTO_MARKER)
        ids = list(human.values_list("listing_id", flat=True))
        if not ids:
            return
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


class SearchPeriodFilter(admin.SimpleListFilter):
    title = _("Zeitraum")
    parameter_name = "zeitraum"

    def lookups(self, request, model_admin):
        return [("7", _("7 Tage")), ("30", _("30 Tage")), ("90", _("90 Tage"))]

    def queryset(self, request, queryset):
        if self.value() in ("7", "30", "90"):
            since = timezone.localdate() - timedelta(days=int(self.value()))
            return queryset.filter(day__gte=since)
        return queryset


class SearchResultFilter(admin.SimpleListFilter):
    title = _("Treffer")
    parameter_name = "treffer"

    def lookups(self, request, model_admin):
        return [
            ("ohne", _("Nichts gefunden")),
            ("nie", _("Immer ohne Treffer")),
            ("tippfehler", _("Nur Tippfehler-Treffer")),
        ]

    def queryset(self, request, queryset):
        if self.value() == "ohne":
            return queryset.filter(zero_results__gt=0)
        if self.value() == "nie":
            return queryset.filter(zero_results=F("searches"))
        if self.value() == "tippfehler":
            return queryset.filter(trigram_hits__gt=0)
        return queryset


def _csv_safe(value) -> str:
    """Защита от CSV-инъекции: запрос вводит посетитель, а файл откроют в Excel."""
    text = str(value if value is not None else "")
    return "'" + text if text[:1] in ("=", "+", "-", "@", "|", "%", "\t", "\r") else text


def _csv_response(filename: str, header: list, rows) -> HttpResponse:
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")  # BOM — Excel читает UTF-8
    writer = csv.writer(response, delimiter=";")
    writer.writerow(header)
    for row in rows:
        writer.writerow([_csv_safe(v) for v in row])
    return response


@admin.register(SearchQueryLog)
class SearchQueryLogAdmin(ModelAdmin):
    """T-8.21: журнал поиска каталога города — только платформе (суперпользователь).

    Агрегат по дням без персональных данных; «Nichts gefunden» и «Nur Tippfehler-Treffer»
    — кандидаты в словарь синонимов (`search_synonyms.py`, правится коммитом).
    """

    list_display = (
        "day",
        "query_norm",
        "surface",
        "city",
        "portal_host",
        "lang",
        "searches",
        "zero_results",
        "trigram_hits",
        "last_mode",
        "last_results",
    )
    list_filter = (SearchPeriodFilter, SearchResultFilter, "surface", "city", "lang", "last_mode")
    date_hierarchy = "day"
    search_fields = ("query_norm",)
    ordering = ("-day", "-searches")
    actions = ("export_csv", "export_csv_grouped")

    def has_module_permission(self, request):
        return bool(request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    @admin.action(description=_("CSV exportieren"))
    def export_csv(self, request, queryset):
        fields = (
            "day",
            "surface",
            "portal_host",
            "city",
            "lang",
            "query_norm",
            "filters_key",
            "searches",
            "zero_results",
            "trigram_hits",
            "last_mode",
            "last_results",
        )
        return _csv_response(
            "suchanfragen.csv", list(fields), queryset.values_list(*fields).order_by("-day")
        )

    @admin.action(description=_("CSV: Top-Suchen zusammengefasst"))
    def export_csv_grouped(self, request, queryset):
        rows = (
            queryset.order_by()
            .values("query_norm", "city", "surface")
            .annotate(
                searches=Sum("searches"),
                zero_results=Sum("zero_results"),
                trigram_hits=Sum("trigram_hits"),
            )
            .order_by("-searches")
        )
        return _csv_response(
            "top-suchen.csv",
            ["query_norm", "city", "surface", "searches", "zero_results", "trigram_hits"],
            (
                (
                    r["query_norm"],
                    r["city"],
                    r["surface"],
                    r["searches"],
                    r["zero_results"],
                    r["trigram_hits"],
                )
                for r in rows
            ),
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


@admin.register(PortalUser)
class PortalUserAdmin(ModelAdmin):
    """T-8.7: житель портала — поиск по e-mail, удаление по запросу (DSGVO):
    каскадом уходят подписки «Folgen», сводки, избранное."""

    list_display = (
        "email",
        "is_active",
        "locale",
        "marketing_opt_out",
        "last_login_at",
        "created_at",
    )
    search_fields = ("email",)
    list_filter = ("is_active", "marketing_opt_out", "locale")
    readonly_fields = ("email", "follow_token", "last_login_at", "created_at", "updated_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_module_permission(self, request):
        return bool(request.user.is_superuser)


@admin.register(FollowSubscription)
class FollowSubscriptionAdmin(ModelAdmin):
    """T-8.7: подписки «Folgen» (только чтение/удаление — доказательство согласия)."""

    list_display = (
        "user",
        "target_kind",
        "target_key",
        "city",
        "frequency",
        "channel",
        "confirmed_at",
        "last_sent_at",
    )
    search_fields = ("user__email", "target_key")
    list_filter = ("target_kind", "frequency", "channel")
    readonly_fields = (
        "user",
        "target_kind",
        "target_key",
        "city",
        "portal",
        "channel",
        "token",
        "confirmed_at",
        "source_host",
        "last_sent_at",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_module_permission(self, request):
        return bool(request.user.is_superuser)


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


class PortalStatDemoFilter(admin.SimpleListFilter):
    """В5: демо-трафик по умолчанию скрыт — сводки платформы без демо (решение В5)."""

    title = _("Demo")
    parameter_name = "demo"

    def lookups(self, request, model_admin):
        return [("ja", _("Nur Demo")), ("alle", _("Alle"))]

    def choices(self, changelist):
        yield {
            "selected": self.value() is None,
            "query_string": changelist.get_query_string(remove=[self.parameter_name]),
            "display": _("Ohne Demo"),
        }
        for lookup, title in self.lookup_choices:
            yield {
                "selected": self.value() == lookup,
                "query_string": changelist.get_query_string({self.parameter_name: lookup}),
                "display": title,
            }

    def queryset(self, request, queryset):
        if self.value() == "ja":
            return queryset.filter(is_demo=True)
        if self.value() == "alle":
            return queryset
        return queryset.filter(is_demo=False)


@admin.register(PortalStat)
class PortalStatAdmin(ModelAdmin):
    """В5: сводка учёта каталога города по всем бизнесам — только платформе
    (суперпользователь). Агрегат по дням без персональных данных."""

    list_display = (
        "day",
        "tenant_schema",
        "listing_kind",
        "source_ref",
        "action",
        "channel",
        "count",
        "is_demo",
    )
    list_filter = (PortalStatDemoFilter, SearchPeriodFilter, "action", "channel")
    date_hierarchy = "day"
    search_fields = ("tenant_schema", "source_ref")
    ordering = ("-day", "-count")
    actions = ("export_csv",)

    def has_module_permission(self, request):
        return bool(request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    @admin.action(description=_("CSV exportieren"))
    def export_csv(self, request, queryset):
        fields = (
            "day",
            "tenant_schema",
            "listing_kind",
            "source_ref",
            "action",
            "channel",
            "is_demo",
            "count",
        )
        return _csv_response(
            "stadtportal-besuche.csv", list(fields), queryset.values_list(*fields).order_by("-day")
        )
