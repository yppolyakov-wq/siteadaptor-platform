import pw from '/opt/node22/lib/node_modules/playwright/index.js';
const { chromium } = pw;
import { readFileSync, writeFileSync } from 'fs';
const cfg = JSON.parse(readFileSync('canvas.json','utf8'));
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
for (const a of cfg.artboards) {
  const p = await b.newPage({ viewport: { width: a.w, height: 400 }, deviceScaleFactor: 2 });
  await p.setContent(readFileSync(a.file,'utf8'), { waitUntil: 'load' });
  a.h = Math.ceil(await p.evaluate(() => document.body.scrollHeight)) + 6;
  await p.setViewportSize({ width: a.w, height: a.h });
  await p.screenshot({ path: a.file.replace('.dc.html','.png'), fullPage: true });
  await p.close();
}
// пере-раскладка: две колонки, вертикальный зазор 130
let y1 = 0, y2 = 0;
cfg.artboards.forEach((a, i) => {
  const col2 = [1, 2, 3, 5, 7].includes(i);
  a.x = col2 ? 1020 : 0;
  if (col2) { a.y = y2; y2 += a.h + 130; } else { a.y = y1; y1 += a.h + 130; }
});
writeFileSync('canvas.json', JSON.stringify(cfg, null, 1));
console.log(cfg.artboards.map(a => `${a.title}: ${a.w}x${a.h} @${a.x},${a.y}`).join('\n'));
