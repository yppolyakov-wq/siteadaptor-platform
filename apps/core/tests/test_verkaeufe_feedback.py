"""VK-волна (фидбэк владельца 2026-08-20 по разделу «Verkäufe»).

План — `docs/verkaeufe-feedback-plan-2026-08-20.md`. Замки на то, что владелец
проверял глазами: доска без пустого места, вход в настройки раздела, понятная
страница «Abläufe» (карта процесса, редактор своих статусов, Trello-колонки),
триал-плашка только при входе и в биллинге.
"""

import uuid

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    username = "owner"


def _tenant(**kw):
    """Честный стартовый набор модулей архетипа (disabled_modules=[] открыл бы
    ВЕСЬ реестр — см. _hotel в test_verkaeufe)."""
    from apps.core.modules import default_disabled_for

    business_type = kw.pop("business_type", "bakery")  # orders активен (C&C)
    kw.setdefault("disabled_modules", list(default_disabled_for(business_type)))
    return TenantFactory(schema_name=f"t{uuid.uuid4().hex[:8]}", business_type=business_type, **kw)


def _req(path="/dashboard/verkaeufe/", tenant=None, **tenant_kwargs):
    req = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = tenant if tenant is not None else _tenant(**tenant_kwargs)
    return req


# --- п.1: «очень много свободного места» -------------------------------------
def test_board_columns_stretch_to_full_width():
    """Колонки были w-64 (фикс. 256px) — три колонки занимали треть широкого
    экрана. Теперь тянутся; min-w сохраняет прокрутку при большом числе колонок."""
    body = views.verkaeufe(_req("/dashboard/verkaeufe/?view=board")).content.decode()
    assert "sm:flex-1" in body and "sm:min-w-[15rem]" in body
    assert "sm:w-64" not in body  # прежняя фиксированная ширина не вернулась
    assert "w-[85vw]" in body  # мобильный snap-скролл цел


# --- п.2: кнопка настроек раздела --------------------------------------------
def test_settings_button_carries_active_kind():
    body = views.verkaeufe(_req("/dashboard/verkaeufe/?tab=order")).content.decode()
    assert "ablaeufe/?kind=order&amp;from=board" in body


# --- пп. 3/4/5: понятная страница «Abläufe» ----------------------------------
def test_ablaeufe_shows_process_map_with_columns_and_statuses():
    """Ответ на «настройки вообще не понятны»: колонки доски и статусы, которые
    в них попадают, — до всяких форм."""
    body = views.ablaeufe_view(_req("/dashboard/ablaeufe/?kind=order")).content.decode()
    assert "So läuft ein Verkauf" in body
    for column in ("Neu", "In Bearbeitung", "Fertig"):
        assert column in body
    assert "Abgeholt" in body  # статус order из колонки «Fertig»


def test_process_map_follows_renamed_and_hidden_columns():
    tenant = _tenant(
        site_config={"board": {"labels": {"intake": "Eingang"}, "hidden": ["terminal"]}}
    )
    body = views.ablaeufe_view(
        _req("/dashboard/ablaeufe/?kind=order", tenant=tenant)
    ).content.decode()
    assert "Eingang" in body  # своё имя колонки — и в карте, и в редакторе
    assert "ausgeblendet" in body  # скрытая колонка честно помечена, а не пропала


def test_custom_status_editor_lives_on_the_page():
    """п.3: раньше редактор своих статусов был ссылкой внутри свёрнутой панели."""
    body = views.ablaeufe_view(_req("/dashboard/ablaeufe/?kind=order")).content.decode()
    assert 'action="/dashboard/status-manager/order/save/"' in body
    assert 'name="new_label"' in body


def test_reservation_transitions_explain_instead_of_vanishing():
    """п.5: у Reservierungen правил скрывать нечего — раздел молча исчезал."""
    tenant = _tenant(business_type="catering")
    body = views.ablaeufe_view(
        _req("/dashboard/ablaeufe/?kind=reservation", tenant=tenant)
    ).content.decode()
    assert "Statusübergänge anpassen" in body
    assert "Eingelöst" in body  # человеческие подписи статусов резерва в карте


# --- п.6: колонки «как в Trello» ---------------------------------------------
def test_columns_panel_is_drag_and_drop():
    body = views.ablaeufe_view(_req("/dashboard/ablaeufe/?kind=order")).content.decode()
    assert "data-col-row" in body and 'draggable="true"' in body
    # порядок — в hidden-поле (перенумеровывает drop), а не в поле ввода числа
    assert '<input type="hidden" name="order_intake"' in body
    assert 'type="number" name="order_intake"' not in body


def test_column_names_are_visible_but_defaults_are_not_materialized():
    """VK-6: поле несёт действующее имя колонки (Trello-стиль). Сохранение
    дефолтного имени НЕ пишет его в site_config — иначе метки колонок замёрзли
    бы на языке кабинета (presence-minimal, класс W6)."""
    from apps.core import views as core_views

    tenant = _tenant(site_config={"notify": {"customer": {"email": True}}})
    body = views.ablaeufe_view(
        _req("/dashboard/ablaeufe/?kind=order", tenant=tenant)
    ).content.decode()
    assert 'name="label_intake" value="Neu"' in body  # имя видно в поле, не в placeholder

    req = RequestFactory().post(
        "/dashboard/board/settings/",
        {"label_intake": "Neu", "label_done": "Fertig zur Abholung"},
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = tenant
    core_views.board_settings(req)
    tenant.refresh_from_db()
    labels = (tenant.site_config.get("board") or {}).get("labels", {})
    assert "intake" not in labels  # дефолт не материализован
    assert labels["done"] == "Fertig zur Abholung"  # своё имя сохранено
    assert tenant.site_config["notify"] == {"customer": {"email": True}}  # targeted-write


# --- п.8: продажа по акции = обычный заказ, но помеченный ---------------------
def test_promo_sale_is_a_normal_order_with_a_visible_badge():
    """Вопрос владельца «разве не должен он попадать в классический заказ даже по
    акции?»: с волны PL так и есть — `promotions.services.purchase` создаёт
    обычный Order (source_channel="promo"). Теперь это ВИДНО: бейдж «Aktion» на
    карточке доски и в списке заказов."""
    from apps.core import transactions
    from apps.orders.models import Customer, Order

    customer = Customer.objects.create(name="Anna", email="a@t.de")
    promo_order = Order.objects.create(
        customer=customer, reference_code="O-PROMO1", source_channel="promo"
    )
    plain = Order.objects.create(customer=customer, reference_code="O-PLAIN1")

    assert transactions.transaction_for("order", promo_order).from_promo is True
    assert transactions.transaction_for("order", plain).from_promo is False

    tenant = _tenant()
    body = views.verkaeufe(
        _req("/dashboard/verkaeufe/?tab=order&view=liste", tenant=tenant)
    ).content.decode()
    assert "O-PROMO1" in body and "🏷" in body
