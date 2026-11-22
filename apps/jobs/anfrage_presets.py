"""KA-12 A-3 (G6): стартовая форма заявки по типу бизнеса.

Кейтерингу форма «дата · гости · повод» нужна с первого дня — без неё заявка
приходит без главного (на сколько человек и когда), и владелец переписывается
с клиентом ради трёх полей. Раньше конфиг `site_config["anfrage"]` писали
только демо-кит и панель «Anfrage-Formular», поэтому новый кейтеринг стартовал
с формой Handwerker'а.

Пресет кладётся при создании бизнеса и при СМЕНЕ типа, и только если ключа ещё
нет: настройку владельца не перетирает, а «все поля сняты» (ключ удалён панелью)
повтор того же шага мастера не отменяет. Значения видов мероприятия — немецкие ключи записи
(`Job.event_type`), показ переводит витрина.

FB-33 M2i-6: тот же реестр держит пресет полей корзины (`form_fields.checkout`) — только
режимы системных полей и подпись заметки, без своих вопросов (решение владельца 2026-11-22):
пекарня, мясная лавка, кафе и ресторан спрашивают телефон обязательно, заметка называется
«Allergien / Wünsche». Правила те же: при создании бизнеса и при СМЕНЕ типа, только если ключа
`form_fields.checkout` ещё нет (ключ есть, даже пустой — «задано»); существующие бизнесы не
переносятся. Запись — только `form_spec.put`; кнопка «Branchen-Vorlage laden» вкладки «Felder»
кладёт тот же пресет в черновик окна (`form_spec.apply_preset`).
"""

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from apps.tenants import siteconfig

#: гастро-типы: за заказом звонят (готово, чего-то нет) — телефон обязателен; заметка — про
#: аллергии и пожелания. Режимы и подписи — ключи реестра `form_spec.FORMS["checkout"]`
_FOOD_CHECKOUT = {"mode": {"phone": "req"}, "labels": {"note": _("Allergien / Wünsche")}}

#: единственный реестр стартовых настроек форм: {форма `form_spec`: {тип бизнеса: пресет}}
PRESETS = {
    "anfrage": {
        "catering": {
            "fields": ["date", "guests", "event_type"],
            "event_types": [
                "Hochzeit",
                "Firmenfeier",
                "Geburtstag",
                "Familienfeier",
                "Sonstiges",
            ],
        },
    },
    "checkout": {
        business_type: _FOOD_CHECKOUT
        for business_type in ("bakery", "butcher", "cafe", "restaurant")
    },
}
ANFRAGE_PRESETS = PRESETS["anfrage"]


def _fields_preset(raw: dict, locales) -> dict:
    """Пресет режимов и подписей в виде состояния `form_spec`: подписи — текстом на основном
    языке (каким бы ни был язык кабинета), `labels_i18n` — на языки `locales` (языки бизнеса
    кроме основного); язык без перевода в каталоге не пишется (показ возьмёт немецкий)."""
    from apps.core import form_answers

    out: dict = {"mode": dict(raw.get("mode") or {})}
    known = set(form_answers.overlay_locales())
    wanted = [loc for loc in dict.fromkeys(locales or ()) if loc in known]
    labels, labels_tr = {}, {}
    for key, label in (raw.get("labels") or {}).items():
        with translation.override(settings.LANGUAGE_CODE):
            labels[key] = str(label)
        tr = {}
        for loc in wanted:
            with translation.override(loc):
                text = str(label)
            if text != labels[key]:
                tr[loc] = text
        if tr:
            labels_tr[key] = tr
    out["labels"] = labels
    if labels_tr:
        out["labels_i18n"] = labels_tr
    return out


def preset_for(business_type, form: str = "anfrage", locales=()) -> dict:
    """Пресет формы для типа бизнеса ({} — пресета нет). `form` — форма вкладки «Felder»:
    у заявки — нормализованный `site_config["anfrage"]`, у корзины (`checkout`, M2i-6) —
    `{"mode", "labels", "labels_i18n"}` для `form_spec.apply_preset`; `locales` — языки
    переводов бизнеса (на них переводится подпись)."""
    raw = (PRESETS.get(form) or {}).get(business_type or "")
    if not raw:
        return {}
    if form == "anfrage":
        return siteconfig.normalize_anfrage(raw)
    return _fields_preset(raw, locales)


def _checkout_entry(business_type, locales):
    """Запись `form_fields.checkout`, какой её кладёт пресет типа (None — пресета нет)."""
    probe: dict = {}
    _add_checkout(probe, business_type, locales)
    return (probe.get("form_fields") or {}).get("checkout")


def _add_checkout(cfg: dict, business_type, locales, previous_type=None) -> bool:
    """Пресет корзины в `cfg` — только при ОТСУТСТВУЮЩЕМ ключе `form_fields.checkout`; запись —
    единственным писателем `form_spec.put`. Вернёт «изменено».

    Смена типа (`previous_type`): запись, равная пресету ПРЕЖНЕГО типа, владелец не правил —
    она уходит вместе с типом (и заменяется пресетом нового, если он есть). Правленная запись
    остаётся. Ключ, который владелец сбросил до пустого, писатель снимает — при следующей
    смене типа пресет ляжет снова (как у заявки)."""
    from apps.core import form_spec

    stored = cfg.get("form_fields")
    if stored is not None and not isinstance(stored, dict):
        return False  # битое значение — не наше дело: его разберёт `siteconfig.normalize`
    dropped = False
    if "checkout" in (stored or {}):
        if not previous_type or previous_type == business_type:
            return False
        if stored["checkout"] != _checkout_entry(previous_type, locales):
            return False
        if stored["checkout"] == _checkout_entry(business_type, locales):
            return False  # у нового типа пресет тот же
        form_spec.put(cfg, "checkout", form_spec.edit_state({}, "checkout"))  # пусто → ключ снят
        dropped = True
    preset = preset_for(business_type, "checkout", locales)
    if not preset:
        return dropped
    state = form_spec.edit_state(cfg, "checkout")
    form_spec.apply_preset(state, "checkout", preset)
    form_spec.put(cfg, "checkout", state)
    return dropped or "checkout" in (cfg.get("form_fields") or {})


def with_default(site_config, business_type, locales=(), previous_type=None) -> tuple[dict, bool]:
    """(новый конфиг, изменён ли) — пресет формы добавлен, только если её ключа нет.
    `locales` — языки переводов бизнеса (подпись заметки корзины); `previous_type` — прежний
    тип при смене (нетронутый пресет корзины прежнего типа уходит с ним)."""
    cfg = dict(site_config) if isinstance(site_config, dict) else {}
    changed = False
    if "anfrage" not in cfg:
        preset = preset_for(business_type)
        if preset:
            cfg["anfrage"] = preset
            changed = True
    if _add_checkout(cfg, business_type, locales, previous_type):
        changed = True
    return cfg, changed
