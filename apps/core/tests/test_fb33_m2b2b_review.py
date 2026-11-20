"""FB-33 M2b-2b: ревью ECC (database, security, silent-failure) — замок на каждый пункт.

1 формы объекта пишут свои вопросы под блокировкой и со сверкой отпечатка `faq_base`;
  полная запись формы (`ModelForm.save`) не возвращает старые вопросы (`lock_fresh`);
2 форма события/тура — пары полей (см. `test_fb33_m2b2b_object_faq`), вопрос до 2000 знаков;
3 смена источника на «Allgemeine FAQ» снимает правку своих вопросов честным сообщением;
4 лимиты формы — с сообщением, сохранённые сверх лимита без явного удаления не теряются;
5 переводы по сырым позициям, скрытый раздел, ссылки без права/при сбое базы, лимит на
  витрине, `commit` вызывается с пользователем, `normalize` не хранит черновик превью.
"""

import copy
from pathlib import Path

import pytest
from django.contrib.messages import get_messages
from django.db import DatabaseError, transaction
from django.test import RequestFactory

from apps.core import aufbau_draft, object_faq
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb33_m2b2b_window import (
    OWN,
    WOPEN,
    _drafts,
    _post,
    _setup,
    _svc,
    own_block,
)
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _urlconf(settings, monkeypatch):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.core import view_perms

    monkeypatch.setattr(view_perms, "allowed", lambda *a, **k: True)


@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        username="owner2br", email="owner2br@test.de", password="pw12345678"
    )


def _product(**kw):
    from apps.catalog.tests.factories import ProductFactory

    return ProductFactory(name={"de": "Tee", "en": ""}, base_price="2.00", **kw)


def _product_post(product, user, extra):
    from apps.catalog import views
    from apps.catalog.tests.test_fb29_structure_tab import BASE
    from apps.catalog.tests.test_views import _attach_session_user

    req = RequestFactory().post(f"/catalog/products/{product.pk}/edit/", {**BASE, **extra})
    _attach_session_user(req, user)
    views.product_edit(req, pk=product.pk)
    product.refresh_from_db()
    return [str(m) for m in get_messages(req)]


# ───────────── 1 ─────────────


def test_form_with_stale_base_does_not_overwrite_questions(user):
    p = _product(faq=OWN)
    stale = object_faq.fingerprint(p, "product")
    p.faq = [{"q": "Vom Kollegen?", "a": "ja"}]
    p.save(update_fields=["faq"])
    msgs = _product_post(
        p, user, {"faq_present": "1", "faq_base": stale, "faq_q_0": "Meins?", "faq_a_0": ""}
    )
    assert p.faq == [{"q": "Vom Kollegen?", "a": "ja"}]
    assert object_faq.form_changed_note() in msgs


def test_form_with_current_base_writes(user):
    p = _product(faq=OWN)
    base = object_faq.fingerprint(p, "product")
    _product_post(p, user, {"faq_present": "1", "faq_base": base, "faq_q_0": "Neu?"})
    assert p.faq == [{"q": "Neu?", "a": ""}]


def test_full_form_save_keeps_fresh_questions(user):
    """Форма товара без пар полей (вкладка без FAQ), открытая до чужой правки: полная запись
    `ModelForm.save` не возвращает старые вопросы."""
    from apps.catalog.forms import ProductForm
    from apps.catalog.tests.test_fb29_structure_tab import BASE

    p = _product(faq=OWN)
    form = ProductForm(BASE, instance=p, tenant=None)  # экземпляр со старыми вопросами
    assert form.is_valid(), form.errors
    type(p).objects.filter(pk=p.pk).update(faq=[{"q": "Frisch?", "a": ""}])
    with transaction.atomic():
        object_faq.lock_fresh(form.instance, "product")
        form.save()
    p.refresh_from_db()
    assert p.faq == [{"q": "Frisch?", "a": ""}]


def test_event_form_keeps_fresh_questions_of_others():
    from apps.events import views
    from apps.events.models import Event
    from apps.events.tests.test_tours import _cab

    ev = Event.objects.create(
        title="Konzert",
        starts_at="2030-01-01T10:00:00Z",
        details={"faq": OWN, "idea": "x"},
    )
    stale = Event.objects.get(pk=ev.pk)
    Event.objects.filter(pk=ev.pk).update(details={"faq": [{"q": "Neu?", "a": ""}], "idea": "x"})
    data = {
        "title": "Konzert",
        "starts_at": "2030-01-01T10:00",
        "capacity": 0,
        "price_eur": "0",
        "idea": "y",
    }
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(views, "get_object_or_404", lambda *a, **k: stale)  # старый экземпляр
        resp = views.event_edit(_cab(method="post", data=data), pk=ev.pk)
    assert resp.status_code == 302
    ev.refresh_from_db()
    assert ev.details["faq"] == [{"q": "Neu?", "a": ""}]


def test_concurrent_form_and_window():
    """Окно сохранило вопросы, затем форма со старым отпечатком — вопросы окна остаются."""
    tenant, svc, code = _setup([own_block()])
    stale = object_faq.fingerprint(svc, "service")
    b = Browser(tenant)
    _post(b, code, svc, faq_remove="0")
    b.post(seite=code, op="save")
    notes: list = []
    object_faq.save_from_form(
        _svc(svc),
        "service",
        {"faq_present": "1", "faq_base": stale, "faq_q_0": "Alt?", "faq_a_0": ""},
        tenant,
        notes,
    )
    assert [f["q"] for f in _svc(svc).faq] == [OWN[1]["q"], OWN[2]["q"]]
    assert notes == [object_faq.form_changed_note()]


# ───────────── 3 ─────────────


def test_switch_to_shared_drops_own_edit_with_a_note():
    from apps.catalog.tests.factories import ProductFactory
    from apps.core import faq_content
    from apps.core import object_structure as ost

    tenant, _svc_obj, _code = _setup()
    p = ProductFactory(name={"de": "Brot"}, faq=OWN)
    host, code = ost.object_host("product", p), ost.schema_code("product", p)
    cfg = copy.deepcopy(tenant.site_config)
    cfg["page_blocks"] = {host: [own_block()]}
    tenant.site_config = siteconfig.normalize(cfg)
    tenant.save()
    b = Browser(tenant)

    def post(**extra):
        items, src = object_faq.state(p, "product", _drafts(b).get(code))
        data = {
            "seite": code, "ref": "faqown01", "op": "update", "faq_present": "1", "wopen": WOPEN,
            "faq_rev": faq_content.revision(items, src),
            "faq_base": object_faq.fingerprint(p, "product"),
        }  # fmt: skip
        for i, it in enumerate(items):
            data[f"faq_{i}_q"], data[f"faq_{i}_a"] = it["q"], it["a"]
        data.update(extra)
        return b.post(**data)

    post(faq_remove="0")
    assert "ofaq" in _drafts(b)[code]
    _resp, msgs = post(faq_source="shared")
    draft = _drafts(b)[code]
    assert "ofaq" not in draft and "ofaq_base" not in draft
    assert object_faq.switched_note() in msgs
    _resp, msgs = b.post(seite=code, op="save")
    p.refresh_from_db()
    assert p.faq == OWN and object_faq.dropped_note() not in msgs


# ───────────── 4 ─────────────


def test_form_limits_have_notes_and_keep_stored_over_limit():
    many = [{"q": f"F{i}?", "a": ""} for i in range(14)]  # данные до среза: 14 > 12
    post = {"faq_present": "1"}
    for i, it in enumerate(many):
        post[f"faq_q_{i}"], post[f"faq_a_{i}"] = it["q"], it["a"]
    notes: list = []
    base, _tr = object_faq.from_form(post, [], "service", notes, keep=14)
    assert len(base) == 14 and notes == []
    post["faq_q_14"] = "Neu?"
    post["faq_q_0"] = "Q" * 300
    base, _tr = object_faq.from_form(post, [], "service", notes, keep=14)
    assert len(base) == 14 and len(base[0]["q"]) == 200
    assert notes == [object_faq.limit_note("service"), object_faq.full_note("service")]


def test_service_view_shows_limit_notes():
    from apps.booking import views
    from apps.booking.models import Service
    from apps.booking.tests.test_service_rich_editing import _base, _post, _tenant

    tenant = _tenant("rich-r4")
    svc = Service.objects.create(name="X", duration_minutes=30)
    data = _base(svc, faq_present="1", faq_q_0="Q" * 250, faq_a_0="a")
    req = _post(data, tenant)
    views.services_view(req)
    svc.refresh_from_db()
    assert len(svc.faq[0]["q"]) == 200
    assert object_faq.limit_note("service") in [str(m) for m in get_messages(req)]


# ───────────── 5 ─────────────


@pytest.mark.parametrize("kind", ["product", "event"])
def test_translations_follow_raw_positions(kind):
    from apps.core.tests.test_fb33_m2b2b_object_faq import make

    raw = [{"q": "", "a": "Leer"}, OWN[0], OWN[1]]
    ru = [{"q": "пусто"}, {"q": "Сколько?"}, {"q": "Мыть?"}]
    obj = make(kind, faq=raw, ru=ru)
    assert object_faq.overlays(obj, kind)["ru"] == ru[1:]
    assert object_faq.localized(obj, kind, "ru")[0]["q"] == "Сколько?"
    fp = object_faq.fingerprint(obj, kind)
    object_faq.put(obj, kind, [OWN[1], OWN[0]], [1, 0], fp)
    assert object_faq.overlays(obj, kind)["ru"] == [ru[2], ru[1]]


def test_hidden_section_hint():
    tenant, svc, code = _setup([])
    b = Browser(tenant)
    b.post(seite=code, op="toggle", ref="faq")
    html = b.get(f"?seite={code}&block=faq&tab=texte")
    assert "data-faq-hidden" in html


def test_panel_without_rights_shows_no_editor_and_no_links(monkeypatch):
    from apps.core import view_perms

    tenant, svc, code = _setup([own_block()], shared_blocks=[own_block("faqsh")])
    monkeypatch.setattr(view_perms, "allowed", lambda *a, **k: False)
    b = Browser(tenant)
    html = b.get(f"?seite={code}&block=faqown01&tab=texte")
    assert 'name="faq_scope" value="noaccess"' in html and 'name="faq_0_q"' not in html
    shared = b.get("?seite=service&block=faqsh&tab=texte")
    assert "data-faq-links" not in shared


def test_links_survive_a_database_error(monkeypatch):
    def boom(*a, **k):
        raise DatabaseError("x")

    monkeypatch.setattr(object_faq, "display_name", boom)
    _setup([])
    assert object_faq._links("service_detail") == []


def test_storefront_caps_questions_by_kind():
    from apps.core.tests.test_fb33_m2b2b_object_faq import make

    obj = make("event", faq=[{"q": f"F{i}?", "a": ""} for i in range(40)], ru=[])
    assert len(object_faq.localized(obj, "event", "de")) == 30
    assert len(object_faq.items(obj, "event")) == 40  # сохранённое не режется


def test_commit_is_called_with_the_request_user():
    src = (ROOT / "apps/core/aufbau_draft.py").read_text()
    assert 'draft["items"], getattr(request, "user", None), draft, notes, force' in src
    assert "_object_faq().commit(locked, kind, draft, user, notes, force)" in src
    for path in (ROOT / "apps").rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if "/tests/" in rel or rel in ("apps/core/aufbau_draft.py", "apps/core/object_faq.py"):
            continue
        assert "object_faq.commit(" not in path.read_text(), rel


def test_normalize_does_not_keep_the_preview_draft():
    cfg = siteconfig.normalize({object_faq.DRAFT_KEY: {"x": {"items": OWN}}})
    assert object_faq.DRAFT_KEY not in cfg


def test_window_noaccess_scope_is_known_to_draft_count():
    """Смена источника без своих вопросов в черновике не добавляет «изменений» ofaq."""
    tenant, svc, code = _setup([own_block()])
    b = Browser(tenant)
    _post(b, code, svc, faq_source="shared")
    draft = _drafts(b)[code]
    assert "ofaq" not in draft
    saved = aufbau_draft._saved_state(
        siteconfig.normalize(tenant.site_config), False, draft["host"]
    )
    assert aufbau_draft.changes(saved, draft) == 1  # только данные блока (источник)
    assert _svc(svc).faq == OWN
