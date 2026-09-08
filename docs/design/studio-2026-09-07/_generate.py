"""Канвас «Studio» — макет редактора в его нынешнем виде (2026-09-07).

Запрос владельца: «Ещё раз создай макет студио». Сентябрьский канвас был решенческим
(«что не так → как будет → A/B/C»); решение принято и волна STU-1…11 в проде, поэтому
здесь — Студия КАК ЕСТЬ: два уровня, панель по типу открытой страницы из реестра,
пилюля охвата. Все подписи, типы и настройки — из `apps/core/studio_pages.py`.

Правки — ЗДЕСЬ, потом `python _generate.py` и пере-сид канваса.
Визуальный словарь — кабинет после редизайна B: холст #F2F4F7, карточки rounded-2xl,
индиго #4f46e5, системный шрифт (у кабинета нет своего — Tailwind-дефолт).
"""

import json
from pathlib import Path

HERE = Path(__file__).parent

# ── визуальный словарь ────────────────────────────────────────────────────────
CSS = """
<style>
  body { margin: 0; font-family: ui-sans-serif, system-ui, "Segoe UI", sans-serif;
         color: #1f2937; }
  .wf { width: 940px; background: #fff; box-sizing: border-box; border: 1px solid #e5e7eb;
        border-radius: 16px; overflow: hidden; }
  .hd { padding: 12px 18px 11px; border-bottom: 1px solid #e5e7eb; background: #fff; }
  .hd .k { font-size: 10px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase;
           color: #4f46e5; }
  .hd h2 { margin: 2px 0 0; font-size: 16px; color: #111827; }
  .hd p { margin: 3px 0 0; font-size: 11px; color: #6b7280; line-height: 1.5; }

  /* ── хром Студии ── */
  .top { display: flex; align-items: center; gap: 8px; padding: 6px 12px; height: 34px;
         box-sizing: border-box; border-bottom: 1px solid #e5e7eb; background: #fff;
         font-size: 10px; color: #6b7280; }
  .top .brand { font-weight: 800; color: #111827; font-size: 12px; letter-spacing: -.01em; }
  .top .sp { flex: 1; }
  .top .btn { border: 1px solid #d1d5db; border-radius: 8px; padding: 3px 8px; color: #374151;
              background: #fff; }
  .top .btn.on { background: #eef2ff; border-color: #c7d2fe; color: #3730a3; font-weight: 700; }
  .top .save { background: #4f46e5; color: #fff; border-color: #4f46e5; font-weight: 700; }
  .top .ico { width: 14px; height: 14px; display: inline-block; vertical-align: -3px; }

  .app { display: flex; height: 400px; background: #f2f4f7; position: relative; }
  .rail { width: 64px; flex: 0 0 64px; background: #fff; border-right: 1px solid #e5e7eb;
          padding: 6px 4px; display: flex; flex-direction: column; gap: 2px; }
  .rail .lv { display: flex; flex-direction: column; align-items: center; gap: 3px;
              padding: 7px 2px; border-radius: 8px; color: #4b5563; font-size: 9px; }
  .rail .lv svg { width: 18px; height: 18px; stroke: currentColor; fill: none;
                  stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
  .rail .lv.on { background: #eef2ff; color: #3730a3; font-weight: 700; }
  .canvas { flex: 1; min-width: 0; padding: 10px; display: flex; flex-direction: column;
            position: relative; }
  .frame { background: #fff; border: 1px solid #d1d5db; border-radius: 8px; flex: 1;
           box-sizing: border-box; padding: 10px; position: relative; overflow: hidden; }
  .pages { height: 26px; display: flex; gap: 4px; align-items: center; padding: 0 2px;
           margin-top: 6px; }
  .pages .pg { border: 1px solid #e5e7eb; border-radius: 999px; padding: 2px 8px;
               font-size: 8px; color: #6b7280; background: #fff; white-space: nowrap; }
  .pages .pg.on { border-color: #4f46e5; color: #3730a3; background: #eef2ff; font-weight: 700; }

  .pane { width: 262px; flex: 0 0 262px; background: #fff; border-left: 1px solid #e5e7eb;
          padding: 8px 10px; box-sizing: border-box; overflow: hidden; }
  .pane .ttl { font-size: 11px; font-weight: 700; color: #374151; margin-bottom: 6px;
               display: flex; align-items: center; gap: 6px; }
  .pane .ttl .x { margin-left: auto; color: #9ca3af; font-weight: 400; }
  .tabs { display: flex; flex-wrap: wrap; gap: 3px; margin-bottom: 8px; }
  .tabs .tb { font-size: 8px; color: #6b7280; padding: 2px 6px; border-radius: 6px; }
  .tabs .tb.on { background: #eef2ff; color: #3730a3; font-weight: 700; }
  .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 8px 9px; margin-bottom: 7px;
          background: #fff; }
  .card .lg { font-size: 10px; font-weight: 700; color: #111827; margin-bottom: 5px; }
  .fld { margin-bottom: 7px; }
  .fld:last-child { margin-bottom: 0; }
  .fld .lb { font-size: 8.5px; color: #6b7280; margin-bottom: 3px; display: flex;
             justify-content: space-between; align-items: center; gap: 6px; }
  .ctrl { border: 1px solid #d1d5db; border-radius: 6px; padding: 4px 7px; font-size: 8.5px;
          color: #374151; background: #fff; display: flex; justify-content: space-between; }
  .ctrl .ch { color: #9ca3af; }
  .tiles { display: flex; gap: 4px; }
  .tiles .t { flex: 1; border: 1px solid #d1d5db; border-radius: 6px; height: 26px;
              background: repeating-linear-gradient(135deg,#eef2f7 0 4px,#f8fafc 4px 8px);
              position: relative; }
  .tiles .t.on { border-color: #4f46e5; box-shadow: 0 0 0 2px #e0e7ff inset; }
  .tiles .t span { position: absolute; left: 0; right: 0; bottom: 2px; text-align: center;
                   font-size: 7px; color: #6b7280; }
  .chips { display: flex; flex-wrap: wrap; gap: 3px; }
  .chip { border: 1px solid #d1d5db; border-radius: 6px; padding: 2px 6px; font-size: 8px;
          color: #374151; background: #fff; }
  .chip.on { background: #111827; color: #fff; border-color: #111827; }
  .chk { display: flex; align-items: center; gap: 5px; font-size: 8.5px; color: #374151; }
  .chk i { width: 10px; height: 10px; border: 1px solid #9ca3af; border-radius: 3px;
           display: inline-block; background: #fff; }
  .chk i.on { background: #4f46e5; border-color: #4f46e5; }
  .rows .r { display: flex; align-items: center; gap: 5px; font-size: 8.5px; color: #374151;
             padding: 3px 4px; border: 1px solid #e5e7eb; border-radius: 6px; margin-bottom: 3px;
             background: #fafafa; }
  .rows .r .h { color: #9ca3af; font-size: 9px; }
  .rows .r .eye { margin-left: auto; color: #9ca3af; }

  /* пилюля охвата — как в проде: две кнопки-«таблетки» + точка «есть своё» */
  .scope { display: flex; align-items: center; gap: 3px; margin-top: 4px; }
  .pill { border: 1px solid #d1d5db; border-radius: 999px; padding: 1px 7px; font-size: 8px;
          color: #6b7280; background: #fff; white-space: nowrap; }
  .pill.on { border-color: #c7d2fe; color: #3730a3; background: #eef2ff; font-weight: 700; }
  .dot { width: 5px; height: 5px; border-radius: 999px; background: #4f46e5;
         display: inline-block; margin-left: 3px; vertical-align: 1px; }
  .hint { font-size: 7.5px; color: #9ca3af; }

  /* ── скетч витрины на канве ── */
  .ph { background: repeating-linear-gradient(135deg, #e5e7eb 0 6px, #f3f4f6 6px 12px);
        border-radius: 4px; }
  .sf-nav { height: 18px; display: flex; gap: 6px; align-items: center; font-size: 8px;
            color: #9ca3af; border-bottom: 1px solid #eef2f7; margin-bottom: 8px; }
  .sf-nav b { color: #374151; }
  .sf-hero { height: 64px; border-radius: 6px; margin-bottom: 8px; position: relative; }
  .sf-hero .t { position: absolute; left: 10px; bottom: 8px; font-size: 10px; font-weight: 800;
                color: #111827; }
  .sf-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }
  .sf-grid .c { height: 58px; border: 1px solid #e5e7eb; border-radius: 6px; padding: 4px;
                box-sizing: border-box; }
  .sf-grid .c .img { height: 30px; border-radius: 3px; }
  .sf-grid .c .ln { height: 5px; width: 70%; background: #e5e7eb; border-radius: 2px;
                    margin-top: 5px; }
  .sf-grid .c .ln.s { width: 40%; }
  .sf-sec { font-size: 8px; color: #6b7280; margin: 6px 0 4px; display: flex;
            justify-content: space-between; }
  .sel { outline: 2px solid rgba(99,102,241,.9); outline-offset: 3px; border-radius: 6px; }
  .tag { position: absolute; right: 12px; top: 12px; font-size: 8px; background: #111827;
         color: #fff; border-radius: 999px; padding: 2px 7px; }
  .sf-text { max-width: 60%; margin: 0 auto; }
  .sf-text .h { height: 9px; width: 55%; background: #d1d5db; border-radius: 2px;
                margin-bottom: 8px; }
  .sf-text .p { height: 5px; background: #e5e7eb; border-radius: 2px; margin-bottom: 4px; }
  .sf-text .p.s { width: 80%; }

  /* ── справочные листы ── */
  .sheet { padding: 12px 18px 16px; }
  table { border-collapse: collapse; width: 100%; font-size: 9.5px; }
  th { text-align: left; font-size: 8.5px; color: #6b7280; font-weight: 600; padding: 4px 8px;
       border-bottom: 1px solid #e5e7eb; }
  td { padding: 4px 8px; border-bottom: 1px solid #f3f4f6; vertical-align: top; color: #374151; }
  td.code { font-family: ui-monospace, Menlo, monospace; font-size: 8.5px; color: #6b7280;
            white-space: nowrap; }
  td.lbl { font-weight: 700; color: #111827; white-space: nowrap; }
  td .st { display: inline-block; border: 1px solid #e5e7eb; border-radius: 6px; padding: 1px 6px;
           margin: 1px 3px 1px 0; background: #fafafa; font-size: 8.5px; }
  td .st.sc { border-color: #c7d2fe; background: #eef2ff; color: #3730a3; }
  td .none { color: #9ca3af; font-style: italic; }
  .note { font-size: 9.5px; color: #6b7280; line-height: 1.55; }
  .note b { color: #111827; }
  .cols { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
  .st8 { border: 1px solid #e5e7eb; border-radius: 12px; padding: 10px; background: #fff; }
  .st8 .k { font-size: 9px; font-weight: 800; color: #4f46e5; text-transform: uppercase;
            letter-spacing: .06em; margin-bottom: 6px; }
  .st8 .desc { font-size: 9px; color: #6b7280; margin-top: 8px; line-height: 1.5; }
  .arrow { font-size: 9px; color: #6b7280; padding: 8px 10px; border: 1px dashed #c7d2fe;
           border-radius: 10px; background: #f8f9ff; margin-top: 12px; line-height: 1.55; }

  /* ── v3: предложение ── */
  .top .pgsel { border: 1px solid #d1d5db; border-radius: 8px; padding: 3px 8px; color: #111827;
                background: #fff; font-weight: 600; display: flex; gap: 5px; align-items: center; }
  .top .pgsel .ch { color: #9ca3af; font-weight: 400; }
  .acc { border: 1px solid #e5e7eb; border-radius: 10px; margin-bottom: 5px; overflow: hidden; }
  .acc > .h { display: flex; align-items: center; gap: 6px; padding: 6px 8px; font-size: 9.5px;
            font-weight: 700; color: #111827; background: #fafafa; }
  .acc > .h .sum { margin-left: auto; font-weight: 400; color: #9ca3af; font-size: 8px;
                 white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 150px; }
  .acc > .h .car { color: #9ca3af; font-size: 8px; width: 8px; }
  .acc .b { padding: 7px 8px 8px; border-top: 1px solid #eef2f7; }
  .acc.open > .h { background: #fff; }
  .diff { width: 100%; border-collapse: collapse; font-size: 9.5px; }
  .diff th { text-align: left; font-size: 8.5px; color: #6b7280; font-weight: 600; padding: 5px 8px;
             border-bottom: 1px solid #e5e7eb; }
  .diff td { padding: 6px 8px; border-bottom: 1px solid #f3f4f6; vertical-align: top;
             color: #374151; line-height: 1.45; }
  .diff td.was { color: #9ca3af; }
  .diff td.now { color: #111827; }
  .diff td.why { color: #6b7280; font-size: 9px; }
  .link { color: #4f46e5; font-weight: 700; }
  .inset { position: absolute; right: 22px; bottom: 22px; width: 300px; background: #fff;
           border: 1px solid #c7d2fe; border-radius: 10px; box-shadow: 0 8px 24px rgba(22,24,29,.12);
           padding: 8px 9px; font-size: 8.5px; }
  .inset .cap { font-size: 8px; font-weight: 800; color: #4f46e5; text-transform: uppercase;
                letter-spacing: .06em; margin-bottom: 5px; }
  .warn { border: 1px dashed #fca5a5; background: #fff7f7; color: #991b1b; border-radius: 8px;
          padding: 6px 8px; font-size: 8.5px; line-height: 1.45; margin-top: 6px; }

  /* ── v4: страница «Entscheidungen» ── */
  .hd .badge { display: inline-block; background: #111827; color: #fff; font-size: 12px;
               font-weight: 800; letter-spacing: 0; border-radius: 7px; padding: 2px 8px;
               margin-right: 8px; vertical-align: middle; text-transform: none; }
  .hd .badge.rec { background: #4f46e5; }
  .hd .rectag { margin-left: 8px; color: #15803d; background: #dcfce7; border-radius: 999px;
                padding: 1px 7px; font-size: 9px; text-transform: none; letter-spacing: 0;
                font-weight: 700; }
  .top .pgsel.open { background: #eef2ff; border-color: #c7d2fe; color: #3730a3; }
  .top .pglabel { color: #111827; font-weight: 600; padding: 3px 4px; }
  .dd { position: absolute; left: 104px; top: 2px; width: 196px; background: #fff; z-index: 3;
        border: 1px solid #d1d5db; border-radius: 10px; box-shadow: 0 10px 28px rgba(22,24,29,.16);
        padding: 5px; font-size: 8.5px; }
  .dd .g { font-size: 7.5px; font-weight: 800; color: #9ca3af; text-transform: uppercase;
           letter-spacing: .06em; padding: 4px 6px 2px; }
  .dd .it { padding: 3px 6px; border-radius: 6px; color: #374151; display: flex; gap: 6px; }
  .dd .it.on { background: #eef2ff; color: #3730a3; font-weight: 700; }
  .dd .it .k { margin-left: auto; color: #9ca3af; font-size: 7.5px; }
  .dd .it.rare { color: #111827; font-weight: 600; }
  .callout { position: absolute; right: 16px; top: 54px; width: 214px; background: #fff;
             border: 1px solid #c7d2fe; border-radius: 10px; padding: 7px 9px; font-size: 8.5px;
             line-height: 1.45; color: #374151; box-shadow: 0 8px 24px rgba(22,24,29,.12); z-index: 3; }
  .callout b { color: #111827; }
  .sf-nav .cart { margin-left: auto; color: #111827; font-weight: 700; }
  .sf-nav .cart.sel-i { outline: 2px solid rgba(99,102,241,.9); outline-offset: 2px; border-radius: 4px; }
  .diff td.rec { color: #15803d; font-weight: 700; white-space: nowrap; }
  .diff td .opt { display: inline-block; background: #111827; color: #fff; font-size: 8.5px;
                  font-weight: 800; border-radius: 5px; padding: 1px 5px; margin-right: 5px; }
  .diff td .opt.rec { background: #4f46e5; }
  .answer { margin-top: 10px; border: 1px dashed #c7d2fe; background: #f8f9ff; border-radius: 10px;
            padding: 8px 10px; font-size: 10px; color: #374151; line-height: 1.5; }
  .answer b { color: #111827; }

  /* ── v5: панели-пересборка — поповеры, тулбар, флайаут, телефон ── */
  .pop { position: absolute; width: 232px; background: #fff; border: 1px solid #d1d5db; z-index: 4;
         border-radius: 10px; box-shadow: 0 12px 32px rgba(22,24,29,.18); padding: 7px 9px 8px;
         font-size: 8.5px; }
  .pop .ph2 { display: flex; align-items: center; gap: 6px; font-size: 9.5px; font-weight: 700;
              color: #111827; margin-bottom: 6px; }
  .pop .ph2 .x { margin-left: auto; color: #9ca3af; font-weight: 400; }
  .pop .ph2 .kind { font-size: 7.5px; font-weight: 600; color: #6b7280; background: #f3f4f6;
                    border-radius: 999px; padding: 1px 6px; }
  .pop::before { content: ""; position: absolute; width: 10px; height: 10px; background: #fff;
                 border-left: 1px solid #d1d5db; border-top: 1px solid #d1d5db; transform: rotate(-45deg); }
  .pop.ar-l::before { left: -6px; top: 14px; }
  .pop.ar-t::before { top: -6px; left: 18px; transform: rotate(45deg); }
  .pop.ar-r::before { right: -6px; top: 14px; transform: rotate(135deg); }
  .pop.ar-b::before { bottom: -6px; left: 18px; transform: rotate(225deg); }
  .pop .more { margin-top: 6px; font-size: 8px; color: #4f46e5; font-weight: 700; }
  .ftb { position: absolute; display: flex; gap: 2px; align-items: center; background: #111827;
         color: #fff; border-radius: 8px; padding: 3px 4px; font-size: 8px; z-index: 4;
         box-shadow: 0 6px 18px rgba(22,24,29,.25); white-space: nowrap; }
  .ftb .b { padding: 2px 6px; border-radius: 5px; }
  .ftb .b.on { background: #4f46e5; }
  .ftb .sep { width: 1px; height: 12px; background: #4b5563; margin: 0 2px; }
  .ftb .nm { font-weight: 700; padding: 2px 6px; color: #c7d2fe; }
  .flyout { width: 250px; flex: 0 0 250px; background: #fff; border-right: 1px solid #e5e7eb;
            padding: 8px 10px; box-sizing: border-box; overflow: hidden; }
  .flyout .ttl { font-size: 11px; font-weight: 700; color: #374151; margin-bottom: 6px;
                 display: flex; align-items: center; gap: 6px; }
  .flyout .ttl .x { margin-left: auto; color: #9ca3af; font-weight: 400; }
  .rail .lv .cnt { position: absolute; top: 3px; right: 6px; font-size: 7px; background: #4f46e5;
                   color: #fff; border-radius: 999px; padding: 0 4px; }
  .rail .lv { position: relative; }
  .sel-el { outline: 2px solid rgba(99,102,241,.9); outline-offset: 2px; border-radius: 4px; }
  .dim { opacity: .55; }
  .phone { width: 390px; background: #fff; border: 1px solid #e5e7eb; border-radius: 16px;
           overflow: hidden; box-sizing: border-box; }
  .phone .top { height: 34px; }
  .phone .app { height: 520px; display: block; }
  .phone .frame { height: 100%; border-radius: 0; border: 0; }
  .sheet-m { position: absolute; left: 0; right: 0; bottom: 0; background: #fff; z-index: 5;
             border-top-left-radius: 14px; border-top-right-radius: 14px; padding: 8px 12px 12px;
             box-shadow: 0 -8px 24px rgba(22,24,29,.14); font-size: 9px; }
  .sheet-m .grab { width: 36px; height: 4px; border-radius: 999px; background: #d1d5db; margin: 0 auto 8px; }
  .tabbar { position: absolute; left: 0; right: 0; bottom: 0; height: 40px; background: #fff;
            border-top: 1px solid #e5e7eb; display: flex; align-items: center; justify-content: space-around;
            font-size: 8px; color: #4b5563; z-index: 4; }
  .tabbar .tb { display: flex; flex-direction: column; align-items: center; gap: 2px; }
  .tabbar .tb svg { width: 16px; height: 16px; stroke: currentColor; fill: none; stroke-width: 1.8; }
  .tabbar .tb.on { color: #3730a3; font-weight: 700; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .inv { border: 1px solid #e5e7eb; border-radius: 12px; padding: 10px 12px; background: #fff; }
  .inv .k { font-size: 9px; font-weight: 800; color: #4f46e5; text-transform: uppercase;
            letter-spacing: .06em; margin-bottom: 6px; }
  .inv ul { margin: 0; padding-left: 14px; font-size: 9px; color: #374151; line-height: 1.5; }
  .inv li b { color: #111827; }
  .inv li .n { color: #9ca3af; font-size: 8px; }
</style>
"""

# ── иконки рейки (stroke-based, как SVG-спрайт кабинета) ─────────────────────
ICONS = {
    "design": '<svg viewBox="0 0 24 24"><path d="M12 3l2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 16.4 6.8 19.2l1-5.9L3.5 9.2l5.9-.8z"/></svg>',
    "page": '<svg viewBox="0 0 24 24"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>',
    "blocks": '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="8" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/><rect x="13" y="13" width="8" height="8" rx="1.5"/></svg>',
    "media": '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M21 16l-5-5-6 6-2-2-5 5"/></svg>',
    "start": '<svg viewBox="0 0 24 24"><path d="M13 2L4 14h7l-1 8 9-12h-7z"/></svg>',
    "menu": '<svg viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16"/></svg>',
}


def wrap(body: str, width: int = 940) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
{CSS}
</helmet>
<div class="wf" style="width: {width}px">
{body}
</div>
</x-dc>
</body>
</html>
"""


def hd(kicker: str, title: str, text: str) -> str:
    return f'<div class="hd"><div class="k">{kicker}</div><h2>{title}</h2><p>{text}</p></div>'


def top(page_label: str) -> str:
    return f"""
<div class="top">
  <span class="brand">Studio</span><span>· Hofladen Sonnenfeld</span>
  <span class="sp"></span>
  <span class="btn on">✏️ Bearbeiten</span><span class="btn">⚙️ Vorlage</span>
  <span class="btn">↶</span><span class="btn">↷</span>
  <span class="btn save">Speichern</span>
</div>"""


def rail(active: str, page_label: str = "Seite") -> str:
    levels = [("design", "Design"), ("page", page_label), ("blocks", "Blöcke"),
              ("media", "Medien"), ("start", "Start")]
    out = ['<div class="rail">']
    for key, label in levels:
        on = " on" if key == active else ""
        out.append(f'<div class="lv{on}">{ICONS[key]}<span>{label}</span></div>')
    out.append("</div>")
    return "".join(out)


def pages(active: str) -> str:
    chips = ["Startseite", "Sortiment", "Getränke &amp; Vorrat", "Aktionen", "Räumung",
             "Über uns", "Impressum", "Kontakt"]
    return '<div class="pages">' + "".join(
        f'<span class="pg{" on" if c == active else ""}">{c}</span>' for c in chips
    ) + "</div>"


def tabs(active: str, page_label: str) -> str:
    items = [("theme", "🎨 Theme"), ("banner", "🖼 Banner"), ("page", f"📄 {page_label}"),
             ("menu", "☰ Menu"), ("library", "📚 Templates")]
    return '<div class="tabs">' + "".join(
        f'<span class="tb{" on" if k == active else ""}">{l}</span>' for k, l in items
    ) + "</div>"


def scope(mode: str = "site", own: bool = False, hint: str = "") -> str:
    """Пилюля охвата: mode = site|own; own=True рисует точку «у объекта есть своё»."""
    dot = '<span class="dot"></span>' if own else ""
    return (f'<div class="scope"><span class="pill{" on" if mode == "site" else ""}">Für alle</span>'
            f'<span class="pill{" on" if mode == "own" else ""}">Nur hier{dot}</span>'
            f'<span class="hint">{hint}</span></div>')


# ── скетчи витрины ────────────────────────────────────────────────────────────
def sf_cards(n: int = 4) -> str:
    return '<div class="sf-grid">' + "".join(
        '<div class="c"><div class="img ph"></div><div class="ln"></div><div class="ln s"></div></div>'
        for _ in range(n)) + "</div>"


HOME_SKETCH = f"""
<div class="sf-nav"><b>Hofladen Sonnenfeld</b><span>Sortiment</span><span>Aktionen</span><span>Über uns</span><span>Kontakt</span></div>
<div class="sf-hero ph sel"><span class="t">Frisch vom Feld — jeden Tag</span></div>
<div class="sf-sec"><span>Unsere Produkte</span><span>Alle anzeigen →</span></div>
{sf_cards(4)}
<div class="sf-sec"><span>Aktionen</span><span>Alle Aktionen →</span></div>
{sf_cards(4)}
"""

CATEGORY_SKETCH = f"""
<div class="sf-nav"><b>Hofladen Sonnenfeld</b><span>Sortiment</span><span>Aktionen</span><span>Über uns</span></div>
<div style="font-size:8px;color:#9ca3af;margin-bottom:4px">Sortiment › <b style="color:#374151">Getränke &amp; Vorrat</b></div>
<div class="sf-hero ph" style="height:44px"><span class="t">Getränke &amp; Vorrat</span></div>
<div class="chips" style="margin-bottom:8px"><span class="chip on">Alle</span><span class="chip">Säfte</span><span class="chip">Wasser</span><span class="chip">Nudeln &amp; Reis</span><span class="chip">Öl</span></div>
<div class="sel" style="padding:4px">{sf_cards(4)}<div style="height:6px"></div>{sf_cards(4)}</div>
"""

PROMO_GROUP_SKETCH = f"""
<div class="sf-nav"><b>Hofladen Sonnenfeld</b><span>Sortiment</span><b>Aktionen</b><span>Über uns</span></div>
<div style="font-size:8px;color:#9ca3af;margin-bottom:4px">Aktionen › <b style="color:#374151">Räumung</b></div>
<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:8px"><span style="font-size:12px;font-weight:800;color:#111827">Räumung</span><span style="font-size:8px;color:#dc2626;font-weight:700">⏳ Endet in 2 Tagen</span></div>
<div class="sel" style="padding:4px">{sf_cards(4)}<div style="height:6px"></div>{sf_cards(4)}</div>
"""

TEXT_SKETCH = """
<div class="sf-nav"><b>Hofladen Sonnenfeld</b><span>Sortiment</span><span>Aktionen</span><b>Über uns</b></div>
<div class="sf-text sel" style="padding:8px">
  <div class="h"></div>
  <div class="p"></div><div class="p"></div><div class="p s"></div>
  <div style="height:8px"></div>
  <div class="p"></div><div class="p"></div><div class="p"></div><div class="p s"></div>
  <div style="height:8px"></div>
  <div class="ph" style="height:36px"></div>
</div>
"""



# ── v3: компоненты предложения ────────────────────────────────────────────────
def top_v3(page: str, extra: str = "") -> str:
    return f"""
<div class="top">
  <span class="brand">Studio</span><span>· Hofladen Sonnenfeld</span>
  <span class="pgsel">Seite: {page}<span class="ch">▾</span></span>
  <span class="sp"></span>{extra}
  <span class="btn on">✏️ Bearbeiten</span>
  <span class="btn">↶</span><span class="btn">↷</span>
  <span class="btn save">Speichern</span>
</div>"""


def rail_v3(active: str, page_label: str, with_design: bool = True) -> str:
    levels = ([("design", "Design")] if with_design else []) + [
        ("page", page_label), ("blocks", "Blöcke"), ("media", "Medien")]
    out = ['<div class="rail">']
    for key, label in levels:
        on = " on" if key == active else ""
        out.append(f'<div class="lv{on}">{ICONS[key]}<span>{label}</span></div>')
    out.append("</div>")
    return "".join(out)


def acc(title: str, summary: str, body: str = "", open_: bool = False) -> str:
    car = "▾" if open_ else "▸"
    b = f'<div class="b">{body}</div>' if open_ else ""
    return (f'<div class="acc{" open" if open_ else ""}"><div class="h"><span class="car">{car}</span>'
            f'{title}<span class="sum">{summary}</span></div>{b}</div>')


def design_pane_v3() -> str:
    look = ('<div class="tiles"><div class="t"><span>Klar</span></div><div class="t on"><span>Warm</span></div>'
            '<div class="t"><span>Nacht</span></div><div class="t"><span>Fein</span></div><div class="t"><span>Natur</span></div></div>'
            '<div class="hint" style="margin-top:4px">Look = Farbe, Schrift und Kartenstil auf einmal. Ihre Seitenvorlagen bleiben.</div>')
    return f"""
<div class="pane">
  <div class="ttl">Design des Shops <span class="x">✕</span></div>
  {acc("Look", "Warm", look, open_=True)}
  {acc("Farbe &amp; Schrift", "● #b45309 · Nunito")}
  {acc("Karten &amp; Fotos", "Regal · rund · Hairline")}
  {acc("Kopf- &amp; Fußzeile", "Classic · CTA an · 6 Punkte")}
  {acc("Vorlagen", "Startpaket · Layout · Demo")}
</div>"""


def page_pane_v3(page_label: str, body: str) -> str:
    return f"""
<div class="pane">
  <div class="ttl">Diese Seite: {page_label} <span class="x">✕</span></div>
  {body}
</div>"""


CATEGORY_BODY_V3 = None  # заполняется ниже, после scope()


# ── артборды ──────────────────────────────────────────────────────────────────
def main_home() -> str:
    pane = f"""
<div class="pane">
  <div class="ttl">📄 Startseite <span class="x">✕</span></div>
  {tabs("page", "Startseite")}
  <div class="card">
    <div class="lg">Abschnitte</div>
    <div class="rows">
      <div class="r"><span class="h">⠿</span>Banner<span class="eye">👁</span></div>
      <div class="r"><span class="h">⠿</span>Kategorien<span class="eye">👁</span></div>
      <div class="r"><span class="h">⠿</span>Produkte<span class="eye">👁</span></div>
      <div class="r"><span class="h">⠿</span>Aktionen<span class="eye">👁</span></div>
      <div class="r" style="opacity:.55"><span class="h">⠿</span>Bewertungen<span class="eye">◌</span></div>
      <div class="r"><span class="h">⠿</span>Kontakt<span class="eye">👁</span></div>
    </div>
  </div>
  <div class="card">
    <div class="lg">Banner</div>
    <div class="fld"><div class="lb">Vorlage</div>
      <div class="tiles"><div class="t"><span>Klar</span></div><div class="t on"><span>Split</span></div><div class="t"><span>Vollbild</span></div><div class="t"><span>Bento</span></div></div>
    </div>
  </div>
</div>"""
    body = (hd("Studio · Startseite",
               "Уровень «Seite» на главной открывает её собственные настройки",
               "Рейка слева — уровни: Design (кожа на весь сайт), Seite (настройки того типа, что "
               "на канве), Blöcke, Medien, Start. Подпись уровня и вкладки берётся из типа "
               "страницы — на главной это «Startseite», и панель показывает ровно две её "
               "настройки из реестра: порядок разделов и вид баннера. Клик по баннеру на канве "
               "открывает эту же панель.")
            + top("Startseite")
            + f'<div class="app">{rail("page", "Startseite")}'
            + f'<div class="canvas"><div class="frame">{HOME_SKETCH}<span class="tag">Startseite</span></div>{pages("Startseite")}</div>'
            + pane + "</div>")
    return wrap(body)


def kategorie() -> str:
    pane = f"""
<div class="pane">
  <div class="ttl">📄 Kategorie <span class="x">✕</span></div>
  {tabs("page", "Kategorie")}
  <div class="card">
    <div class="lg">Vorlage der Seite</div>
    <div class="fld">
      <div class="tiles"><div class="t"><span>Standard</span></div><div class="t"><span>Kopfbild</span></div><div class="t on"><span>Regale</span></div><div class="t"><span>Navigator</span></div></div>
      {scope("own", own=True)}
    </div>
    <div class="fld"><div class="lb">Kartenform</div>
      <div class="tiles"><div class="t on"><span>Regal</span></div><div class="t"><span>Lookbook</span></div><div class="t"><span>Deal</span></div></div>
      {scope("site")}
    </div>
  </div>
  <div class="card">
    <div class="lg">Raster &amp; Anzeige</div>
    <div class="fld"><div class="lb">Raster</div><div class="chips"><span class="chip">3</span><span class="chip on">4</span><span class="chip">5</span><span class="chip">6</span><span class="chip">Preisliste</span></div></div>
    <div class="fld"><div class="lb">Sortierung</div><div class="ctrl"><span>Neueste zuerst</span><span class="ch">▾</span></div></div>
    <div class="fld"><div class="chk"><i class="on"></i>Filter anzeigen</div></div>
    <div class="fld"><div class="chk"><i class="on"></i>Unterkategorien zuerst</div></div>
  </div>
</div>"""
    body = (hd("Studio · Kategorie",
               "Панель = реестр: категория спрашивает свои восемь настроек",
               "У «Vorlage der Seite» и «Kartenform» — пилюля охвата. Точка на «Nur hier» означает, "
               "что у ЭТОЙ категории есть своё значение, и общий выбор сайта её не касается: "
               "«Regale» здесь, «Standard» — на остальных. Когда канва уходит на страницу без объекта, "
               "контрол возвращается к значению сайта.")
            + top("Kategorie")
            + f'<div class="app">{rail("page", "Kategorie")}'
            + f'<div class="canvas"><div class="frame">{CATEGORY_SKETCH}<span class="tag">Kategorie</span></div>{pages("Getränke &amp; Vorrat")}</div>'
            + pane + "</div>")
    return wrap(body)


def aktionsgruppe() -> str:
    pane = f"""
<div class="pane">
  <div class="ttl">📄 Aktionsgruppe <span class="x">✕</span></div>
  {tabs("page", "Aktionsgruppe")}
  <div class="card">
    <div class="lg">Vorlage der Gruppenseite</div>
    <div class="fld">
      <div class="tiles"><div class="t"><span>Schaufenster</span></div><div class="t"><span>Prospekt</span></div><div class="t on"><span>Countdown</span></div><div class="t"><span>Vergleich</span></div></div>
      {scope("own", own=True)}
    </div>
    <div class="fld"><div class="lb">Kartenform</div>
      <div class="tiles"><div class="t on"><span>Regal</span></div><div class="t"><span>Coupon</span></div><div class="t"><span>Ring</span></div></div>
      {scope("site")}
    </div>
  </div>
  <div class="note" style="padding:4px 2px">Только две настройки — потому что на странице группы не действуют ни «Vorlage der Seite» обзора акций, ни «Darstellung der Gruppen»: реестр их сюда не кладёт.</div>
</div>"""
    body = (hd("Studio · Aktionsgruppe",
               "Реестр не предлагает того, что на странице не действует",
               "Страница группы акций /aktionen/?gruppe=… — у неё ровно две настройки: шаблон "
               "группы (со своим значением для «Räumung» — Countdown) и форма карточки. Обзор "
               "акций получил бы ещё «Vorlage der Seite» и «Darstellung der Gruppen». Канва держит "
               "параметр группы при любой смене настройки.")
            + top("Aktionsgruppe")
            + f'<div class="app" style="height:344px">{rail("page", "Aktionsgruppe")}'
            + f'<div class="canvas"><div class="frame">{PROMO_GROUP_SKETCH}<span class="tag">Aktionsgruppe</span></div>{pages("Räumung")}</div>'
            + pane + "</div>")
    return wrap(body)


def textseite() -> str:
    pane = f"""
<div class="pane">
  <div class="ttl">📄 Textseite <span class="x">✕</span></div>
  {tabs("page", "Textseite")}
  <div class="card">
    <div class="lg">Textbreite</div>
    <div class="fld">
      <div class="ctrl"><span>Schmale Spalte</span><span class="ch">▾</span></div>
      <div class="chips" style="margin-top:5px">
        <span class="chip">Wie bisher</span><span class="chip on">Schmale Spalte</span><span class="chip">Breite Spalte</span><span class="chip">Volle Breite</span>
      </div>
    </div>
  </div>
  <div class="note" style="padding:4px 2px">Одна настройка на все текстовые страницы: «Über uns», правовые, блог, команда, галерея, отзывы. «Wie bisher» — страница как была (у «Über uns» узкая, у команды и галереи без ограничителя), остальные три задают ширину явно. Выбор виден на канве сразу, без сохранения.</div>
</div>"""
    body = (hd("Studio · Textseite",
               "Одна настройка — и честные значения",
               "«Textbreite» действует на всех страницах типов Textseite, Blog и Rechtliches. "
               "Четыре значения: «Wie bisher» (ничего не навязывать), узкая, широкая, во всю ширину. "
               "На «Über uns» ширина держит всю страницу — вводный блок, контакты и блоки страницы.")
            + top("Textseite")
            + f'<div class="app" style="height:344px">{rail("page", "Textseite")}'
            + f'<div class="canvas"><div class="frame">{TEXT_SKETCH}<span class="tag">Textseite</span></div>{pages("Über uns")}</div>'
            + pane + "</div>")
    return wrap(body)


# Реестр — из apps/core/studio_pages.py (2026-09-07). Настройки с пилюлей охвата
# помечены классом sc (per-объект значение: категория / акция / группа / товар).
REGISTRY = [
    ("home", "Startseite", ["Abschnitte", "Banner"]),
    ("catalog", "Katalog", ["Vorlage der Seite", "Raster", "Sortierung", "Filter",
                            "Preise in der Speisekarte", "Kennzeichnung", "Kartenform"]),
    ("category", "Kategorie", ["Vorlage der Seite*", "Raster", "Filter", "Unterkategorien zuerst",
                               "Kartenform*", "Sortierung", "Preise in der Speisekarte", "Kennzeichnung"]),
    ("product", "Produktseite", ["Aufbau der Detailseite", "Abschnitte", "Kartenform*", "Ähnliche Produkte"]),
    ("promos", "Aktionen", ["Vorlage der Seite", "Darstellung der Gruppen", "Gruppierung", "Kartenform*"]),
    ("promo_group", "Aktionsgruppe", ["Vorlage der Gruppenseite*", "Kartenform*"]),
    ("promo", "Aktionsseite", ["Kartenform*"]),
    ("services", "Leistungen", ["Raster", "Kartenform"]),
    ("service", "Leistung", ["Abschnitte", "Kartenform"]),
    ("stays", "Zimmer", ["Raster", "Kartenform"]),
    ("stay", "Zimmerseite", ["Abschnitte", "Kartenform"]),
    ("events", "Veranstaltungen", ["Raster", "Kartenform"]),
    ("tours", "Reisen", []),
    ("event", "Veranstaltungsseite", ["Abschnitte", "Kartenform"]),
    ("cart", "Warenkorb", ["Passt dazu"]),
    ("checkout", "Kasse", []),
    ("text", "Textseite", ["Textbreite"]),
    ("blog", "Blog", ["Textbreite"]),
    ("legal", "Rechtliches", ["Textbreite"]),
]


def register() -> str:
    rows = []
    for code, label, settings in REGISTRY:
        if settings:
            cells = "".join(
                f'<span class="st{" sc" if s.endswith("*") else ""}">{s.rstrip("*")}</span>'
                for s in settings)
        else:
            cells = '<span class="none">нет настроек — правится прямо на канве</span>'
        rows.append(f'<tr><td class="code">{code}</td><td class="lbl">{label}</td><td>{cells}</td></tr>')
    body = (hd("Реестр · тип страницы → настройки",
               "Единственный источник ответа «что у этой страницы настраивается»",
               "apps/core/studio_pages.py. Тип канва сообщает сама (атрибут на body — по уже "
               "разобранному маршруту), панель показывает строки только своего типа; замок сверяет "
               "реестр и разметку в обе стороны. Синие — настройки с пилюлей охвата «Für alle / Nur hier».")
            + '<div class="sheet"><table><tr><th>код</th><th>тип на канве</th><th>настройки в панели «Seite»</th></tr>'
            + "".join(rows) + "</table></div>")
    return wrap(body)


def umfang() -> str:
    col1 = f"""
<div class="st8"><div class="k">① Объекта нет</div>
  <div class="fld"><div class="lb">Vorlage der Seite</div>
    <div class="tiles"><div class="t on"><span>Standard</span></div><div class="t"><span>Regale</span></div><div class="t"><span>Navigator</span></div></div>
  </div>
  <div class="desc">Канва на списке товаров или на главной: «этой категории» нет — пилюли не видно, контрол показывает и правит значение САЙТА.</div>
</div>"""
    col2 = f"""
<div class="st8"><div class="k">② Für alle</div>
  <div class="fld"><div class="lb">Vorlage der Seite</div>
    <div class="tiles"><div class="t on"><span>Standard</span></div><div class="t"><span>Regale</span></div><div class="t"><span>Navigator</span></div></div>
    {scope("site")}
  </div>
  <div class="desc">Канва на категории, у неё своего значения нет. Выбор пишется как дефолт сайта — той же кнопкой «Speichern».</div>
</div>"""
    col3 = f"""
<div class="st8"><div class="k">③ Nur hier</div>
  <div class="fld"><div class="lb">Vorlage der Seite</div>
    <div class="tiles"><div class="t"><span>Standard</span></div><div class="t on"><span>Regale</span></div><div class="t"><span>Navigator</span></div></div>
    {scope("own", own=True, hint="")}
  </div>
  <div class="desc">У категории своё значение — точка на пилюле. Контрол показывает ЕГО и пишет точечно в объект; общий выбор сайта его не трогает.</div>
</div>"""
    body = (hd("Охват · Für alle / Nur hier",
               "Три состояния одной пилюли — и правило, которое их держит",
               "Вариант A: пилюля у КАЖДОЙ настройки, у которой есть объектный уровень (категория, "
               "товар, акция, группа акций). Две кнопки, точка = «у объекта есть своё».")
            + f'<div class="sheet"><div class="cols">{col1}{col2}{col3}</div>'
            + '<div class="arrow"><b style="color:#111827">Правило.</b> Контрол один, а значений два — объекта и сайта. '
              'В режиме «Nur hier» он держит значение объекта; как только канва уходит на страницу, где объекта нет, '
              'контрол возвращается к значению сайта — ещё до сохранения, и то же самое после Ctrl+Z. '
              'Иначе выбор одной категории стал бы дефолтом всего сайта.</div></div>')
    return wrap(body)



def v3_home() -> str:
    body = (hd("Вариант A · один уровень для всего глобального",
               "«Design des Shops»: пять секций-аккордеон вместо пяти входов",
               "Рейка — два уровня и два инструмента: Design · Diese Seite · Blöcke · Medien. "
               "Ни вкладок в панели, ни «⚙️ Vorlage» в верхней строке, ни ленты страниц внизу: "
               "«где я» и переход к редким страницам — одна выпадашка «Seite: … ▾». Свёрнутая секция "
               "показывает текущее значение одной строкой — состояние читается без раскрытия. "
               "Экран кабинета «Design» ведёт сюда же.")
            + top_v3("Startseite")
            + f'<div class="app">{rail_v3("design", "Startseite")}'
            + f'<div class="canvas"><div class="frame">{HOME_SKETCH}<span class="tag">Startseite</span></div></div>'
            + design_pane_v3() + "</div>")
    return wrap(body)


def v3_kategorie() -> str:
    body_pane = f"""
  <div class="card">
    <div class="lg">Vorlage der Seite</div>
    <div class="fld">
      <div class="tiles"><div class="t"><span>Standard</span></div><div class="t"><span>Kopfbild</span></div><div class="t on"><span>Regale</span></div><div class="t"><span>Navigator</span></div></div>
      {scope("own", own=True)}
    </div>
    <div class="fld"><div class="lb">Kartenform</div>
      <div class="tiles"><div class="t on"><span>Regal</span></div><div class="t"><span>Lookbook</span></div><div class="t"><span>Deal</span></div></div>
      {scope("site")}
    </div>
  </div>
  <div class="card">
    <div class="lg">Raster &amp; Anzeige</div>
    <div class="fld"><div class="lb">Raster</div><div class="chips"><span class="chip">3</span><span class="chip on">4</span><span class="chip">5</span><span class="chip">6</span><span class="chip">Preisliste</span></div></div>
    <div class="fld"><div class="lb">Sortierung</div><div class="ctrl"><span>Neueste zuerst</span><span class="ch">▾</span></div></div>
    <div class="fld"><div class="chk"><i class="on"></i>Filter anzeigen</div></div>
    <div class="fld"><div class="chk"><i class="on"></i>Unterkategorien zuerst</div></div>
  </div>"""
    body = (hd("Вариант A · на категории",
               "Кликнул категорию на канве — панель уже её",
               "Никакого выбора страницы: канва — живой сайт, категорию открываешь кликом по ней, "
               "товар — по товару, право — из подвала. Подпись уровня и заголовок панели — тип "
               "страницы; состав — ровно реестр (как сегодня). Пилюля охвата там же.")
            + top_v3("Getränke &amp; Vorrat")
            + f'<div class="app">{rail_v3("page", "Kategorie")}'
            + f'<div class="canvas"><div class="frame">{CATEGORY_SKETCH}<span class="tag">Kategorie</span></div></div>'
            + page_pane_v3("Kategorie", body_pane) + "</div>")
    return wrap(body)


def v3_alt() -> str:
    inset = """
<div class="inset">
  <div class="cap">Kabinett · Design</div>
  <div class="fld"><div class="lb">Look</div><div class="tiles"><div class="t"><span>Klar</span></div><div class="t on"><span>Warm</span></div><div class="t"><span>Nacht</span></div><div class="t"><span>Fein</span></div></div></div>
  <div class="fld"><div class="lb">Farbe &amp; Schrift</div><div class="ctrl"><span>● #b45309 · Nunito</span><span class="ch">▾</span></div></div>
  <div class="fld"><div class="lb">Karten &amp; Fotos</div><div class="ctrl"><span>Regal · rund · Hairline</span><span class="ch">▾</span></div></div>
  <div class="fld"><div class="lb">Kopf- &amp; Fußzeile</div><div class="ctrl"><span>Classic · CTA an</span><span class="ch">▾</span></div></div>
  <div class="warn">Живого превью нет: результат виден после сохранения, когда вернёшься в Студию.</div>
</div>"""
    pane = page_pane_v3("Startseite", """
  <div class="card">
    <div class="lg">Abschnitte</div>
    <div class="rows">
      <div class="r"><span class="h">⠿</span>Banner<span class="eye">👁</span></div>
      <div class="r"><span class="h">⠿</span>Kategorien<span class="eye">👁</span></div>
      <div class="r"><span class="h">⠿</span>Produkte<span class="eye">👁</span></div>
      <div class="r"><span class="h">⠿</span>Aktionen<span class="eye">👁</span></div>
    </div>
  </div>
  <div class="card"><div class="lg">Banner</div>
    <div class="tiles"><div class="t"><span>Klar</span></div><div class="t on"><span>Split</span></div><div class="t"><span>Vollbild</span></div></div>
  </div>""")
    body = (hd("Вариант B · глобальное — вон из Студии",
               "Студия только постраничная; «Design des Shops» — экран кабинета",
               "Рейка без уровня Design; в верхней строке одна ссылка «Design des Shops →», которая "
               "уводит на экран кабинета (сегодняшний /dashboard/design/, расширенный цветом, "
               "шрифтом, шапкой и подвалом). Минус: цвет и форму карточек меняешь вслепую — канвы "
               "рядом нет. Плюс: Студия становится совсем простой.")
            + top_v3("Startseite", '<span class="link">Design des Shops →</span>')
            + f'<div class="app">{rail_v3("page", "Startseite", with_design=False)}'
            + f'<div class="canvas"><div class="frame">{HOME_SKETCH}<span class="tag">Startseite</span></div>{inset}</div>'
            + pane + "</div>")
    return wrap(body)


def v3_diff() -> str:
    rows = [
        ("Входов в дизайн",
         "5: уровень «Design» · ⚙️ Vorlage · вкладка 🎨 Theme · 📚 Templates · экран /dashboard/design/",
         "1: уровень «Design des Shops»; экран кабинета ведёт сюда же",
         "Три из пяти открывали одну и ту же область — наслоения W1 → ST-3 → DL-7"),
        ("Вкладки внутри панели",
         "Theme · Banner · Seite · Menu · Templates — вторая навигация поверх рейки",
         "нет: панель = то, что выбрано на рейке",
         "Две навигации по одному и тому же — источник «каши»"),
        ("Лента страниц внизу",
         "чипы всех страниц, постоянно",
         "убрана; «Seite: … ▾» в верхней строке для редких страниц (корзина, касса)",
         "Канва — живой сайт: категория, товар, право открываются кликом"),
        ("Рейка",
         "Design · Seite · Blöcke · Medien · Start",
         "Design des Shops · Diese Seite: ‹тип› · Blöcke · Medien",
         "«Start» — шаблоны и демо — становится секцией «Vorlagen» внутри Design"),
        ("Меню и подвал",
         "отдельная область «Menu» + подвал внутри «Дизайна»",
         "секция «Kopf- &amp; Fußzeile» в Design",
         "Шапка и подвал — глобальные, как цвет и шрифт"),
        ("Настройки типа страницы",
         "реестр, подпись «Seite»",
         "реестр без изменений, подпись «Diese Seite: Kategorie»",
         "Это уже работает — трогать не нужно"),
    ]
    tr = "".join(f'<tr><td class="lbl">{a}</td><td class="was">{b}</td><td class="now">{c}</td><td class="why">{d}</td></tr>'
                 for a, b, c, d in rows)
    body = (hd("Что меняется", "Сегодня → предложение, построчно",
               "Общее для обоих вариантов: один вход в дизайн, панель без вкладок, без ленты страниц. "
               "Различие только в том, ГДЕ живёт глобальное — внутри Студии (A) или на экране кабинета (B).")
            + f'<div class="sheet"><table class="diff"><tr><th>что</th><th>сегодня</th><th>предложение</th><th>почему</th></tr>{tr}</table></div>')
    return wrap(body)


# ── v4: страница «Entscheidungen» — четыре развилки, каждая двумя картинками ─────
def hd2(badge: str, kicker: str, title: str, text: str, rec: bool = False) -> str:
    b = f'<span class="badge{" rec" if rec else ""}">{badge}</span>'
    r = '<span class="rectag">✓ empfohlen</span>' if rec else ""
    return f'<div class="hd"><div class="k">{b}{kicker}{r}</div><h2>{title}</h2><p>{text}</p></div>'


def rail_v4(active: str, levels: list) -> str:
    out = ['<div class="rail">']
    for key, label in levels:
        on = " on" if key == active else ""
        out.append(f'<div class="lv{on}">{ICONS[key]}<span>{label}</span></div>')
    out.append("</div>")
    return "".join(out)


LEVELS_4 = [("design", "Design"), ("page", "Startseite"), ("blocks", "Blöcke"), ("media", "Medien")]


def top_v4(page: str, mode: str = "sel", extra: str = "") -> str:
    """mode: sel — выпадашка закрыта · open — раскрыта · plain — только подпись."""
    if mode == "plain":
        pg = f'<span class="pglabel">{page}</span>'
    else:
        pg = f'<span class="pgsel{" open" if mode == "open" else ""}">Seite: {page}<span class="ch">▾</span></span>'
    return f"""
<div class="top">
  <span class="brand">Studio</span><span>· Hofladen Sonnenfeld</span>
  {pg}
  <span class="sp"></span>{extra}
  <span class="btn on">✏️ Bearbeiten</span>
  <span class="btn">↶</span><span class="btn">↷</span>
  <span class="btn save">Speichern</span>
</div>"""


LOOK_BODY = ('<div class="tiles"><div class="t"><span>Klar</span></div><div class="t on"><span>Warm</span></div>'
             '<div class="t"><span>Nacht</span></div><div class="t"><span>Fein</span></div><div class="t"><span>Natur</span></div></div>'
             '<div class="hint" style="margin-top:4px">Look = Farbe, Schrift und Kartenstil auf einmal. Ihre Seitenvorlagen bleiben.</div>')

MENU_ROWS = ('<div class="rows">'
             '<div class="r"><span class="h">⠿</span>Sortiment<span class="eye">👁</span></div>'
             '<div class="r"><span class="h">⠿</span>Aktionen<span class="eye">👁</span></div>'
             '<div class="r"><span class="h">⠿</span>Kontakt<span class="eye">👁</span></div></div>')

KOPF_FIELDS = (
    '<div class="fld"><div class="lb">Kopfzeile</div><div class="tiles"><div class="t on"><span>Classic</span></div>'
    '<div class="t"><span>Zentriert</span></div><div class="t"><span>Minimal</span></div></div></div>'
    '<div class="fld"><div class="chk"><i class="on"></i>CTA-Button „Jetzt bestellen“</div></div>'
    f'<div class="fld"><div class="lb">Menüpunkte<span class="hint">⠿ ziehen · 👁 ausblenden</span></div>{MENU_ROWS}</div>'
    '<div class="fld"><div class="lb">Fußzeile</div><div class="chips"><span class="chip on">Kontakt</span>'
    '<span class="chip on">Öffnungszeiten</span><span class="chip on">Social</span><span class="chip">Newsletter</span></div></div>'
)

VORLAGEN_FIELDS = (
    '<div class="fld"><div class="lb">Startpaket<span class="hint">Komposition + Look</span></div>'
    '<div class="tiles"><div class="t on"><span>Fokus</span></div><div class="t"><span>Prospekt</span></div><div class="t"><span>Boutique</span></div></div></div>'
    '<div class="fld"><div class="lb">Layout-Vorlage<span class="hint">nur Abschnitte</span></div>'
    '<div class="ctrl"><span>Hofladen (empfohlen)</span><span class="ch">▾</span></div></div>'
    '<div class="fld"><div class="lb">Demo-Inhalte</div>'
    '<div class="ctrl" style="justify-content:center;color:#3730a3;border-color:#c7d2fe;font-weight:700">Demo-Inhalte laden</div>'
    '<div class="hint" style="margin-top:3px">Beispielprodukte und eine Aktion — jederzeit wieder löschbar.</div></div>'
)


def design_pane_v4(open_key: str, with_kopf: bool = True, with_vorlagen: bool = True) -> str:
    secs = [("look", "Look", "Warm", LOOK_BODY),
            ("farbe", "Farbe &amp; Schrift", "● #b45309 · Nunito", ""),
            ("karten", "Karten &amp; Fotos", "Regal · rund · Hairline", "")]
    if with_kopf:
        secs.append(("kopf", "Kopf- &amp; Fußzeile", "Classic · CTA an · 3 Punkte", KOPF_FIELDS))
    if with_vorlagen:
        secs.append(("vorlagen", "Vorlagen", "Fokus · Hofladen · Demo", VORLAGEN_FIELDS))
    body = "".join(acc(t, s, b, open_=(k == open_key)) for k, t, s, b in secs)
    return f'<div class="pane"><div class="ttl">Design des Shops <span class="x">✕</span></div>{body}</div>'


HOME_SKETCH_NAV = HOME_SKETCH.replace('<div class="sf-nav">', '<div class="sf-nav sel">', 1).replace(
    '<div class="sf-hero ph sel">', '<div class="sf-hero ph">', 1)
HOME_SKETCH_CART = HOME_SKETCH.replace(
    '<span>Kontakt</span></div>', '<span>Kontakt</span><span class="cart sel-i">🛒 2</span></div>', 1).replace(
    '<div class="sf-hero ph sel">', '<div class="sf-hero ph">', 1)

HOME_PAGE_PANE = page_pane_v3("Startseite", """
  <div class="card">
    <div class="lg">Abschnitte</div>
    <div class="rows">
      <div class="r"><span class="h">⠿</span>Banner<span class="eye">👁</span></div>
      <div class="r"><span class="h">⠿</span>Kategorien<span class="eye">👁</span></div>
      <div class="r"><span class="h">⠿</span>Produkte<span class="eye">👁</span></div>
      <div class="r"><span class="h">⠿</span>Aktionen<span class="eye">👁</span></div>
    </div>
  </div>
  <div class="card"><div class="lg">Banner</div>
    <div class="tiles"><div class="t"><span>Klar</span></div><div class="t on"><span>Split</span></div><div class="t"><span>Vollbild</span></div></div>
  </div>""")


def studio(top_html: str, rail_html: str, sketch: str, tag: str, pane_html: str, canvas_extra: str = "") -> str:
    return (top_html + f'<div class="app">{rail_html}'
            + f'<div class="canvas"><div class="frame">{sketch}<span class="tag">{tag}</span></div>{canvas_extra}</div>'
            + pane_html + "</div>")



# ── v5: помощники пересборки панелей (заполняются по итогам воркфлоу) ──────────
LEVELS_DEC = [("page", "Startseite"), ("menu", "Menü"), ("blocks", "Blöcke"), ("media", "Medien")]


def top_dec(page: str, mode: str = "sel", extra: str = "") -> str:
    """Верхняя строка по решениям 1B+3A: «Seite ▾» + ссылка «Design des Shops →»."""
    link = '<span class="link">Design des Shops →</span>'
    return top_v4(page, mode=mode, extra=link + extra)


def pop(x: int, y: int, title: str, body: str, kind: str = "", arrow: str = "l", width: int = 232,
        more: str = "") -> str:
    k = f'<span class="kind">{kind}</span>' if kind else ""
    m = f'<div class="more">{more}</div>' if more else ""
    return (f'<div class="pop ar-{arrow}" style="left:{x}px;top:{y}px;width:{width}px">'
            f'<div class="ph2">{title}{k}<span class="x">✕</span></div>{body}{m}</div>')


def ftb(x: int, y: int, name: str, buttons: list) -> str:
    bs = "".join(f'<span class="b{" on" if on else ""}">{b}</span>' for b, on in buttons)
    return f'<div class="ftb" style="left:{x}px;top:{y}px"><span class="nm">{name}</span><span class="sep"></span>{bs}</div>'


def flyout(title: str, body: str) -> str:
    return f'<div class="flyout"><div class="ttl">{title}<span class="x">✕</span></div>{body}</div>'


# ── 0 · бланк выбора ───────────────────────────────────────────────────────────
def e0_wahlzettel() -> str:
    rows = [
        ("1", "Wo lebt das globale Design (Look, Farbe, Schrift, Karten)?",
         "In der Studio-Leiste als Ebene «Design des Shops» — Änderung sofort auf der Leinwand",
         "Eigener Kabinett-Bildschirm; Studio bleibt nur seitenweise",
         "1A", "цвет и форму карточек хочется видеть живьём"),
        ("2", "Kopf- &amp; Fußzeile (Menüpunkte, CTA, Footer)",
         "Sektion innerhalb «Design des Shops»",
         "Eigene Leisten-Ebene «Menü»",
         "2A", "шапка глобальна, как цвет; пятый уровень — снова много входов"),
        ("3", "Seiten, die man auf der Leinwand nicht anklicken kann (Warenkorb, Kasse)",
         "Ausklappliste «Seite: … ▾» in der oberen Zeile",
         "Keine Liste — nur über die Leinwand (Korb-Symbol → Warenkorb → Kasse)",
         "3A", "две страницы, к которым иначе нужен полный корзинный сценарий"),
        ("4", "Bereich «⚡ Start» (Layout-Vorlagen, Demo-Inhalte)",
         "Sektion «Vorlagen» innerhalb «Design des Shops»",
         "Bleibt eigene Leisten-Ebene «Start»",
         "4A", "нужно раз при старте; уровень рейки — для ежедневного"),
    ]
    tr = "".join(
        f'<tr><td class="lbl">{n}</td><td>{q}</td>'
        f'<td class="now"><span class="opt{" rec" if r == n + "A" else ""}">{n}A</span>{a}</td>'
        f'<td class="now"><span class="opt{" rec" if r == n + "B" else ""}">{n}B</span>{b}</td>'
        f'<td class="rec">{r}</td><td class="why">{w}</td></tr>'
        for n, q, a, b, r, w in rows)
    body = (hd("Wahlzettel", "Четыре развилки — ответ в форме «1A · 2A · 3A · 4A»",
               "Ниже каждая развилка — парой артбордов, слева A, справа B; на картинках отличается "
               "только то, что решается. Развилки независимы, кроме одной оговорки: при 1B "
               "секции из 2A и 4A живут на экране кабинета, а не в панели Студии.")
            + '<div class="sheet"><table class="diff"><tr><th>№</th><th>Frage</th><th>A</th><th>B</th>'
            + f'<th>Empf.</th><th>почему</th></tr>{tr}</table>'
            + '<div class="answer"><b>Общее для всех вариантов</b> (уже решено предложением): один вход в дизайн, '
              'панель без вкладок, лента страниц внизу убрана, настройки типа страницы — как сегодня, '
              'экран кабинета «Design» ведёт в Студию.</div></div>')
    return wrap(body)


# ── 1 · где живёт глобальный дизайн ───────────────────────────────────────────
def e1a() -> str:
    body = (hd2("1A", "Globales Design", "Ebene «Design des Shops» in der Studio-Leiste",
                "Look, цвет, шрифт, карточки, шапка и шаблоны — одной панелью-аккордеоном. "
                "Свёрнутая секция показывает текущее значение строкой. Каждое изменение сразу на "
                "канве; Undo и Save — штатные.", rec=True)
            + studio(top_v4("Startseite"), rail_v4("design", LEVELS_4), HOME_SKETCH, "Startseite",
                     design_pane_v4("look")))
    return wrap(body)


def e1b() -> str:
    inset = """
<div class="inset">
  <div class="cap">Kabinett · Design des Shops</div>
  <div class="fld"><div class="lb">Look</div><div class="tiles"><div class="t"><span>Klar</span></div><div class="t on"><span>Warm</span></div><div class="t"><span>Nacht</span></div><div class="t"><span>Fein</span></div></div></div>
  <div class="fld"><div class="lb">Farbe &amp; Schrift</div><div class="ctrl"><span>● #b45309 · Nunito</span><span class="ch">▾</span></div></div>
  <div class="fld"><div class="lb">Karten &amp; Fotos</div><div class="ctrl"><span>Regal · rund · Hairline</span><span class="ch">▾</span></div></div>
  <div class="warn">Живого превью нет: результат виден после сохранения, когда вернёшься в Студию.</div>
</div>"""
    body = (hd2("1B", "Globales Design", "Eigener Kabinett-Bildschirm; Studio nur seitenweise",
                "Рейка без уровня Design; ссылка «Design des Shops →» уводит на экран кабинета "
                "(сегодняшний /dashboard/design/, расширенный цветом и шрифтом). Студия проще, "
                "но цвет и форму карточек меняешь вслепую.")
            + studio(top_v4("Startseite", extra='<span class="link">Design des Shops →</span>'),
                     rail_v4("page", LEVELS_4[1:]), HOME_SKETCH, "Startseite", HOME_PAGE_PANE, inset))
    return wrap(body)


# ── 2 · шапка и подвал ────────────────────────────────────────────────────────
def e2a() -> str:
    body = (hd2("2A", "Kopf- &amp; Fußzeile", "Sektion innerhalb «Design des Shops»",
                "Клик по шапке на канве раскрывает секцию «Kopf- &amp; Fußzeile» в панели дизайна: "
                "вид шапки, CTA-кнопка, пункты меню (перетаскивание, скрытие), состав подвала. "
                "Рейка остаётся из четырёх уровней.", rec=True)
            + studio(top_v4("Startseite"), rail_v4("design", LEVELS_4), HOME_SKETCH_NAV, "Kopfzeile",
                     design_pane_v4("kopf")))
    return wrap(body)


def e2b() -> str:
    pane = f"""
<div class="pane">
  <div class="ttl">Kopf- &amp; Fußzeile <span class="x">✕</span></div>
  <div class="card"><div class="lg">Kopfzeile</div>
    <div class="fld"><div class="tiles"><div class="t on"><span>Classic</span></div><div class="t"><span>Zentriert</span></div><div class="t"><span>Minimal</span></div></div></div>
    <div class="fld"><div class="chk"><i class="on"></i>CTA-Button „Jetzt bestellen“</div></div>
  </div>
  <div class="card"><div class="lg">Menüpunkte</div>{MENU_ROWS}</div>
  <div class="card"><div class="lg">Fußzeile</div>
    <div class="chips"><span class="chip on">Kontakt</span><span class="chip on">Öffnungszeiten</span><span class="chip on">Social</span><span class="chip">Newsletter</span></div>
  </div>
</div>"""
    levels = [("design", "Design"), ("page", "Startseite"), ("menu", "Menü"), ("blocks", "Blöcke"), ("media", "Medien")]
    body = (hd2("2B", "Kopf- &amp; Fußzeile", "Eigene Leisten-Ebene «Menü»",
                "Пятый уровень на рейке со своей панелью; «Design des Shops» остаётся из четырёх "
                "секций (Look · Farbe &amp; Schrift · Karten &amp; Fotos · Vorlagen). Содержимое то же, "
                "что в 2A, — отличается только место.")
            + studio(top_v4("Startseite"), rail_v4("menu", levels), HOME_SKETCH_NAV, "Kopfzeile", pane))
    return wrap(body)


# ── 3 · страницы, до которых не дойти кликом ──────────────────────────────────
def e3a() -> str:
    dd = """
<div class="dd">
  <div class="g">Über die Website erreichbar</div>
  <div class="it on">Startseite</div>
  <div class="it">Katalog · Kategorie · Produkt<span class="k">klicken</span></div>
  <div class="it">Aktionen · Gruppe · Aktion<span class="k">klicken</span></div>
  <div class="it">Über uns · Blog · Rechtliches<span class="k">klicken</span></div>
  <div class="g">Nur von hier</div>
  <div class="it rare">Warenkorb</div>
  <div class="it rare">Kasse</div>
</div>"""
    body = (hd2("3A", "Seltene Seiten", "Ausklappliste «Seite: … ▾» in der oberen Zeile",
                "Одна выпадашка вместо ленты чипов: показывает, где стоишь, и ведёт к двум "
                "страницам, которые на канве кликом не открыть, — Warenkorb и Kasse. Все прочие "
                "типы открываются кликом по содержимому (список для ориентира).", rec=True)
            + studio(top_v4("Startseite", mode="open"), rail_v4("page", LEVELS_4), HOME_SKETCH, "Startseite",
                     HOME_PAGE_PANE, dd))
    return wrap(body)


def e3b() -> str:
    callout = """
<div class="callout">
  <b>Ohne Liste:</b> Warenkorb — über das Korb-Symbol auf der Leinwand; Kasse — aus dem Warenkorb
  über „Zur Kasse“ (dafür muss im Vorschau-Korb etwas liegen).
  <div class="warn">Пустая корзина = до Kasse из Студии не дойти; настройки касcы тогда только через реестр без канвы.</div>
</div>"""
    body = (hd2("3B", "Seltene Seiten", "Keine Liste — nur über die Leinwand",
                "В верхней строке только подпись «где стою». Корзина и касса достигаются как "
                "посетителем: иконка корзины → Warenkorb → «Zur Kasse». Совсем без второго "
                "элемента навигации, но с оговоркой про пустую корзину.")
            + studio(top_v4("Startseite", mode="plain"), rail_v4("page", LEVELS_4), HOME_SKETCH_CART, "Startseite",
                     HOME_PAGE_PANE, callout))
    return wrap(body)


# ── 4 · область «Start» ───────────────────────────────────────────────────────
def e4a() -> str:
    body = (hd2("4A", "Bereich «Start»", "Sektion «Vorlagen» innerhalb «Design des Shops»",
                "Startpaket (композиция + Look), Layout-Vorlage (только состав секций) и "
                "Demo-Inhalte — одной секцией внизу панели дизайна. Уровень «Start» с рейки уходит.",
                rec=True)
            + studio(top_v4("Startseite"), rail_v4("design", LEVELS_4), HOME_SKETCH, "Startseite",
                     design_pane_v4("vorlagen")))
    return wrap(body)


def e4b() -> str:
    tpl = ('<div class="rows"><div class="r" style="background:#fff"><span style="width:7px;height:7px;border-radius:999px;background:#b45309;display:inline-block"></span>'
           'Hofladen<span class="eye" style="color:#15803d;font-size:7.5px">empfohlen</span></div>'
           '<div class="r" style="background:#fff"><span style="width:7px;height:7px;border-radius:999px;background:#4f46e5;display:inline-block"></span>Klassisch<span class="eye">Anwenden</span></div>'
           '<div class="r" style="background:#fff"><span style="width:7px;height:7px;border-radius:999px;background:#0f766e;display:inline-block"></span>Minimal<span class="eye">Anwenden</span></div></div>')
    pane = f"""
<div class="pane">
  <div class="ttl">⚡ Start <span class="x">✕</span></div>
  <div class="card"><div class="lg">Demo-Inhalte</div>
    <div class="hint" style="margin-bottom:5px">Beispielprodukte und eine Aktion. Jederzeit wieder löschbar.</div>
    <div class="ctrl" style="justify-content:center;color:#3730a3;border-color:#c7d2fe;font-weight:700">Demo-Inhalte laden</div>
  </div>
  <div class="card"><div class="lg">Layout-Vorlagen</div>
    <div class="hint" style="margin-bottom:5px">Fertiger Aufbau. Ihre Texte bleiben — nur leere Felder werden gefüllt.</div>
    {tpl}
  </div>
  <div class="hint">Startpaket bleibt unter Design → Look.</div>
</div>"""
    levels = LEVELS_4 + [("start", "Start")]
    body = (hd2("4B", "Bereich «Start»", "Bleibt eigene Leisten-Ebene «Start»",
                "Как сегодня: пятый уровень с демо-контентом и Layout-шаблонами; Startpaket "
                "остаётся в Design → Look. Плюс — быстрый вход при первом заходе, минус — второй "
                "уровень про шаблоны.")
            + studio(top_v4("Startseite"), rail_v4("start", levels), HOME_SKETCH, "Startseite", pane))
    return wrap(body)


ARTBOARDS = {
    "Main": (main_home, 940, 556, "Studio · Startseite"),
    "Kategorie": (kategorie, 940, 556, "Studio · Kategorie"),
    "Aktionsgruppe": (aktionsgruppe, 940, 500, "Studio · Aktionsgruppe"),
    "Textseite": (textseite, 940, 500, "Studio · Textseite"),
    "Register": (register, 940, 640, "Реестр: тип → настройки"),
    "Umfang": (umfang, 940, 360, "Охват: Für alle / Nur hier"),
    # ── страница «Vorschlag» ──
    "V3Home": (v3_home, 940, 556, "A · Design des Shops"),
    "V3Kategorie": (v3_kategorie, 940, 556, "A · Diese Seite: Kategorie"),
    "V3Alt": (v3_alt, 940, 556, "B · глобальное вне Студии"),
    "V3Diff": (v3_diff, 940, 404, "Что меняется"),
    # ── страница «Entscheidungen» ──
    "E0": (e0_wahlzettel, 940, 420, "Wahlzettel · 1A/1B · 2A/2B · 3A/3B · 4A/4B"),
    "E1A": (e1a, 940, 556, "1A · Design in der Studio-Leiste"),
    "E1B": (e1b, 940, 556, "1B · Design als Kabinett-Bildschirm"),
    "E2A": (e2a, 940, 556, "2A · Kopf/Fuß als Sektion im Design"),
    "E2B": (e2b, 940, 556, "2B · Kopf/Fuß als eigene Ebene «Menü»"),
    "E3A": (e3a, 940, 556, "3A · Ausklappliste «Seite: … ▾»"),
    "E3B": (e3b, 940, 556, "3B · keine Liste, nur Leinwand"),
    "E4A": (e4a, 940, 556, "4A · Start als Sektion «Vorlagen»"),
    "E4B": (e4b, 940, 556, "4B · Start bleibt eigene Ebene"),
}

PAGE_OF = {k: ("entscheidungen" if k.startswith("E") else "vorschlag" if k.startswith("V3") else "heute")
           for k in ARTBOARDS}

LAYOUT = {
    "Main": (0, 0), "Kategorie": (1040, 0),
    "Aktionsgruppe": (0, 696), "Textseite": (1040, 696),
    "Register": (0, 1336), "Umfang": (1040, 1336),
    "V3Home": (0, 0), "V3Kategorie": (1040, 0),
    "V3Alt": (0, 696), "V3Diff": (1040, 696),
    "E0": (0, 0),
    "E1A": (0, 560), "E1B": (1040, 560),
    "E2A": (0, 1256), "E2B": (1040, 1256),
    "E3A": (0, 1952), "E3B": (1040, 1952),
    "E4A": (0, 2648), "E4B": (1040, 2648),
}


def main() -> None:
    boards = []
    for name, (fn, w, h, title) in ARTBOARDS.items():
        (HERE / f"{name}.dc.html").write_text(fn(), encoding="utf-8")
        x, y = LAYOUT[name]
        boards.append({"file": f"{name}.dc.html", "x": x, "y": y, "w": w, "h": h, "title": title,
                       "page": PAGE_OF[name]})
    (HERE / "canvas.json").write_text(
        json.dumps({
            "pages": [{"id": "heute", "name": "Heute"}, {"id": "vorschlag", "name": "Vorschlag"},
                      {"id": "entscheidungen", "name": "Entscheidungen"}],
            "artboards": boards,
            "launch": {"view": "canvas", "page": "entscheidungen"},
        }, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print("артбордов:", len(boards))


if __name__ == "__main__":
    main()
