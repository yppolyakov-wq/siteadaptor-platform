"""Формы кабинета: создание/редактирование акций.

i18n-поля (title/description) редактируются парами de/en и собираются в
JSONField. Статус акции через форму не меняется — только через PromotionSM
(кнопки переходов). starts_at/ends_at — datetime-local.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Product
from apps.loyalty.models import LoyaltyProgram

from .models import Promotion

_DT_FMT = "%Y-%m-%dT%H:%M"


class _DateTimeLocal(forms.DateTimeField):
    def __init__(self, **kwargs):
        super().__init__(
            required=False,
            input_formats=[_DT_FMT],
            widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=_DT_FMT),
            **kwargs,
        )


class PromotionForm(forms.ModelForm):
    title_de = forms.CharField(label=_("Title (DE)"), max_length=200)
    title_en = forms.CharField(label=_("Title (EN)"), max_length=200, required=False)
    description_de = forms.CharField(
        label=_("Description (DE)"), widget=forms.Textarea(attrs={"rows": 3}), required=False
    )
    description_en = forms.CharField(
        label=_("Description (EN)"), widget=forms.Textarea(attrs={"rows": 3}), required=False
    )
    starts_at = _DateTimeLocal(label=_("Starts at"))
    ends_at = _DateTimeLocal(label=_("Ends at"))

    class Meta:
        model = Promotion
        fields = [
            "product",
            "promo_type",
            "compare_at_price",
            "discount_percent",
            "price_override",
            "available_quantity",
            "max_per_customer",
            "reservation_ttl_hours",
            "auto_confirm",
            "starts_at",
            "ends_at",
            "strikethrough_old_price",
            "show_countdown",
            "discount_style",
            "is_surprise",
            "recurrence",
            "group",
        ]
        labels = {
            "group": _("Section / group"),
            "compare_at_price": _("Old price (struck through)"),
            "discount_percent": _("Discount %"),
            "price_override": _("New price"),
            "strikethrough_old_price": _("Strike through the old price"),
            "show_countdown": _("Show countdown to end"),
            "discount_style": _("Discount display style"),
            "is_surprise": _("Surprise bag (rescue leftovers, anti-waste)"),
            "recurrence": _("Repeat automatically"),
        }
        help_texts = {
            "compare_at_price": _("Leave blank to use the linked product's price."),
            "discount_percent": _("Either a % or a new price — the rest is computed."),
            "is_surprise": _(
                "Shows an „Überraschungstüte“ badge on your storefront and the aggregator."
            ),
            "recurrence": _(
                "When it ends, a copy is scheduled for the next day/week automatically."
            ),
            "discount_style": _(
                "How the discount looks on your storefront — badge, struck-through "
                "price, fixed price, from-price or countdown accent."
            ),
            "group": _(
                "Optional. Groups offers into sections (e.g. „Fastfood“, „Fertiggerichte“) — "
                "shown as filters on /aktionen/ and selectable in the menu builder."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.all()
        self.fields["product"].required = False
        if self.instance and self.instance.pk:
            self.fields["title_de"].initial = (self.instance.title or {}).get("de", "")
            self.fields["title_en"].initial = (self.instance.title or {}).get("en", "")
            self.fields["description_de"].initial = (self.instance.description or {}).get("de", "")
            self.fields["description_en"].initial = (self.instance.description or {}).get("en", "")

    def clean(self):
        cleaned = super().clean()
        starts, ends = cleaned.get("starts_at"), cleaned.get("ends_at")
        if starts and ends and ends <= starts:
            self.add_error("ends_at", _("End must be after start."))
        return cleaned

    def save(self, commit=True):
        promo = super().save(commit=False)
        promo.title = {
            "de": self.cleaned_data["title_de"],
            "en": self.cleaned_data.get("title_en", ""),
        }
        promo.description = {
            "de": self.cleaned_data.get("description_de", ""),
            "en": self.cleaned_data.get("description_en", ""),
        }
        if commit:
            promo.save()
        return promo


class PublicReservationForm(forms.Form):
    """Публичная форма брони на витрине (без логина).

    website — honeypot (должно остаться пустым). form_token — для
    идемпотентности сабмита (защита от двойной отправки по F5).
    """

    name = forms.CharField(label=_("Your name"), max_length=200)
    email = forms.EmailField(label=_("Email"), required=False)
    phone = forms.CharField(label=_("Phone"), max_length=40, required=False)
    quantity = forms.IntegerField(label=_("Quantity"), min_value=1, initial=1)
    website = forms.CharField(required=False, widget=forms.HiddenInput)
    form_token = forms.CharField(required=False, widget=forms.HiddenInput)
    channel = forms.CharField(required=False, widget=forms.HiddenInput)  # атрибуция источника


class WaitlistForm(forms.Form):
    """Лист ожидания для распроданной акции."""

    name = forms.CharField(label=_("Your name"), max_length=200, required=False)
    email = forms.EmailField(label=_("Email"))
    website = forms.CharField(required=False, widget=forms.HiddenInput)  # honeypot


class VoucherCreateForm(forms.Form):
    """Генерация пачки ваучеров."""

    label = forms.CharField(
        label=_("Label"), max_length=120, help_text=_("e.g. −10 % or Free coffee")
    )
    count = forms.IntegerField(label=_("How many"), min_value=1, max_value=200, initial=1)
    max_uses = forms.IntegerField(
        label=_("Uses per voucher (0 = unlimited)"), min_value=0, initial=1
    )
    expires_at = _DateTimeLocal(label=_("Expires at"))
    # A4 промокод на онлайн-заказе: скидка % ИЛИ € + мин-заказ (опц.).
    discount_percent = forms.IntegerField(
        label=_("Discount % (online order)"), min_value=1, max_value=100, required=False
    )
    discount_eur = forms.DecimalField(
        label=_("Discount € (online order)"),
        min_value=0,
        decimal_places=2,
        max_digits=10,
        required=False,
    )
    min_order_eur = forms.DecimalField(
        label=_("Minimum order €"),
        min_value=0,
        decimal_places=2,
        max_digits=10,
        required=False,
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("discount_percent") and cleaned.get("discount_eur"):
            raise forms.ValidationError(_("Use either % or € discount, not both."))
        return cleaned


class LoyaltyProgramForm(forms.ModelForm):
    class Meta:
        model = LoyaltyProgram
        fields = ["label", "stamps_required", "reward_label", "is_active"]
        labels = {
            "label": _("Program name"),
            "stamps_required": _("Stamps required"),
            "reward_label": _("Reward"),
        }
