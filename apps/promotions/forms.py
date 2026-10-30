"""Формы кабинета: создание/редактирование акций.

i18n-поля (title/description) редактируются парами de/en и собираются в
JSONField. Статус акции через форму не меняется — только через PromotionSM
(кнопки переходов). starts_at/ends_at — datetime-local.
"""

from datetime import timedelta

from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Product
from apps.core import card_forms
from apps.core.form_fields import MoneyField
from apps.core.i18n_input import DynamicI18nFormMixin, extra_locales
from apps.loyalty.models import LoyaltyProgram

from . import group_styles
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


class PromotionForm(DynamicI18nFormMixin, forms.ModelForm):
    # L3d.5: база (de) статическая, прочие локали — динамически (см. i18n_input).
    title_de = forms.CharField(label=_("Title (DE)"), max_length=200)
    description_de = forms.CharField(
        label=_("Description (DE)"), widget=forms.Textarea(attrs={"rows": 3}), required=False
    )
    i18n_fields = (
        ("title", {"label": _("Titel"), "max_length": 200}),
        ("description", {"label": _("Beschreibung"), "textarea": True}),
    )
    starts_at = _DateTimeLocal(label=_("Starts at"))
    ends_at = _DateTimeLocal(label=_("Ends at"))

    class Meta:
        model = Promotion
        # KA-M2: цены принимают «12,50».
        field_classes = {
            "compare_at_price": MoneyField,
            "price_override": MoneyField,
            "discount_off": MoneyField,
        }
        fields = [
            "product",
            # W11-4: цели ценового слоя PL (P1) — движок готов с 2026-08-04,
            # теперь выбираются из формы (гейт по модулям в __init__).
            "service",
            "stay_unit",
            "combo",
            # KA-12 PR-1: область шире товара — категория (с подкатегориями) / весь магазин.
            "category",
            "whole_shop",
            "promo_type",
            "compare_at_price",
            "discount_percent",
            "discount_off",
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
            "card_style",
            "page_style",
            "is_surprise",
            "recurrence",
            "group",
        ]
        labels = {
            "product": _("Product"),
            "promo_type": _("Art der Aktion"),
            "available_quantity": _("Verfügbare Menge"),
            "max_per_customer": _("Max. pro Kunde"),
            "reservation_ttl_hours": _("Reservierung gültig (Stunden)"),
            "auto_confirm": _("Automatisch bestätigen"),
            "group": _("Typ der Aktion (Rubrik)"),
            "category": _("Ganze Kategorie"),
            "whole_shop": _("Ganzer Shop"),
            "compare_at_price": _("Old price (struck through)"),
            "discount_percent": _("Discount %"),
            "discount_off": _("Rabatt in € pro Stück"),
            "price_override": _("New price"),
            "strikethrough_old_price": _("Strike through the old price"),
            "show_countdown": _("Show countdown to end"),
            "discount_style": _("Discount display style"),
            "card_style": _("Card form"),
            "page_style": _("Vorlage der Seite"),
            "is_surprise": _("Surprise bag (rescue leftovers, anti-waste)"),
            "recurrence": _("Repeat automatically"),
        }
        help_texts = {
            "compare_at_price": _("Leave blank to use the linked product's price."),
            "discount_percent": _("Either a percentage or a new price — the rest is computed."),
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
            "category": _(
                "Rabatt in Prozent auf jedes Produkt dieser Kategorie und ihrer Unterkategorien — "
                "direkt im Warenkorb."
            ),
            "whole_shop": _("Rabatt in Prozent auf jedes Produkt im Shop — direkt im Warenkorb."),
            "group": _(
                "Optional. Der Typ bündelt Aktionen (z. B. „Wochenangebote“, „Räumung“): "
                "eigene Seite, eigene Vorlage und eigenes Raster unter „Aktionstypen“, "
                "Filter auf /aktionen/ und Menüpunkt im Menü-Generator."
            ),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.all()
        self.fields["product"].required = False
        from apps.catalog.models import Category

        if tenant is not None and not tenant.is_module_active("catalog"):
            self.fields.pop("category", None)
            self.fields.pop("whole_shop", None)
        else:
            self.fields["category"].queryset = Category.objects.all()
            self.fields["category"].required = False
        # W11-4: цели PL — селекты только при активном модуле (tenant=None в
        # тестах → fail-open, как у прочих гейтов формы).
        from apps.booking.models import Service
        from apps.catalog.models import Combo
        from apps.stays.models import StayUnit

        _targets = (
            ("service", "booking", Service, _("Leistung")),
            ("stay_unit", "stays", StayUnit, _("Zimmer")),
            ("combo", "catalog", Combo, _("Kombi")),
        )
        for fname, module, model, label in _targets:
            if tenant is not None and not tenant.is_module_active(module):
                self.fields.pop(fname, None)
                continue
            self.fields[fname].queryset = model.objects.all()
            self.fields[fname].required = False
            self.fields[fname].label = label
        if "service" in self.fields:
            self.fields["service"].help_text = _(
                "Aktion gilt für diese Leistung — Aktionspreis greift automatisch bei der Buchung."
            )
        if "stay_unit" in self.fields:
            self.fields["stay_unit"].help_text = _(
                "Aktion gilt für dieses Zimmer — wirkt als Preis-Kandidat bei der Buchung."
            )
        # DL-19: ФОРМА карточки этой акции — из реестра card_forms; пусто = «как в
        # настройках сайта», заданное значение побеждает общий выбор владельца.
        self.fields["card_style"] = forms.ChoiceField(
            label=_("Card form"),
            required=False,
            choices=[
                (key, f"{label} — {hint}" if hint else label)
                for key, label, hint in card_forms.forms_for(card_forms.PROMO)
            ],
            help_text=_("Leer = wie in den Website-Einstellungen eingestellt."),
        )
        # STU-15a: ШАБЛОН СТРАНИЦЫ этой акции. Тот же приём: реестр даёт варианты,
        # поэтому список растёт без миграции (в модели choices не зашиты).
        page_style_label = _("Vorlage der Seite")
        self.fields["page_style"] = forms.ChoiceField(
            label=page_style_label,
            required=False,
            choices=[
                (key, f"{label} — {hint}" if hint else label)
                for key, label, hint in group_styles.PROMOTION_DETAIL_STYLES
            ],
            help_text=_("Leer = wie in den Website-Einstellungen eingestellt."),
        )
        # T-8.2: что делает кнопка акции на витрине (Promotion.metadata["response"],
        # без миграции). Пусто = автоматически: онлайн-заказ при модуле заказов,
        # иначе «Zurücklegen».
        from . import response as promo_response

        self.fields["customer_response"] = forms.ChoiceField(
            label=_("Reaktion der Kundschaft"),
            required=False,
            choices=promo_response.CHOICES,
            initial=promo_response.chosen(self.instance),
            help_text=_(
                "Was der Button auf der Aktionsseite tut. „Automatisch“: online bestellen, "
                "wenn Bestellungen aktiv sind — sonst zurücklegen lassen."
            ),
        )
        # KA-12 PR-4: «Gratis-Artikel ab Bestellwert» — порог в metadata, цель = подарок.
        from . import gifts

        gift_min0 = gifts.threshold(self.instance)
        self.fields["gift_min_order"] = MoneyField(
            label=_("Gratis dazu ab Bestellwert (€)"),
            required=False,
            min_value=0,
            decimal_places=2,
            max_digits=10,
            initial=gift_min0,
            help_text=_(
                "Das gewählte Produkt kommt kostenlos in jede Bestellung ab diesem Warenwert. "
                "Der Preis des Produkts selbst ändert sich nicht."
            ),
        )
        # KA-12 PR-5: кому действует онлайн-цена акции (metadata["customer_rule"]).
        from . import eligibility

        self.fields["customer_rule"] = forms.ChoiceField(
            label=_("Für wen gilt der Online-Preis?"),
            required=False,
            choices=eligibility.CHOICES,
            initial=eligibility.rule_of(self.instance),
            help_text=_(
                "Geprüft an der Kasse über E-Mail oder Telefon. Wer nicht passt, bekommt einen "
                "Hinweis statt des Aktionspreises."
            ),
        )
        # KA-12 E6.6 (Р-3): код купона — только письмом (проверка владения адресом).
        meta0 = self.instance.metadata if isinstance(self.instance.metadata, dict) else {}
        self.fields["coupon_by_email"] = forms.BooleanField(
            label=_("Coupon nur an E-Mail senden"),
            required=False,
            initial=meta0.get("coupon_delivery") == "email",
            help_text=_(
                "Für begrenzte Coupons: der Code kommt nur per E-Mail, nicht im Browser — "
                "so holt sich niemand alle Coupons mit erfundenen Adressen."
            ),
        )
        # SF-8b: исключение § 11 Abs. 4 PAngV — флаг владельца в metadata (без миграции);
        # при выключенном исключении (settings) поля в форме нет вовсе.
        from . import reference_price

        if reference_price.exemption_enabled() and reference_price.food_allowed(tenant):
            self.fields["perishable"] = forms.BooleanField(
                label=_("Schnell verderblich / kurze Haltbarkeit"),
                required=False,
                initial=bool((self.instance.metadata or {}).get("perishable"))
                if isinstance(self.instance.metadata, dict)
                else False,
                help_text=_(
                    "§ 11 Abs. 4 PAngV: Preissenkung wegen drohenden Verderbs oder ablaufender "
                    "Haltbarkeit — der niedrigste Preis der letzten 30 Tage wird dann nicht "
                    "angewendet."
                ),
            )
        # В2: условие цены («2. Stück −50 %»): metadata["price_condition"], без миграции.
        from apps.core import price_conditions as pc

        cond = pc.of(self.instance) or {}
        self.fields["price_condition_kind"] = forms.ChoiceField(
            label=_("Preis gilt nur unter Bedingung"),
            required=False,
            choices=pc.CHOICES,
            initial=cond.get("kind", ""),
            help_text=_(
                "Zum Beispiel „zweite Pizza zum halben Preis“: der Stückpreis bleibt normal, die Aktion "
                "zeigt die Bedingung statt eines falschen Stückpreises. Online-Kauf ist "
                "dann nicht möglich."
            ),
        )
        self.fields["price_condition_n"] = forms.IntegerField(
            label=_("Stückzahl (n)"),
            required=False,
            min_value=2,
            max_value=99,
            initial=cond.get("n"),
        )
        self.fields["price_condition_pay"] = forms.IntegerField(
            label=_("Bezahlt werden (m)"),
            required=False,
            min_value=1,
            max_value=9,
            initial=cond.get("pay"),
        )
        self.fields["price_condition_note"] = forms.CharField(
            label=_("Hinweis zur Bedingung"),
            required=False,
            max_length=pc.NOTE_MAX,
            initial=(cond.get("note") or {}).get(settings.LANGUAGE_CODE, ""),
        )
        # KA-12 GA-8: окно действия «дни недели / часы» (target_rules). Движок окна
        # (price_layer.rules_match, повтор, витрина) готов давно — в полной форме
        # его не было; задавали только пресеты и ассистент.
        from django.utils.dates import WEEKDAYS_ABBR

        rules0 = self.instance.target_rules if isinstance(self.instance.target_rules, dict) else {}
        self.fields["rule_weekdays"] = forms.MultipleChoiceField(
            label=_("Gültig an"),
            required=False,
            choices=[(str(i), str(WEEKDAYS_ABBR[i])) for i in range(7)],
            widget=forms.CheckboxSelectMultiple,
            initial=[str(d) for d in (rules0.get("weekdays") or []) if isinstance(d, int)],
            help_text=_("Leer = jeden Tag. Wiederholte Aktionen überspringen die übrigen Tage."),
        )
        self.fields["rule_hour_from"] = forms.IntegerField(
            label=_("Gültig ab (Uhr)"),
            required=False,
            min_value=0,
            max_value=23,
            initial=rules0.get("hour_from"),
        )
        self.fields["rule_hour_to"] = forms.IntegerField(
            label=_("Gültig bis (Uhr)"),
            required=False,
            min_value=1,
            max_value=24,
            initial=rules0.get("hour_to"),
        )
        # T-8.13a: категория каталога города + признаки. Новая акция — подсказка по типу
        # бизнеса уже выбрана; пусто = подсказка в момент выкладки.
        from apps.core import city_categories as cc

        from . import city_fields

        # UUID-pk есть и у несохранённой акции — новизну смотрим по _state.adding.
        is_new = self.instance._state.adding
        category = "" if is_new else self.instance.city_category
        if is_new and tenant is not None:
            category = cc.suggest_for_business_type(getattr(tenant, "business_type", ""))
        city_fields.add_fields(
            form=self,
            category=category,
            tags=self.instance.city_tags,
            business_type=getattr(tenant, "business_type", None) if tenant else None,
            keep="" if is_new else self.instance.city_category,
        )
        self.init_i18n_fields(tenant)  # L3d.5
        # `group` — flat+overlay (плоское значение = ключ фасета `?gruppe=`,
        # переводы = только метка), поэтому НЕ через DynamicI18nFormMixin:
        # базовая локаль остаётся полем `group`, прочие приезжают динамически.
        # PT: подсказка существующих типов. Поле остаётся СВОБОДНЫМ текстом (новый
        # тип завести по-прежнему можно), но владелец больше не угадывает написание:
        # опечатка плодила бы второй тип с теми же акциями и своей страницей.
        try:
            existing = sorted(
                {
                    g
                    for g in self._meta.model.objects.exclude(group="").values_list(
                        "group", flat=True
                    )
                    if g
                }
            )
        except Exception:  # noqa: BLE001
            existing = []
        #: существующие типы для <datalist> (шаблон рисует его рядом с полем)
        self.promo_type_options = existing
        if existing:
            self.fields["group"].widget.attrs["list"] = "promo-type-options"
        self._group_locales = extra_locales(tenant)
        # msgid наружу: внутри f-строки xgettext его не видит (I18N-13).
        group_label = _("Typ der Aktion (Rubrik)")
        overlay = getattr(self.instance, "group_i18n", None) or {}
        for loc in self._group_locales:
            self.fields[f"group_{loc}"] = forms.CharField(
                label=f"{group_label} ({loc.upper()})",
                max_length=50,
                required=False,
                initial=overlay.get(loc, "") if isinstance(overlay, dict) else "",
            )

    def _non_negative(self, name):
        value = self.cleaned_data.get(name)
        if value is not None and value < 0:
            raise forms.ValidationError(_("Price must be ≥ 0."))
        return value

    def clean_compare_at_price(self):
        return self._non_negative("compare_at_price")

    def clean_price_override(self):
        return self._non_negative("price_override")

    def clean(self):
        cleaned = super().clean()
        starts, ends = cleaned.get("starts_at"), cleaned.get("ends_at")
        if starts and ends and ends <= starts:
            self.add_error("ends_at", _("End must be after start."))
        self._clean_price_condition(cleaned)
        self._clean_rule_window(cleaned, starts, ends)
        self._clean_scope(cleaned)
        # SF-9: у услуги и номера цена акции видна в сетке слотов/расчёте брони — секрет
        # «сюрприза» не спрятать, поэтому сочетание запрещено (товар — только своя страница).
        if cleaned.get("discount_style") == "mystery" and (
            cleaned.get("service") or cleaned.get("stay_unit")
        ):
            self.add_error(
                "discount_style",
                _("Überraschungspreis ist bei Leistungen und Zimmern nicht möglich."),
            )
        return cleaned

    def _clean_scope(self, cleaned):
        """KA-12 PR-1: у акции одна цель; область (категория/магазин) — процент или «−X €»:
        «новая/старая цена» и условие цены — свойства одного товара."""
        targets = [
            name
            for name in ("product", "service", "stay_unit", "combo", "category")
            if cleaned.get(name)
        ] + (["whole_shop"] if cleaned.get("whole_shop") else [])
        if len(targets) > 1:
            self.add_error(targets[-1], _("Bitte nur ein Ziel wählen: Produkt, Kategorie, Shop, …"))
            return
        # PR-2: вид выгоды — один: процент, «−X € pro Stück» или новая цена.
        kinds = [
            n for n in ("discount_percent", "discount_off", "price_override") if cleaned.get(n)
        ]
        if len(kinds) > 1:
            self.add_error(
                kinds[-1], _("Bitte nur eine Art: Prozent, Euro pro Stück oder neuer Preis.")
            )
            return
        if cleaned.get("discount_off") is not None and cleaned["discount_off"] <= 0:
            self.add_error("discount_off", _("Bitte einen Betrag über 0 eingeben."))
        product = cleaned.get("product")
        off = cleaned.get("discount_off")
        if off is not None and product is not None:
            base = cleaned.get("compare_at_price") or product.base_price
            if base is not None and off >= base:
                # Ревью PR-2: «−X €» не дороже самой цены — иначе заказ на 0 €.
                self.add_error("discount_off", _("Der Rabatt muss kleiner als der Preis sein."))
        if cleaned.get("gift_min_order"):
            # PR-4: подарок — конкретный товар, без собственной скидки и условия цены.
            if not cleaned.get("product"):
                self.add_error("gift_min_order", _("Bitte das Geschenk-Produkt wählen."))
            if kinds or getattr(self, "_price_condition", None):
                self.add_error(
                    "gift_min_order",
                    _("Ein Geschenk hat keinen eigenen Rabatt — Felder für Rabatt leer lassen."),
                )
        if cleaned.get("customer_rule") and (cleaned.get("service") or cleaned.get("stay_unit")):
            # Ревью PR-5: запись и проживание не проходят через create_order — правило
            # молча не действовало бы.
            self.add_error(
                "customer_rule",
                _("Gilt nur für Produkte und den Shop — nicht für Leistungen oder Zimmer."),
            )
        if not ({"category", "whole_shop"} & set(targets)):
            return
        if not (cleaned.get("discount_percent") or cleaned.get("discount_off")):
            self.add_error(
                "discount_percent",
                _(
                    "Für eine Kategorie oder den ganzen Shop bitte einen Rabatt in Prozent "
                    "oder Euro angeben."
                ),
            )
        for name in ("price_override", "compare_at_price"):
            if cleaned.get(name) is not None:
                self.add_error(
                    name,
                    _(
                        "Bei Kategorie oder Shop gilt nur ein Rabatt in Prozent oder Euro je Produkt."
                    ),
                )
        if getattr(self, "_price_condition", None):
            self.add_error(
                "price_condition_kind",
                _("Bei Kategorie oder Shop gilt nur ein Rabatt in Prozent oder Euro je Produkt."),
            )
        if cleaned.get("discount_style") == "mystery":
            self.add_error(
                "discount_style", _("Überraschungspreis gibt es nur für ein einzelnes Produkt.")
            )

    def _clean_rule_window(self, cleaned, starts, ends):
        """Ревью GA-8: окно часов не должно быть пустым и обязано пересекаться с
        временем однодневной акции — иначе цена молча не действует никогда."""
        lo, hi = cleaned.get("rule_hour_from"), cleaned.get("rule_hour_to")
        if lo is None and hi is None:
            return
        if lo is not None and hi is not None and lo == hi:
            self.add_error("rule_hour_to", _("Das Zeitfenster ist leer."))
            return
        if not (starts and ends) or ends - starts >= timedelta(days=1):
            return
        from .price_layer import rules_match

        rules = {"hour_from": lo, "hour_to": hi}
        probe = starts
        while probe < ends:
            if rules_match(rules, probe):
                return
            probe += timedelta(minutes=30)
        self.add_error(
            "rule_hour_from",
            _("Die Uhrzeit passt nicht zum Zeitraum der Aktion — der Preis würde nie gelten."),
        )

    def _clean_price_condition(self, cleaned):
        """В2: условие собирается и проверяется одной функцией с витриной."""
        from apps.core import price_conditions as pc

        self._price_condition = None
        kind = cleaned.get("price_condition_kind") or ""
        if "price_condition_present" not in self.data or not kind:
            return
        note = (cleaned.get("price_condition_note") or "").strip()
        # Заметка правится в базовом языке; переводы других языков сохраняются.
        prev = pc.of(self.instance) or {}
        notes = dict(prev.get("note") or {})
        if note:
            notes[settings.LANGUAGE_CODE] = note
        else:
            notes = {}
        n = cleaned.get("price_condition_n")
        high = pc.N_RANGE.get(kind, (2, 99))[1]
        if n is not None and n > high:
            self.add_error("price_condition_n", _("Höchstens %(max)s Stück.") % {"max": high})
            return
        raw = {
            "kind": kind,
            "n": n,
            "pay": cleaned.get("price_condition_pay"),
            "note": notes,
        }
        cond = pc.normalize(raw)
        if cond is None:
            self.add_error(
                "price_condition_kind",
                _(
                    "Bedingung unvollständig: Stückzahl (und bei „n für m“ den Preis in Stück) "
                    "oder einen Hinweis angeben."
                ),
            )
            return
        if kind in pc.PERCENT_KINDS and not cleaned.get("discount_percent"):
            self.add_error(
                "discount_percent", _("Für diese Bedingung bitte den Rabatt in Prozent angeben.")
            )
        if cleaned.get("discount_style") == "mystery":
            self.add_error(
                "discount_style",
                _("Überraschungspreis und Bedingung passen nicht zusammen."),
            )
        if cleaned.get("price_override") is not None:
            self.add_error(
                "price_override",
                _("Mit einer Bedingung gilt kein fester Aktionspreis — bitte leer lassen."),
            )
        self._price_condition = cond

    def save(self, commit=True):
        promo = super().save(commit=False)
        promo.title = self.collect_i18n("title")
        promo.description = self.collect_i18n("description")
        overlay = dict(promo.group_i18n or {})
        for loc in getattr(self, "_group_locales", []):
            val = (self.cleaned_data.get(f"group_{loc}") or "").strip()
            if val:
                overlay[loc] = val
            else:
                overlay.pop(loc, None)  # пустой перевод → фолбэк на базовую метку
        promo.group_i18n = overlay
        if "city_category" in self.data:  # presence-guard: чужие POST-ы не стирают выбор
            from . import city_fields

            promo.city_category, promo.city_tags = city_fields.cleaned(self)
        if "customer_response" in self.data:  # presence-guard: чужие POST-ы не стирают выбор
            meta = dict(promo.metadata) if isinstance(promo.metadata, dict) else {}
            value = self.cleaned_data.get("customer_response") or ""
            if value:
                meta["response"] = value
            else:
                meta.pop("response", None)
            promo.metadata = meta
        if "gift_min_order" in self.data:  # presence-guard (W0)
            meta = dict(promo.metadata) if isinstance(promo.metadata, dict) else {}
            gift_min = self.cleaned_data.get("gift_min_order")
            if gift_min:
                meta["gift_min_order"] = f"{gift_min:.2f}"
            else:
                meta.pop("gift_min_order", None)
            promo.metadata = meta
        if "customer_rule" in self.data:  # presence-guard (W0)
            meta = dict(promo.metadata) if isinstance(promo.metadata, dict) else {}
            rule = self.cleaned_data.get("customer_rule") or ""
            if rule:
                meta["customer_rule"] = rule
            else:
                meta.pop("customer_rule", None)
            promo.metadata = meta
        # KA-12 E6.6: сентинел `coupon_by_email_present` — снятый чекбокс браузер не шлёт.
        if "coupon_by_email_present" in self.data:
            meta = dict(promo.metadata) if isinstance(promo.metadata, dict) else {}
            if self.cleaned_data.get("coupon_by_email"):
                meta["coupon_delivery"] = "email"
            else:
                meta.pop("coupon_delivery", None)
            promo.metadata = meta
        # В2: сентинел `price_condition_present` — чужой POST условие не стирает (W0).
        if "price_condition_present" in self.data:
            meta = dict(promo.metadata) if isinstance(promo.metadata, dict) else {}
            cond = getattr(self, "_price_condition", None)
            if cond:
                meta["price_condition"] = cond
            else:
                meta.pop("price_condition", None)
            promo.metadata = meta
        # SF-8b: сентинел `perishable_present` — снятый чекбокс браузер не шлёт (W0),
        # поэтому чужой POST без него флаг не стирает.
        if "perishable_present" in self.data and "perishable" in self.fields:
            meta = dict(promo.metadata) if isinstance(promo.metadata, dict) else {}
            if self.cleaned_data.get("perishable"):
                meta["perishable"] = True
            else:
                meta.pop("perishable", None)
            promo.metadata = meta
        # KA-12 GA-8: сентинел `rules_present` — окно пишется только формой, которая его
        # рисует; прочие ключи target_rules (мастер, даты номера) сохраняются.
        if "rules_present" in self.data:
            rules = dict(promo.target_rules) if isinstance(promo.target_rules, dict) else {}
            days = sorted({int(d) for d in self.cleaned_data.get("rule_weekdays") or []})
            if days and len(days) < 7:
                rules["weekdays"] = days
            else:
                rules.pop("weekdays", None)
            for key in ("hour_from", "hour_to"):
                value = self.cleaned_data.get(f"rule_{key}")
                if value is None:
                    rules.pop(key, None)
                else:
                    rules[key] = value
            promo.target_rules = rules
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
        label=_("Label"), max_length=120, help_text=_("e.g. −10 percent or Free coffee")
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
    discount_eur = MoneyField(
        label=_("Discount € (online order)"),
        min_value=0,
        decimal_places=2,
        max_digits=10,
        required=False,
    )
    min_order_eur = MoneyField(
        label=_("Minimum order €"),
        min_value=0,
        decimal_places=2,
        max_digits=10,
        required=False,
    )

    combinable = forms.BooleanField(
        label=_("Combinable with other discounts"),
        required=False,
        help_text=_(
            "Off: the code only reduces items that are not already discounted "
            "(promotions, quantity deals, automatic room discounts)."
        ),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("discount_percent") and cleaned.get("discount_eur"):
            raise forms.ValidationError(_("Use either a percentage or € discount, not both."))
        return cleaned


class CouponCampaignForm(forms.Form):
    """B4/CM-9: купон-кампания по сегменту (персональные коды + письмо)."""

    name = forms.CharField(label=_("Campaign name"), max_length=200)
    # Сегмент (AND; всё пустое = вся opt-in-база).
    tag = forms.CharField(label=_("Customer tag"), max_length=50, required=False)
    inactive_days = forms.IntegerField(
        label=_("No purchase for N days"), min_value=1, required=False
    )
    top_ltv = forms.IntegerField(label=_("Top N by revenue"), min_value=1, required=False)
    # Параметры кода.
    discount_percent = forms.IntegerField(
        label=_("Discount %"), min_value=1, max_value=100, required=False
    )
    discount_eur = MoneyField(
        label=_("Discount €"), min_value=0, decimal_places=2, max_digits=10, required=False
    )
    min_order_eur = MoneyField(
        label=_("Minimum order €"), min_value=0, decimal_places=2, max_digits=10, required=False
    )
    valid_days = forms.IntegerField(
        label=_("Code valid for days"), min_value=1, max_value=365, initial=30
    )
    # Письмо.
    subject = forms.CharField(label=_("Subject"), max_length=200)
    body = forms.CharField(label=_("Message"), widget=forms.Textarea, required=False)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("discount_percent") and cleaned.get("discount_eur"):
            raise forms.ValidationError(_("Use either a percentage or € discount, not both."))
        if not cleaned.get("discount_percent") and not cleaned.get("discount_eur"):
            raise forms.ValidationError(_("Set a percentage or € discount for the code."))
        return cleaned


class LoyaltyProgramForm(forms.ModelForm):
    class Meta:
        model = LoyaltyProgram
        fields = ["label", "stamps_required", "reward_label", "is_active"]
        labels = {
            "is_active": _("Active"),
            "label": _("Program name"),
            "stamps_required": _("Stamps required"),
            "reward_label": _("Reward"),
        }
