"""FB-33 M2i-5b C0: замки ДО переводов полей формы заявки по id (план — scratchpad
`m2i5b-plan.md`, `docs/fb33-editor-model-2026-11-19.md` §«План M2i-5»).

* немецкая витрина без переводов — байт-в-байт (`/anfrage/`, полоса главной, модалка): ключи
  переводов читаются только на другом языке;
* ru с ПОЗИЦИОННЫМ оверлеем вариантов «Art der Veranstaltung» (`i18n.ru.anfrage.event_types`,
  так пишет демо до среза) — те же подписи (запасное чтение и перенос `form_i18n_realign`);
* ru со своей немецкой подписью без перевода — немецкая подпись (решение владельца 2);
* окно «Felder» у бизнеса с одним языком — байт-в-байт (ни кнопок языка, ни полей перевода).

Обновить (осознанно): FB33M2I5B_GOLDEN=update uv run pytest <этот файл>
"""

import copy
import os
import re
from pathlib import Path

import pytest
from django.utils import translation

from apps.core.tests import test_fb31p5_detail_golden as _p5
from apps.core.tests.test_fb33_m2i5_before import CUSTOM

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb33m2i5b"
UPDATE = os.environ.get("FB33M2I5B_GOLDEN") == "update"
frozen_now = _p5.frozen_now

#: CUSTOM + позиционный перевод вариантов события (как пишет демо-сидер до среза)
POSITIONAL = copy.deepcopy(CUSTOM)
POSITIONAL["i18n"] = {"ru": {"anfrage": {"event_types": ["Свадьба", "Корпоратив"]}}}
CONFIGS = {"custom": CUSTOM, "positional": POSITIONAL}


@pytest.fixture(autouse=True)
def _urlconf(settings, frozen_now):
    settings.ROOT_URLCONF = "config.urls_tenant"


def check(name, got, ext="html"):
    path = GOLDEN / f"{name}.{ext}"
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {path.name}: FB33M2I5B_GOLDEN=update")
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(got)
        return
    assert got == path.read_text(), f"изменилось: {path.name}"


def anfrage_html(cfg):
    from apps.jobs import public_views

    return _p5._normalize(public_views.anfrage(_p5._req("/anfrage/", cfg)).content.decode())


def modal_html(cfg):
    from apps.jobs import public_views

    return _p5._normalize(
        public_views.anfrage_modal(_p5._req("/anfrage/modal/", cfg)).content.decode()
    )


def band_html(cfg):
    from django.template import Context, Template

    from apps.tenants import siteconfig

    tpl = Template('{% include "storefront/sections/_anfrage.html" %}')
    ctx = Context(
        {
            "request": _p5._req("/", cfg),
            "site": siteconfig.localize(siteconfig.normalize(cfg), translation.get_language()),
            "storefront_jobs_enabled": True,
            "section_row": {"style": "band"},
        }
    )
    return _p5._normalize(tpl.render(ctx))


def band_cfg(cfg):
    """Полоса рисует выбор события только без «полной» формы: без своего выбора-вопроса."""
    out = copy.deepcopy(cfg)
    out["form_fields"]["anfrage"]["custom"] = [
        q for q in out["form_fields"]["anfrage"]["custom"] if q["type"] != "choice"
    ]
    return out


@pytest.mark.parametrize("lang", ["de", "ru"])
@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_storefront_forms_before(name, lang):
    cfg = CONFIGS[name]
    with translation.override(lang):
        check(f"anfrage-{name}-{lang}", anfrage_html(cfg))
        check(f"modal-{name}-{lang}", modal_html(cfg))
        check(f"band-{name}-{lang}", band_html(band_cfg(cfg)))


def test_positional_overlay_shows_translated_options_in_ru():
    with translation.override("ru"):
        html = anfrage_html(POSITIONAL)
    assert '<option value="Hochzeit">Свадьба</option>' in html
    assert '<option value="Firmenfeier">Корпоратив</option>' in html


def test_own_german_label_without_translation_stays_german_in_ru():
    with translation.override("ru"):
        html = anfrage_html(CUSTOM)
    assert ">Handy<" in html and ">Wann?<" in html  # свои подписи владельца
    assert ">Budget<" in html and ">Raum<" in html  # свои вопросы


def _window_part(cfg):
    from apps.core.tests.test_fb27_r2_draft import Browser
    from apps.core.tests.test_fb33_m2i5_draft import _tenant

    b = Browser(_tenant(cfg))
    with translation.override("de"):
        html = b.get("?seite=anfrage&block=form&tab=felder")
    start = html.index("data-form-felder")
    part = _p5._normalize(html[start : html.index("</form>", start)])
    return re.sub(r'(name="wopen" value=")[^"]*', r"\1X", part)  # токен открытия окна


def test_window_single_language_before():
    check("window-single-language", _window_part(CUSTOM))
