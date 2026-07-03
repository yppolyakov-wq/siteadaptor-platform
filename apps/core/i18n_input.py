"""L3d: per-locale ввод для моделей с overlay-семантикой i18n.

База живёт в ПЛОСКОМ поле (= settings.LANGUAGE_CODE, source of truth —
см. I18nMixin.get_overlay), переводы неосновных локалей — в JSONField
`<field>_i18n`. Паттерн ввода — как legal_docs_view: динамические имена
`<field>_<locale>` по active_locales тенанта, presence-guard (отсутствующее
поле не трогаем). Инвариант «без дрейфа»: базовая локаль НИКОГДА не пишется
в оверлей (extra_locales её исключает).
"""

from django.conf import settings


def extra_locales(tenant) -> list[str]:
    """Локали доп. инпутов формы: активные локали тенанта минус базовая.

    Тенант с одной (базовой) локалью → [] — форма выглядит как раньше.
    Без тенанта (тесты/CLI) — тоже [] (fail-safe)."""
    base = settings.LANGUAGE_CODE
    try:
        return [loc for loc in tenant.active_locales if loc != base]
    except Exception:  # noqa: BLE001 — ввод переводов не должен ломать CRUD
        return []


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


def form_locales(tenant) -> list[str]:
    """L3d.5: локали для форм ПОЛНОГО i18n-словаря (Category/Product/Promotion:
    JSON {locale: str}, база хранится в самом словаре). Базовая локаль всегда
    первая; без тенанта — весь реестр settings.LANGUAGES (паритет старых
    вызовов форм без tenant-kwarg)."""
    base = settings.LANGUAGE_CODE
    try:
        locs = list(tenant.active_locales)
    except Exception:  # noqa: BLE001
        locs = [code for code, _label in settings.LANGUAGES]
    return [base] + [loc for loc in locs if loc != base]


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
                        label=f"{opts.get('label', f.capitalize())} ({loc.upper()})",
                        max_length=opts.get("max_length"),
                        required=False,
                        widget=dj_forms.Textarea(attrs={"rows": 3})
                        if opts.get("textarea")
                        else None,
                    )
                if getattr(self.instance, "pk", None):
                    src = getattr(self.instance, f, None) or {}
                    if isinstance(src, dict):
                        self.fields[fname].initial = src.get(loc, "")

    def collect_i18n(self, f) -> dict:
        return {loc: (self.cleaned_data.get(f"{f}_{loc}") or "") for loc in self._i18n_locales}
