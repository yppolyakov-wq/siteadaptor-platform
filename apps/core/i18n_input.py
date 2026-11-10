"""L3d: per-locale ввод для моделей с overlay-семантикой i18n.

База живёт в ПЛОСКОМ поле (= settings.LANGUAGE_CODE, source of truth —
см. I18nMixin.get_overlay), переводы неосновных локалей — в JSONField
`<field>_i18n`. Паттерн ввода — как legal_docs_view: динамические имена
`<field>_<locale>` по active_locales тенанта, presence-guard (отсутствующее
поле не трогаем). Инвариант «без дрейфа»: базовая локаль НИКОГДА не пишется
в оверлей (extra_locales её исключает).
"""

from django.conf import settings
from django.utils.text import format_lazy

from apps.core.richtext import clean_input


def extra_locales(tenant) -> list[str]:
    """Локали доп. инпутов формы: активные локали тенанта минус базовая.

    Тенант с одной (базовой) локалью → [] — форма выглядит как раньше.
    Без тенанта (тесты/CLI) — тоже [] (fail-safe)."""
    base = settings.LANGUAGE_CODE
    try:
        return [loc for loc in tenant.active_locales if loc != base]
    except Exception:  # noqa: BLE001 — ввод переводов не должен ломать CRUD
        return []


#: M21.8: overlay-поля длинного текста (визуальный редактор) — санитайз при записи.
RICH_OVERLAY_FIELDS = frozenset({"description", "bio", "house_rules", "body"})


def apply_i18n_overlay(obj, post, tenant, fields=("name", "description")) -> list[str]:
    """Собрать оверлеи из POST (`<field>_<locale>`) в `obj.<field>_i18n`.

    Пустое присланное значение удаляет ключ локали (фолбэк на базу);
    отсутствующее в POST поле не трогается (старые формы-клиенты без
    per-locale инпутов проходят насквозь). Возвращает список изменённых
    `*_i18n`-полей — для update_fields (сам save() не зовёт)."""
    changed = []
    for f in fields:
        overlay_field = f"{f}_i18n"
        if not hasattr(obj, overlay_field):
            continue
        overlay = dict(getattr(obj, overlay_field) or {})
        touched = False
        for loc in extra_locales(tenant):
            val = post.get(f"{f}_{loc}")
            if val is None:
                continue
            touched = True
            val = val.strip()
            if f in RICH_OVERLAY_FIELDS:  # M21.8: длинный текст с визуального редактора
                val = clean_input(val)
            if val:
                overlay[loc] = val
            else:
                overlay.pop(loc, None)
        if touched:
            setattr(obj, overlay_field, overlay)
            changed.append(overlay_field)
    return changed


def i18n_inputs_for(obj, tenant, fields=("name", "description")) -> list[dict]:
    """Данные для рендера per-locale инпутов существующего объекта:
    [{"locale", "field", "input_name", "value"}, …] — шаблону не нужны
    фильтры доступа к dict."""
    out = []
    for loc in extra_locales(tenant):
        for f in fields:
            overlay = getattr(obj, f"{f}_i18n", None) or {}
            out.append(
                {
                    "locale": loc,
                    "field": f,
                    "input_name": f"{f}_{loc}",
                    "value": overlay.get(loc, "") if isinstance(overlay, dict) else "",
                }
            )
    return out


def apply_seq_overlay(obj, overlay_field: str, per_locale: dict, tenant) -> bool:
    """Оверлей СПИСОЧНОГО поля (`attributes_i18n`/`faq_i18n`) из уже разобранного
    `{locale: [...]}`.

    Разбор POST оставляем вьюхе: у списка строк и у списка пар разная разметка,
    а семантика оверлея одна — здесь она и живёт. Пустой список локали удаляет
    ключ (фолбэк на базу целиком); локали, которой нет в `per_locale`, не
    трогаем (presence-guard: старый клиент формы не стирает перевод). Возвращает
    True, если поле изменилось — для `update_fields`.
    """
    current = getattr(obj, overlay_field, None)
    overlay = dict(current) if isinstance(current, dict) else {}
    before = dict(overlay)
    for loc in extra_locales(tenant):
        if loc not in per_locale:
            continue
        items = per_locale[loc]
        if items:
            overlay[loc] = items
        else:
            overlay.pop(loc, None)
    if overlay == before:
        return False
    setattr(obj, overlay_field, overlay)
    return True


def form_locales(tenant) -> list[str]:
    """L3d.5: локали для форм ПОЛНОГО i18n-словаря (Category/Product/Promotion:
    JSON {locale: str}, база хранится в самом словаре). Базовая локаль всегда
    первая; без тенанта — базовая пара de+en (см. ниже)."""
    base = settings.LANGUAGE_CODE
    try:
        locs = list(tenant.active_locales)
    except Exception:  # noqa: BLE001
        # Без тенанта (тесты/edge) — базовая ПАРА de+en (полностью поддержанные локали),
        # а НЕ весь реестр settings.LANGUAGES: рост реестра (доп. языки витрины) иначе
        # раздувает формы 11 полями и ломает точечные i18n-ассерты. Прод всегда с тенантом.
        locs = [base, "en"]
    return [base] + [loc for loc in locs if loc != base]


def i18n_form_groups(form, tenant, fields=("name", "description")) -> dict:
    """Ф1 (per-language ввод): группы bound-полей формы ПО ЛОКАЛИ для переключателя языка.

    Возвращает ``{"i18n_groups": [{code,label,is_base,fields:[BoundField,…]}], "i18n_multi": bool}``.
    `fields` — базовые имена i18n-полей формы (name/description ИЛИ title/description). Шаблон
    показывает группу только выбранного языка (data-i18n-loc), базовая (LANGUAGE_CODE) видна по
    умолчанию. Поля ВСЕХ локалей остаются в DOM → Save собирает всё (инвариант W0). Свитчер
    показываем при >1 языке (`i18n_multi`)."""
    from django.conf import settings as s

    base = s.LANGUAGE_CODE
    lang_names = dict(s.LANGUAGES)
    locs = form_locales(tenant)
    groups = []
    for loc in locs:
        bound = [form[f"{f}_{loc}"] for f in fields if f"{f}_{loc}" in form.fields]
        groups.append(
            {
                "code": loc,
                "label": str(lang_names.get(loc, loc.upper())),
                "is_base": loc == base,
                "fields": bound,
            }
        )
    return {"i18n_groups": groups, "i18n_multi": len(locs) > 1}


class DynamicI18nFormMixin:
    """L3d.5: N-locale поля вместо хардкода пар de/en в ModelForm.

    Базовое поле `<f>_<LANGUAGE_CODE>` остаётся статическим на классе
    (обязательность/лейбл как раньше); поля прочих локалей создаются в
    `init_i18n_fields` по локалям тенанта. `collect_i18n(f)` в save()
    собирает полный словарь {locale: str} по всем локалям формы."""

    # (("name", {"label": "Name", "max_length": 200, "textarea": False}), …)
    i18n_fields = ()

    def init_i18n_fields(self, tenant):
        from django import forms as dj_forms

        base = settings.LANGUAGE_CODE
        self._i18n_locales = form_locales(tenant)
        for f, opts in self.i18n_fields:
            for loc in self._i18n_locales:
                fname = f"{f}_{loc}"
                if loc != base and fname not in self.fields:
                    self.fields[fname] = dj_forms.CharField(
                        # format_lazy, а не f-строка: подпись базы приходит
                        # lazy-переводом, f-строка вычислила бы её сразу и
                        # заморозила на немецком (I18N-13).
                        label=format_lazy(
                            "{base} ({loc})",
                            base=opts.get("label") or f.capitalize(),
                            loc=loc.upper(),
                        ),
                        max_length=opts.get("max_length"),
                        required=False,
                        # M21.8: «rich» — визуальный редактор и у переводов (data-rte).
                        widget=dj_forms.Textarea(
                            attrs={"rows": 3, **({"data-rte": "text"} if opts.get("rich") else {})}
                        )
                        if opts.get("textarea")
                        else None,
                    )
                if getattr(self.instance, "pk", None):
                    src = getattr(self.instance, f, None) or {}
                    if isinstance(src, dict):
                        self.fields[fname].initial = src.get(loc, "")

    def collect_i18n(self, f) -> dict:
        return {
            loc: clean_input(self.cleaned_data.get(f"{f}_{loc}") or "")
            for loc in self._i18n_locales
        }


class OverlayI18nFormMixin:
    """E9.10: переводы overlay-полей в ModelForm (событие, тур, …).

    База остаётся в плоском поле модели (язык `LANGUAGE_CODE`), переводы — в
    `<field>_i18n`. Для каждого языка тенанта, кроме базового, рядом с базовым
    полем добавляется `<field>_<loc>`; всем им ставится атрибут `i18n_loc` —
    шаблон по нему (фильтр `i18n_loc`) оборачивает поле в `data-i18n-loc`, и
    выпадашка языка у заголовка показывает поля одного языка.

    Запись: после валидации оверлей переносится в `instance.<field>_i18n`.
    Presence-guard: поле, которого нет в POST, не трогаем; пустое значение
    удаляет перевод (витрина покажет базу)."""

    overlay_i18n_fields: tuple = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.db import connection

        self.init_overlay_i18n(getattr(connection, "tenant", None))

    def init_overlay_i18n(self, tenant):
        from django import forms as dj_forms

        base = settings.LANGUAGE_CODE
        # Повторный вызов (форма знает тенанта точнее, чем соединение) — начинаем
        # с чистого листа: прежние поля переводов снимаем.
        for name in getattr(self, "_overlay_added", ()):
            self.fields.pop(name, None)
        self._overlay_added = []
        self._overlay_locales = extra_locales(tenant)
        if not self._overlay_locales:
            for name in self.overlay_i18n_fields:
                if name in self.fields:
                    self.fields[name].i18n_loc = ""
                    self.fields[name].i18n_siblings = []
            return
        ordered = {}
        for name, field in self.fields.items():
            ordered[name] = field
            if name not in self.overlay_i18n_fields:
                continue
            field.i18n_loc = base
            field.i18n_siblings = [f"{name}_{loc}" for loc in self._overlay_locales]
            overlay = getattr(self.instance, f"{name}_i18n", None) or {}
            for loc in self._overlay_locales:
                widget = (
                    dj_forms.Textarea(attrs=dict(field.widget.attrs))
                    if isinstance(field.widget, dj_forms.Textarea)
                    else None
                )
                extra = dj_forms.CharField(
                    label=format_lazy("{base} ({loc})", base=field.label or name, loc=loc.upper()),
                    max_length=getattr(field, "max_length", None),
                    required=False,
                    widget=widget,
                    initial=overlay.get(loc, "") if isinstance(overlay, dict) else "",
                )
                extra.i18n_loc = loc
                ordered[f"{name}_{loc}"] = extra
                self._overlay_added.append(f"{name}_{loc}")
        self.fields = ordered

    def _post_clean(self):
        # M21.8: поля с визуальным редактором (виджет data-rte) — санитайз ДО записи в
        # instance (и база, и переводы).
        for key, field in self.fields.items():
            if "data-rte" in getattr(field.widget, "attrs", {}) and key in self.cleaned_data:
                self.cleaned_data[key] = clean_input(self.cleaned_data[key])
        super()._post_clean()
        if not self.is_bound or not getattr(self, "_overlay_locales", None):
            return
        for name in self.overlay_i18n_fields:
            overlay_field = f"{name}_i18n"
            if not hasattr(self.instance, overlay_field):
                continue
            overlay = dict(getattr(self.instance, overlay_field) or {})
            for loc in self._overlay_locales:
                key = f"{name}_{loc}"
                if key not in self.data:
                    continue
                val = (self.cleaned_data.get(key) or "").strip()
                if val:
                    overlay[loc] = val
                else:
                    overlay.pop(loc, None)
            setattr(self.instance, overlay_field, overlay)


def save_row_translations(obj, post, tenant, fields) -> bool:
    """E9.10: сохранить переводы одной строки списка (доп. услуга, тариф карты,
    программа лояльности, группа набора) из формы «под строкой».

    Только оверлеи: базовые поля строки не трогаем (у таких экранов база
    правится в другом месте или не правится вовсе). Presence-guard — как у
    `apply_i18n_overlay`. True — если что-то изменилось."""
    changed = apply_i18n_overlay(obj, post, tenant, fields=fields)
    if not changed:
        return False
    update = list(changed)
    if any(f.name == "updated_at" for f in obj._meta.concrete_fields):
        update.append("updated_at")
    obj.save(update_fields=update)
    return True
