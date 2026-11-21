"""FB-33 M2i: «Поля форм» — какие поля формы заявки и оформления спрашивать и какие обязательны.

План — `docs/fb33-editor-model-2026-11-19.md` §«План M2i». Реестр системных полей формы, режим
каждого (`off` — не спрашивать, `opt` — можно, `req` — обязательно) и закреплённые поля, которые
выключить нельзя (форма без них не работает: «Что нужно» и имя в заявке, имя в корзине).
Свои вопросы владельца — ядро `form_answers`.

Хранение `site_config["form_fields"][<форма>] = {"mode": {ключ: режим}, "labels": {ключ: текст},
"custom": [...], "next_id": n}` — только отличия от умолчания (presence-minimal: без настроек
формы байт-в-байт прежние, замки `test_fb33_m2i_before`). Умолчание событийных полей заявки
берётся из прежнего `anfrage.fields` (AF-1): выключенное поле, которое там включено, хранится
явным `off` — иначе старое включение оживало бы (pitfalls «пустая настройка действует»).

Обязательность проверяет ТОЛЬКО вьюха формы (`/anfrage/` — туда же постят полоса и модалка,
корзина): сервисы `create_job`/`create_order` её не знают — у обратного звонка, кабинета,
офферов и демо свой минимум (вердикт architect).
Модуль не импортирует `siteconfig` на уровне модуля (тот нормализует через него).
"""

from __future__ import annotations

import logging
import re
from typing import NamedTuple

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from apps.core import form_answers

logger = logging.getLogger(__name__)

OFF, OPT, REQ = "off", "opt", "req"
MODES = (OFF, OPT, REQ)
LABEL_MAX = 120
#: FB-33 M2i-5b: переводы подписей полей и вариантов события — по ключу/тексту, не по позиции
#: id подсказки над полями переводов вкладки «Felder» (`_bw_formfields.html`)
LANG_HINT_ID = "ff-lang-hint"
LABELS_I18N = "labels_i18n"
EVENTS_I18N = "event_types_i18n"


class Field(NamedTuple):
    key: str
    label: object  # подпись по умолчанию (как была в шаблоне)
    req_label: object = None  # подпись при «обязательно» (без «(optional)»); None — та же
    default: str = OPT
    pinned: bool = False  # закреплено: всегда обязательно, режим не меняется
    legacy: str = ""  # ключ прежнего `anfrage.fields` (AF-1): включён там → умолчание `opt`


FORMS: dict[str, tuple[Field, ...]] = {
    "anfrage": (
        Field("title", _("What do you need?"), default=REQ, pinned=True),
        Field("description", _("Details (optional)"), _("Details")),
        Field("event_date", _("Event date (optional)"), _("Event date"), OFF, legacy="date"),
        Field(
            "guest_count",
            _("Number of guests (optional)"),
            _("Number of guests"),
            OFF,
            legacy="guests",
        ),
        Field(
            "event_type",
            _("Type of event (optional)"),
            _("Type of event"),
            OFF,
            legacy="event_type",
        ),
        Field("site_address", _("Job address (optional)"), _("Job address")),
        Field("name", _("Name"), default=REQ, pinned=True),
        Field("email", _("Email")),
        Field("phone", _("Phone")),
        Field("photos", _("Photos (optional, up to 5)"), _("Photos (up to 5)")),
    ),
    # корзина (FB-33 M2i-34): подписи — те же, что рисует витрина (`storefront/cart.html`);
    # имя закреплено (у столика его заменяет номер стола)
    "checkout": (
        Field("name", _("Name"), default=REQ, pinned=True),
        Field("email", _("Email")),
        Field("phone", _("Phone")),
        Field("note", _("Note (optional)"), _("Note")),
    ),
}
#: способ связи в заявке: хотя бы одно из полей спрашивается (оба «нет» нельзя); у корзины
#: оба «нет» можно (обязательно только имя), у заказа за столиком их не спрашивают вовсе
CONTACT = ("email", "phone")
#: полоса заявки на главной сама рисует событийные поля, имя и e-mail; остальные обязательные
#: она дорисовывает — до `BAND_EXTRA_MAX`, больше (или фото) — кнопка на /anfrage/ (решение)
BAND_NATIVE = frozenset({"title", "event_date", "guest_count", "event_type", "name", "email"})
BAND_EXTRA_MAX = 3

_BY_FORM = {form: {f.key: f for f in fields} for form, fields in FORMS.items()}


def fields_of(form: str) -> tuple[Field, ...]:
    return FORMS.get(form, ())


def _default(field: Field, legacy_fields) -> str:
    if field.legacy and field.legacy in (legacy_fields or ()):
        return OPT
    return field.default


def normalize(raw, form: str, legacy_fields=(), event_types=()) -> dict:
    """Настройки одной формы: только отличия от умолчания. Мусор — молча прочь.

    FB-33 M2i-5b: переводы по ключу, не по позиции — `labels_i18n` {поле: {язык: текст}},
    у своего вопроса `label_i18n`/`options_i18n` (`form_answers.normalize_questions`), у заявки
    `event_types_i18n` {вариант на основном языке: {язык: текст}} для вариантов `event_types`
    (`anfrage.event_types`). Только языки платформы, существующие ключи и варианты; пустой и
    равный своей немецкой подписи перевод не хранится."""
    raw = raw if isinstance(raw, dict) else {}
    by_key = _BY_FORM.get(form, {})
    out: dict = {}
    mode_raw = raw.get("mode") if isinstance(raw.get("mode"), dict) else {}
    modes = {}
    for key, field in by_key.items():
        value = mode_raw.get(key)
        if field.pinned or value not in MODES or value == _default(field, legacy_fields):
            continue
        modes[key] = value
    if form == "anfrage" and all(
        modes.get(k, _default(by_key[k], legacy_fields)) == OFF for k in CONTACT
    ):
        modes.pop("phone", None)  # способ связи нельзя снять целиком — телефон остаётся
    if modes:
        out["mode"] = modes
    label_raw = raw.get("labels") if isinstance(raw.get("labels"), dict) else {}
    labels = {}
    for key in by_key:
        text = form_answers.clean_text(label_raw.get(key), LABEL_MAX)
        if text:
            labels[key] = text
    if labels:
        out["labels"] = labels
    tr_raw = raw.get(LABELS_I18N) if isinstance(raw.get(LABELS_I18N), dict) else {}
    labels_tr = {}
    for key in by_key:
        tr = form_answers.translations(tr_raw.get(key), labels.get(key, ""), LABEL_MAX)
        if tr:
            labels_tr[key] = tr
    if labels_tr:
        out[LABELS_I18N] = labels_tr
    custom, next_id = form_answers.normalize_questions(raw.get("custom"), raw.get("next_id"))
    if custom:
        out["custom"] = custom
    if next_id:
        out["next_id"] = next_id  # номер помнится и после удаления всех вопросов
    if form == "anfrage":
        events_tr = _event_translations(raw.get(EVENTS_I18N), event_types)
        if events_tr:
            out[EVENTS_I18N] = events_tr
    return out


def _event_translations(raw, event_types) -> dict:
    """Переводы вариантов «Art der Veranstaltung» {вариант: {язык: текст}} — только для
    вариантов из списка (порядок списка), лимит и чистка как у варианта."""
    from apps.tenants import siteconfig

    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for value in event_types or ():
        tr = form_answers.translations(raw.get(value), value, siteconfig._EVENT_TYPE_MAX)
        if tr:
            out[value] = tr
    return out


def normalize_all(raw, legacy_fields=(), event_types=()) -> dict:
    """`site_config["form_fields"]` целиком: известные формы с непустыми настройками.
    `event_types` — нормализованные варианты `anfrage.event_types` (ключи их переводов)."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for form in FORMS:
        legacy = legacy_fields if form == "anfrage" else ()
        events = event_types if form == "anfrage" else ()
        entry = normalize(raw.get(form), form, legacy, events)
        if entry:
            out[form] = entry
    return out


def _legacy(site) -> list:
    return ((site.get("anfrage") or {}).get("fields")) or []


def mode_of(site, form: str, key: str) -> str:
    """Режим поля по нормализованным настройкам сайта (`siteconfig.normalize`)."""
    field = _BY_FORM.get(form, {}).get(key)
    if field is None:
        return OFF
    if field.pinned:
        return REQ
    stored = ((site.get("form_fields") or {}).get(form) or {}).get("mode") or {}
    return stored.get(key) or _default(field, _legacy(site) if form == "anfrage" else ())


class FieldView(NamedTuple):
    mode: str
    label: str

    @property
    def on(self) -> bool:
        return self.mode != OFF

    @property
    def req(self) -> bool:
        return self.mode == REQ


def questions(site, form: str) -> list[dict]:
    """Свои вопросы владельца формы (нормализованы `form_answers.normalize_questions`)."""
    return ((site.get("form_fields") or {}).get(form) or {}).get("custom") or []


#: свои вопросы, которые полоса заявки может нарисовать одной строкой (выбор и «да/нет» —
#: только на полной форме)
BAND_QUESTION_TYPES = frozenset({"text", "textarea", "number", "date"})


def shown_locale(locale=None) -> str:
    """Язык перевода для показа: `locale` (по умолчанию — активный язык запроса), если это
    язык перевода платформы; на основном языке — "" (переводы не читаются: байт-в-байт)."""
    from django.utils.translation import get_language

    loc = locale if locale is not None else (get_language() or "")
    return loc if loc in form_answers.overlay_locales() else ""


def _shown_question(q: dict, loc: str) -> dict:
    """Свой вопрос для показа на языке `loc`: подпись и пары вариантов `choices` (value —
    всегда вариант на основном языке: его проверяет `collect` и хранит снимок сделки)."""
    out = {key: v for key, v in q.items() if key not in ("label_i18n", "options_i18n")}
    out["req"] = q.get("mode") == "req"
    if loc:
        out["label"] = (q.get("label_i18n") or {}).get(loc) or q["label"]
    tr = q.get("options_i18n") or {}
    out["choices"] = [
        _choice(o, (tr.get(o) or {}).get(loc) if loc else None, loc) for o in q.get("options") or []
    ]
    return out


def _checkout_mode(key: str, mode: str, *, table: bool) -> str:
    """FB-33 M2i-34: режим поля корзины по обстоятельствам заказа. У столика контакты не
    спрашиваются (гостя находят по номеру стола). FB-33 M2i-7: онлайн-оплата режим e-mail
    больше не меняет — без адреса в форме он приходит из оплаты (вебхук Stripe)."""
    if key in CONTACT and table:
        return OFF
    return mode


def view(site, form: str, locale=None, *, table: bool = False) -> dict:
    """Что рисует форма: {ключ: FieldView} + свои вопросы (`custom`) + сводка для полосы
    заявки (`band_extra`, `band_custom`, `band_full`) и `any_event`.

    FB-33 M2i-5b: подписи — на языке показа (`shown_locale`): перевод → своя немецкая подпись
    → подпись по умолчанию (gettext). На основном языке переводы не читаются.
    FB-33 M2i-34: у корзины (`checkout`) `table` — заказ за столиком (`_checkout_mode`)."""
    loc = shown_locale(locale)
    entry = (site.get("form_fields") or {}).get(form) or {}
    labels = entry.get("labels") or {}
    labels_tr = (entry.get(LABELS_I18N) or {}) if loc else {}
    out: dict = {}
    for field in fields_of(form):
        mode = mode_of(site, form, field.key)
        if field.key == "event_type" and not (site.get("anfrage") or {}).get("event_types"):
            mode = OFF  # выбор без вариантов владельца не рисуется и не обязателен
        if form == "checkout":
            mode = _checkout_mode(field.key, mode, table=table)
        default = field.req_label if mode == REQ and field.req_label is not None else field.label
        label = (labels_tr.get(field.key) or {}).get(loc) or labels.get(field.key) or str(default)
        out[field.key] = FieldView(mode, label)
    out["custom"] = [_shown_question(q, loc) for q in questions(site, form)]
    if form == "anfrage":
        extra = [
            k for k, f in out.items() if isinstance(f, FieldView) and f.req and k not in BAND_NATIVE
        ]
        if not out["email"].on and "phone" not in extra:
            extra.append("phone")  # единственный способ связи — полоса спрашивает его
        # способ связи обязателен (сервер, M2i ревью): у полосы телефона нет — e-mail обязателен
        out["band_email_req"] = out["email"].on and (out["email"].req or "phone" not in extra)
        custom_req = [q for q in out["custom"] if q["req"]]
        out["band_full"] = (
            "photos" in extra
            or any(q["type"] not in BAND_QUESTION_TYPES for q in custom_req)
            or len(extra) + len(custom_req) > BAND_EXTRA_MAX
        )
        out["band_extra"] = [] if out["band_full"] else [(k, out[k]) for k in extra]
        out["band_custom"] = [] if out["band_full"] else custom_req
        out["any_event"] = any(out[k].on for k in ("event_date", "guest_count", "event_type"))
    return out


CONTACT_MISSING = "contact"


def _filled(post, key) -> str:
    return form_answers.clean_text(post.get(key) or "", 10_000)


def _valid_email(raw: str) -> bool:
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    try:
        validate_email(raw)
    except ValidationError:
        return False
    return True


def missing(site, form: str, post, files=None, *, table: bool = False) -> list[str]:
    """Обязательные включённые поля без значения (проверка сервера — POST в обход формы).
    Значение проверяется так же, как его разберёт вьюха (битая дата = нет значения). У заявки
    ещё и способ связи: хотя бы один из включённых e-mail/телефон (`CONTACT_MISSING`).
    FB-33 M2i-34: у корзины обязательный e-mail — настоящий адрес (на него уходит
    подтверждение); `table` — заказ за столиком (контакты не спрашиваются)."""
    from datetime import date

    out = []
    shown = view(site, form, table=table)
    for field in fields_of(form):
        f = shown[field.key]
        if not f.req or field.pinned:
            continue  # закреплённые проверяет сама вьюха (прежние тексты ошибок)
        raw = _filled(post, field.key)
        ok = bool(raw)
        if field.key == "photos":
            ok = bool(files and files.getlist("photos"))
        elif field.key == "event_date" and raw:
            try:
                date.fromisoformat(raw)
            except ValueError:
                ok = False
        elif field.key == "guest_count" and raw:
            try:  # как `_parse_event_fields`: «²»/«①» — не число
                ok = raw.isascii() and 1 <= int(raw) <= 100000
            except ValueError:
                ok = False
        elif field.key == "event_type" and raw:
            ok = raw in ((site.get("anfrage") or {}).get("event_types") or [])
        elif field.key == "email" and raw and form == "checkout":
            ok = _valid_email(raw)
        if not ok:
            out.append(field.key)
    qs = questions(site, form)
    out += form_answers.validate(qs, form_answers.collect(qs, post))
    contacts = [k for k in CONTACT if form == "anfrage" and shown[k].on]
    if contacts and not any(_filled(post, k) for k in contacts):
        out.append(CONTACT_MISSING)
    return out


def missing_labels(site, form: str, keys, *, table: bool = False) -> str:
    """Подписи незаполненных полей для сообщения («Phone, Details»)."""
    from django.utils.translation import gettext

    shown = view(site, form, table=table)
    custom = {q["id"]: q["label"] for q in shown["custom"]}
    names = []
    for k in keys:
        if k == CONTACT_MISSING:
            names.append(gettext("Email or phone"))
        elif k in custom:
            names.append(custom[k])
        elif isinstance(shown.get(k), FieldView):
            names.append(shown[k].label)
    return ", ".join(names)


def sync_legacy_panel(config: dict, checked) -> None:
    """Один писатель событийных полей заявки (ревью M2i): старая панель «Anfrage-Formular»
    (`anfrage.fields`) пишет и режимы `form_fields` — снятое там поле теряет свой режим
    (выключено), отмеченное — явный «off» (включено). Иначе две настройки спорили бы: панель
    сняла «date», а `form_fields` держал бы «обязательно». Меняет `config` на месте."""
    ff = config.get("form_fields")
    anfrage = ff.get("anfrage") if isinstance(ff, dict) else None
    modes = anfrage.get("mode") if isinstance(anfrage, dict) else None
    if not isinstance(modes, dict):
        return
    for field in fields_of("anfrage"):
        if not field.legacy:
            continue
        if field.legacy not in checked or modes.get(field.key) == OFF:
            modes.pop(field.key, None)
    if not modes:
        anfrage.pop("mode", None)
    if not anfrage:
        ff.pop("anfrage", None)
    if not ff:
        config.pop("form_fields", None)


# ───────────── FB-33 M2i-5: вкладка «Felder» окна блока формы (через черновик) ─────────────
# План — `docs/fb33-editor-model-2026-11-19.md` §«План M2i-5». Состояние вкладки — «полное»
# представление настроек одной формы (режим каждого незакреплённого поля, подписи, свои
# вопросы, номер, варианты «Art der Veranstaltung»): так черновик сравнивается с сохранённым
# байт-в-байт, а «Abbrechen» возвращает ровно открытое. На сайт его пишет только `put`.

#: служебный ключ превью «Seitenaufbau»: состояние вкладки черновика (с временными id) для
#: панели; нормализатор сайта его роняет — на сайт он не попадает
EDIT_KEY = "_form_edit"
#: служебный ключ превью: черновик вкладки нельзя показать (номера вопросов кончились)
FORM_ERROR_KEY = "_form_error"
#: ключ строки схемы, которую наполняет вкладка (часть окна `formfields`)
PANEL_KEY = "form_spec"
#: вариантов «Art der Veranstaltung» и строк ввода — режем ДО циклов
_TEXT_CAP = 4000

TYPE_LABELS = {
    "text": pgettext_lazy("form question type", "Kurzer Text"),
    "textarea": pgettext_lazy("form question type", "Langer Text"),
    "choice": pgettext_lazy("form question type", "Auswahl"),
    "bool": pgettext_lazy("form question type", "Ja/Nein"),
    "number": pgettext_lazy("form question type", "Zahl"),
    "date": pgettext_lazy("form question type", "Datum"),
}
MODE_LABELS = {
    OFF: pgettext_lazy("form field mode", "Nicht fragen"),
    OPT: pgettext_lazy("form field mode", "Optional"),
    REQ: pgettext_lazy("form field mode", "Pflicht"),
}


class FormSpecError(ValueError):
    """Правку вкладки нельзя принять целиком (номера вопросов кончились)."""


def _is_temp(qid) -> bool:
    return bool(form_answers.TEMP_ID.match(str(qid or "")))


def edit_state(site, form: str = "anfrage") -> dict:
    """Состояние вкладки по нормализованным настройкам сайта (`siteconfig.normalize`)."""
    import copy

    stored = ((site.get("form_fields") or {}).get(form) or {}) if isinstance(site, dict) else {}
    try:
        next_id = int(stored.get("next_id") or 0)
    except (TypeError, ValueError):
        next_id = 0
    events = list((site.get("anfrage") or {}).get("event_types") or []) if form == "anfrage" else []
    return {
        "mode": {f.key: mode_of(site, form, f.key) for f in fields_of(form) if not f.pinned},
        "labels": dict(stored.get("labels") or {}),
        LABELS_I18N: copy.deepcopy(stored.get(LABELS_I18N) or {}),
        "custom": copy.deepcopy(stored.get("custom") or []),
        "next_id": next_id,
        "event_types": events,
        # FB-33 M2i-5b: переводы вариантов — по тексту; старый позиционный перевод
        # (`i18n.<язык>.anfrage.event_types`) виден здесь же, запись переносит его (`put`)
        EVENTS_I18N: event_translations(site) if form == "anfrage" else {},
    }


def _event_types(raw) -> list[str]:
    """Варианты «Art der Veranstaltung» — тем же нормализатором, что и сохранённые."""
    from apps.tenants import siteconfig

    items = raw if isinstance(raw, list) else []
    cap = siteconfig._MAX_EVENT_TYPES * 2  # пустые/дубли выпадут в нормализаторе
    return siteconfig.normalize_anfrage({"event_types": items[:cap]}).get("event_types", [])


def canonical(state, form: str = "anfrage") -> dict:
    """Состояние вкладки в каноническом виде: режимы и подписи — через `normalize`, свои
    вопросы — через `form_answers.normalize_questions` (временные id разрешены)."""
    state = state if isinstance(state, dict) else {}
    fields = fields_of(form)
    raw_mode = state.get("mode") if isinstance(state.get("mode"), dict) else {}
    legacy = [f.legacy for f in fields if f.legacy and raw_mode.get(f.key) in (OPT, REQ)]
    events = _event_types(state.get("event_types")) if form == "anfrage" else []
    spec = normalize(
        {
            "mode": raw_mode,
            "labels": state.get("labels"),
            LABELS_I18N: state.get(LABELS_I18N),
            EVENTS_I18N: state.get(EVENTS_I18N),
        },
        form,
        legacy,
        events,
    )
    by_key = {f.key: f for f in fields}
    mode = {
        f.key: (spec.get("mode") or {}).get(f.key) or _default(by_key[f.key], legacy)
        for f in fields
        if not f.pinned
    }
    custom, _counter = form_answers.normalize_questions(state.get("custom"), 0, temp=True)
    try:
        next_id = min(max(int(state.get("next_id") or 0), 0), form_answers.ID_MAX)
    except (TypeError, ValueError, OverflowError):
        next_id = 0
    return {
        "mode": mode,
        "labels": spec.get("labels") or {},
        LABELS_I18N: spec.get(LABELS_I18N) or {},
        "custom": custom,
        "next_id": next_id,
        "event_types": events,
        EVENTS_I18N: spec.get(EVENTS_I18N) or {},
    }


def _lines(raw, limit: int, width: int = 0, cuts: list | None = None) -> list[str]:
    """Строки textarea (вариант на строку): длина и число строк режутся до разбора. `cuts` —
    отметка «обрезано» (больше `limit` строк или строка длиннее `width`) для сообщения."""
    if not isinstance(raw, str):
        return []
    lines = [line.strip() for line in raw[:_TEXT_CAP].splitlines()[: limit * 2 + 1]]
    lines = [line for line in lines if line]
    if cuts is not None and (
        len(raw) > _TEXT_CAP
        or len(dict.fromkeys(lines)) > limit
        or (width and any(len(form_answers.clean_text(x, _TEXT_CAP)) > width for x in lines))
    ):
        cuts.append(True)
    return lines[: limit * 2]


def _text(raw, limit: int, cuts: list | None = None) -> str:
    if not isinstance(raw, str):
        return ""
    text = form_answers.clean_text(raw[:_TEXT_CAP], _TEXT_CAP)
    if cuts is not None and len(text) > limit:
        cuts.append(True)
    return text[:limit]


def _temp_id(custom: list[dict]) -> str:
    used = {q.get("id") for q in custom}
    return next(f"n{k}" for k in range(1, 1000) if f"n{k}" not in used)


_DO = re.compile(r"^(up|down|del):(q[1-9][0-9]{0,3}|n[0-9]{1,3})$")


def parse_post(post, current, form: str = "anfrage", preset: dict | None = None):
    """Правка вкладки «Felder» → (новое состояние, сообщения владельцу).

    `post` — поля формы окна (без префикса `f_`), `current` — состояние черновика. Режимы и
    типы — из белых списков, лимиты (10 вопросов × 20 вариантов × 120 символов, 12 вариантов
    события × 60) — до циклов, обрезка — с сообщением; правятся только вопросы из `current`
    (id из запроса не создаёт и не берёт чужой вопрос). Закреплённые поля (что нужно, имя)
    не меняются; оба способа связи «нет» — телефон остаётся. Набранный новый вопрос по
    «Übernehmen»/Enter (`commit_new`) добавляется так же, как по «+ Frage».
    `FormSpecError("ids")` — номера вопросов кончились (`ID_MAX`)."""
    from django.utils.translation import gettext

    from apps.tenants import siteconfig

    state = canonical(current, form)
    get = post.get if hasattr(post, "get") else {}.get
    notes: list[str] = []
    cuts: list = []
    _parse_translations(state, post, get, cuts)
    had_tr = _translated_options(state)
    for field in fields_of(form):
        if field.pinned:
            continue
        value = get(f"mode_{field.key}")
        if value in MODES:
            state["mode"][field.key] = value
        elif value is not None:
            logger.info("form tab: ignored mode for field %s", field.key)
        if f"label_{field.key}" in post:
            text = _text(get(f"label_{field.key}"), LABEL_MAX, cuts)
            if text:
                state["labels"][field.key] = text
            else:
                state["labels"].pop(field.key, None)
    for q in state["custom"]:
        prefix = f"q_{q['id']}_"
        if prefix + "label" not in post:
            continue  # вопроса не было в форме — остаётся как есть
        label = _text(get(prefix + "label"), form_answers.LABEL_MAX, cuts)
        if label:
            q["label"] = label
        else:
            notes.append(gettext("Eine Frage ohne Text bleibt wie bisher."))
        kind = get(prefix + "type")
        if kind is not None and kind not in form_answers.TYPES:
            logger.info("form tab: ignored type for question %s", q["id"])
        options = (
            _lines(get(prefix + "options"), form_answers.MAX_OPTIONS, form_answers.LABEL_MAX, cuts)
            if prefix + "options" in post
            else list(q.get("options") or [])
        )
        if kind in form_answers.TYPES:
            if kind == "choice" and not options:
                notes.append(gettext("Für eine Auswahl bitte mindestens eine Option eintragen."))
            else:
                if q["type"] == "choice" and kind != "choice" and q.get("options"):
                    notes.append(
                        gettext("Die Optionen gelten nur für „Auswahl“ und wurden entfernt.")
                    )
                q["type"] = kind
        if q["type"] == "choice" and options:
            q["options"] = options
        elif q["type"] != "choice":
            q.pop("options", None)
        if get(prefix + "req") == "1":
            q["mode"] = REQ
        else:
            q.pop("mode", None)
    if form == "anfrage" and "event_types" in post:
        state["event_types"] = _lines(
            get("event_types"), siteconfig._MAX_EVENT_TYPES, siteconfig._EVENT_TYPE_MAX, cuts
        )
    _action(state, get, form, preset, notes, cuts)
    if contact_dropped(state, form):
        state["mode"]["phone"] = OPT  # способ связи нельзя снять целиком (как `normalize`)
        notes.append(contact_note())
    state = canonical(state, form)
    after = set(_translated_options(state))
    ids = {q["id"] for q in state["custom"]}
    gone = [k[-1] for k in had_tr if k not in after and (k[0] == "et" or k[1] in ids)]
    if gone:
        notes.append(dropped_note(dict.fromkeys(gone)))
    if cuts:
        notes.append(gettext("Zu lange Texte oder zu viele Einträge wurden gekürzt."))
    if form == "anfrage":
        if state["mode"].get("event_type", OFF) != OFF and not state["event_types"]:
            notes.append(
                gettext(
                    "„Art der Veranstaltung“ erscheint erst mit einer Auswahlliste – bitte "
                    "Optionen eintragen."
                )
            )
    return state, notes


def text_hash(text: str) -> str:
    """Короткий ключ варианта в имени поля перевода (`f_et_<h>_<язык>`, `f_q_<id>_o<h>_…`):
    от УЖЕ нормализованного текста варианта (NFC) — одинаково при рисовании и разборе."""
    import hashlib
    import unicodedata

    return hashlib.sha1(unicodedata.normalize("NFC", text).encode()).hexdigest()[:8]


def hashed(texts) -> list[tuple[str, str]]:
    """[(текст, h)] без коллизий: второй вариант с тем же `h` (sha1[:8]) пропускается — его
    перевод не рисуется и не пишется (ревью; на практике не встречается)."""
    seen: set[str] = set()
    out = []
    for text in texts or ():
        h = text_hash(text)
        if h in seen:
            logger.warning("form tab: option hash collision, translation skipped")
            continue
        seen.add(h)
        out.append((text, h))
    return out


def _set_tr(node: dict, loc: str, raw, limit: int, cuts: list) -> None:
    text = _text(raw, limit, cuts)
    if text:
        node[loc] = text
    else:
        node.pop(loc, None)


def _parse_translations(state: dict, post, get, cuts: list) -> None:
    """Поля переводов вкладки (FB-33 M2i-5b): `label_<поле>_<язык>`, `q_<id>_label_<язык>`,
    `q_<id>_o<h>_<язык>`, `et_<h>_<язык>`. Только языки платформы и только присланные поля
    (presence-guard: перевод языка, которого в форме не было, не трогается); вариант по `h` —
    из ТЕКУЩЕГО состояния черновика, не из запроса. Пустое поле — перевода нет."""
    from apps.tenants import siteconfig

    locs = form_answers.overlay_locales()
    labels = state.setdefault(LABELS_I18N, {})
    for key in list(state["mode"]):
        for loc in locs:
            name = f"label_{key}_{loc}"
            if name in post:
                node = dict(labels.get(key) or {})
                _set_tr(node, loc, get(name), LABEL_MAX, cuts)
                labels[key] = node
    for q in state["custom"]:
        prefix = f"q_{q['id']}_"
        for loc in locs:
            if f"{prefix}label_{loc}" in post:
                node = dict(q.get("label_i18n") or {})
                _set_tr(node, loc, get(f"{prefix}label_{loc}"), form_answers.LABEL_MAX, cuts)
                q["label_i18n"] = node
        opts = dict(q.get("options_i18n") or {})
        for opt, h in hashed(q.get("options") or []):
            for loc in locs:
                if f"{prefix}o{h}_{loc}" in post:
                    node = dict(opts.get(opt) or {})
                    _set_tr(node, loc, get(f"{prefix}o{h}_{loc}"), form_answers.LABEL_MAX, cuts)
                    opts[opt] = node
        if opts:
            q["options_i18n"] = opts
    events = state.setdefault(EVENTS_I18N, {})
    for value, h in hashed(state.get("event_types") or []):
        for loc in locs:
            if f"et_{h}_{loc}" in post:
                node = dict(events.get(value) or {})
                _set_tr(node, loc, get(f"et_{h}_{loc}"), siteconfig._EVENT_TYPE_MAX, cuts)
                events[value] = node


def _translated_options(state: dict) -> list[tuple]:
    """Варианты с переводом — (`"q"`, id, вариант) у своих выборов и (`"et"`, вариант) у
    события: сверка до и после правки говорит владельцу, что перевод выпал вместе с
    переименованным или удалённым вариантом (удалённый вопрос — не повод)."""
    out: list[tuple] = []
    for q in state.get("custom") or []:
        for opt, tr in (q.get("options_i18n") or {}).items():
            if tr and opt in (q.get("options") or []):
                out.append(("q", q["id"], opt))
    for value, tr in (state.get(EVENTS_I18N) or {}).items():
        if tr and value in (state.get("event_types") or []):
            out.append(("et", value))
    return out


def contact_note() -> str:
    """Одна фраза «способ связи остаётся» — для вкладки и записи черновика."""
    from django.utils.translation import gettext

    return gettext("E-Mail oder Telefon muss gefragt werden – das Telefon bleibt in der Form.")


def contact_dropped(state, form: str = "anfrage") -> bool:
    """Оба способа связи выключены (запись оставит телефон — `normalize`)."""
    modes = (state or {}).get("mode") or {}
    return form == "anfrage" and all(modes.get(k) == OFF for k in CONTACT)


def _action(state: dict, get, form: str, preset, notes: list, cuts: list | None = None) -> None:
    """Кнопка вкладки: «+ Frage», вверх/вниз/удалить, «Branchen-Vorlage»."""
    from django.utils.translation import gettext

    do = get("do") or ""
    custom = state["custom"]
    if not do and _text(get("new_label"), form_answers.LABEL_MAX):
        if get("commit_new") == "1":
            do = "add"  # «Übernehmen»/Enter с набранным новым вопросом — не терять его
        else:
            notes.append(
                gettext("Die neue Frage ist noch nicht hinzugefügt – bitte „+ Frage“ wählen.")
            )
    if do == "add":
        label = _text(get("new_label"), form_answers.LABEL_MAX, cuts)
        kind = get("new_type") if get("new_type") in form_answers.TYPES else "text"
        options = _lines(get("new_options"), form_answers.MAX_OPTIONS, form_answers.LABEL_MAX, cuts)
        if len(custom) >= form_answers.MAX_QUESTIONS:
            notes.append(
                gettext("Höchstens %(n)s eigene Fragen.") % {"n": form_answers.MAX_QUESTIONS}
            )
        elif not label:
            notes.append(gettext("Bitte zuerst den Text der neuen Frage eingeben."))
        elif kind == "choice" and not options:
            notes.append(gettext("Für eine Auswahl bitte mindestens eine Option eintragen."))
        else:
            used = sum(1 for q in custom if _is_temp(q.get("id")))
            if int(state.get("next_id") or 0) + used + 1 > form_answers.ID_MAX:
                raise FormSpecError("ids")
            question = {"id": _temp_id(custom), "type": kind, "label": label}
            if kind == "choice":
                question["options"] = options
            if get("new_req") == "1":
                question["mode"] = REQ
            custom.append(question)
        return
    if do == "preset" and form == "anfrage":
        if not preset:
            notes.append(gettext("Für Ihre Branche gibt es keine Vorlage."))
            return
        chosen = set(preset.get("fields") or ())
        for field in fields_of(form):
            if field.legacy:
                on = field.legacy in chosen
                was = state["mode"].get(field.key)
                state["mode"][field.key] = (REQ if was == REQ else OPT) if on else OFF
        state["event_types"] = list(preset.get("event_types") or [])
        notes.append(
            gettext("Branchen-Vorlage übernommen – mit „Speichern“ erscheint sie auf der Seite.")
        )
        return
    match = _DO.match(do)
    if not match:
        return
    action, qid = match.groups()
    at = next((i for i, q in enumerate(custom) if q.get("id") == qid), None)
    if at is None:
        return  # не вопрос этого черновика
    if action == "del":
        custom.pop(at)
    elif action == "up" and at > 0:
        custom[at - 1], custom[at] = custom[at], custom[at - 1]
    elif action == "down" and at < len(custom) - 1:
        custom[at + 1], custom[at] = custom[at], custom[at + 1]


def put(config: dict, form: str, state) -> dict:
    """Единственный писатель `site_config["form_fields"][form]` из кабинета (вкладка «Felder»
    через черновик) — и событийных полей заявки `anfrage` (тем же нормализатором
    `siteconfig.normalize_anfrage`, что старая панель). `config` — нормализованный, меняется на
    месте. Хранятся только отличия; состояние, равное сохранённому, — ни байта правки.

    Номера своих вопросов: новый (временный `n<k>`) и любой id, которого нет среди сохранённых,
    получает `q<n>` от СОХРАНЁННОГО `next_id` (вызывать под блокировкой строки бизнеса —
    `aufbau_draft.commit`): номер удалённого вопроса не достаётся новому."""
    from apps.tenants import siteconfig

    state = canonical(state, form)
    current = edit_state(config, form)
    if state == current:
        return config
    if form == "anfrage":
        # FB-33 M2i-5b: старый позиционный перевод вариантов — прочь (он уже в состоянии
        # вкладки ключом по тексту: `edit_state` его показал, черновик начат с него)
        _drop_legacy_event_i18n(config)
    fields = fields_of(form)
    legacy = list(_legacy(config)) if form == "anfrage" else []
    for field in fields:
        if not field.legacy:
            continue
        new, old = state["mode"][field.key], current["mode"][field.key]
        if new == old:
            continue  # событийное поле без правки — прежнее место в `anfrage.fields`
        if new == OFF:
            legacy = [x for x in legacy if x != field.legacy]
        elif field.legacy not in legacy:
            legacy.append(field.legacy)
    if form == "anfrage":
        anfrage = siteconfig.normalize_anfrage(
            {"fields": legacy, "event_types": state["event_types"]}
        )
        if anfrage:
            config["anfrage"] = anfrage
        else:
            config.pop("anfrage", None)
        legacy = list(anfrage.get("fields") or [])
    counter = current["next_id"]
    known = {q["id"] for q in current["custom"]}
    custom = []
    for q in state["custom"]:
        if q["id"] not in known:
            counter += 1
            if counter > form_answers.ID_MAX:
                raise FormSpecError("ids")
            q = {**q, "id": f"q{counter}"}
        custom.append(q)
    entry = normalize(
        {
            "mode": state["mode"],
            "labels": state["labels"],
            LABELS_I18N: state[LABELS_I18N],
            "custom": custom,
            "next_id": counter,
            EVENTS_I18N: state[EVENTS_I18N],
        },
        form,
        legacy,
        (config.get("anfrage") or {}).get("event_types") or [] if form == "anfrage" else (),
    )
    ff = dict(config.get("form_fields") or {})
    if entry:
        ff[form] = entry
    else:
        ff.pop(form, None)
    if ff:
        config["form_fields"] = ff
    else:
        config.pop("form_fields", None)
    return config


def panel(site, form: str = "anfrage", state=None, preset: bool = False) -> dict:
    """Модель вкладки «Felder»: поля реестра с режимом, свои вопросы, варианты события.
    `state` — состояние черновика (иначе — сохранённое)."""
    state = canonical(state if state is not None else edit_state(site, form), form)
    custom = state["custom"]
    rows = []
    for field in fields_of(form):
        mode = REQ if field.pinned else state["mode"][field.key]
        plain = field.req_label if field.req_label is not None else field.label
        rows.append(
            {
                "key": field.key,
                "label": str(plain),
                # подсказка в поле своей подписи — как подпись на витрине при этом режиме
                "default_label": str(plain if mode == REQ else field.label),
                "pinned": field.pinned,
                "mode": mode,
                "custom_label": state["labels"].get(field.key, ""),
                "event_type": field.key == "event_type",
                "_tr": state[LABELS_I18N].get(field.key) or {},
            }
        )
    event_on = state["mode"].get("event_type", OFF) != OFF
    return {
        "form": form,
        "fields": rows,
        "modes": [(m, MODE_LABELS[m]) for m in MODES],
        "types": [(t, TYPE_LABELS[t]) for t in form_answers.TYPES],
        "custom": [
            {
                **q,
                "req": q.get("mode") == REQ,
                "options_text": "\n".join(q.get("options") or []),
                "first": i == 0,
                "last": i == len(custom) - 1,
                "new": _is_temp(q.get("id")),
            }
            for i, q in enumerate(custom)
        ],
        "can_add": len(custom) < form_answers.MAX_QUESTIONS,
        "max_questions": form_answers.MAX_QUESTIONS,
        "event_types_text": "\n".join(state["event_types"]),
        "event_hint": form == "anfrage" and event_on and not state["event_types"],
        "preset": preset,
        "_events": [(v, state[EVENTS_I18N].get(v) or {}) for v in state["event_types"]],
        "locales": [],  # FB-33 M2i-5b: языки переводов — `with_locales` (у бизнеса с одним — нет)
    }


def _merge_translations(base: dict, mine: dict, out: dict) -> None:
    """Слить переводы {ключ: {язык: текст}} по (ключ, язык): что владелец изменил во вкладке
    (`mine` против `base`) — его, остальное — как в `out` (сохранённое сейчас). На месте."""
    for key in set(mine) | set(base):
        old, new = base.get(key) or {}, mine.get(key) or {}
        for loc in set(old) | set(new):
            if old.get(loc) == new.get(loc):
                continue
            node = dict(out.get(key) or {})
            if loc in new:
                node[loc] = new[loc]
            else:
                node.pop(loc, None)
            if node:
                out[key] = node
            else:
                out.pop(key, None)


def dropped_note(values) -> str:
    """Сообщение: перевод варианта выпал — вариант переименован или удалён."""
    from django.utils.translation import gettext

    return gettext(
        "Übersetzungen entfernt, weil die Option geändert oder gelöscht wurde: %(names)s"
    ) % {"names": ", ".join(f"„{v}“" for v in values)}


def merge(base, mine, theirs, form: str = "anfrage", notes: list | None = None) -> dict:
    """Трёхстороннее слияние состояния вкладки (ревью M2i-5, H2): `base` — сохранённое на
    момент первой правки черновика, `mine` — черновик, `theirs` — сохранённое сейчас (старая
    панель «Anfrage-Formular» могла записать между ними). Что владелец во вкладке не трогал
    (`mine == base`) — как в `theirs`; поля и подписи — по ключу, свои вопросы и варианты
    события — списком целиком. Номер `next_id` — сохранённый (номера даёт `put`). Если
    слияние выключило оба способа связи, телефон остаётся — и сообщение в `notes`."""
    raw_modes = (mine or {}).get("mode") if isinstance((mine or {}).get("mode"), dict) else {}
    base, mine, theirs = (canonical(x, form) for x in (base, mine, theirs))
    out = canonical(theirs, form)
    for key in out["mode"]:
        value = raw_modes.get(key, mine["mode"].get(key))
        if value in MODES and value != base["mode"].get(key):
            out["mode"][key] = value
    for key in set(mine["labels"]) | set(base["labels"]):
        if mine["labels"].get(key) != base["labels"].get(key):
            if key in mine["labels"]:
                out["labels"][key] = mine["labels"][key]
            else:
                out["labels"].pop(key, None)
    for key in ("custom", "event_types"):
        if mine[key] != base[key]:
            out[key] = mine[key]
    # FB-33 M2i-5b: переводы подписей и вариантов события — по (ключ, язык)
    for name in (LABELS_I18N, EVENTS_I18N):
        _merge_translations(base[name], mine[name], out[name])
    dropped = [
        value
        for value in mine[EVENTS_I18N]
        if mine[EVENTS_I18N][value] != base[EVENTS_I18N].get(value)
        and value not in out["event_types"]
    ]
    # ревью: варианты своих вопросов, чьи переводы из черновика не дошли до итога
    final = canonical(out, form)
    after, ids = set(_translated_options(final)), {q["id"] for q in final["custom"]}
    dropped += [
        k[-1] for k in _translated_options(mine) if k[0] == "q" and k[1] in ids and k not in after
    ]
    if dropped and notes is not None:
        notes.append(dropped_note(dropped))
    if contact_dropped(out, form):
        out["mode"]["phone"] = OPT
        if notes is not None:
            notes.append(contact_note())
    return canonical(out, form)


# ───────────── FB-33 M2i-5b: переводы вариантов «Art der Veranstaltung» по тексту ─────────────
# До среза варианты переводились ПОЗИЦИОННО оверлеем `i18n[язык].anfrage.event_types` (пишет
# демо-сидер `demo_i18n`): переставили/удалили вариант во вкладке — перевод садился на чужой.
# Теперь — `form_fields.anfrage.event_types_i18n` {вариант: {язык: текст}}. Старый оверлей —
# ВРЕМЕННЫЙ запасной путь чтения (до прогона `form_i18n_realign` на сервере, срок — roadmap):
# его впитывают запись вкладки (`put`), старый POST панели и команда переноса.


def _legacy_event_list(site) -> list[str]:
    """Варианты так, как их видел позиционный оверлей ДО среза: та же чистка, что у
    `normalize_anfrage`, но БЕЗ дедупа (дубли занимали свои позиции), кап — 12 записей."""
    from apps.tenants import siteconfig

    anfrage = site.get("anfrage") if isinstance(site.get("anfrage"), dict) else {}
    raw = anfrage.get("event_types") if isinstance(anfrage.get("event_types"), list) else []
    out = []
    for item in raw:
        text = item.strip()[: siteconfig._EVENT_TYPE_MAX] if isinstance(item, str) else ""
        if text:
            out.append(text)
        if len(out) >= siteconfig._MAX_EVENT_TYPES:
            break
    return out


def _legacy_lists(site) -> dict:
    """{язык: позиционный список переводов} старого оверлея `i18n.<язык>.anfrage`."""
    i18n = site.get("i18n") if isinstance(site.get("i18n"), dict) else {}
    out = {}
    for loc in form_answers.overlay_locales():
        node = i18n.get(loc) if isinstance(i18n.get(loc), dict) else {}
        anfrage = node.get("anfrage") if isinstance(node.get("anfrage"), dict) else {}
        shown = anfrage.get("event_types")
        if isinstance(shown, list):
            out[loc] = shown
    return out


def has_legacy(site) -> bool:
    """Есть старый позиционный оверлей `i18n.<язык>.anfrage`."""
    i18n = (site or {}).get("i18n") if isinstance(site, dict) else None
    return isinstance(i18n, dict) and any(
        isinstance(node, dict) and "anfrage" in node for node in i18n.values()
    )


def legacy_mismatch(site) -> bool:
    """Позиционный перенос сомнителен: длина оверлея не равна списку вариантов или в списке
    были дубли (ревью: такие сайты `form_i18n_realign --dry-run` печатает отдельно)."""
    site = site if isinstance(site, dict) else {}
    events = _legacy_event_list(site)
    lists = _legacy_lists(site)
    return bool(lists) and (
        len(set(events)) != len(events) or any(len(v) != len(events) for v in lists.values())
    )


def legacy_event_i18n(site) -> dict:
    """Старые позиционные переводы вариантов {вариант: {язык: текст}}: i-й перевод — i-му
    варианту НЕдедуплицированного списка (как накладывал `localize` до среза); у дубля
    варианта — перевод его первой позиции."""
    site = site if isinstance(site, dict) else {}
    events = _legacy_event_list(site)
    out: dict = {}
    for loc, shown in _legacy_lists(site).items():
        for value, text in zip(events, shown, strict=False):
            if isinstance(text, str) and loc not in out.get(value, {}):
                out.setdefault(value, {})[loc] = text
    return _event_translations(out, list(dict.fromkeys(events)))


def event_translations(site) -> dict:
    """Переводы вариантов события: ключом по тексту, недостающие (вариант, язык) — из
    старого позиционного оверлея (запасной путь до переноса)."""
    from apps.tenants import siteconfig

    site = site if isinstance(site, dict) else {}
    events = siteconfig.normalize_anfrage(site.get("anfrage")).get("event_types") or []
    stored = ((site.get("form_fields") or {}).get("anfrage") or {}).get(EVENTS_I18N)
    out = _event_translations(stored, events)
    for value, tr in legacy_event_i18n(site).items():
        for loc, text in tr.items():
            out.setdefault(value, {}).setdefault(loc, text)
    return {value: out[value] for value in events if value in out}


def event_type_choices(site, locale=None) -> list[tuple[str, str, str]]:
    """Пары (value, подпись) выбора «Art der Veranstaltung»: value — ВСЕГДА вариант на
    основном языке (его проверяет `/anfrage/` и хранит `Job.event_type`), подпись — перевод
    языка показа (ключом → старый позиционный → основной)."""
    site = site if isinstance(site, dict) else {}
    events = (site.get("anfrage") or {}).get("event_types") or []
    loc = shown_locale(locale)
    tr = event_translations(site) if loc else {}
    return [_choice(value, (tr.get(value) or {}).get(loc), loc) for value in events]


def _choice(value: str, label, loc: str) -> tuple[str, str, str]:
    """(value, подпись, lang): непереведённый вариант на странице другого языка — с `lang`
    основного языка (скринридер читает его по-немецки); на основном языке lang пуст."""
    from django.conf import settings

    if label:
        return (value, label, "")
    return (value, value, settings.LANGUAGE_CODE[:2] if loc else "")


def _drop_legacy_event_i18n(config: dict) -> bool:
    """Убрать старый позиционный оверлей `i18n.*.anfrage` (на месте; пустые узлы — тоже)."""
    i18n = config.get("i18n")
    if not isinstance(i18n, dict):
        return False
    changed = False
    for loc in list(i18n):
        node = i18n[loc]
        if isinstance(node, dict) and "anfrage" in node:
            node = {k: v for k, v in node.items() if k != "anfrage"}
            changed = True
            if node:
                i18n[loc] = node
            else:
                i18n.pop(loc)
    if not i18n:
        config.pop("i18n", None)
    return changed


def absorb_legacy_event_i18n(config: dict) -> bool:
    """Перенести старые позиционные переводы вариантов в `event_types_i18n` (ключом по
    тексту; уже записанный ключевой перевод главнее) и убрать `i18n.*.anfrage`. Меняет
    `config` на месте (сырой или нормализованный); True — было что переносить/чистить.
    Вызывать под блокировкой строки бизнеса (старый POST панели, `form_i18n_realign`)."""
    if not isinstance(config, dict):
        return False
    from apps.tenants import siteconfig

    events = siteconfig.normalize_anfrage(config.get("anfrage")).get("event_types") or []
    merged = event_translations(config)
    if not _drop_legacy_event_i18n(config):
        return False
    ff = (
        dict(config.get("form_fields") or {}) if isinstance(config.get("form_fields"), dict) else {}
    )
    entry = dict(ff.get("anfrage") or {}) if isinstance(ff.get("anfrage"), dict) else {}
    merged = _event_translations(merged, events)
    if merged:
        entry[EVENTS_I18N] = merged
    else:
        entry.pop(EVENTS_I18N, None)
    if entry:
        ff["anfrage"] = entry
    else:
        ff.pop("anfrage", None)
    if ff:
        config["form_fields"] = ff
    else:
        config.pop("form_fields", None)
    return True


def lost_event_translations(config: dict, new_events) -> list[str]:
    """Варианты с переводом, которых нет в новом списке (старый POST панели переименовал или
    удалил вариант — перевод выпадет): для сообщения владельцу."""
    return [v for v, tr in event_translations(config).items() if tr and v not in new_events]


def set_event_translations(config: dict, translations: dict, overwrite: bool = False) -> None:
    """Дописать переводы вариантов события {вариант: {язык: текст}} (демо-сидер `demo_i18n`):
    существующий перевод (ручной) главнее, если не `overwrite`. Меняет `config` на месте."""
    from apps.tenants import siteconfig

    events = siteconfig.normalize_anfrage(config.get("anfrage")).get("event_types") or []
    ff = (
        dict(config.get("form_fields") or {}) if isinstance(config.get("form_fields"), dict) else {}
    )
    entry = dict(ff.get("anfrage") or {}) if isinstance(ff.get("anfrage"), dict) else {}
    out = _event_translations(entry.get(EVENTS_I18N), events)
    for value, tr in (translations or {}).items():
        for loc, text in (tr or {}).items():
            node = out.setdefault(value, {})
            if overwrite or loc not in node:
                node[loc] = text
    out = _event_translations(out, events)
    if out:
        entry[EVENTS_I18N] = out
    else:
        entry.pop(EVENTS_I18N, None)
    if entry:
        ff["anfrage"] = entry
        config["form_fields"] = ff


def with_locales(fs: dict, locales, wanted: str = "") -> dict:
    """FB-33 M2i-5b: поля переводов вкладки «Felder» на языки бизнеса `locales` (без основного;
    пусто — вкладка прежняя байт-в-байт). Группы всех языков — в DOM, видна одна: `wanted`, если
    он из `locales`, иначе первая; выбор — серверными кнопками `f_sprache` (без скриптов, язык
    помнится). Имя (`name`) — только у полей ВЫБРАННОГО языка (ревью: предел числа полей формы
    `DATA_UPLOAD_MAX_NUMBER_FIELDS`); не присланное не трогается (presence-guard разбора)."""
    from django.conf import settings
    from django.utils import translation

    names = dict(settings.LANGUAGES)
    base = settings.LANGUAGE_CODE[:2]
    allowed = set(form_answers.overlay_locales())
    locs = [loc for loc in locales or () if loc in allowed]
    if not locs:
        return fs
    lang = wanted if wanted in locs else locs[0]
    fs["lang"] = lang
    fs["lang_label"] = names.get(lang, lang)
    fs["locales"] = [
        {"code": loc, "label": names.get(loc, loc), "shown": loc == lang} for loc in locs
    ]

    def inputs(tr: dict, name: str, ident: str, empty, of: str = "", src: str = "") -> list[dict]:
        """`empty(loc)` — (текст, язык), что покажет сайт без перевода. M2i-5c: источник для
        кнопки ИИ — `of` (имя поля этой формы с основным текстом, живое значение) или `src`
        (текст варианта: имя поля перевода — от его хеша)."""
        out = []
        for loc in locs:
            text, text_lang = empty(loc)
            out.append(
                {
                    "loc": loc,
                    "label": names.get(loc, loc),
                    "name": f"f_{name}_{loc}",
                    "id": f"ff-{ident}-{loc}",
                    "value": tr.get(loc, ""),
                    "shown": loc == lang,
                    "empty": text,
                    "empty_lang": text_lang,
                    # подсказка «Leeres Feld…» над полями (id в `_bw_formfields.html`)
                    "hint": LANG_HINT_ID,
                    "of": of,
                    "src": src,
                }
            )
        return out

    def german(text):
        return lambda _loc: (text, base)

    def default_label(row):
        """Без перевода сайт покажет свою немецкую подпись, а без неё — подпись по
        умолчанию НА ЭТОМ языке (gettext), не немецкую."""
        field = _BY_FORM[fs["form"]][row["key"]]
        plain = (
            field.req_label if row["mode"] == REQ and field.req_label is not None else field.label
        )

        def empty(loc):
            if row["custom_label"]:
                return row["custom_label"], base
            with translation.override(loc):
                return str(plain), loc

        return empty

    def options(pairs, tr, name, ident):
        items = [
            {
                "text": text,
                "inputs": inputs(tr.get(text) or {}, name(h), ident(i), german(text), src=text),
            }
            for i, (text, h) in enumerate(pairs)
        ]
        filled = any(t["value"] for o in items for t in o["inputs"] if t["shown"])
        return items, filled

    for row in fs["fields"]:
        if not row["pinned"]:
            row["translations"] = inputs(
                row["_tr"],
                f"label_{row['key']}",
                f"label-{row['key']}",
                default_label(row),
                of=f"f_label_{row['key']}",
            )
    for q in fs["custom"]:
        if _is_temp(q.get("id")):
            continue  # новый вопрос: переводы — после «Übernehmen»
        qid = q["id"]
        q["translations"] = inputs(
            q.get("label_i18n") or {},
            f"q_{qid}_label",
            f"q-{qid}",
            german(q["label"]),
            of=f"f_q_{qid}_label",
        )
        if q.get("type") == "choice":
            q["option_translations"], q["options_open"] = options(
                hashed(q.get("options") or []),
                q.get("options_i18n") or {},
                lambda h, qid=qid: f"q_{qid}_o{h}",
                lambda i, qid=qid: f"q-{qid}-o{i}",
            )
    fs["event_translations"], fs["events_open"] = options(
        hashed([v for v, _tr in fs["_events"]]),
        dict(fs["_events"]),
        lambda h: f"et_{h}",
        lambda i: f"et-{i}",
    )
    return fs
