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

import re
from typing import NamedTuple

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

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


# ───────────── FB-33 M2i-5: вкладка «Felder» окна блока формы (через черновик) ─────────────
# План — `docs/fb33-editor-model-2026-11-19.md` §«План M2i-5». Состояние вкладки — «полное»
# представление настроек одной формы (режим каждого незакреплённого поля, подписи, свои
# вопросы, номер, варианты «Art der Veranstaltung»): так черновик сравнивается с сохранённым
# байт-в-байт, а «Abbrechen» возвращает ровно открытое. На сайт его пишет только `put`.

#: служебный ключ превью «Seitenaufbau»: состояние вкладки черновика (с временными id) для
#: панели; нормализатор сайта его роняет — на сайт он не попадает
EDIT_KEY = "_form_edit"
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
    return {
        "mode": {f.key: mode_of(site, form, f.key) for f in fields_of(form) if not f.pinned},
        "labels": dict(stored.get("labels") or {}),
        "custom": copy.deepcopy(stored.get("custom") or []),
        "next_id": next_id,
        "event_types": list((site.get("anfrage") or {}).get("event_types") or [])
        if form == "anfrage"
        else [],
    }


def _event_types(raw) -> list[str]:
    """Варианты «Art der Veranstaltung» — тем же нормализатором, что и сохранённые."""
    from apps.tenants import siteconfig

    items = raw if isinstance(raw, list) else []
    return siteconfig.normalize_anfrage({"fields": ["event_type"], "event_types": items[:50]}).get(
        "event_types", []
    )


def canonical(state, form: str = "anfrage") -> dict:
    """Состояние вкладки в каноническом виде: режимы и подписи — через `normalize`, свои
    вопросы — через `form_answers.normalize_questions` (временные id разрешены)."""
    state = state if isinstance(state, dict) else {}
    fields = fields_of(form)
    raw_mode = state.get("mode") if isinstance(state.get("mode"), dict) else {}
    legacy = [f.legacy for f in fields if f.legacy and raw_mode.get(f.key) in (OPT, REQ)]
    spec = normalize({"mode": raw_mode, "labels": state.get("labels")}, form, legacy)
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
        "custom": custom,
        "next_id": next_id,
        "event_types": _event_types(state.get("event_types")) if form == "anfrage" else [],
    }


def _lines(raw, limit: int) -> list[str]:
    """Строки textarea (вариант на строку): длина и число строк режутся до разбора."""
    if not isinstance(raw, str):
        return []
    return [line.strip() for line in raw[:_TEXT_CAP].splitlines()[:limit] if line.strip()]


def _text(raw, limit: int) -> str:
    return form_answers.clean_text(raw[:_TEXT_CAP] if isinstance(raw, str) else raw, limit)


def _temp_id(custom: list[dict]) -> str:
    used = {q.get("id") for q in custom}
    return next(f"n{k}" for k in range(1, 1000) if f"n{k}" not in used)


_DO = re.compile(r"^(up|down|del):(q[1-9][0-9]{0,3}|n[0-9]{1,3})$")


def parse_post(post, current, form: str = "anfrage", preset: dict | None = None):
    """Правка вкладки «Felder» → (новое состояние, сообщения владельцу).

    `post` — поля формы окна (без префикса `f_`), `current` — состояние черновика. Режимы и
    типы — из белых списков, лимиты (10 вопросов × 20 вариантов × 120 символов) — до циклов;
    правятся только вопросы из `current` (id из запроса не создаёт и не берёт чужой вопрос).
    Закреплённые поля (что нужно, имя) не меняются; оба способа связи «нет» — телефон остаётся.
    `FormSpecError("ids")` — номера вопросов кончились (`ID_MAX`)."""
    from django.utils.translation import gettext

    state = canonical(current, form)
    get = post.get if hasattr(post, "get") else {}.get
    notes: list[str] = []
    for field in fields_of(form):
        if field.pinned:
            continue
        value = get(f"mode_{field.key}")
        if value in MODES:
            state["mode"][field.key] = value
        if f"label_{field.key}" in post:
            text = _text(get(f"label_{field.key}"), LABEL_MAX)
            if text:
                state["labels"][field.key] = text
            else:
                state["labels"].pop(field.key, None)
    for q in state["custom"]:
        prefix = f"q_{q['id']}_"
        if prefix + "label" not in post:
            continue  # вопроса не было в форме — остаётся как есть
        label = _text(get(prefix + "label"), form_answers.LABEL_MAX)
        if label:
            q["label"] = label
        else:
            notes.append(gettext("Eine Frage ohne Text bleibt wie bisher."))
        kind = get(prefix + "type")
        options = (
            _lines(get(prefix + "options"), form_answers.MAX_OPTIONS * 2)
            if prefix + "options" in post
            else list(q.get("options") or [])
        )
        if kind in form_answers.TYPES:
            if kind == "choice" and not options:
                notes.append(gettext("Für eine Auswahl bitte mindestens eine Option eintragen."))
            else:
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
        state["event_types"] = _lines(get("event_types"), 24)
    _action(state, get, form, preset, notes)
    if form == "anfrage" and all(state["mode"].get(k) == OFF for k in CONTACT):
        state["mode"]["phone"] = OPT  # способ связи нельзя снять целиком (как `normalize`)
        notes.append(
            gettext("E-Mail oder Telefon muss gefragt werden – das Telefon bleibt in der Form.")
        )
    state = canonical(state, form)
    if form == "anfrage":
        if state["mode"].get("event_type", OFF) != OFF and not state["event_types"]:
            notes.append(
                gettext(
                    "„Art der Veranstaltung“ erscheint erst mit einer Auswahlliste – bitte "
                    "Optionen eintragen."
                )
            )
    return state, notes


def _action(state: dict, get, form: str, preset, notes: list) -> None:
    """Кнопка вкладки: «+ Frage», вверх/вниз/удалить, «Branchen-Vorlage»."""
    from django.utils.translation import gettext

    do = get("do") or ""
    custom = state["custom"]
    if do == "add":
        label = _text(get("new_label"), form_answers.LABEL_MAX)
        kind = get("new_type") if get("new_type") in form_answers.TYPES else "text"
        options = _lines(get("new_options"), form_answers.MAX_OPTIONS * 2)
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
        {"mode": state["mode"], "labels": state["labels"], "custom": custom, "next_id": counter},
        form,
        legacy,
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
        rows.append(
            {
                "key": field.key,
                "label": str(field.req_label if field.req_label is not None else field.label),
                "default_label": str(field.label),
                "pinned": field.pinned,
                "mode": REQ if field.pinned else state["mode"][field.key],
                "custom_label": state["labels"].get(field.key, ""),
                "event_type": field.key == "event_type",
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
    }
