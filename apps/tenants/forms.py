"""Форма онбординга бизнеса (публичная схема).

Регистрация владельца = создание Tenant + Domain + первого User в схеме бизнеса.
"""

import re

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Tenant

_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
_RESERVED_SLUGS = {"www", "admin", "api", "app", "static", "media", "public", "mail"}


class BusinessSignupForm(forms.Form):
    business_name = forms.CharField(label=_("Business name"), max_length=200)
    slug = forms.SlugField(
        label=_("Subdomain"),
        max_length=100,
        help_text=_("{slug}.siteadaptor.de — only a-z, 0-9 and hyphen."),
    )
    business_type = forms.ChoiceField(label=_("Business type"), choices=Tenant.BUSINESS_TYPES)
    city = forms.CharField(label=_("City"), max_length=100)
    email = forms.EmailField(label=_("Your email"))
    password1 = forms.CharField(label=_("Password"), widget=forms.PasswordInput, min_length=8)
    password2 = forms.CharField(label=_("Confirm password"), widget=forms.PasswordInput)

    def clean_slug(self):
        slug = self.cleaned_data["slug"].lower()
        if not _SLUG_RE.match(slug):
            raise forms.ValidationError(_("Only lowercase letters, digits and hyphen."))
        if slug in _RESERVED_SLUGS:
            raise forms.ValidationError(_("This subdomain is reserved."))
        if Tenant.objects.filter(slug=slug).exists():
            raise forms.ValidationError(_("This subdomain is already taken."))
        # schema_name выводится из slug; проверим и его уникальность
        if Tenant.objects.filter(schema_name=slug.replace("-", "_")).exists():
            raise forms.ValidationError(_("This subdomain is already taken."))
        return slug

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", _("Passwords do not match."))
        return cleaned


class BusinessSettingsForm(forms.ModelForm):
    """Настройки бизнеса: контакты + правовые тексты (редактирует владелец)."""

    class Meta:
        model = Tenant
        fields = [
            "name",
            "address",
            "city",
            "contact_email",
            "contact_phone",
            "website_url",
            "opening_hours",
            "map_url",
            "service_area_plz",
            "service_area_note",
            "auto_redeem_on_scan",
            "owner_digest_enabled",
            "vat_id",
            "tax_number",
            "small_business",
            "register_entry",
            "legal_responsible",
            "impressum",
            "privacy_policy",
            "withdrawal_policy",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "opening_hours": forms.Textarea(attrs={"rows": 3}),
            "impressum": forms.Textarea(attrs={"rows": 5}),
            "privacy_policy": forms.Textarea(attrs={"rows": 6}),
            "withdrawal_policy": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {
            "auto_redeem_on_scan": _("Auto-redeem on scan (logged-in staff)"),
            "owner_digest_enabled": _("Morning digest email"),
        }
        help_texts = {
            "service_area_plz": _(
                "Postal codes you serve, comma-separated (e.g. 40724, 42697). "
                "Leave blank if you serve everyone."
            ),
            "service_area_note": _(
                "Free text shown to customers (e.g. “Hilden, Solingen and surroundings”)."
            ),
            "auto_redeem_on_scan": _(
                "When on, opening a redemption QR as logged-in staff redeems immediately."
            ),
            "owner_digest_enabled": _(
                "A short morning email: yesterday's revenue, today's bookings and "
                "what needs your attention."
            ),
            "impressum": _("Leave blank to generate from the fields above."),
            "privacy_policy": _("Leave blank for a default template (please adapt)."),
            "withdrawal_policy": _("Leave blank for a default template (please adapt)."),
        }
