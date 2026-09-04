import pw from '/opt/node22/lib/node_modules/playwright/index.js';
const { chromium } = pw;
import { readFileSync } from 'fs';
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const boards = JSON.parse(readFileSync('canvas.json','utf8')).artboards;
for (const a of boards) {
  const p = await b.newPage({ viewport: { width: a.w, height: a.h }, deviceScaleFactor: 2 });
  await p.setContent(readFileSync(a.file,'utf8'), { waitUntil: 'load' });
  await p.screenshot({ path: a.file.replace('.dc.html', '.png'), fullPage: true });
  await p.close();
}
await b.close();
console.log('ok');
