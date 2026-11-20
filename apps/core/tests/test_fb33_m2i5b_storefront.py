"""FB-33 M2i-5b C2: витрина показывает переводы полей формы заявки по ключу.

`/anfrage/`, модалка и полоса главной на русском берут перевод подписи поля, своего вопроса и
варианта; value варианта (выбор события и свой выбор) — всегда на основном языке, снимок ответа
заявки — тоже (решение владельца 3: переводится показ, а не запись). На немецком — байт-в-байт
(замки `test_fb33_m2i5b_before`, `test_fb33_m2i5_before`).
"""

import copy

import pytest
from django.contrib.messages import get_messages
from django.utils import translation

from apps.core.tests.test_fb33_m2i5_before import CUSTOM
from apps.core.tests.test_fb33_m2i5b_before import anfrage_html, band_cfg, band_html, modal_html
from apps.core.tests.test_fb33_m2i_before import _anfrage_request
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

TR = copy.deepcopy(CUSTOM)
TR["form_fields"]["anfrage"].update(
    labels_i18n={"phone": {"ru": "Мобильный"}, "guest_count": {"ru": "Сколько гостей"}},
    event_types_i18n={"Hochzeit": {"ru": "Свадьба"}},
)
TR["form_fields"]["anfrage"]["custom"][0]["label_i18n"] = {"ru": "Бюджет"}
TR["form_fields"]["anfrage"]["custom"][1].update(
    label_i18n={"ru": "Зал"}, options_i18n={"Garten": {"ru": "Сад"}}
)
# старый позиционный оверлей поверх ключевого: ключевой главнее, пропуск — из старого
TR["i18n"] = {"ru": {"anfrage": {"event_types": ["Венчание", "Корпоратив"]}}}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_anfrage_page_in_ru_shows_translations_with_main_values():
    with translation.override("ru"):
        html = anfrage_html(TR)
    assert ">Мобильный<" in html and ">Сколько гостей<" in html
    assert ">Wann?<" in html  # своя немецкая подпись без перевода — немецкая
    assert ">Бюджет<" in html and ">Зал<" in html and "> Vegan?<" in html
    assert '<option value="Saal" lang="de">Saal</option><option value="Garten">Сад</option>' in html
    assert '<option value="Hochzeit">Свадьба</option>' in html
    assert '<option value="Firmenfeier">Корпоратив</option>' in html


def test_modal_and_band_in_ru():
    with translation.override("ru"):
        modal = modal_html(TR)
        band = band_html(band_cfg(TR))
    assert ">Мобильный<" in modal and '<option value="Hochzeit">Свадьба</option>' in modal
    assert '<option value="Hochzeit">Свадьба</option>' in band
    assert "Мобильный *" in band  # обязательный телефон полоса дорисовывает своей подписью
    assert "Бюджет" not in band  # необязательный свой вопрос полоса не рисует


@pytest.mark.parametrize("cfg", [CUSTOM, TR], ids=["plain", "translated"])
def test_german_is_unchanged_by_translations(cfg):
    with translation.override("de"):
        assert anfrage_html(cfg) == anfrage_html(CUSTOM)
        assert modal_html(cfg) == modal_html(CUSTOM)


def test_localized_site_keeps_main_language_variants():
    """Замок для каждого читателя локализованного `site.anfrage` (полоса главной, siteui,
    страницы): значения вариантов — на основном языке, перевод — только у показа."""
    site = siteconfig.normalize(copy.deepcopy(TR))
    for loc in ("ru", "en", "de"):
        assert siteconfig.localize(site, loc)["anfrage"] == site["anfrage"]


def test_answer_snapshot_and_event_type_stay_on_main_language():
    from apps.jobs import public_views
    from apps.jobs.models import Job

    data = {"title": "Fest", "name": "A", "phone": "1", "guest_count": "5", "q2": "Garten"}
    data["event_type"] = "Hochzeit"
    with translation.override("ru"):
        resp = public_views.anfrage(_anfrage_request(data, copy.deepcopy(TR)))
    assert resp.status_code == 302
    job = Job.objects.get()
    assert job.event_type == "Hochzeit"
    assert job.custom_answers["q2"] == {"label": "Raum", "value": "Garten", "type": "choice"}


def test_translated_variant_is_refused_as_value():
    from apps.jobs import public_views
    from apps.jobs.models import Job

    data = {"title": "Fest", "name": "A", "phone": "1", "guest_count": "5", "q2": "Сад"}
    with translation.override("ru"):
        req = _anfrage_request(data, copy.deepcopy(TR))
        public_views.anfrage(req)
        said = [str(m) for m in get_messages(req)]
    assert not Job.objects.exists()
    assert any("Зал" in m for m in said)  # сообщение — подписью языка показа
