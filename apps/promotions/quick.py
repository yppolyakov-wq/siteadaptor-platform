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


def until_time_key(term, until) -> str:
    """К какому сроку относится час окончания: «today» / ISO-дата / "" (ни к какому)."""
    if term == TERM_TODAY:
        return TERM_TODAY
    if term == TERM_DATE and until:
        return until.isoformat() if hasattr(until, "isoformat") else str(until)
    return ""


def term_end(term: str, tenant, *, until=None, until_time=None, now=None) -> datetime | None:
    """Конец акции для выбранного чипа срока (в локальной таймзоне проекта).

    T-8.10b: ``until_time`` — конкретный час («bis 18 Uhr») для «сегодня»/даты."""
    now = timezone.localtime(now or timezone.now())
    today = now.date()
    if until_time is not None and term in (TERM_TODAY, TERM_DATE):
        day = until if (term == TERM_DATE and until) else today
        return timezone.make_aware(datetime.combine(day, until_time))
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


def default_term(tenant) -> str:
    """Д1: срок по умолчанию — правило, а не ИИ. Еда → сегодня, мода/торговля → выходные."""
    from apps.core.archetypes import FOOD_BUSINESS_TYPES

    btype = getattr(tenant, "business_type", "") or ""
    if btype in FOOD_BUSINESS_TYPES:
        return TERM_TODAY
    if btype in ("clothing", "retail", "online_shop"):
        return TERM_WEEKEND
    return TERM_WEEK


MAX_PHOTOS = 6


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiplePhotoField(forms.FileField):
    """Несколько фото одним полем (T-8.5b): ``cleaned_data`` — список файлов."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else [data]
        files = [f for f in files if f]
        if len(files) > MAX_PHOTOS:
            raise forms.ValidationError(
                _("Höchstens %(n)s Fotos.") % {"n": MAX_PHOTOS}, code="too_many"
            )
        return [super(MultiplePhotoField, self).clean(f, initial) for f in files]


def save_photos(files) -> list[dict]:
    """Сохранить фото по порядку (первое — главное). Ошибка одного — откат всех."""
    from apps.catalog.images import delete_stored_image, save_product_image

    saved: list[dict] = []
    try:
        for i, upload in enumerate(files or []):
            saved.append(
                save_product_image(upload, is_primary=(i == 0), sort_order=i, folder="promotions")
            )
    except Exception:
        for ref in saved:
            delete_stored_image(ref)
        raise
    return saved


class QuickPromotionForm(forms.Form):
    title = forms.CharField(label=_("Was bieten Sie an?"), max_length=200)
    description = forms.CharField(
        label=_("Kurz beschreiben (optional)"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    photo = MultiplePhotoField(label=_("Fotos"), required=False)
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
    # T-8.10b: конкретный час окончания (из сообщения в Telegram); пусто = прежний срок.
    until_time = forms.TimeField(required=False, widget=forms.HiddenInput)
    # …и к какому сроку этот час относится («today» или ISO-дата): сменил владелец срок
    # в форме — час из сообщения к новому дню не прилипает.
    until_time_for = forms.CharField(required=False, max_length=10, widget=forms.HiddenInput)
    # T-8.10b: токен черновика из Telegram (✏️ «Bearbeiten»).
    entwurf = forms.CharField(required=False, max_length=32, widget=forms.HiddenInput)
    # SF-8b: исключение § 11 Abs. 4 PAngV (кнопка-флаг рядом с ценой).
    perishable = forms.BooleanField(
        label=_("Schnell verderblich / kurze Haltbarkeit"), required=False
    )
    customer_response = forms.ChoiceField(label=_("Was tun Kund:innen?"), widget=forms.RadioSelect)
    group = forms.CharField(required=False, max_length=50, widget=forms.HiddenInput)
    # T-8.23d: товар — основа акции. Пусто = новый товар из этих же данных.
    product = forms.ModelChoiceField(label=_("Für welches Produkt?"), queryset=None, required=False)
    sku = forms.CharField(label=_("Artikelnummer (optional)"), required=False, max_length=100)
    category = forms.ModelChoiceField(label=_("Kategorie"), queryset=None, required=False)
    new_category = forms.CharField(label=_("Neue Kategorie"), required=False, max_length=100)
    # Д1: владелец принял черновик ИИ (ставит скрипт кнопки) — для замера принятия.
    ai_draft = forms.BooleanField(required=False, widget=forms.HiddenInput)
    # Д1 (T-8.10c): подсказка «Was heute starten?» — ключ; цель берётся из пересчёта БД.
    vorschlag = forms.CharField(required=False, max_length=120, widget=forms.HiddenInput)

    def __init__(self, *args, tenant=None, suggestion=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        self.suggestion = suggestion
        from . import reference_price

        # В6: исключение § 11 Abs. 4 — только у бизнесов с продуктами питания.
        if not (reference_price.exemption_enabled() and reference_price.food_allowed(tenant)):
            self.fields.pop("perishable", None)
        from apps.catalog.models import Category, Product

        # Выборки ленивые: на публичном хосте («Aktion in 3 Klicks») каталога ещё нет,
        # поля там не рисуются и не запрашиваются.
        self.fields["product"].queryset = Product.objects.filter(is_active=True).order_by(
            "-created_at"
        )
        self.fields["category"].queryset = Category.objects.filter(is_active=True)
        # «＋ Neue Kategorie» в селекте — не pk: имя приходит отдельным полем.
        if self.is_bound and self.data.get("category") == "__new":
            self.data = self.data.copy()
            self.data["category"] = ""
        self.response_options = response_options(tenant)
        self.fields["customer_response"].choices = [
            (k, label) for k, label, _h in self.response_options
        ]
        self.fields["customer_response"].initial = default_response(tenant)
        if self.booking_target:
            # Цель — услуга/номер: отклик всегда онлайн-бронь (response.py), выбора нет.
            self.fields["customer_response"].required = False
        from apps.core import city_categories as cc

        from . import city_fields

        # T-8.13a: одной строкой, подсказка по типу бизнеса уже выбрана.
        suggestion = (
            cc.suggest_for_business_type(getattr(tenant, "business_type", "")) if tenant else ""
        )
        city_fields.add_fields(self, category=suggestion)

    @property
    def booking_target(self) -> bool:
        target = getattr(self.suggestion, "target", None)
        return bool(target and target[0] in ("service", "stay_unit"))

    def clean(self):
        cleaned = super().clean()
        if self.booking_target:
            # Услуга/номер считают скидку ТОЛЬКО процентом (price_layer): цена «Aktionspreis/
            # statt» молча не действовала бы — акция вышла бы без скидки.
            cleaned["new_price"] = cleaned["old_price"] = None
            if not cleaned.get("percent"):
                self.add_error("percent", _("Bitte einen Rabatt in Prozent angeben."))
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
        until_time = cleaned.get("until_time")
        if until_time is not None and cleaned.get("until_time_for") != until_time_key(
            cleaned.get("term"), cleaned.get("until")
        ):
            cleaned["until_time"] = until_time = None
        if until_time is not None and cleaned.get("term") in (TERM_TODAY, TERM_DATE):
            end = term_end(
                cleaned["term"], self.tenant, until=cleaned.get("until"), until_time=until_time
            )
            if end is not None and end <= timezone.now():
                self.add_error(None, _("Die Uhrzeit liegt in der Vergangenheit."))
        return cleaned

    def build(self):
        """Несохранённая ``Promotion`` из ввода (без фото и без статуса)."""
        from . import city_fields
        from .models import Promotion

        data = self.cleaned_data
        meta = {"response": data["customer_response"]} if data.get("customer_response") else {}
        if data.get("perishable") and "perishable" in self.fields:
            meta["perishable"] = True
        if data.get("ai_draft"):
            meta["ai_draft"] = True
        if self.suggestion is not None:
            meta["suggestion"] = self.suggestion.rule
        if self.booking_target:
            meta.pop("response", None)

        city_category, city_tags = city_fields.cleaned(self)
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
            ends_at=term_end(
                data["term"],
                self.tenant,
                until=data.get("until"),
                until_time=data.get("until_time"),
            ),
            group=(data.get("group") or "").strip(),
            city_category=city_category,
            city_tags=city_tags,
            metadata=meta,
        )


def publish_built(form, promo, images: list[dict], *, tenant, actor, publish: bool = True):
    """Общий хвост «Schnell-Aktion» (веб T-8.4 и Telegram T-8.10b): цель → сохранить →
    активировать с учётом лимита Р-5. → (promo, activated)."""
    from . import limits

    if not apply_suggestion(form, promo, images):
        attach_product(form, promo, images)  # T-8.23d: акция от товара
    promo.save()
    activated = False
    if publish:
        try:
            limits.activate(promo, tenant, actor=actor)
            activated = True
        except limits.ActivationLimit:
            pass  # остаётся черновиком — экран «Fertig» / бот объясняют почему
    return promo, activated


def apply_suggestion(form, promo, images: list[dict]) -> bool:
    """Д1 (T-8.10c): цель и правила подсказки — из ПЕРЕСЧИТАННОЙ подсказки, не из POST.

    True — цель привязана здесь (товар/услуга/номер), `attach_product` не нужен: для
    услуги и номера он создал бы лишний товар из цены."""
    suggestion = getattr(form, "suggestion", None)
    if suggestion is None or not suggestion.target:
        return False
    kind, pk = suggestion.target
    if kind == "product":
        promo.product_id = pk
    elif kind == "service":
        promo.service_id = pk
    elif kind == "stay_unit":
        promo.stay_unit_id = pk
    else:
        return False
    promo.target_rules = dict(suggestion.target_rules or {})
    promo.images = images
    return True


def attach_product(form, promo, images: list[dict]) -> None:
    """T-8.23d: акция всегда от товара (решение владельца 2026-10-11).

    Выбран товар — привязка, фото ассистента остаются у акции. Не выбран — товар
    создаётся из тех же данных: название, описание, цена «statt» (иначе акционная),
    артикул, категория; фото переходят в товар (у акции пусто — витрина берёт фото и
    старую цену у товара, файлы не копируются). Остатки не ведутся (S1). Без цены вовсе
    («−20 % auf alles») товар честно не создать — акция остаётся свободной.
    """
    from apps.catalog.models import Category, Product

    data = form.cleaned_data
    product = data.get("product")
    if product is not None:
        promo.product = product
        promo.images = images
        return
    regular = data.get("old_price")
    if regular is None:
        regular = data.get("new_price")
    if regular is None:
        promo.images = images
        return
    category = data.get("category")
    new_cat = (data.get("new_category") or "").strip()
    if new_cat:
        from apps.catalog.slugs import unique_slug

        category = Category.objects.create(
            name={settings.LANGUAGE_CODE: new_cat},
            slug=unique_slug(Category, new_cat, fallback="kategorie"),
        )
    promo.product = Product.objects.create(
        name=dict(promo.title or {}),
        description=dict(promo.description or {}),
        base_price=regular,
        sku=(data.get("sku") or "").strip(),
        category=category,
        images=images,
    )
    promo.images = []


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
        "city_category": promo.city_category,
        "city_tags": list(promo.city_tags or []),
        "term": TERM_WEEK,
    }
    if promo.available_quantity:
        initial["quantity"] = promo.available_quantity
    meta = promo.metadata if isinstance(promo.metadata, dict) else {}
    if meta.get("perishable"):
        # SF-8b: «Wiederholen» переносит выбор владельца как есть (действует он только
        # у товара — `is_perishable`; у свободной акции флаг хранится, но инертен).
        initial["perishable"] = True
    chosen = resp.chosen(promo)
    if chosen:
        initial["customer_response"] = chosen
    if promo.images:
        initial["photo_from"] = promo.pk
    if promo.product_id:
        initial["product"] = promo.product_id  # T-8.23d: «Wiederholen» — тот же товар
    return {k: v for k, v in initial.items() if v not in (None, "", [])}


def initial_for_product(product) -> dict:
    """T-8.23d: «% Aktion» с карточки товара — товар выбран, заголовок и «statt» из него."""
    return {
        "product": product.pk,
        "title": _base_text(product.name) or str(product),
        "old_price": product.base_price,
        "term": TERM_WEEK,
    }


def copy_images(source) -> list[dict]:
    """Копии ВСЕХ фото акции отдельными файлами (удаление у одной не трогает другую).

    Порядок прежний, главное — первое; битый/пропавший файл пропускается."""
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    from apps.catalog.images import save_product_image

    if source is None:
        return []
    images = sorted(
        (i for i in (source.images or []) if isinstance(i, dict) and i.get("path")),
        key=lambda i: (not i.get("is_primary"), i.get("sort_order", 0)),
    )
    copies: list[dict] = []
    for img in images:
        path = img["path"]
        try:
            with default_storage.open(path, "rb") as fh:
                content = ContentFile(fh.read(), name=path.rsplit("/", 1)[-1])
            copies.append(
                save_product_image(
                    content, is_primary=not copies, sort_order=len(copies), folder="promotions"
                )
            )
        except Exception:  # noqa: BLE001 — нет файла/битый — без этого фото
            continue
    return copies


def copy_primary_image(source) -> dict | None:
    """Совместимость: первая из копий (главное фото)."""
    copies = copy_images(source)
    return copies[0] if copies else None
