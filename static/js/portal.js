/* FLT-1e: фильтры городского портала — шторка «Alle Filter» и поповеры.
 * Без этого файла всё работает: шторка — обычная форма (noscript), поповеры — <details>,
 * сортировка — кнопка «OK». Скрипт только улучшает поведение. План FLT §4, §6.
 * Сортировка НЕ отправляется по change: стрелки в закрытом <select> на Windows дают change
 * на каждое нажатие — страница перезагружалась бы с первой клавиши (WCAG 3.2.2). */
(function () {
  "use strict";
  // Витрина подменяет список fetch'ем (KAT-5): скрипт внутри подменённой зоны не
  // перезапускается, а привязки к старым элементам умирают → всё делегировано на
  // document, а повторное подключение файла — no-op.
  if (window.__fltInit) return;
  window.__fltInit = true;
  // шторку ищем в момент действия: строка могла быть перерисована (fetch-своп)
  function getDrawer() {
    return document.getElementById("flt-drawer");
  }
  var opener = null;
  var mobile = window.matchMedia("(max-width: 639px)");

  function openDrawer(section, from) {
    var drawer = getDrawer();
    if (!drawer || typeof drawer.showModal !== "function") return false;
    opener = from || document.activeElement;
    drawer.showModal();
    var target = section && drawer.querySelector('[data-flt-sec="' + section + '"]');
    if (target) {
      target.scrollIntoView({ block: "start" });
      // имя группы читается первым; клавиатура телефона не выскакивает в поле цены
      var legend = target.querySelector("legend, p[id]");
      if (legend) {
        if (!legend.hasAttribute("tabindex")) legend.setAttribute("tabindex", "-1");
        legend.focus();
      }
    }
    return true;
  }

  function closeDrawer() {
    var drawer = getDrawer();
    if (drawer && drawer.open) drawer.close();
  }

  // close не всплывает — ловим на фазе захвата
  document.addEventListener(
    "close",
    function (e) {
      if (!e.target || e.target.id !== "flt-drawer") return;
      if (opener && opener.isConnected && typeof opener.focus === "function") opener.focus();
      opener = null;
    },
    true
  );

  // С JS ссылка «Alle Filter» и пилюли ▾ на телефоне открывают диалог — так и называем
  document.querySelectorAll("[data-flt-open]").forEach(function (a) {
    a.setAttribute("role", "button");
    a.setAttribute("aria-haspopup", "dialog");
  });
  function syncSummaries() {
    document.querySelectorAll("[data-flt-pop] > summary").forEach(function (s) {
      if (mobile.matches) s.setAttribute("aria-haspopup", "dialog");
      else s.removeAttribute("aria-haspopup");
    });
  }
  syncSummaries();
  if (mobile.addEventListener) mobile.addEventListener("change", syncSummaries);

  document.addEventListener("click", function (e) {
    if (e.target.id === "flt-drawer") {
      closeDrawer(); // клик по затемнению
      return;
    }
    var open = e.target.closest("[data-flt-open]");
    if (open && openDrawer("", open)) {
      e.preventDefault();
      return;
    }
    if (e.target.closest("[data-flt-close]")) {
      e.preventDefault();
      closeDrawer();
      return;
    }
    // телефон: поповер в прокручиваемой строке обрезается — пилюля ▾ открывает шторку
    var summary = e.target.closest("[data-flt-pop] > summary");
    if (summary && mobile.matches) {
      var pop = summary.parentElement;
      if (openDrawer(pop.getAttribute("data-flt-pop"), summary)) {
        e.preventDefault();
        return;
      }
    }
    document.querySelectorAll("[data-flt-pop][open]").forEach(function (d) {
      if (!d.contains(e.target)) d.removeAttribute("open"); // клик вне — закрыть
    });
  });

  // toggle не всплывает — ловим на фазе захвата
  document.addEventListener(
    "toggle",
    function (e) {
      var d = e.target;
      if (!d.matches || !d.matches("[data-flt-pop]") || !d.open) return;
      document.querySelectorAll("[data-flt-pop][open]").forEach(function (o) {
        if (o !== d) o.removeAttribute("open"); // один поповер за раз
      });
    },
    true
  );
  // Tab ушёл из поповера — закрыть, чтобы он не накрывал содержимое
  document.addEventListener("focusout", function (e) {
    var d = e.target.closest && e.target.closest("[data-flt-pop][open]");
    if (d && e.relatedTarget && !d.contains(e.relatedTarget)) d.removeAttribute("open");
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || e.defaultPrevented) return;
    var d = document.activeElement && document.activeElement.closest("[data-flt-pop][open]");
    if (!d) return; // Esc в другом поле поповеры не трогает (шторка закрывается сама)
    d.removeAttribute("open");
    var s = d.querySelector("summary");
    if (s) s.focus();
  });

  // пустые поля не тащим в адрес («preis_von=&datum=»): правим только отправляемые данные,
  // DOM не трогаем — ничего не «гаснет» и не остаётся отключённым после отмены
  document.addEventListener(
    "formdata",
    function (e) {
      if (!e.target.closest || !e.target.closest("[data-flt]")) return;
      var empty = [];
      e.formData.forEach(function (value, key) {
        if (value === "") empty.push(key);
      });
      empty.forEach(function (key) {
        var kept = e.formData.getAll(key).filter(function (v) {
          return v !== "";
        });
        e.formData.delete(key);
        kept.forEach(function (v) {
          e.formData.append(key, v);
        });
      });
    },
    true
  );

  // ---- PH-2: мега-меню «Kategorien» (портал) ----
  // Без JS кнопка — ссылка на якорь разделов главной; с JS открывает <dialog>.
  var menuOpener = null;
  document.addEventListener("click", function (e) {
    var open = e.target.closest && e.target.closest("[data-portal-menu-open]");
    if (open) {
      var menu = document.getElementById("portal-menu");
      if (menu && typeof menu.showModal === "function") {
        e.preventDefault();
        menuOpener = open;
        menu.showModal();
        var first = menu.querySelector("[data-portal-menu-section]");
        if (first) first.focus();
      }
      return;
    }
    var menuEl = document.getElementById("portal-menu");
    if (!menuEl || !menuEl.open) return;
    if (e.target.closest("[data-portal-menu-close]") || e.target === menuEl) {
      menuEl.close();
    }
  });
  document.addEventListener("close", function (e) {
    if (e.target && e.target.id === "portal-menu" && menuOpener) {
      menuOpener.focus();
      menuOpener = null;
    }
  }, true);
  // Подкатегории справа — по наведению/фокусу на строку раздела.
  function showPanel(row) {
    var menu = document.getElementById("portal-menu");
    if (!menu || !row) return;
    var key = row.getAttribute("data-portal-menu-row");
    menu.querySelectorAll("[data-portal-menu-panel]").forEach(function (p) {
      p.hidden = p.getAttribute("data-portal-menu-panel") !== key;
    });
  }
  ["mouseover", "focusin"].forEach(function (type) {
    document.addEventListener(type, function (e) {
      var row = e.target.closest && e.target.closest("[data-portal-menu-row]");
      if (row) showPanel(row);
    });
  });

  // ---- PH-3: «Endet in …» — по истечении срока карточка помечается «Beendet»
  // (главная кэшируется до 2 минут; текст считает сервер). ----
  function tickEnds() {
    var now = Date.now();
    document.querySelectorAll("[data-ends-at]").forEach(function (el) {
      var t = Date.parse(el.getAttribute("data-ends-at"));
      if (!isNaN(t) && t <= now && !el.hasAttribute("data-ended")) {
        el.setAttribute("data-ended", "");
        var txt = el.querySelector("[data-ends-text]");
        if (txt) txt.textContent = el.getAttribute("data-ended-label") || "";
        el.style.opacity = "0.6";
      }
    });
  }
  tickEnds();
  setInterval(tickEnds, 60000);

  // ---- PH-5: «In der Nähe» на главной — только при геолокации (без JS кнопки нет) ----
  document.querySelectorAll("[data-near-me]").forEach(function (btn) {
    if (navigator.geolocation) btn.hidden = false;
  });
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-near-me]");
    if (!btn || !navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(function (pos) {
      var u = new URL("/", window.location.href);
      u.searchParams.set("kind", "alle");
      u.searchParams.set("lat", pos.coords.latitude.toFixed(5));
      u.searchParams.set("lng", pos.coords.longitude.toFixed(5));
      u.searchParams.set("sort", "naehe");
      window.location.href = u.toString();
    });
  });
  // «Alle Filter» с главной: лента открывается с шторкой фильтров.
  if (window.location.hash === "#filter") {
    openDrawer("", null);
  }
})();
