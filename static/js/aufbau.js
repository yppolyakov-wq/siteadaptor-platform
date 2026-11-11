/* FB-27 R1: «Seitenaufbau». Без JS экран работает целиком (select + «Öffnen»). */
(function () {
  "use strict";
  // Смена типа страницы — сразу; кнопка «Öffnen» нужна только без JS.
  document.querySelectorAll("[data-autosubmit-hide]").forEach(function (b) { b.style.display = "none"; });
  document.addEventListener("change", function (e) {
    var sel = e.target.closest && e.target.closest("select[data-autosubmit]");
    if (sel && sel.form) sel.form.submit();
  });
  // После выбора блока фокус — в панель (телефон: панель стоит под схемой).
  if (location.hash === "#schema-panel") {
    var panel = document.getElementById("schema-panel");
    if (panel && panel.querySelector("[data-schema-confirm], form")) panel.focus({ preventScroll: false });
  }
})();
