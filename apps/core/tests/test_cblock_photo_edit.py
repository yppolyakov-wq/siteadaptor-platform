"""UC6-4: замена фото C-блока (image/image_text) прямо на канве превью.

site_cblock_photo_edit: файл → save_product_image(folder="cblock") → url в data
блока публикуемого конфига + зеркало в сессионный черновик и БД-`_draft`
(иначе push() черновика откатывал бы фото)."""

from io import BytesIO
from types import SimpleNamespace

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from PIL import Image

from apps.core.views import site_cblock_photo_edit
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(tenant, bid, *, with_file=True, session_draft=None):
    req = RequestFactory().post("/dashboard/site/cblock-photo/", data={"pk": bid})
    SessionMiddleware(lambda r: None).process_request(req)
    if session_draft is not None:
        req.session["site_preview_draft"] = session_draft
    if with_file:
        buf = BytesIO()
        Image.new("RGB", (40, 40), "#abc").save(buf, format="PNG")
        req.FILES["image"] = SimpleUploadedFile("b.png", buf.getvalue(), content_type="image/png")
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _tenant_with_image_block(bid="ph1", extra_cfg=None):
    cfg = siteconfig.normalize(
        {"sections": [{"key": "image", "id": bid, "data": {"url": "/alt.jpg", "caption": "C"}}]}
    )
    if extra_cfg:
        cfg = {**cfg, **extra_cfg}
    return TenantFactory(slug=f"ph-{bid}", name="P", site_config=cfg)


def _block(cfg, bid):
    return next(s for s in siteconfig.normalize(cfg)["sections"] if s.get("id") == bid)


def test_replace_updates_published_session_and_db_draft(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    draft_cfg = siteconfig.normalize(
        {"sections": [{"key": "image", "id": "ph1", "data": {"url": "/draft-old.jpg"}}]}
    )
    tenant = _tenant_with_image_block("ph1", extra_cfg={"_draft": draft_cfg})
    resp = site_cblock_photo_edit(_req(tenant, "ph1", session_draft=dict(draft_cfg)))
    assert resp.status_code == 200
    import json

    url = json.loads(resp.content)["url"]
    assert url and url != "/alt.jpg"
    tenant.refresh_from_db()
    assert _block(tenant.site_config, "ph1")["data"]["url"] == url  # публикуемый конфиг
    db_draft = tenant.site_config.get("_draft")
    assert _block(db_draft, "ph1")["data"]["url"] == url  # БД-_draft тоже


def test_unknown_block_404_and_missing_file_400(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    tenant = _tenant_with_image_block("ph2")
    assert site_cblock_photo_edit(_req(tenant, "nope")).status_code == 404
    assert site_cblock_photo_edit(_req(tenant, "ph2", with_file=False)).status_code == 400
    tenant.refresh_from_db()
    assert _block(tenant.site_config, "ph2")["data"]["url"] == "/alt.jpg"  # не тронут
