import { chromium } from 'playwright';
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const page = await (await b.newContext({ viewport: { width: 1000, height: 900 } })).newPage();
const boards = JSON.parse(await (await import('fs')).promises.readFile('canvas.json', 'utf8')).artboards;
for (const a of boards) {
  await page.goto('file://' + process.cwd() + '/' + a.file);
  await page.waitForTimeout(150);
  const h = await page.evaluate(() => { const w = document.querySelector('.wf'); return Math.ceil(w.getBoundingClientRect().height); });
  const fits = h <= a.h ? 'ok ' : 'КЛИП';
  console.log(`${fits} ${a.file.padEnd(22)} нужно ${String(h).padStart(4)} · кадр ${a.h}`);
  await page.screenshot({ path: a.file.replace('.dc.html', '.png'), fullPage: true });
}
await b.close();
