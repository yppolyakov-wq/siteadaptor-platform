"""T-8.23c: лёгкий кабинет для магазинов «Nur Aktionen» (план
docs/t8-23-lite-feedback-plan-2026-10-10.md §8).

Экраны — Start · Aktionen · Angebot · Sichtbar (T-8.31) · Geschäft · Teilen. Реестр якорей W8 (мораторий X7)
не трогаем: ``modules.sidebar_nav`` отдаёт этот плоский набор только лёгкому режиму.
T-8.32b: прочие экраны кабинета у лёгкого пакета закрыты (`PackageScopeMiddleware`,
страница «nicht enthalten»); меню показывает только то, что пакет открывает.
"""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.core import storefront_profile
from apps.core.roles import owner_required

# (url_name, nav_key, emoji, подпись) — nav_key существующие: подсветка и иконки даром.
LITE_NAV = (
    # T-8.31a: первые четыре — мобильный таб-бар макета (Start · Aktionen · Angebot ·
    # Sichtbar).
    ("dashboard", "dashboard", "🏠", _("Start")),
    ("promotions:promotion-list", "promotions", "📣", _("Aktionen")),
    # T-8.32b (KA-3 В-1): у пакета «Aktionen» вместо «Angebot» — «Nachrichten».
    ("inbox:list", "inbox", "💬", _("Nachrichten")),
    ("sellable-manage", "sellables", "📦", _("Angebot")),
    # T-8.31c: «Sichtbar» — где видно + подключения (свой бот, оплата, домен; T-8.29);
    # полный список подключений — ссылкой со страницы.
    ("lite-visibility", "integrations", "👁", _("Sichtbar")),
    # KA-12 E8.9: заявки (модуль jobs) — список был недостижим; «Teilen» живёт
    # ссылкой на странице «Sichtbar» (дубль пункта меню убран).
    ("lite-requests", "board", "📝", _("Anfragen")),
    ("lite-business", "settings", "🏪", _("Geschäft")),
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


# KA-H9: пункты только для владельца (мидлварь отдаёт сотруднику 403 — в меню их нет).
_OWNER_ONLY_ITEMS = frozenset({"lite-business"})
# Пункты меню, видимые только при включённом модуле.
_MODULE_ITEMS = {"inbox:list": "inbox", "lite-requests": "jobs"}


def sidebar_items(tenant=None, user=None) -> list[dict]:
    """Плоский набор пунктов в форме ``modules.sidebar_nav`` (без подменю).
    ``user`` — owner-гейт; без user (fail-open) показываем всё: доступ держит мидлварь."""
    nav = LITE_NAV
    try:
        if tenant is not None and storefront_profile.is_eintrag(tenant):
            nav = LITE_NAV + EINTRAG_NAV
    except Exception:  # noqa: BLE001 — хром кабинета не падает из-за профиля
        pass
    # T-8.32b: только то, что пакет открывает (полный бизнес в Mini App — как раньше;
    # «Nachrichten» — только при включённом чате).
    try:
        from apps.core import modules, packages

        nav = tuple(
            item
            for item in nav
            if (tenant is None or packages.view_allowed(tenant, item[0]))
            and (
                item[0] not in _MODULE_ITEMS
                or tenant is None
                or modules.is_module_active(tenant, _MODULE_ITEMS[item[0]])
            )
        )
    except Exception:  # noqa: BLE001 — хром кабинета не падает из-за пакета
        pass
    if user is not None and getattr(user, "is_authenticated", False):
        try:
            from apps.core.roles import is_owner

            if not is_owner(user):
                nav = tuple(item for item in nav if item[0] not in _OWNER_ONLY_ITEMS)
        except Exception:  # noqa: BLE001 — роли недоступны → fail-open
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


def impressum_missing(tenant) -> list[str]:
    """KA-12 E7.2: недостающее в Impressum; демо/внутренние — без предупреждения.

    Вызывается в запросе тенанта: свой Impressum в LegalDoc (TENANT-модель) читаем
    только когда соединение стоит в схеме ЭТОГО тенанта (иначе — ложный ответ или
    упавшая транзакция в public)."""
    from django.db import connection

    if getattr(tenant, "is_demo", False) or getattr(tenant, "is_internal", False):
        return []
    if getattr(connection, "schema_name", None) == tenant.schema_name:
        from apps.core.models import LegalDoc

        if LegalDoc.objects.filter(kind="impressum").exclude(text="").exists():
            return []
    return tenant.impressum_missing()


class LiteBusinessForm(forms.ModelForm):
    """«Geschäft»: что видит клиент акции (адрес, телефон, WhatsApp) + KA-12 E7.1
    правовые данные Impressum (§ 5 DDG) — свой e-mail вместо почты входа, правовая
    форма, представитель, реестр, налоговые данные."""

    # Группы полей формы (шаблон рисует их разделами).
    SECTIONS = (
        ("kontakt", _("Kontakt"), ("name", "contact_phone", "whatsapp_number", "contact_email")),
        ("standort", _("Standort"), ("address", "city", "district")),
        (
            "recht",
            _("Rechtliches (Impressum)"),
            (
                "legal_form",
                "legal_representative",
                "register_court",
                "register_number",
                "vat_id",
                "tax_number",
                "tax_choice",
            ),
        ),
    )

    # KA-12 B2-8a (T-1): Soll/Ist/§ 19 одной группой; пишет `small_business` и
    # `tax_regime` (поле не модельное — у Kleinunternehmer режим не меняется).
    tax_choice = forms.ChoiceField(
        label=_("Besteuerung"),
        choices=(),
        widget=forms.RadioSelect,
        required=False,  # не прислано (старая форма/API) — режим не трогаем
    )

    class Meta:
        from apps.tenants.models import Tenant

        model = Tenant
        fields = [
            "name",
            "address",
            "city",
            "district",
            "contact_phone",
            "whatsapp_number",
            "contact_email",
            "legal_form",
            "legal_representative",
            "register_court",
            "register_number",
            "vat_id",
            "tax_number",
        ]
        labels = {
            "name": _("Name Ihres Geschäfts"),
            "address": _("Adresse"),
            "city": _("Stadt"),
            "district": _("Stadtteil"),
            "contact_phone": _("Telefon"),
            "whatsapp_number": _("WhatsApp-Nummer"),
            "contact_email": _("E-Mail für Kundschaft und Impressum"),
            "legal_form": _("Rechtsform"),
            "legal_representative": _("Vertreten durch (Geschäftsführer/in, Inhaber/in)"),
            "register_court": _("Registergericht"),
            "register_number": _("Registernummer"),
            "vat_id": _("USt-IdNr."),
            "tax_number": _("Steuernummer"),
        }
        help_texts = {
            "contact_email": _("Erscheint im Impressum — nicht Ihre Login-Adresse."),
            "register_court": _("Nur mit Handelsregister-Eintrag, z. B. „Amtsgericht Wuppertal“."),
        }
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "contact_email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "contact_phone": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
            "whatsapp_number": forms.TextInput(attrs={"type": "tel"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core import districts
        from apps.finance import ustva

        self.fields["tax_choice"].choices = ustva.REGIME_CHOICES
        self.fields["tax_choice"].initial = ustva.regime_of(self.instance)

        # Обязателен, если показать в Impressum нечего: иначе префилл почтой входа.
        self.fields["contact_email"].required = True
        if not self.is_bound and not self.instance.contact_email:
            # Префилл почтой входа — владелец видит её и может сменить (не молча в Impressum).
            self.initial["contact_email"] = self.instance.owner_email
        city = (self.data.get("city") if self.is_bound else None) or self.instance.city
        choices = districts.choices_for(city)
        if choices:
            # Ревью W1.1: CharField + Select, а не ChoiceField — район старого города после
            # смены города не валит форму (clean_district его нормализует), а сохранённое
            # значение вне справочника остаётся выбранным и не стирается при любом Save.
            stored = self.instance.district
            if stored and stored not in {slug for slug, _n in choices}:
                choices = [*choices, (stored, stored)]
            self.fields["district"] = forms.CharField(
                label=_("Stadtteil"),
                required=False,
                widget=forms.Select(choices=[("", "—"), *choices]),
            )
        else:
            self.fields["district"].widget = forms.HiddenInput()

    def sections(self):
        return [
            {"key": key, "title": title, "fields": [self[n] for n in names if n in self.fields]}
            for key, title, names in self.SECTIONS
        ]

    def save(self, commit=True):
        from apps.finance import ustva

        obj = super().save(commit=False)
        ustva.apply_regime(obj, self.cleaned_data.get("tax_choice", ""))
        if commit:
            obj.save()
        return obj

    def clean_district(self):
        from apps.core import districts

        city = self.cleaned_data.get("city") or self.instance.city
        value = (self.cleaned_data.get("district") or "").strip()
        slug = districts.normalize(city, value)
        if not slug and value and value == self.instance.district and city == self.instance.city:
            return value  # старое значение вне справочника — не стираем при чужом Save
        return slug

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
@owner_required  # KA-12: правовые и налоговые данные — только владелец (не только middleware)
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
            update_fields=[
                *LiteBusinessForm.Meta.fields,
                "small_business",
                "tax_regime",
                "opening_hours_structured",
                "updated_at",
            ]
        )
        from apps.aggregator.tasks import refresh_tenant_fields

        refresh_tenant_fields(obj)  # имя/адрес — в листинги каталога города
        messages.success(request, gettext("Gespeichert."))
        return redirect("lite-business")
    return render(
        request,
        "tenant/lite_business.html",
        {
            "form": form,
            "nav": "settings",
            "opening_hours_rows": _opening_hours_rows(tenant),
            "impressum_missing": impressum_missing(tenant),
        },
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


def _can(user, key) -> bool:
    from apps.core.permissions import has_perm

    try:
        return has_perm(user, key)
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
    channels = _can(request.user, "kanaele.edit")
    stats = _can(request.user, "stadtportal.view")
    # T-8.30 (Р-2): из Telegram — только статусы; свой бот подключается по e-mail-входу.
    can_manage_bot = channels and not tg_login.is_tg_session(request)

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
            "is_owner": channels,
            "can_manage_bot": can_manage_bot,
            "site_url": _block(lambda: _public_url(request, "/"), ""),
            "portal": _block(
                lambda: _portal_block(tenant, stats), {"reason": "", "count": 0, "views": None}
            ),
            "google_on": _block(_google_connected, False),
            "publishing_on": tenant.is_module_active("publishing"),
            "platform_bot": st.safe(lambda: st.telegram(tenant)),
            "own_bot": st.own_bot(tenant),
            "payments_on": bool(getattr(tenant, "payments_enabled", False)),
            "domain": st.safe(lambda: st.domain(tenant)),
        },
    )


@login_required
def lite_requests(request):
    """KA-12 E8.9: «Anfragen» лёгкого кабинета — заявки клиентов (модуль jobs) списком,
    50 на страницу. Карточка заявки (смета, деньги) — вне Telegram; в Mini App видно
    сообщение и контакты клиента, чтобы ответить."""
    from django.http import Http404

    from apps.core.pagination import paginate_queryset
    from apps.jobs.models import Job

    if not request.tenant.is_module_active("jobs"):
        raise Http404
    status = request.GET.get("status", "")
    qs = Job.objects.select_related("customer").order_by("-created_at")
    if status in dict(Job.STATUSES):
        qs = qs.filter(status=status)
    page = paginate_queryset(qs, page_raw=request.GET.get("seite"))
    return render(
        request,
        "tenant/lite_requests.html",
        {
            "nav": "board",
            "jobs": page.items,
            "page": page,
            "statuses": Job.STATUSES,
            "active_status": status,
        },
    )
