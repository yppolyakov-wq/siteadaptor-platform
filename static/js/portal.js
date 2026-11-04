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
  var drawer = document.getElementById("flt-drawer");
  var opener = null;
  var mobile = window.matchMedia("(max-width: 639px)");

  function openDrawer(section, from) {
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
    if (drawer && drawer.open) drawer.close();
  }

  if (drawer) {
    drawer.addEventListener("close", function () {
      if (opener && typeof opener.focus === "function") opener.focus();
      opener = null;
    });
    drawer.addEventListener("click", function (e) {
      if (e.target === drawer) closeDrawer(); // клик по затемнению
    });
  }

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
})();
