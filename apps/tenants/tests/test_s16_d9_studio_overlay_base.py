"""FB-33 стопка 16 D9: Save Студии на языке перевода не переносит перевод в немецкую базу.

Дефект данных (ревью architect CRITICAL №1, №2): при Save на языке перевода вьюха Студии
локализует ВЕСЬ конфиг (`siteconfig.localize`), а `split_translation` возвращает базу на место
только для ключей, которые узнаёт. Пункты полосы доверия он искал по полю `title` (у них —
`label`), поэтому русские тексты уходили в немецкую базу и перевод снимался. Тот же класс —
`seo`: `localize` накладывал `i18n.<язык>.seo`, а разбор его не возвращает.

Замки через вьюху Студии (`views.home_builder_view`, RequestFactory): Save без правок не
меняет ни базу, ни оверлей ни одного ключа, у которого в `i18n.ru` есть перевод; новый ключ
перевода у писателей без записи здесь — красный.
"""

import ast
import copy
import itertools
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.conf import settings as dj_settings
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_N = itertools.count()

USP_DE = [
    {"icon": "clock", "label": "Schnell", "text": "In 1 Tag"},
    {"icon": "bio", "label": "Frisch"},
]
USP_RU = [{"label": "Быстро", "text": "За 1 день"}, {"label": "Свежо"}]

# ключ оверлея → (немецкая база, перевод ru) — данные, которые переживают `normalize`
CASES = {
    "hero_title": ("Willkommen", "Добро пожаловать"),
    "hero_text": ("Frisch gebacken", "Свежая выпечка"),
    "about_title": ("Über uns", "О нас"),
    "about_text": ("Seit 1990", "С 1990 года"),
    "section_titles": ({"faq": "Fragen"}, {"faq": "Вопросы"}),
    "section_intros": ({"products": "Kurz erklärt"}, {"products": "Коротко"}),
    "cta": (
        {"title": "Jetzt bestellen", "text": "Heute", "button_label": "Los", "button_url": ""},
        {"title": "Закажите", "text": "Сегодня", "button_label": "Вперёд"},
    ),
    "faq": ([{"q": "Parkplatz?", "a": "Ja."}], [{"q": "Парковка?", "a": "Да."}]),
    "testimonials": ([{"name": "Anna", "text": "Toll"}], [{"name": "Анна", "text": "Отлично"}]),
    "process": (
        [{"title": "Anrufen", "text": "Kurz"}],
        [{"title": "Позвонить", "text": "Коротко"}],
    ),
    "heroes": (
        [{"image": "", "title": "Sommer", "text": "Neu", "button_label": "", "button_url": ""}],
        [{"title": "Лето", "text": "Новое"}],
    ),
    "trust": ({"since": "1990", "marks": ["Meisterbetrieb"]}, {"marks": ["Мастерская"]}),
    "archetypes": (
        {
            "catalog": {
                "label": "Laden",
                "blurb": "Alles da",
                "hidden": False,
                "intro": "",
                "hero_image": "",
                "button_label": "",
                "button_url": "",
                "gallery": [],
            }
        },
        {"catalog": {"label": "Магазин", "blurb": "Всё есть"}},
    ),
    "usp_bar": (USP_DE, USP_RU),
    "team": ([{"name": "Max", "role": "Bäcker", "photo": ""}], [{"role": "Пекарь"}]),
    "before_after": (
        [{"before": "/b.jpg", "after": "/a.jpg", "text": "Vorher"}],
        [{"text": "До и после"}],
    ),
    "page_titles": ({"services": {"title": "Leistungen"}}, {"services": {"title": "Услуги"}}),
    "confirmation_next": ("Wir melden uns", "Мы свяжемся"),
    "catalog_title": ("Sortiment", "Ассортимент"),
    "catalog_intro": ("Alles frisch", "Всё свежее"),
    "sections": (
        [{"key": "text", "id": "b1", "enabled": True, "data": {"title": "Hallo", "body": "x"}}],
        [{"data": {"title": "Привет"}}],
    ),
    "page_blocks": (
        {
            "info": [
                {"key": "text", "id": "p1", "enabled": True, "data": {"title": "Wir", "body": "y"}}
            ]
        },
        {"info": [{"data": {"title": "Мы"}}]},
    ),
    "seo": (
        {"pages": {"info": {"title": "Über uns — Café"}}},
        {"pages": {"info": {"title": "О нас — кафе"}}},
    ),
}
# `anfrage` — не оверлей: старый `i18n.<язык>.anfrage` normalize переносит в
# `form_fields.anfrage.event_types_i18n` (FB-33 M2i-5b), `localize` его не накладывает
NOT_OVERLAY = {"anfrage"}


def _req(tenant, method, path, data=None, **extra):
    req = getattr(RequestFactory(), method)(path, data or {}, **extra)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _tenant(config: dict):
    tenant = TenantFactory(schema_name="public", slug=f"d9{next(_N)}", name="D9")
    tenant.site_config = siteconfig.normalize(config)
    tenant.enabled_locales = ["de", "ru"]
    tenant.save()
    return tenant


def _stored(tenant) -> dict:
    return siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)


def _studio_save(tenant, data: dict) -> dict:
    data = {"content_lang": "ru", **data}
    resp = views.home_builder_view(_req(tenant, "post", "/dashboard/site/home/", data))
    assert resp.status_code == 302
    return _stored(tenant)


def _trim(value):
    """Хвост пустых переводов списка не хранится — сравниваем без него."""
    if isinstance(value, list):
        value = list(value)
        while value and not value[-1]:
            value.pop()
    elif isinstance(value, dict):
        value = {k: _trim(v) for k, v in value.items()}
    return value


def _case_tenant(key: str):
    """Тенант случая: у `sections` перевод C-блока стоит на позиции блока в нормализованном
    списке (оверлей секций позиционный, фикс-секции идут первыми)."""
    base, ru = copy.deepcopy(CASES[key])
    tenant = _tenant({key: base})
    if key == "sections":
        rows = siteconfig.normalize(tenant.site_config)["sections"]
        at = next(i for i, row in enumerate(rows) if row.get("id") == "b1")
        ru = [{}] * at + ru
    tenant.site_config = siteconfig.normalize({**tenant.site_config, "i18n": {"ru": {key: ru}}})
    tenant.save()
    return tenant


def _base_of(cfg: dict, key: str):
    """База ключа без служебного: у `sections` — только C-блоки (фикс-секции — структура)."""
    value = cfg.get(key)
    if key == "sections":
        return [s for s in value or [] if isinstance(s, dict) and s.get("id")]
    return value


# --- №1/№13: пункты полосы доверия ---------------------------------------------------


def test_studio_ru_save_keeps_german_usp_base():
    tenant = _tenant({"usp_bar": USP_DE, "i18n": {"ru": {"usp_bar": USP_RU}}})
    cfg = _studio_save(tenant, {})
    assert cfg["usp_bar"] == USP_DE
    assert cfg["i18n"]["ru"]["usp_bar"] == USP_RU


def test_studio_ru_usp_edit_goes_to_translation():
    """Пункты прислала форма (старый черновик, демо-кит) в ru: правка — в перевод, база цела."""
    tenant = _tenant({"usp_bar": USP_DE, "i18n": {"ru": {"usp_bar": USP_RU}}})
    usp_text = "clock | Быстро | За 2 дня\nbio | Свежо"
    cfg = _studio_save(tenant, {"content_sections_present": "1", "usp_text": usp_text})
    assert cfg["usp_bar"] == USP_DE
    assert cfg["i18n"]["ru"]["usp_bar"][0] == {"label": "Быстро", "text": "За 2 дня"}
    assert cfg["i18n"]["ru"]["usp_bar"][1] == {"label": "Свежо"}


# --- класс: ни один ключ с переводом не уходит в базу ---------------------------------


@pytest.mark.parametrize("key", sorted(CASES))
def test_studio_ru_save_without_edits_keeps_every_base(key):
    tenant = _case_tenant(key)
    before = _stored(tenant)
    # предусловие: данные случая переживают normalize (иначе замок ничего не держит)
    assert _base_of(before, key), key
    assert before.get("i18n", {}).get("ru", {}).get(key), key
    after = _studio_save(tenant, {})
    assert _base_of(after, key) == _base_of(before, key)
    assert _trim(after["i18n"]["ru"][key]) == _trim(before["i18n"]["ru"][key])


def _writer_overlay_keys() -> set:
    """Корни путей, которые пишут писатели переводов (`set_overlay_value`, `_set_path`).

    Литеральные пути — из ast (кортеж аргументом писателя, присвоенный `path` или
    возвращённый функцией пути); вычисляемые — из реестров, по которым их строят."""
    from apps.core import home_texts, page_title

    keys = set()
    root = Path(dj_settings.BASE_DIR) / "apps"
    path_funcs = {"tr_path", "_path", "_block_path"}
    for src in root.rglob("*.py"):
        if "tests" in src.parts or "migrations" in src.parts:
            continue
        text = src.read_text(encoding="utf-8")
        if "set_overlay_value(" not in text and "_set_path(" not in text:
            continue
        tree = ast.parse(text)
        tuples = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                if name in ("set_overlay_value", "_set_path") and len(node.args) >= 3:
                    tuples.append(node.args[2])
            elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "path" for t in node.targets
            ):
                tuples.append(node.value)
            elif isinstance(node, ast.FunctionDef) and node.name in path_funcs:
                tuples += [r.value for r in ast.walk(node) if isinstance(r, ast.Return)]
        for tup in tuples:
            if isinstance(tup, ast.Tuple) and tup.elts:
                first = tup.elts[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    keys.add(first.value)
    # поля секций главной пишутся переводом по одному только у скаляров и вложенных
    # словарей (`home_texts.set_text`); списки — разбором `split_translation`
    for key, fields in home_texts.FIELDS.items():
        if key in home_texts.SCALAR_KEYS or key in home_texts._NESTED:
            for field in fields:
                keys.add(home_texts.tr_path(key, field[0])[0])
    for name in page_title.CATALOG_KEYS:
        keys.add(page_title.tr_path(page_title.CATALOG, name)[0])
    keys.update(siteconfig.TRANSLATABLE_KEYS)
    return keys


def test_every_overlay_key_has_a_case():
    """Новый ключ под `i18n.<язык>` без записи в CASES — красный: класс держится целиком."""
    missing = _writer_overlay_keys() - set(CASES) - NOT_OVERLAY
    assert not missing, f"ключи перевода без замка D9: {sorted(missing)}"


# --- localize и реестр ключей пунктов ---------------------------------------------------


def test_localize_skips_seo():
    cfg = siteconfig.normalize(
        {
            "seo": CASES["seo"][0],
            "anfrage": {"fields": ["event_type"], "event_types": ["Hochzeit"]},
            "hero_title": "Willkommen",
            "i18n": {
                "ru": {
                    "seo": CASES["seo"][1],
                    "anfrage": {"event_types": ["Свадьба"]},
                    "hero_title": "Добро пожаловать",
                }
            },
        }
    )
    shown = siteconfig.localize(cfg, "ru")
    assert shown["seo"] == CASES["seo"][0]
    assert shown["anfrage"] == cfg["anfrage"]
    assert shown["hero_title"] == "Добро пожаловать"
    assert "i18n" not in shown


def test_usp_overlay_key_is_label():
    assert siteconfig.LIST_OVERLAY_KEYS["usp_bar"] == "label"
    cfg = {"usp_bar": copy.deepcopy(USP_DE), "i18n": {"ru": {"usp_bar": copy.deepcopy(USP_RU)}}}
    new = [USP_DE[1], {"icon": "check", "label": "Neu"}, USP_DE[0]]
    siteconfig.realign_list_overlays(cfg, {"usp_bar": new})
    assert cfg["i18n"]["ru"]["usp_bar"] == [USP_RU[1], {}, USP_RU[0]]
