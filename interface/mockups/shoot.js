// Screenshots of the mockup pages (Playwright, 1440 wide, retina).
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
(async () => {
  const b = await chromium.launch();
  const pg = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  for (const f of fs.readdirSync(__dirname).filter(f => f.endsWith('.html'))) {
    await pg.goto('file://' + path.join(__dirname, f));
    await pg.screenshot({ path: path.join(__dirname, f.replace('.html', '.png')), fullPage: true });
    console.log('wrote', f.replace('.html', '.png'));
  }
  await b.close();
})();
