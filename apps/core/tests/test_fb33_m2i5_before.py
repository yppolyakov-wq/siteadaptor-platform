"""FB-33 M2i-5 C0: замки ДО вкладки «Felder» (план — `docs/fb33-editor-model-2026-11-19.md`
§«План M2i-5»).

* форма `/anfrage/` и модалка — байт-в-байт для трёх конфигов (пустой, прежний
  `anfrage.fields`, свои режимы + подписи + три своих вопроса): вкладка пишет те же ключи, а
  витрина читает их прежним путём (превью черновика — только через `raw_config`);
* старый POST `jobs:anfrage-form-settings` (осознанный второй путь под `ablaeufe.edit`) пишет
  тот же `site_config`, что и до среза;
* `site_config["form_fields"]` пишут только `form_spec` (и нормализатор `siteconfig`).

Окно других блоков — прежние замки `test_fb33_m3_window_before` и `test_fb33_m3_2_nojs`.
Обновить (осознанно): FB33M2I5_GOLDEN=update uv run pytest <этот файл>
"""

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.utils import translation

from apps.core.tests import test_fb31p5_detail_golden as _p5

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb33m2i5"
UPDATE = os.environ.get("FB33M2I5_GOLDEN") == "update"
frozen_now = _p5.frozen_now

CUSTOM = {
    "anfrage": {
        "fields": ["date", "guests", "event_type"],
        "event_types": ["Hochzeit", "Firmenfeier"],
    },
    "form_fields": {
        "anfrage": {
            "mode": {"phone": "req", "description": "off", "guest_count": "req"},
            "labels": {"phone": "Handy", "event_date": "Wann?"},
            "custom": [
                {"id": "q1", "type": "text", "label": "Budget"},
                {
                    "id": "q2",
                    "type": "choice",
                    "label": "Raum",
                    "options": ["Saal", "Garten"],
                    "mode": "req",
                },
                {"id": "q4", "type": "bool", "label": "Vegan?"},
            ],
            "next_id": 5,
        }
    },
}
CONFIGS = {
    "empty": {},
    "legacy": {"anfrage": {"fields": ["date", "guests"]}},
    "custom": CUSTOM,
}


@pytest.fixture(autouse=True)
def _urlconf(settings, frozen_now):
    settings.ROOT_URLCONF = "config.urls_tenant"


def check(name, got, ext="html"):
    path = GOLDEN / f"{name}.{ext}"
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {path.name}: FB33M2I5_GOLDEN=update")
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(got)
        return
    assert got == path.read_text(), f"изменилось: {path.name}"


def anfrage_html(cfg, query=""):
    from apps.jobs import public_views

    return _p5._normalize(public_views.anfrage(_p5._req("/anfrage/" + query, cfg)).content.decode())


def modal_html(cfg):
    from apps.jobs import public_views

    return _p5._normalize(
        public_views.anfrage_modal(_p5._req("/anfrage/modal/", cfg)).content.decode()
    )


@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_anfrage_and_modal_before(name):
    with translation.override("de"):
        check(f"anfrage-{name}", anfrage_html(CONFIGS[name]))
        check(f"modal-{name}", modal_html(CONFIGS[name]))


def test_anfrage_custom_before_ru():
    with translation.override("ru"):
        check("anfrage-custom-ru", anfrage_html(CUSTOM))


# --- старый POST «Anfrage-Formular» (второй путь, `ablaeufe.edit`) -------------------------

OLD_POSTS = {
    "check-date-type": (CUSTOM, {"af_date": "on", "af_event_type": "on", "af_event_types": "A\nB"}),
    "uncheck-all": ({"anfrage": {"fields": ["date", "guests"]}}, {}),
    "guests-on-empty": ({}, {"af_guests": "on"}),
}


def _old_post(cfg, data, business_type="cafe"):
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.jobs import views
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(business_type=business_type, site_config=json.loads(json.dumps(cfg)))
    req = RequestFactory().post("/dashboard/jobs/anfrage-form/", data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    resp = views.anfrage_form_settings(req)
    tenant.refresh_from_db()
    return resp, tenant.site_config


@pytest.mark.parametrize("name", sorted(OLD_POSTS))
def test_old_panel_post_writes_as_before(name):
    cfg, data = OLD_POSTS[name]
    resp, stored = _old_post(cfg, data)
    assert resp.status_code == 302
    check(f"oldpost-{name}", json.dumps(stored, sort_keys=True, indent=1) + "\n", "json")


def test_old_panel_preset_writes_as_before():
    resp, stored = _old_post(CUSTOM, {"load_preset": "1"}, business_type="catering")
    assert resp.status_code == 302
    check("oldpost-preset", json.dumps(stored, sort_keys=True, indent=1) + "\n", "json")


# --- один писатель `form_fields` ------------------------------------------------------------

#: кто вправе писать ключ: ядро «Поля форм» и нормализатор сайта
WRITERS = {"apps/core/form_spec.py", "apps/tenants/siteconfig.py"}
_WRITE = re.compile(
    r"""\[\s*["']form_fields["']\s*\]\s*=(?!=)"""
    r"""|\.(?:pop|setdefault|update)\(\s*["']form_fields["']"""
    r"""|\.update\(\s*\{\s*["']form_fields["']"""
)


def test_form_fields_has_one_writer():
    root = Path(__file__).resolve().parents[3]
    found = []
    for path in (root / "apps").rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if "/tests/" in rel or "/migrations/" in rel or rel in WRITERS:
            continue
        if _WRITE.search(path.read_text()):
            found.append(rel)
    assert found == [], f"site_config['form_fields'] пишет не form_spec: {found}"
