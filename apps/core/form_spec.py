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
    # корзина (M2i-3): имя закреплено (у столика его заменяет номер стола)
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
        if _default(by_key["phone"], legacy_fields) == OFF:
            modes["phone"] = OPT
    if modes:
        out["mode"] = modes
    label_raw = raw.get("labels") if isinstance(raw.get("labels"), dict) else {}
    labels = {}
    for key in by_key:
        text = label_raw.get(key)
        if isinstance(text, str) and text.strip():
            labels[key] = " ".join(text.split())[:LABEL_MAX]
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


def view(site, form: str) -> dict:
    """Что рисует форма: {ключ: FieldView} + сводка для полосы заявки (`band_extra`,
    `band_full`) и `any_event` (есть ли включённое событийное поле)."""
    labels = ((site.get("form_fields") or {}).get(form) or {}).get("labels") or {}
    out: dict = {}
    for field in fields_of(form):
        mode = mode_of(site, form, field.key)
        if field.key == "event_type" and not (site.get("anfrage") or {}).get("event_types"):
            mode = OFF  # выбор без вариантов владельца не рисуется и не обязателен
        default = field.req_label if mode == REQ and field.req_label is not None else field.label
        out[field.key] = FieldView(mode, labels.get(field.key) or str(default))
    if form == "anfrage":
        extra = [k for k, f in out.items() if f.req and k not in BAND_NATIVE]
        out["band_full"] = "photos" in extra or len(extra) > BAND_EXTRA_MAX
        out["band_extra"] = [] if out["band_full"] else [(k, out[k]) for k in extra]
        out["any_event"] = any(out[k].on for k in ("event_date", "guest_count", "event_type"))
    return out


def missing(site, form: str, post, files=None) -> list[str]:
    """Обязательные включённые поля без значения (проверка сервера — POST в обход формы).
    Значение проверяется так же, как его разберёт вьюха (битая дата = нет значения)."""
    from datetime import date

    out = []
    shown = view(site, form)
    for field in fields_of(form):
        f = shown[field.key]
        if not f.req or field.pinned:
            continue  # закреплённые проверяет сама вьюха (прежние тексты ошибок)
        raw = (post.get(field.key) or "").strip()
        ok = bool(raw)
        if field.key == "photos":
            ok = bool(files and files.getlist("photos"))
        elif field.key == "event_date" and raw:
            try:
                date.fromisoformat(raw)
            except ValueError:
                ok = False
        elif field.key == "guest_count" and raw:
            ok = raw.isdigit() and 1 <= int(raw) <= 100000
        elif field.key == "event_type" and raw:
            ok = raw in ((site.get("anfrage") or {}).get("event_types") or [])
        if not ok:
            out.append(field.key)
    return out
