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

from typing import NamedTuple

from django.utils.translation import gettext_lazy as _

from apps.core import form_answers

OFF, OPT, REQ = "off", "opt", "req"
MODES = (OFF, OPT, REQ)
LABEL_MAX = 120


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
    # корзина — заготовка M2i-3 (режимы полей оформления): пока без потребителя; имя
    # закреплено (у столика его заменяет номер стола)
    "checkout": (
        Field("name", _("Name"), default=REQ, pinned=True),
        Field("email", _("Email")),
        Field("phone", _("Phone")),
        Field("note", _("Note")),
    ),
}
#: способ связи в заявке: хотя бы одно из полей спрашивается (оба «нет» нельзя)
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


def normalize(raw, form: str, legacy_fields=()) -> dict:
    """Настройки одной формы: только отличия от умолчания. Мусор — молча прочь."""
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
    custom, next_id = form_answers.normalize_questions(raw.get("custom"), raw.get("next_id"))
    if custom:
        out["custom"] = custom
    if next_id:
        out["next_id"] = next_id  # номер помнится и после удаления всех вопросов
    return out


def normalize_all(raw, legacy_fields=()) -> dict:
    """`site_config["form_fields"]` целиком: известные формы с непустыми настройками."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for form in FORMS:
        legacy = legacy_fields if form == "anfrage" else ()
        entry = normalize(raw.get(form), form, legacy)
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


def view(site, form: str) -> dict:
    """Что рисует форма: {ключ: FieldView} + свои вопросы (`custom`) + сводка для полосы
    заявки (`band_extra`, `band_custom`, `band_full`) и `any_event`."""
    labels = ((site.get("form_fields") or {}).get(form) or {}).get("labels") or {}
    out: dict = {}
    for field in fields_of(form):
        mode = mode_of(site, form, field.key)
        if field.key == "event_type" and not (site.get("anfrage") or {}).get("event_types"):
            mode = OFF  # выбор без вариантов владельца не рисуется и не обязателен
        default = field.req_label if mode == REQ and field.req_label is not None else field.label
        out[field.key] = FieldView(mode, labels.get(field.key) or str(default))
    out["custom"] = [{**q, "req": q.get("mode") == "req"} for q in questions(site, form)]
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


def missing(site, form: str, post, files=None) -> list[str]:
    """Обязательные включённые поля без значения (проверка сервера — POST в обход формы).
    Значение проверяется так же, как его разберёт вьюха (битая дата = нет значения). У заявки
    ещё и способ связи: хотя бы один из включённых e-mail/телефон (`CONTACT_MISSING`)."""
    from datetime import date

    out = []
    shown = view(site, form)
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
        if not ok:
            out.append(field.key)
    qs = questions(site, form)
    out += form_answers.validate(qs, form_answers.collect(qs, post))
    contacts = [k for k in CONTACT if form == "anfrage" and shown[k].on]
    if contacts and not any(_filled(post, k) for k in contacts):
        out.append(CONTACT_MISSING)
    return out


def missing_labels(site, form: str, keys) -> str:
    """Подписи незаполненных полей для сообщения («Phone, Details»)."""
    from django.utils.translation import gettext

    shown = view(site, form)
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
