"""STU-15a: у страницы акции есть свой шаблон — «только эта акция» бьёт дефолт сайта.

До этой волны шаблон страницы был у товара, категории, группы акций и обзора акций,
а у детали одной акции — нет ни одного. Разметка детали одна на все шаблоны (паритет
DL-16.3/UE-волн цел), различие несёт `data-promo-detail` на корне + каскад в app.css:
поэтому замки проверяют именно атрибут.
"""

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions import public_views
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db


def _render(promo, site_config=None):
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = AnonymousUser()
    req.tenant = SimpleNamespace(name="Demo", site_config=site_config or {})
    return public_views.promotion_detail(req, pk=promo.pk).content.decode()


def test_default_page_is_unchanged():
    """Ничего не настроено → атрибута нет вовсе: страница байт-в-байт прежняя."""
    html = _render(PromotionFactory(status="active"))
    assert "data-promo-detail" not in html


def test_site_default_applies_to_every_offer():
    html = _render(
        PromotionFactory(status="active"),
        {"site_defaults": {"promo_detail_style": "plakat"}},
    )
    assert 'data-promo-detail="plakat"' in html


def test_own_style_beats_the_site_default():
    """«Только эта акция» — ради этого поле и заводилось (длинный рассказ у одной,
    короткий флаер у другой)."""
    promo = PromotionFactory(status="active", page_style="kompakt")
    html = _render(promo, {"site_defaults": {"promo_detail_style": "plakat"}})
    assert 'data-promo-detail="kompakt"' in html


def test_unknown_style_falls_back_instead_of_crashing():
    """Мусор в поле (старый конфиг, ручная правка) → прежний вид, а не 500."""
    promo = PromotionFactory(status="active", page_style="quatsch")
    html = _render(promo, {"site_defaults": {"promo_detail_style": "quatsch"}})
    assert "data-promo-detail" not in html


def test_cabinet_form_offers_the_page_template():
    """Выбор доступен и из кабинета (Studio — не единственный вход)."""
    from apps.promotions.forms import PromotionForm

    form = PromotionForm()
    assert "page_style" in form.fields
    assert any(code == "plakat" for code, _label in form.fields["page_style"].choices)
