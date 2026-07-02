# UC2-2 — on-canvas add/move за пределами главной (план, 2026-07-02)

Инкремент волны U-C (`uc-plan §11` п.5): «расширить инсертер "+"/moveBlock за пределы
home; data-sf-section drop-targets на всех страницах». План по разведке (агент,
адверсариально верифицировано против site_home.html/siteconfig.py/detail_sections.py).

## 1. Ключевые факты разведки

- **E.2 клик→инспектор НЕ гейтится** (site_home.html:1963) и работает на любой странице,
  НО только если ключ `data-sf-section` резолвится: `order_<key>` (home) → `.cb-row` →
  `.page-block[data-page-key=<key>]` (per-page инспектор). `event_detail` уже имел
  обёртку → попап работал; **service/stay-партиалы эмитили СОСТАВНЫЕ ключи**
  (`service_faq`, `stay_amenities`) — ничему не соответствуют → клик рисовал только
  рамку; **product_detail не имел маркеров вовсе**.
- **E.3 инсертер «+» и E.4 drag гейтятся `previewPath === "/"`** (1987/2028). Drag —
  value-based: перестановка `.home-block`-строк + перенумерация `order_*` инпутов +
  `schedule()`; на не-home строк `order_*` нет → `moveBlock` early-return.
- **Инсертер — full-POST** `add_block`/`use_block_template:<id>` c `add_after=<ключ>`.
- **C-блоки живут ТОЛЬКО в `config["sections"]`** (normalize_sections → home);
  рендер — только `section_blocks` → `home.html`. На детальных/листингах нет ни
  хранения, ни рендера C-блоков.
- Порядок секций деталей: **orderable только events** (`ed_order_*`); catalog/booking/
  stays — hide-only (реестр detail_sections.py:44-85).

## 2. Слайсы

- **Слайс 1 ✅ (2026-07-02): клик→инспектор на ВСЕХ детальных.** Обёртки
  `data-sf-section="<page-key>"` на service/stay (вокруг body_sections-цикла, образец
  event) + маркеры на product_detail (aside `#kaufen` + `#bewertungen`). Ключ =
  `data-page-key` per-page инспектора → `openBlockPopup` находит блок. Замок —
  `test_detail_bodies_carry_page_inspector_markers`. Составные ключи партиалов
  оставлены (безвредны; кандидаты на пер-секционные попапы позже).
- **Слайс 2 ✅ (2026-07-02): drag-reorder тематических секций события НА КАНВЕ.** Пер-
  секционные `data-sf-section="ed:<key>"`-маркеры в `_event_thematic.html` + ветка в
  drag-обработчике: на странице события drop мутирует `ed_order_*` (`.ed-order-input`)
  вместо `order_*` + `schedule()` (драфт уже поддерживает event_detail.order через
  apply_page_payload). Только events — единственный orderable-модуль.
- **Слайс 3 (L, ЗАБЛОКИРОВАН архитектурой): инсертер C-блоков на не-home.** Требует
  per-page ХРАНЕНИЯ секций (`config["sections"]` — home-only) + рендер-пути
  (`section_blocks` только в home.html) — это «UE1-хост на каждой странице», решение
  D1/UE1 (промо-блок сознательно отложен до движка). Делать ПОСЛЕ решения владельца о
  формате per-page секций (расширение normalize — горячее). НЕ входит в UC2-2.

## 3. Замки
`test_preview_pages.py::test_detail_bodies_carry_page_inspector_markers`, паритеты
секций (`test_service_detail_section_order_parity`, stay/product/event), golden
normalize, `test_home_builder` (order_*/ed_order_* пути не тронуты в слайсе 1).
