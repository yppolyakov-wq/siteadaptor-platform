"""T-8.13a: поля «Kategorie im Stadtkatalog» + «Merkmale» — одни на все формы акции.

Полная форма, ассистент T-8.4 и `/aktion-starten/` берут поля отсюда, чтобы подписи,
варианты и нормализация не расходились. Справочник — `apps/core/city_categories.py`.
"""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core import city_categories as cc


def category_field(
    initial: str = "", *, business_type: str | None = None, keep: str = ""
) -> forms.ChoiceField:
    return forms.ChoiceField(
        label=_("Kategorie im Stadtkatalog"),
        required=False,
        choices=[
            ("", _("Automatisch (nach Art des Geschäfts)")),
            *cc.grouped_choices(business_type, keep=keep),
        ],
        initial=initial,
        help_text=_("Damit Leute Ihr Angebot im Stadtportal unter der richtigen Rubrik finden."),
    )


def tags_field(initial=None) -> forms.MultipleChoiceField:
    return forms.MultipleChoiceField(
        label=_("Merkmale"),
        required=False,
        choices=cc.tag_choices(),
        initial=list(initial or []),
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Nur ankreuzen, was wirklich zutrifft (z. B. vegan, regional)."),
    )


def add_fields(
    form, *, category: str = "", tags=None, business_type: str | None = None, keep: str = ""
) -> None:
    """``business_type`` — список категорий только разделов этого типа (None = все:
    тип ещё не выбран, как на странице регистрации); ``keep`` — уже сохранённая
    категория вне разделов остаётся выбираемой (Save её не сбросит)."""
    form.fields["city_category"] = category_field(category, business_type=business_type, keep=keep)
    form.fields["city_tags"] = tags_field(tags)
    form.city_category_groups = cc.grouped_choices(business_type, keep=keep)
    form.city_tag_map = cc.tag_map()  # T-8.23e: признаки по категории (фильтр чипов)


def cleaned(form) -> tuple[str, list[str]]:
    """Категория и признаки; T-8.23e: признаки чужого раздела отбрасываются
    («Automatisch» — без категории — оставляет все известные)."""
    data = getattr(form, "cleaned_data", {}) or {}
    category = cc.normalize_category(data.get("city_category"))
    return category, cc.allowed_tags(data.get("city_tags"), category)
