import { chromium } from 'playwright';
const SP = '/tmp/claude-0/-home-user-siteadaptor-platform/e8852805-0be9-5327-9267-8b58a434db3e/scratchpad';
const base = 'http://pranasy.siteadaptor.de:8000';
const browser = await chromium.launch({
  executablePath: '/opt/pw-browsers/chromium',
  args: ['--host-resolver-rules=MAP pranasy.siteadaptor.de 127.0.0.1'],
});
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1200 }, locale: 'de-DE' });
const page = await ctx.newPage();
const r = await page.goto(base + '/sortiment/catering/', { waitUntil: 'networkidle', timeout: 45000 });
console.log('catering', r.status());
await page.screenshot({ path: `${SP}/s-catering-top.png` });
// сколько столбцов реально у сетки блюд
const cols = await page.evaluate(() => {
  const g = document.querySelector('[data-grid="catalog"]');
  if (!g) return 'нет сетки (прайс-вид?)';
  return getComputedStyle(g).gridTemplateColumns.split(' ').length;
});
console.log('столбцов в сетке блюд:', cols);
const order = await page.evaluate(() => {
  const html = document.body.innerHTML;
  return {
    sets: html.indexOf('data-category-sets'),
    kat: html.indexOf('Kategorien'),
    grid: html.indexOf('data-sf-section="catalog"'),
  };
});
console.log('порядок (sets < Kategorien < grid):', order.sets < order.kat && order.kat < order.grid, order);
const g = await page.$('[data-grid="catalog"]');
if (g) { await g.scrollIntoViewIfNeeded(); await page.waitForTimeout(400); await page.screenshot({ path: `${SP}/s-catering-grid.png` }); }
await browser.close();
