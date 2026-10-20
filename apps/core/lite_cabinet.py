"""T-8.23c: лёгкий кабинет для магазинов «Nur Aktionen» (план
docs/t8-23-lite-feedback-plan-2026-10-10.md §8).

Экраны — Start · Aktionen · Angebot · Sichtbar (T-8.31) · Geschäft · Teilen. Реестр якорей W8 (мораторий X7)
не трогаем: ``modules.sidebar_nav`` отдаёт этот плоский набор только лёгкому режиму.
Полный кабинет по прямым адресам доступен как раньше — режим упрощает вход, а не запрещает.
"""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.core import storefront_profile

# (url_name, nav_key, emoji, подпись) — nav_key существующие: подсветка и иконки даром.
LITE_NAV = (
    # T-8.31a: первые четыре — мобильный таб-бар макета (Start · Aktionen · Angebot ·
    # Sichtbar).
    ("dashboard", "dashboard", "🏠", _("Start")),
    ("promotions:promotion-list", "promotions", "📣", _("Aktionen")),
    ("sellable-manage", "sellables", "📦", _("Angebot")),
    # T-8.31c: «Sichtbar» — где видно + подключения (свой бот, оплата, домен; T-8.29);
    # полный список подключений — ссылкой со страницы.
    ("lite-visibility", "integrations", "👁", _("Sichtbar")),
    ("lite-business", "settings", "🏪", _("Geschäft")),
    ("lite-share", "site", "🔗", _("Teilen")),
)
# Ревью Г1: у визитки «eintrag» сортимент живёт на сайте владельца — повторный импорт
# должен быть доступен из меню (иначе вход только через прямую ссылку).
EINTRAG_NAV = (("imports:website", "imports", "🌐", _("Website-Import")),)


def is_lite(tenant) -> bool:
    try:
        return storefront_profile.is_aktionen(tenant)
    except Exception:  # noqa: BLE001 — хром кабинета не падает из-за профиля
        return False


def is_lite_request(request) -> bool:
    """T-8.30 (Р-5): лёгкий кабинет — по профилю бизнеса ИЛИ для сессии из Telegram
    Mini App (у полного кабинета там те же лёгкие экраны)."""
    from apps.core import tg_login

    return is_lite(getattr(request, "tenant", None)) or tg_login.is_tg_session(request)


def sidebar_items(tenant=None) -> list[dict]:
    """Плоский набор пунктов в форме ``modules.sidebar_nav`` (без подменю)."""
    nav = LITE_NAV
    try:
        if tenant is not None and storefront_profile.is_eintrag(tenant):
            nav = LITE_NAV + EINTRAG_NAV
    except Exception:  # noqa: BLE001 — хром кабинета не падает из-за профиля
        pass
    return [
        {
            "url_name": url_name,
            "nav_key": nav_key,
            "icon": icon,
            "label": label,
            "search": "",
            "children": [],
        }
        for url_name, nav_key, icon, label in nav
    ]


class LiteBusinessForm(forms.ModelForm):
    """«Geschäft»: только то, что видит клиент акции — адрес, телефон, WhatsApp."""

    class Meta:
        from apps.tenants.models import Tenant

        model = Tenant
        fields = ["name", "address", "contact_phone", "whatsapp_number"]
        labels = {
            "name": _("Name Ihres Geschäfts"),
            "address": _("Adresse"),
            "contact_phone": _("Telefon"),
            "whatsapp_number": _("WhatsApp-Nummer"),
        }
        widgets = {"address": forms.Textarea(attrs={"rows": 2})}

    def clean_address(self):
        address = " ".join((self.cleaned_data.get("address") or "").split())
        if not address:
            raise forms.ValidationError(_("Bitte die Adresse angeben."))
        return address

    def clean_contact_phone(self):
        phone = " ".join((self.cleaned_data.get("contact_phone") or "").split())
        if not phone:
            raise forms.ValidationError(_("Bitte eine gültige Telefonnummer eingeben."))
        return phone


@login_required
def lite_business(request):
    """«Geschäft»: название, адрес, телефон, WhatsApp, часы работы — одна колонка."""
    from apps.core.views import _opening_hours_rows, _parse_opening_hours

    tenant = request.tenant
    form = LiteBusinessForm(request.POST or None, instance=tenant)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.opening_hours_structured = _parse_opening_hours(request)
        # W0/W7a: пишем только поля этого экрана, чужие колонки не трогаем.
        obj.save(
            update_fields=[*LiteBusinessForm.Meta.fields, "opening_hours_structured", "updated_at"]
        )
        from apps.aggregator.tasks import refresh_tenant_fields

        refresh_tenant_fields(obj)  # имя/адрес — в листинги каталога города
        messages.success(request, gettext("Gespeichert."))
        return redirect("lite-business")
    return render(
        request,
        "tenant/lite_business.html",
        {"form": form, "nav": "settings", "opening_hours_rows": _opening_hours_rows(tenant)},
    )


def _qr_svg(url: str) -> str:
    import segno

    return segno.make(url, error="m").svg_inline(scale=5, border=2)


@login_required
def lite_share(request):
    """«Teilen»: адрес сайта, QR, мессенджеры и плакат магазина."""
    from apps.core.share_links import share_targets

    tenant = request.tenant
    from apps.promotions.views import _public_url

    url = _public_url(request, "/")  # T-8.25: основной адрес (свой домен)
    return render(
        request,
        "tenant/lite_share.html",
        {
            "nav": "site",
            "site_url": url,
            "qr_svg": _qr_svg(url),
            "share": share_targets(getattr(tenant, "name", ""), url),
        },
    )


def _is_owner(user) -> bool:
    from apps.core.roles import is_owner

    try:
        return is_owner(user)
    except Exception:  # noqa: BLE001 — нет роли → как сотрудник (меньше видно)
        return False


def _portal_block(tenant, owner: bool) -> dict:
    """Каталог города: видна ли витрина, сколько предложений, просмотры за 7 дней
    (только владельцу — те же цифры, что owner-only экран «Stadtportal»)."""
    from apps.aggregator.models import AggregatorListing
    from apps.promotions import where

    block = {"reason": where._catalog_reason(tenant), "count": 0, "views": None}
    block["count"] = (
        AggregatorListing.objects.public().filter(tenant_schema=tenant.schema_name).count()
    )
    if owner:
        from apps.aggregator import owner_stats

        funnel = owner_stats.summary(tenant, 7)["funnel"]
        block["views"] = next((f["value"] for f in funnel if f["code"] == "view"), None)
    return block


def _google_connected() -> bool:
    from apps.publishing.models import Channel

    return Channel.objects.filter(type=Channel.GOOGLE_BUSINESS, is_enabled=True).exists()


@login_required
def lite_visibility(request):
    """T-8.31c «Sichtbarkeit & Verbindungen» по макету: где клиенты находят бизнес
    (сайт · каталог города · Google) и подключения (общий бот · свой бот · Stripe ·
    домен). Только чтение и входы на штатные экраны; owner-only — только владельцу."""
    from apps.core import integration_status as st
    from apps.core import tg_login
    from apps.promotions.views import _public_url

    tenant = request.tenant
    owner = _is_owner(request.user)
    # T-8.30 (Р-2): из Telegram — только статусы; свой бот подключается по e-mail-входу.
    can_manage_bot = owner and not tg_login.is_tg_session(request)

    def _block(fn, fallback):
        try:
            return fn()
        except Exception:  # noqa: BLE001 — сломанный блок не роняет страницу
            return fallback

    return render(
        request,
        "tenant/lite_visibility.html",
        {
            "nav": "integrations",
            "is_owner": owner,
            "can_manage_bot": can_manage_bot,
            "site_url": _block(lambda: _public_url(request, "/"), ""),
            "portal": _block(
                lambda: _portal_block(tenant, owner), {"reason": "", "count": 0, "views": None}
            ),
            "google_on": _block(_google_connected, False),
            "publishing_on": tenant.is_module_active("publishing"),
            "platform_bot": st.safe(lambda: st.telegram(tenant)),
            "own_bot": st.own_bot(tenant),
            "payments_on": bool(getattr(tenant, "payments_enabled", False)),
            "domain": st.safe(lambda: st.domain(tenant)),
        },
    )
