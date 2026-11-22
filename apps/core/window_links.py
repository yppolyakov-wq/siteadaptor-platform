"""FB-33 M4: адреса окна блока «Seitenaufbau» — для ⚙ Студии и ссылок в кабинете.

Окно блока открывается адресом экрана `?seite=<код>&block=<строка>[&tab=]` (M3-0…M3-2;
токен открытия `wopen` адрес не несёт — экран выдаёт новый). Студия знает только путь
канвы и ключ секции на ней (`data-sf-section`): `studio_settings_url` переводит их в адрес
окна. Всё, что уходит в адрес, — либо из белого списка, либо прошло `urlencode`; адрес
всегда внутри экрана «Seitenaufbau». Ничего не пишет (черновик только читается).
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlencode

from django.contrib import messages
from django.urls import reverse
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

#: ключ секции канвы: id C-блока, ключ секции/раздела, `pbhost:<хост>` (как `open_block` Студии)
REF_RE = re.compile(r"[A-Za-z0-9_:-]{1,40}")
#: обёртка области своих блоков страницы на канве (`data-sf-section="pbhost:<хост>"`)
PB_HOST_PREFIX = "pbhost:"
#: суффикс хостов деталей: раздел детали на канве — `<страница>_<раздел>` (`service_faq`)
DETAIL_SUFFIX = "_detail"


def schema_url() -> str:
    return reverse("site-schema")


def page_url(code: str) -> str:
    """Схема страницы без выбранного блока (как `site_schema.url_for_path`)."""
    return f"{schema_url()}?{urlencode({'seite': code})}"


def block_window_url(code: str, ref: str, tab: str = "") -> str:
    """Адрес окна строки `ref` страницы `code` (по образцу `site_schema.form_window_url`);
    вкладка — только из белого списка окна."""
    from apps.core import block_window

    query = {"seite": code, "block": ref}
    if tab in block_window.TAB_KEYS:
        query["tab"] = tab
    return f"{schema_url()}?{urlencode(query)}#schema-panel"


def clean_ref(raw) -> str:
    """Ключ секции из запроса — только безопасные символы ("" — мусор)."""
    if not isinstance(raw, str) or not REF_RE.fullmatch(raw):
        return ""
    return raw


def _host(tenant, code: str) -> str:
    from apps.core import site_schema

    try:
        _pt, host, _home = site_schema.resolve(tenant, code)
    except site_schema.SchemaError:
        return ""
    return host


def _refs(request, code: str, host: str) -> set[str]:
    """Строки схемы страницы — с черновиком «Seitenaufbau» (как их видит окно)."""
    from apps.core import aufbau_draft, site_schema
    from apps.tenants import siteconfig

    saved = siteconfig.normalize(request.tenant.site_config)
    draft = aufbau_draft.get(request, code)
    config = aufbau_draft.overlay(saved, draft) if draft else saved
    blocks = site_schema.blocks_for(config, code, host=host or None, summaries=False)
    refs = {b["ref"] for b in blocks}
    # FB-33 M5b-1: строка «Einstellungen der Seite» — там же, где её показывает экран
    if site_schema.page_row_ref(request.tenant, code, blocks) == site_schema.PAGE_REF:
        refs.add(site_schema.PAGE_REF)
    return refs


def _type_code(code: str) -> str:
    return code.split("@", 1)[0]


def _block_of(request, code: str, host: str, ref: str) -> str:
    """Строка схемы для ключа секции канвы ("" — такой строки нет)."""
    from apps.core import detail_parts, site_schema

    refs = _refs(request, code, host)
    if ref in refs:  # точное совпадение раньше снятия префикса: строка `service_x` ≠ раздел `x`
        return ref
    alias = site_schema.page_ref(ref)  # FB-33 M5b-2: старая ссылка «Seitentitel» → ★-строка
    if alias != ref and alias in refs:
        return alias
    base = detail_parts.shared_host(host or "")
    if base.endswith(DETAIL_SUFFIX):  # раздел детали: `service_faq` → `faq`
        prefix = base[: -len(DETAIL_SUFFIX)] + "_"
        if ref.startswith(prefix) and ref[len(prefix) :] in refs:
            return ref[len(prefix) :]
    return ""


def _is_page_key(code: str, host: str, ref: str) -> bool:
    """Ключ самой страницы канвы: обёртка списка/детали или область своих блоков."""
    from apps.core import detail_parts

    key = ref.removeprefix(PB_HOST_PREFIX)
    return key in {host, detail_parts.shared_host(host or ""), _type_code(code)} - {""}


def whole_page_refs() -> frozenset[str]:
    """Строки самой страницы — ключи из их единых мест: ★ основной список, «Einstellungen der
    Seite», «Seitentitel», «Kaufen»."""
    from apps.core import detail_parts, page_title, site_schema
    from apps.tenants import siteconfig

    return frozenset(
        {
            siteconfig.MAIN_LIST_KEY,
            site_schema.PAGE_REF,
            page_title.TITLE_REF,
            detail_parts.KAUF_REF,
        }
    )


def whole_page(ref: str) -> bool:
    """Строка самой страницы: у неё нет своего места на витрине — превью окна показывает
    страницу целиком."""
    return ref in whole_page_refs()


def canvas_key(request, code: str, ref: str, host: str | None = None) -> str:
    """FB-33 M3-7: ключ секции витрины (`data-sf-section`) для строки `ref` страницы `code` —
    обратная к `_block_of` (якорь «Vorschau» окна). Строка самой страницы — обёртка страницы
    (ключ хоста; "" — у главной её нет); раздел детали — `<страница>_<раздел>`
    (`service_faq`); C-блок и секция — свой id/ключ. "" — начало страницы. `host` — уже
    известный хост страницы (иначе — `site_schema.resolve`). Ничего не пишет."""
    from apps.core import detail_parts

    ref = clean_ref(ref)
    if not ref:
        return ""
    if host is None:
        host = _host(request.tenant, code)
    base = detail_parts.shared_host(host or "")
    if whole_page(ref):
        return clean_ref(base)
    if base.endswith(DETAIL_SUFFIX) and ref in detail_parts.section_keys(base):
        return clean_ref(base[: -len(DETAIL_SUFFIX)] + "_" + ref)
    return ref


def studio_settings_url(request, path: str, ref: str = "", tab: str = "") -> str:
    """⚙ Студии: адрес окна блока `ref` страницы канвы `path`. Без `ref` — схема страницы;
    ключ самой страницы — её настройки (`site_schema.settings_url`); строка общих блоков
    типа у страницы объекта — окно на общей схеме; иначе — страница без блока и подсказка."""
    from apps.core import site_schema

    tenant = request.tenant
    code = site_schema.code_for_path(tenant, path)
    ref = clean_ref(ref)
    if not code:
        if ref:
            messages.info(request, _("Diesen Block finden Sie im Seitenaufbau nicht."))
        return schema_url()
    if not ref:
        return page_url(code)
    host = _host(tenant, code)
    try:
        block = _block_of(request, code, host, ref)
        if block and site_schema.is_title_alias(ref) and block == site_schema.PAGE_REF:
            # FB-33 M5b-2 (A-M5): старый ⚙ «Seitentitel» — окно ★-строки, вкладка «Seite»
            return block_window_url(code, block, "seite")
        if block:
            return block_window_url(code, block, tab)
        if _is_page_key(code, host, ref):
            return site_schema.settings_url(_type_code(code))
        if site_schema.is_object_code(code):
            # T2: общий блок типа на странице объекта правится на общей схеме типа
            shared = site_schema.OBJECT_PAGE_TYPES.get(_type_code(code), _type_code(code))
            block = _block_of(request, shared, _host(tenant, shared), ref)
            if block:
                return block_window_url(shared, block, tab)
    except Exception:  # noqa: BLE001 — ⚙ не должна ронять переход: экран страницы
        logger.warning("window link: block %r of %s not resolved", ref, code, exc_info=True)
    messages.info(request, _("Diesen Block finden Sie im Seitenaufbau nicht."))
    return page_url(code)
