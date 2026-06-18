/** Tailwind build (P5): компилируем purged CSS вместо CDN (Core Web Vitals).
 *  Сканируем все шаблоны; darkMode:'class' — под переключатель тёмной темы. */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./apps/**/templates/**/*.html",
  ],
  darkMode: "class",
  theme: { extend: {} },
  plugins: [],
};
