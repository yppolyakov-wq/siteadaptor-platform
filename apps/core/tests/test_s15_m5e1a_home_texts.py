"""FB-33 стопка 15 M5e-1a: один писатель текстов секций главной (`apps/core/home_texts.py`).

План — `docs/fb33-stack15-plan-2026-11-25.md` §2 «M5e-1», §4 «M5e-1», §14.1 A1–A4, A14, A15.
Замки первого коммита: где поведения ещё нет — strict xfail (снимаются в коммитах реализации).

- A1: все писатели (Студия, черновик превью Студии, правка на канве, мастер) — через
  `home_texts`; импорт и демо-сидеры — исключения списком (`test_home_texts_writers_ast`).
- A2: сохранение в режиме перевода пишет только свой язык, без выравнивания и снятия.
- A3: устаревшая вкладка Студии не возвращает старые тексты (отпечаток `htx_base_<ключ>`).
- A4 (сторона Студии): правка немецкого снимает перевод ИМЕННО этого поля.
- A14: `home_texts.FIELDS` — источник, `siteconfig.CONTENT_FIELDS` — производный.
- A15: фото команды не стирается (единственное разрешённое отличие вывода Студии).
- §9 №4: потолки 120 / 2000 / 4000, неизменённое старое не режется; ссылка кнопки CTA —
  только http(s)/mailto/tel/относительная.
"""

from __future__ import annotations

import ast
import json
import os
import pathlib
import re
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parents[3]
GOLDEN = pathlib.Path(__file__).with_name("golden_s15_m5e1a") / "studio_save.json"
#: ключи `site_config`, которые пишет `home_texts` (замок «один писатель» A1)
TEXT_KEYS = frozenset(
    {
        "hero_title",
        "hero_text",
        "about_title",
        "about_text",
        "cta",
        "process",
        "team",
        "testimonials",
        "trust",
        "archetypes",
    }
)
#: осознанные исключения (решение владельца A1): импорт, демо-сидеры, образцы дизайна,
#: нормализация и обложки разделов (они пишут intro/hero_image/gallery архетипа, не тексты)
WRITER_EXCEPTIONS = {
    "apps/core/home_texts.py": None,  # сам писатель
    "apps/imports/site/apply.py": None,  # импорт сайта (A1)
    "apps/imports/cscart.py": None,  # импорт CS-Cart (A1)
    "apps/tenants/demo.py": None,  # демо-сидер (A1)
    "apps/tenants/demo_kits.py": None,  # демо-киты (A1)
    "apps/core/design_samples.py": None,  # образцы предпросмотра дизайна, не запись
    "apps/tenants/siteconfig.py": {"normalize", "_normalize_impl"},  # нормализация, не правка
    "apps/core/views.py": {
        # обложки разделов: intro/hero_image/gallery/кнопка архетипа (не label/blurb)
        "_upload_cover_gallery",
        "_upload_cover_hero",
        "_delete_cover_image",
        "sections_view",
    },
}


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method, path, data=None, tenant=None, lang_cookie=None, body=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    if body is not None:
        req._body = json.dumps(body).encode()
        req.META["CONTENT_TYPE"] = "application/json"
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    if lang_cookie:
        req.COOKIES[settings.LANGUAGE_COOKIE_NAME] = lang_cookie
    return req


BASE_CFG = {
    "hero_title": "Willkommen",
    "hero_text": "Frisch aus dem Ofen",
    "about_title": "Über uns",
    "about_text": "Seit 1998.",
    "cta": {
        "title": "Jetzt bestellen",
        "text": "Wir freuen uns",
        "button_label": "Los",
        "button_url": "/termin/",
    },
    "process": [
        {"title": "Wählen", "text": "Im Sortiment"},
        {"title": "Abholen", "text": "Im Laden"},
    ],
    "team": [
        {"name": "Anna", "role": "Chefin", "photo": "https://cdn.example/anna.jpg"},
        {"name": "Ben", "role": "Bäcker", "photo": "https://cdn.example/ben.jpg"},
    ],
    "testimonials": [{"name": "Eva", "text": "Super!", "stars": "5", "photo": ""}],
    "trust": {"since": "1998", "marks": ["Meisterbetrieb", "Bio"]},
    "faq": [{"q": "Parkplatz?", "a": "Ja."}],
}

I18N = {
    "ru": {
        "hero_title": "Добро пожаловать",
        "hero_text": "Прямо из печи",
        "about_title": "О нас",
        "cta": {"title": "Заказать", "text": "Ждём вас"},
        "process": [{"title": "Выбрать", "text": "В ассортименте"}, {"title": "Забрать"}],
        "team": [{"role": "Хозяйка"}, {"role": "Пекарь"}],
        "trust": {"marks": ["Мастер", "Био"]},
    },
    "en": {"hero_title": "Welcome", "about_title": "About us"},
}


def _tenant(slug, i18n=False, **cfg):
    data = {**BASE_CFG, **cfg}
    if i18n:
        data["i18n"] = json.loads(json.dumps(I18N))
    t = TenantFactory(
        slug=slug,
        name=slug.upper(),
        enabled_locales=["de", "en", "ru"],
        default_locale="de",
    )
    t.site_config = siteconfig.normalize(data)
    t.save(update_fields=["site_config"])
    return t


def _arch_fields(tenant, label="", blurb="", visible=True):
    from apps.tenants import storefront

    out = {}
    for spec in storefront.teaser_specs(tenant):
        key = spec["key"]
        out[f"arch_label_{key}"] = label
        out[f"arch_blurb_{key}"] = blurb
        if visible:
            out[f"arch_visible_{key}"] = "on"
    return out


def _form(tenant=None, **extra):
    """Полный POST текстов главной (все поля формы Студии)."""
    data = {
        "hero_title": "Willkommen",
        "hero_text": "Frisch aus dem Ofen",
        "about_title": "Über uns",
        "about_text": "Seit 1998.",
        "content_sections_present": "1",
        "cta_title": "Jetzt bestellen",
        "cta_text": "Wir freuen uns",
        "cta_button_label": "Los",
        "cta_button_url": "/termin/",
        "process_text": "Wählen | Im Sortiment\nAbholen | Im Laden",
        "team_text": "Anna | Chefin\nBen | Bäcker",
        "testimonials_text": "Eva | Super! | 5",
        "trust_since": "1998",
        "trust_marks": "Meisterbetrieb\nBio",
        "faq_present": "1",
        "faq_q_0": "Parkplatz?",
        "faq_a_0": "Ja.",
    }
    if tenant is not None:
        data.update(_arch_fields(tenant))
    data.update(extra)
    return data


def _save(tenant, data, lang_cookie=None):
    req = _req("post", "/dashboard/site/home/", data, tenant, lang_cookie=lang_cookie)
    resp = views.home_builder_view(req)
    assert resp.status_code == 302, resp.status_code
    tenant.refresh_from_db()
    return siteconfig.normalize(tenant.site_config), [str(m) for m in get_messages(req)]


def _body(tenant, lang_cookie=None):
    resp = views.home_builder_view(
        _req("get", "/dashboard/site/home/", tenant=tenant, lang_cookie=lang_cookie)
    )
    assert resp.status_code == 200
    return resp.content.decode()


def _texts(cfg) -> dict:
    keep = sorted(TEXT_KEYS | {"faq", "usp_bar"})
    out = {k: cfg.get(k) for k in keep}
    out["i18n"] = cfg.get("i18n") or {}
    return json.loads(json.dumps(out, ensure_ascii=False, sort_keys=True))


def _without_team_photo(texts: dict) -> dict:
    """A15: единственное разрешённое отличие вывода Студии — `team[*].photo`."""
    out = json.loads(json.dumps(texts))
    for m in out.get("team") or ():
        m.pop("photo", None)
    return out


# ───────────── сценарии «Студия байт-в-байт» (эталон снят на P0 `083bae3`) ─────────────


def _scenarios() -> dict:
    out = {}
    # 1) немецкий: правка всех секций, переводов нет
    t = _tenant("s15a1")
    cfg, _m = _save(
        t,
        _form(
            t,
            hero_title="Hallo",
            about_text="Seit 1999.",
            cta_title="Tisch reservieren",
            cta_button_url="https://example.com/buchen",
            process_text="Abholen | Im Laden\nWählen | Online",
            team_text="Ben | Meister\nAnna | Chefin\nCleo | Azubi",
            testimonials_text="Eva | Super! | 5\nOli | Lecker | 4",
            trust_since="2001",
            trust_marks="Bio\nHandwerk",
        ),
    )
    out["de_all_changed"] = _texts(cfg)
    # 2) немецкий, переводы есть, тексты не менялись
    t = _tenant("s15a2", i18n=True)
    cfg, _m = _save(t, _form(t))
    out["de_unchanged_with_i18n"] = _texts(cfg)
    # 3) перевод (ru): правка русских текстов
    t = _tenant("s15a3", i18n=True)
    cfg, _m = _save(
        t,
        _form(
            t,
            content_lang="ru",
            hero_title="Привет",
            hero_text="Прямо из печи",
            about_title="О нас",
            cta_title="Забронировать",
            cta_text="Ждём вас",
            process_text="Выбрать | В ассортименте\nЗабрать | Im Laden",
            team_text="Anna | Хозяйка\nBen | Пекарь",
            trust_marks="Мастер\nБио",
        ),
        lang_cookie="ru",
    )
    out["ru_translation"] = _texts(cfg)
    # 4) архетипы: подписи и видимость
    t = _tenant("s15a4")
    data = _form()
    data.update(_arch_fields(t, label="Unsere Brote", blurb="Frisch", visible=False))
    cfg, _m = _save(t, data)
    out["archetypes"] = _texts(cfg)
    return out


def test_studio_save_bytes_unchanged():
    got = _scenarios()
    if os.environ.get("S15_M5E1A_REGEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(got, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    want = json.loads(GOLDEN.read_text())
    assert set(got) == set(want)
    for name in want:
        assert _without_team_photo(got[name]) == _without_team_photo(want[name]), name


# ───────────── A14 / A1: один реестр и один писатель ─────────────


def test_content_fields_derived_from_home_texts():
    from apps.core import home_texts

    names = [n for key in home_texts.CONTENT_KEYS for n in home_texts.names(key)]
    assert tuple(siteconfig.CONTENT_FIELDS[: len(names)]) == tuple(names)
    extra = set(siteconfig.CONTENT_FIELDS) - set(names)
    assert extra == {"faq_text", "faq_present", "usp_text"}, "FAQ и полоса — не home_texts"


def test_parse_content_sections_composes_one_parser():
    import inspect

    src = inspect.getsource(siteconfig.parse_content_sections)
    assert "parse_content_section(" in src
    get = _form().get
    whole = siteconfig.parse_content_sections(get)
    for key in ("cta", "testimonials", "process", "team", "trust"):
        assert siteconfig.parse_content_section(key, get) == whole[key], key


def test_studio_names_equal_registry():
    """Имена полей Студии (`name=`) = реестр `home_texts.FIELDS` (подписи — msgid Студии)."""
    from apps.core import home_texts

    tpl = (ROOT / "templates/tenant/_section_fields.html").read_text()
    home = (ROOT / "templates/tenant/site_home.html").read_text()
    for key in home_texts.FIELDS:
        for name in home_texts.names(key):
            if key == "archetypes":
                assert f'name="{name}{{{{ a.key }}}}"' in home, name
            elif key == "hero":
                assert f'name="{name}"' in home, name
            else:
                assert f'name="{name}"' in tpl, name


def _writes(path: pathlib.Path):
    """(функция, ключ, строка) — присваивания ключей текстов главной в файле."""
    tree = ast.parse(path.read_text())
    funcs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.col_offset == 0:
            funcs.append(node)

    def owner(lineno):
        for f in funcs:
            if f.lineno <= lineno <= f.end_lineno:
                return f.name
        return "<module>"

    def is_nav(value):
        if isinstance(value, ast.Name):
            return value.id in ("nav", "_nav")
        return isinstance(value, ast.Subscript) and getattr(value.slice, "value", None) == "nav"

    for node in ast.walk(tree):
        hits = []
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if (
                    isinstance(t, ast.Subscript)
                    and isinstance(t.slice, ast.Constant)
                    and t.slice.value in TEXT_KEYS
                    and not is_nav(t.value)
                ):
                    hits.append(t.slice.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("update", "setdefault") and not is_nav(node.func.value):
                for a in node.args:
                    if isinstance(a, ast.Dict):
                        hits += [
                            k.value
                            for k in a.keys
                            if isinstance(k, ast.Constant) and k.value in TEXT_KEYS
                        ]
                    if (
                        node.func.attr == "setdefault"
                        and isinstance(a, ast.Constant)
                        and a.value in TEXT_KEYS
                    ):
                        hits.append(a.value)
                hits += [k.arg for k in node.keywords if k.arg in TEXT_KEYS]
            if node.func.attr == "parse_content_section":
                hits.append("parse_content_section()")
        for key in hits:
            yield owner(node.lineno), key, node.lineno


def test_home_texts_writers_ast():
    bad = []
    for path in sorted((ROOT / "apps").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if "/tests/" in rel or "/migrations/" in rel:
            continue
        allowed = WRITER_EXCEPTIONS.get(rel, set())
        for func, key, line in _writes(path):
            if allowed is None or func in allowed:
                continue
            bad.append(f"{rel}:{line} {func} → {key}")
    assert not bad, "тексты главной пишет только home_texts:\n" + "\n".join(bad)


def test_one_writer_studio(monkeypatch):
    from apps.core import home_texts

    seen = []
    real = home_texts.put

    def spy(config, key, get, **kw):
        seen.append(key)
        return real(config, key, get, **kw)

    monkeypatch.setattr(home_texts, "put", spy)
    t = _tenant("s15w1")
    _save(t, _form(t))
    assert set(seen) >= {"hero", "about", "cta", "process", "team", "testimonials", "trust"}
    assert "archetypes" in seen


def test_one_writer_preview_draft(monkeypatch):
    from apps.core import home_texts

    seen = []
    real = home_texts.put

    def spy(config, key, get, **kw):
        seen.append(key)
        return real(config, key, get, **kw)

    monkeypatch.setattr(home_texts, "put", spy)
    t = _tenant("s15w2")
    req = _req(
        "post",
        "/dashboard/site/preview-draft/",
        tenant=t,
        body={"hero_title": "Neu", "about_text": "Text", "cta_title": "Komm"},
    )
    views.site_preview_draft(req)
    assert {"hero", "about", "cta"} <= set(seen)
    draft = req.session["site_preview_draft"]
    assert draft["hero_title"] == "Neu" and draft["cta"]["title"] == "Komm"
    assert draft["team"][0]["photo"] == "https://cdn.example/anna.jpg", "черновик не стирает фото"


def test_one_writer_inline_edit(monkeypatch):
    from apps.core import home_texts

    seen = []
    real = home_texts.set_text

    def spy(config, key, name, value, locale=""):
        seen.append((key, name, locale))
        return real(config, key, name, value, locale)

    monkeypatch.setattr(home_texts, "set_text", spy)
    t = _tenant("s15w3", i18n=True)
    for field, value in (("hero_title", "Servus"), ("cta.title", "Komm vorbei")):
        req = _req(
            "post", "/dashboard/site/inline-edit/", tenant=t, body={"field": field, "value": value}
        )
        assert views.site_inline_edit(req).status_code == 204
    req = _req(
        "post",
        "/dashboard/site/inline-edit/",
        tenant=t,
        body={"field": "about_title", "value": "Про нас", "locale": "ru"},
    )
    assert views.site_inline_edit(req).status_code == 204
    assert seen == [
        ("hero", "hero_title", ""),
        ("cta", "cta_title", ""),
        ("about", "about_title", "ru"),
    ]
    t.refresh_from_db()
    cfg = siteconfig.normalize(t.site_config)
    assert cfg["hero_title"] == "Servus" and cfg["cta"]["title"] == "Komm vorbei"
    assert "hero_title" not in cfg["i18n"]["ru"], "правка немецкого снимает перевод поля"
    assert cfg["i18n"]["ru"]["hero_text"] == "Прямо из печи", "чужое поле не тронуто"
    assert cfg["i18n"]["ru"]["about_title"] == "Про нас"
    assert cfg["about_title"] == "Über uns"


def test_one_writer_wizard(monkeypatch):
    from apps.core import home_texts, setup_steps

    seen = []
    real = home_texts.set_text

    def spy(config, key, name, value, locale=""):
        seen.append((key, name))
        return real(config, key, name, value, locale)

    monkeypatch.setattr(home_texts, "set_text", spy)
    t = _tenant("s15w4")
    req = _req("post", "/setup/", {"hero_title": "Hallo", "hero_text": "Brot"}, tenant=t)
    setup_steps.save_hero(req, t)
    req = _req("post", "/setup/", {"about_title": "Wir", "about_text": "Seit immer"}, tenant=t)
    setup_steps._post_about(req)
    assert ("hero", "hero_title") in seen and ("hero", "hero_text") in seen
    assert ("about", "about_title") in seen and ("about", "about_text") in seen


# ───────────── A15, realign, старые форматы ─────────────


def test_studio_keeps_team_photo():
    t = _tenant("s15p1")
    cfg, _m = _save(t, _form(t, team_text="Ben | Meister\nAnna | Chefin\nCleo | Azubi"))
    photos = {m["name"]: m.get("photo", "") for m in cfg["team"]}
    assert photos == {
        "Ben": "https://cdn.example/ben.jpg",
        "Anna": "https://cdn.example/anna.jpg",
        "Cleo": "",
    }, "фото едет за именем и после перестановки"


def test_list_overlays_realigned():
    """Охранный: удаление шага в немецком — русский перевод остаётся у своего шага."""
    t = _tenant("s15r1", i18n=True)
    cfg, _m = _save(t, _form(t, process_text="Abholen | Im Laden"))
    assert cfg["process"] == [{"title": "Abholen", "text": "Im Laden"}]
    assert cfg["i18n"]["ru"]["process"] == [{"title": "Забрать"}]


@pytest.mark.parametrize(
    "stored",
    [
        {"team": [{"name": "Anna"}, "мусор", {"role": "без имени"}]},
        {"trust": "seit 1998"},
        {"archetypes": {"fremd": {"label": "Alt", "blurb": "X", "hidden": True}}},
        {"cta": "Jetzt", "process": "kein Liste"},
    ],
    ids=["team_without_role", "trust_not_dict", "archetypes_foreign", "cta_not_dict"],
)
def test_old_formats(stored):
    from apps.core import home_texts

    cfg = {**BASE_CFG, **stored}
    for key in home_texts.FIELDS:
        home_texts.put(cfg, key, _form().get, tenant=None)
        home_texts.fingerprint(cfg, key)
    assert cfg["cta"]["title"] == "Jetzt bestellen"
    if "archetypes" in stored:
        assert cfg["archetypes"]["fremd"] == {"label": "Alt", "blurb": "X", "hidden": True}


# ───────────── A4 (Студия), A2: переводы ─────────────


def test_german_edit_drops_translation():
    t = _tenant("s15g1", i18n=True)
    cfg, _m = _save(
        t,
        _form(
            t,
            hero_title="Hallo",
            cta_title="Tisch reservieren",
            process_text="Wählen | Online\nAbholen | Im Laden",
            trust_marks="Meisterbetrieb\nBio\nRegional",
        ),
    )
    ru = cfg["i18n"]["ru"]
    assert "hero_title" not in ru and ru["hero_text"] == "Прямо из печи", "только это поле"
    assert ru["about_title"] == "О нас"
    assert "title" not in ru["cta"] and ru["cta"]["text"] == "Ждём вас"
    assert ru["process"][0] == {"title": "Выбрать"}, "у шага снят перевод изменённого текста"
    assert ru["process"][1] == {"title": "Забрать"}
    assert "marks" not in ru.get("trust", {})
    assert "hero_title" not in cfg["i18n"]["en"], "снимается у всех языков"
    assert cfg["i18n"]["en"]["about_title"] == "About us"


def test_translation_mode_writes_only_its_language():
    """A2/A4 охранный: правка в ru пишет только ru; база и en не тронуты."""
    t = _tenant("s15g2", i18n=True)
    cfg, _m = _save(
        t,
        _form(
            t,
            content_lang="ru",
            hero_title="Привет",
            hero_text="Прямо из печи",
            about_title="О нас",
            cta_title="Заказать",
            cta_text="Ждём вас",
            process_text="Выбрать | В ассортименте\nЗабрать | Im Laden",
            team_text="Anna | Хозяйка\nBen | Пекарь",
            trust_marks="Мастер\nБио",
        ),
        lang_cookie="ru",
    )
    assert cfg["hero_title"] == "Willkommen" and cfg["cta"]["title"] == "Jetzt bestellen"
    assert cfg["i18n"]["ru"]["hero_title"] == "Привет"
    assert cfg["i18n"]["en"] == {"hero_title": "Welcome", "about_title": "About us"}
    assert [p["title"] for p in cfg["process"]] == ["Wählen", "Abholen"]


def test_studio_ru_save_keeps_other_locales():
    """A2: сохранение перевода не выравнивает и не снимает переводы прочих языков."""
    t = _tenant("s15g3", i18n=True)
    before = siteconfig.normalize(t.site_config)["i18n"]["en"]
    cfg, _m = _save(t, _form(t, content_lang="ru", hero_title="Привет"), lang_cookie="ru")
    assert cfg["i18n"]["en"] == before
    assert cfg["hero_title"] == "Willkommen"


# ───────────── A3: устаревшая вкладка ─────────────


def _htx_base(body, key):
    m = re.search(rf'name="htx_base_{key}" value="([0-9a-f]+)"', body)
    return m.group(1) if m else ""


def test_stale_studio_tab_does_not_revert_window_texts():
    t = _tenant("s15s1")
    body = _body(t)
    base_about = _htx_base(body, "about")
    base_cta = _htx_base(body, "cta")
    assert base_about and base_cta
    # тем временем окно блока сохранило новые тексты «Über uns»
    cfg = siteconfig.normalize(t.site_config)
    cfg["about_title"] = "Wer wir sind"
    t.site_config = cfg
    t.save(update_fields=["site_config"])
    t.refresh_from_db()
    cfg, _m = _save(
        t,
        _form(t, htx_base_about=base_about, htx_base_cta=base_cta, cta_title="Neu bestellen"),
    )
    assert cfg["about_title"] == "Wer wir sind", "устаревшая вкладка не вернула старый текст"
    assert cfg["cta"]["title"] == "Neu bestellen", "секция без расхождения записана"


def test_archetypes_absent_keys_untouched():
    from apps.tenants import storefront

    t = _tenant("s15s2")
    keys = [s["key"] for s in storefront.teaser_specs(t)]
    assert keys, "у тенанта нужны тизеры"
    cfg = siteconfig.normalize(t.site_config)
    cfg["archetypes"] = {k: {"label": "Alt", "blurb": "Alt-Text", "hidden": True} for k in keys}
    t.site_config = cfg
    t.save(update_fields=["site_config"])
    t.refresh_from_db()
    cfg, _m = _save(t, _form())  # без полей arch_* (форма без строки «Unser Angebot»)
    for k in keys:
        assert cfg["archetypes"][k]["label"] == "Alt"
        assert cfg["archetypes"][k]["blurb"] == "Alt-Text"
        assert cfg["archetypes"][k]["hidden"] is True


@pytest.mark.xfail(
    strict=True,
    reason="нужен msgid заметки «Texte … inzwischen an anderer Stelle geändert» (не в P0)",
)
def test_stale_studio_tab_note():
    t = _tenant("s15s3")
    base = _htx_base(_body(t), "about")
    cfg = siteconfig.normalize(t.site_config)
    cfg["about_title"] = "Wer wir sind"
    t.site_config = cfg
    t.save(update_fields=["site_config"])
    t.refresh_from_db()
    _cfg, msgs = _save(t, _form(t, htx_base_about=base, about_title="Meins"))
    assert any("inzwischen" in m and "Über uns" in m for m in msgs)


# ───────────── §9 №4: потолки и ссылка кнопки ─────────────


def test_caps_server():
    from apps.core import home_texts

    assert (home_texts.TITLE_MAX, home_texts.TEXT_MAX, home_texts.LIST_MAX) == (120, 2000, 4000)
    t = _tenant("s15c1")
    cfg, msgs = _save(t, _form(t, hero_title="H" * 200, about_text="A" * 2500))
    assert cfg["hero_title"] == "H" * 120 and cfg["about_text"] == "A" * 2000
    assert siteconfig.cap_note() in msgs
    # неизменённое старое длинное значение не режется
    cfg, msgs = _save(t, _form(t, hero_title="H" * 120, about_text="A" * 2000))
    stored = siteconfig.normalize(t.site_config)
    stored["hero_title"] = "L" * 300
    t.site_config = stored
    t.save(update_fields=["site_config"])
    t.refresh_from_db()
    cfg, msgs = _save(t, _form(t, hero_title="L" * 300))
    assert cfg["hero_title"] == "L" * 300
    assert siteconfig.cap_note() not in msgs


@pytest.mark.parametrize("url", ["javascript:alert(1)", "//evil.example", "data:text/html,x"])
def test_cta_url_rejects_javascript(url):
    t = _tenant("s15u1")
    cfg, msgs = _save(t, _form(t, cta_button_url=url))
    assert cfg["cta"]["button_url"] == "/termin/", "небезопасная ссылка не записана"
    assert any("https://" in m for m in msgs)


# ───────────── ревью круга 1 (django-reviewer, security-reviewer, silent-failure-hunter) ─────────────

R1 = "ревью M5e-1a круг 1"


def _stale_note(name):
    from django.utils.translation import gettext

    return gettext(
        "Die Texte von „%(name)s“ wurden inzwischen an anderer Stelle geändert – Ihre Änderung "
        "daran wurde nicht übernommen."
    ) % {"name": name}


def _store(t, **changes):
    cfg = siteconfig.normalize(t.site_config)
    cfg.update(changes)
    t.site_config = cfg
    t.save(update_fields=["site_config"])
    t.refresh_from_db()


@pytest.mark.xfail(strict=True, reason=f"{R1}: №1 пропуск секции не виден")
def test_two_stale_sections_noted_each():
    t = _tenant("s15r1a")
    body = _body(t)
    bases = {k: _htx_base(body, k) for k in ("about", "cta", "hero")}
    _store(t, about_title="Wer wir sind", cta={**BASE_CFG["cta"], "title": "Anders"})
    cfg, msgs = _save(
        t, _form(t, **{f"htx_base_{k}": v for k, v in bases.items()}, hero_title="Neu")
    )
    assert cfg["about_title"] == "Wer wir sind" and cfg["cta"]["title"] == "Anders"
    assert cfg["hero_title"] == "Neu"
    assert _stale_note("Über uns") in msgs
    assert sum(m.startswith("Die Texte von") for m in msgs) == 2


@pytest.mark.xfail(strict=True, reason=f"{R1}: №1 put_form не возвращает пропущенные")
def test_put_form_returns_skipped():
    from apps.core import home_texts

    stored = siteconfig.normalize(BASE_CFG)
    cfg = siteconfig.normalize(BASE_CFG)
    stale, _written = home_texts.put_form(
        cfg,
        {"about_title": "X", "htx_base_about": "0" * 16}.get,
        ("about",),
        stored=stored,
    )
    assert stale == ["about"] and cfg["about_title"] == "Über uns"


@pytest.mark.xfail(strict=True, reason=f"{R1}: №2 CRLF считается правкой")
def test_crlf_unchanged_keeps_translation_and_legacy_length():
    t = _tenant("s15r2a", i18n=True)
    legacy = "Zeile\n" + "x" * 2500
    _store(t, about_text=legacy)
    cfg = siteconfig.normalize(t.site_config)
    cfg["i18n"]["ru"]["about_text"] = "Строка"
    t.site_config = cfg
    t.save(update_fields=["site_config"])
    t.refresh_from_db()
    cfg, msgs = _save(t, _form(t, about_text=legacy.replace("\n", "\r\n")))
    assert cfg["about_text"] == legacy, "старое длинное не режется"
    assert cfg["i18n"]["ru"]["about_text"] == "Строка", "перевод не снят"
    assert siteconfig.cap_note() not in msgs
    cfg, _m = _save(t, _form(t, about_text="Eins\r\nZwei\rDrei"))
    assert cfg["about_text"] == "Eins\nZwei\nDrei"


@pytest.mark.xfail(strict=True, reason=f"{R1}: №3 _menu_href пропускает \\ и пробелы")
@pytest.mark.parametrize(
    "url", ["/\\evil.example", "/a\\b", "/a\tb", "https://x.de/\nY", "/a b", "/a\x00"]
)
def test_home_texts_cta_url_rejects_backslash_and_tab(url):
    from apps.core import home_texts

    cfg = siteconfig.normalize(BASE_CFG)
    notes = []
    home_texts.put(cfg, "cta", {"cta_button_url": url}.get, notes=notes)
    assert cfg["cta"]["button_url"] == "/termin/"
    assert notes


@pytest.mark.xfail(strict=True, reason=f"{R1}: №3 _menu_href пропускает \\ и пробелы")
def test_menu_item_rejects_backslash_and_tab():
    for bad in ("/\\evil.example", "/a\tb", "https:/\\x"):
        node = siteconfig._clean_menu_node({"label": "X", "type": "url", "target": bad}, 0)
        assert node is None or node["target"] == "", bad
    for good in ("/sortiment/", "#kontakt", "https://x.de/a?b=1", "mailto:a@b.de", "tel:+49"):
        assert (
            siteconfig._clean_menu_node({"label": "X", "type": "url", "target": good}, 0)["target"]
            == good
        )


@pytest.mark.xfail(strict=True, reason=f"{R1}: №3 normalize хранит javascript: в cta")
def test_stored_javascript_cta_not_rendered():
    from django.template.loader import render_to_string

    site = siteconfig.normalize(
        {"cta": {"title": "T", "button_label": "Los", "button_url": "javascript:alert(1)"}}
    )
    assert site["cta"]["button_url"] == ""
    html = render_to_string("storefront/sections/_cta.html", {"site": site, "section_row": {}})
    assert "javascript:" not in html


def _inline(t, body):
    req = _req("post", "/dashboard/site/inline-edit/", tenant=t, body=body)
    return views.site_inline_edit(req)


@pytest.mark.xfail(strict=True, reason=f"{R1}: №4 канва молча режет текст")
def test_inline_capped_answers_with_stored_value():
    from apps.core import home_texts

    t = _tenant("s15r4a")
    resp = _inline(t, {"field": "about_text", "value": "A" * (home_texts.TEXT_MAX + 1)})
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["capped"] is True and data["value"] == "A" * home_texts.TEXT_MAX
    t.refresh_from_db()
    assert t.site_config["about_text"] == "A" * home_texts.TEXT_MAX


@pytest.mark.xfail(strict=True, reason=f"{R1}: №4 set_text не сообщает результат")
def test_set_text_results():
    from apps.core import home_texts

    cfg = siteconfig.normalize(BASE_CFG)
    assert home_texts.set_text(cfg, "cta", "cta_button_url", "javascript:x") == home_texts.REJECTED
    assert cfg["cta"]["button_url"] == "/termin/"
    assert home_texts.set_text(cfg, "cta", "cta_button_url", "javascript:x", "ru") == (
        home_texts.REJECTED
    )
    assert "cta" not in (cfg.get("i18n") or {}).get("ru", {})
    assert home_texts.set_text(cfg, "hero", "hero_title", "Willkommen") == home_texts.UNCHANGED
    assert home_texts.set_text(cfg, "hero", "hero_title", "Neu") == home_texts.CHANGED
    assert home_texts.set_text(cfg, "hero", "hero_title", "H" * 121) == home_texts.CAPPED


@pytest.mark.xfail(strict=True, reason=f"{R1}: №4/№6 канва: неверный ввод не отвергается")
def test_inline_rejects_unsafe_and_non_str():
    t = _tenant("s15r4b")
    assert _inline(t, {"field": "about_title", "value": 5}).status_code == 400
    from apps.core import home_texts

    real = home_texts.set_text
    try:
        home_texts.set_text = lambda *a, **k: home_texts.REJECTED
        assert _inline(t, {"field": "cta.title", "value": "x"}).status_code == 422
    finally:
        home_texts.set_text = real


@pytest.mark.xfail(strict=True, reason=f"{R1}: №4 мастер молча режет текст")
def test_wizard_capped_warns():
    from apps.core import home_texts, setup_steps

    t = _tenant("s15r4c")
    req = _req("post", "/setup/", {"hero_title": "H" * 300, "hero_text": "B"}, tenant=t)
    setup_steps.save_hero(req, t)
    assert t.site_config["hero_title"] == "H" * home_texts.TITLE_MAX
    assert siteconfig.cap_note() in [str(m) for m in get_messages(req)]


@pytest.mark.xfail(strict=True, reason=f"{R1}: №5 сверка отпечатка вне блокировки")
def test_fingerprint_checked_under_lock(monkeypatch):
    """Окно блока записало тексты ПОСЛЕ начала запроса Студии — сверка под блокировкой."""
    from apps.core import home_texts

    t = _tenant("s15r5a")
    base = _htx_base(_body(t), "about")
    real = home_texts.put_form
    tenant_pk = t.pk

    def racing(*a, **kw):
        out = real(*a, **kw)
        from apps.tenants.models import Tenant

        row = Tenant.objects.get(pk=tenant_pk)
        cfg = siteconfig.normalize(row.site_config)
        cfg["about_title"] = "Vom Fenster"
        Tenant.objects.filter(pk=tenant_pk).update(site_config=cfg)
        return out

    monkeypatch.setattr(home_texts, "put_form", racing)
    cfg, msgs = _save(t, _form(t, htx_base_about=base, about_title="Aus Studio"))
    assert cfg["about_title"] == "Vom Fenster"
    assert _stale_note("Über uns") in msgs


@pytest.mark.xfail(strict=True, reason=f"{R1}: №5 сентинел htx_base_present")
def test_missing_fingerprint_stale_only_with_sentinel():
    t = _tenant("s15r5b")
    body = _body(t)
    assert 'name="htx_base_present"' in body
    cfg, _m = _save(t, _form(t, about_title="Alte Vorlage"))  # открыта до деплоя: пишет
    assert cfg["about_title"] == "Alte Vorlage"
    cfg, msgs = _save(t, _form(t, htx_base_present="1", about_title="Ohne Abdruck"))
    assert cfg["about_title"] == "Alte Vorlage"
    assert _stale_note("Über uns") in msgs


@pytest.mark.xfail(strict=True, reason=f"{R1}: №6 исключение не перечислено")
def test_sitetemplates_listed_in_writer_exceptions():
    """№6: писатель шаблонов витрины с переменным ключом — исключение явно, с причиной."""
    assert WRITER_EXCEPTIONS.get("apps/tenants/sitetemplates.py") == {"_apply"}
