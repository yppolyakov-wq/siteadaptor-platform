/* FB-27 R1: «Seitenaufbau». Экран работает без JS; здесь только фокус.
   Тип страницы меняется кнопкой «Öffnen», не по change: стрелки в списке на Windows
   сразу шлют change, и страница перезагружалась бы при просмотре списка (WCAG 3.2.2). */
(function () {
  "use strict";
  // После выбора блока или действия фокус — в панель (на телефоне она под схемой).
  if (location.hash === "#schema-panel") {
    var panel = document.getElementById("schema-panel");
    if (panel) panel.focus();
  }
})();
