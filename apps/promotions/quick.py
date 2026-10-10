"""T-8.4: «Schnell-Aktion» — акция с телефона за три шага.

План — docs/t8-4-assistant-plan-2026-10-10.md §2–3. Ассистент создаёт ОБЫЧНУЮ
``Promotion``: дальше её ведёт всё существующее (полная форма, витрина, портал,
резерв, аналитика). Здесь только короткий ввод, расчёт срока чипами и «Wiederholen».
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django import forms
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from . import response as promo_response

TERM_TODAY = "today"
TERM_WEEKEND = "weekend"
TERM_WEEK = "week"
TERM_DATE = "date"

TERM_CHOICES = [
    (TERM_TODAY, _("Heute bis Ladenschluss")),
    (TERM_WEEKEND, _("Dieses Wochenende")),
    (TERM_WEEK, _("7 Tage")),
    (TERM_DATE, _("Eigenes Datum")),
]

# Подписи откликов в ассистенте — короче, чем в полной форме, и с примером.
RESPONSE_HINTS = {
    promo_response.RESERVE: _("Kund:innen lassen es zurücklegen und holen es bei Ihnen ab."),
    promo_response.COUPON: _("Kund:innen holen sich einen Code und zeigen ihn an der Kasse."),
    promo_response.SHOW: _("Nur zeigen: Preis, Adresse, Route und Anruf."),
    promo_response.INQUIRE: _("Kund:innen schicken eine Anfrage mit Datum und Wunsch."),
    promo_response.BUY: _("Kund:innen bestellen direkt online."),
}


def response_options(tenant) -> list[tuple[str, str, str]]:
    """Выполнимые отклики для этого тенанта: (ключ, подпись, подсказка)."""
    labels = dict(promo_response.CHOICES)
    keys = [promo_response.RESERVE, promo_response.COUPON, promo_response.SHOW]
    if promo_response.can_inquire(tenant):
        keys.append(promo_response.INQUIRE)
    if promo_response.can_buy(tenant):
        keys.insert(0, promo_response.BUY)
    return [(k, labels[k], RESPONSE_HINTS[k]) for k in keys]


def default_response(tenant) -> str:
    """То, что выбрала бы автоматика: онлайн-заказ, если можно, иначе «отложить»."""
    return promo_response.BUY if promo_response.can_buy(tenant) else promo_response.RESERVE


def _end_of_day(day) -> datetime:
    return timezone.make_aware(datetime.combine(day, time(23, 59)))


def term_end(term: str, tenant, *, until=None, now=None) -> datetime | None:
    """Конец акции для выбранного чипа срока (в локальной таймзоне проекта)."""
    now = timezone.localtime(now or timezone.now())
    today = now.date()
    if term == TERM_TODAY:
        from apps.tenants import openinghours

        hours = openinghours.normalize(getattr(tenant, "opening_hours_structured", None))
        rng = hours.get(str(today.weekday()))
        if rng:
            h, m = (int(x) for x in rng[1].split(":"))
            close = timezone.make_aware(datetime.combine(today, time(h, m)))
            if close > now:
                return close
        return _end_of_day(today)
    if term == TERM_WEEKEND:
        # До воскресенья 23:59 (в воскресенье — до конца этого дня).
        return _end_of_day(today + timedelta(days=(6 - today.weekday())))
    if term == TERM_DATE and until:
        return _end_of_day(until)
    return _end_of_day(today + timedelta(days=7))


class QuickPromotionForm(forms.Form):
    title = forms.CharField(label=_("Was bieten Sie an?"), max_length=200)
    description = forms.CharField(
        label=_("Kurz beschreiben (optional)"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    photo = forms.FileField(label=_("Foto"), required=False)
    # Фото прошлой акции при «Wiederholen» (копия файла, а не общая ссылка).
    photo_from = forms.UUIDField(required=False, widget=forms.HiddenInput)
    new_price = forms.DecimalField(
        label=_("Aktionspreis €"), required=False, min_value=0, max_digits=10, decimal_places=2
    )
    old_price = forms.DecimalField(
        label=_("Statt €"), required=False, min_value=0, max_digits=10, decimal_places=2
    )
    percent = forms.IntegerField(
        label=_("oder Rabatt in Prozent"), required=False, min_value=1, max_value=99
    )
    term = forms.ChoiceField(
        label=_("Wie lange?"), choices=TERM_CHOICES, initial=TERM_WEEK, widget=forms.RadioSelect
    )
    until = forms.DateField(
        label=_("Bis"), required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    quantity = forms.IntegerField(label=_("Stückzahl (optional)"), required=False, min_value=1)
    customer_response = forms.ChoiceField(label=_("Was tun Kund:innen?"), widget=forms.RadioSelect)
    group = forms.CharField(required=False, max_length=50, widget=forms.HiddenInput)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        self.response_options = response_options(tenant)
        self.fields["customer_response"].choices = [
            (k, label) for k, label, _h in self.response_options
        ]
        self.fields["customer_response"].initial = default_response(tenant)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("new_price") is not None and cleaned.get("percent"):
            self.add_error("percent", _("Bitte entweder einen Preis oder einen Rabatt angeben."))
        old, new = cleaned.get("old_price"), cleaned.get("new_price")
        if old is not None and new is not None and old <= new:
            self.add_error("old_price", _("Der alte Preis muss höher sein als der Aktionspreis."))
        if cleaned.get("term") == TERM_DATE:
            until = cleaned.get("until")
            if not until:
                self.add_error("until", _("Bitte ein Datum wählen."))
            elif until < timezone.localdate():
                self.add_error("until", _("Das Datum liegt in der Vergangenheit."))
        return cleaned

    def build(self):
        """Несохранённая ``Promotion`` из ввода (без фото и без статуса)."""
        from .models import Promotion

        data = self.cleaned_data
        meta = {"response": data["customer_response"]} if data.get("customer_response") else {}
        return Promotion(
            title={settings.LANGUAGE_CODE: data["title"].strip()},
            description=(
                {settings.LANGUAGE_CODE: data["description"].strip()}
                if (data.get("description") or "").strip()
                else {}
            ),
            promo_type=Promotion.DISCOUNT,
            price_override=data.get("new_price"),
            compare_at_price=data.get("old_price"),
            discount_percent=data.get("percent"),
            available_quantity=data.get("quantity"),
            starts_at=timezone.now(),
            ends_at=term_end(data["term"], self.tenant, until=data.get("until")),
            group=(data.get("group") or "").strip(),
            metadata=meta,
        )


def _base_text(value) -> str:
    """Базовый текст i18n-поля (тот, что ассистент и пишет)."""
    return (value or {}).get(settings.LANGUAGE_CODE, "") if isinstance(value, dict) else ""


def initial_from(promo) -> dict:
    """«Wiederholen»: то же предложение, новый срок выбирает владелец."""
    from . import response as resp

    initial = {
        "title": _base_text(promo.title) or promo.title_text,
        "description": _base_text(promo.description),
        "new_price": promo.price_override,
        "old_price": promo.compare_at_price,
        "percent": promo.discount_percent if promo.price_override is None else None,
        "quantity": None,
        "group": promo.group,
        "term": TERM_WEEK,
    }
    if promo.available_quantity:
        initial["quantity"] = promo.available_quantity
    chosen = resp.chosen(promo)
    if chosen:
        initial["customer_response"] = chosen
    if promo.images:
        initial["photo_from"] = promo.pk
    return {k: v for k, v in initial.items() if v not in (None, "")}


def copy_primary_image(source) -> dict | None:
    """Копия главного фото акции отдельным файлом (удаление у одной не трогает другую)."""
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    from apps.catalog.images import save_product_image

    img = source.primary_image if source is not None else None
    path = (img or {}).get("path")
    if not path:
        return None
    try:
        with default_storage.open(path, "rb") as fh:
            content = ContentFile(fh.read(), name=path.rsplit("/", 1)[-1])
        return save_product_image(content, is_primary=True, folder="promotions")
    except Exception:  # noqa: BLE001 — нет файла/битый — акция без своего фото
        return None
