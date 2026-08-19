const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const jobs = [
    ['https://www.hkmu.edu.hk/REG/reg_ftae/GE/GE_catalog_3cru.pdf', '/tmp/GE_catalog_3cru.pdf'],
    ['https://www.hkmu.edu.hk/REG/reg_ftae/advice_sheet/UG_elective_catalog_3cru.pdf', '/tmp/UG_elective_catalog_3cru.pdf'],
  ];
  const browser = await chromium.launch({ headless: false, ignoreDefaultArgs: ['--enable-automation'], args: ['--disable-blink-features=AutomationControlled'] });
  const ctx = await browser.newContext({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36' });
  const page = await ctx.newPage();
  await page.goto('https://www.hkmu.edu.hk/REG/reg_ftae/advice-on-course-selection/', { waitUntil: 'domcontentloaded', timeout: 45000 });
  for (let i = 0; i < 40; i++) { await page.waitForTimeout(1000); if (!(await page.title()).includes('Just a moment')) { console.log('CF ok'); break; } }
  await page.goto('https://www.hkmu.edu.hk/REG/reg_ftae/advice-on-course-selection/', { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(()=>{});
  await page.waitForTimeout(1500);
  for (const [u, out] of jobs) {
    const b64 = await page.evaluate(async (url) => {
      const r = await fetch(url, { credentials: 'include' });
      if (!r.ok) return 'ERR' + r.status;
      const bytes = new Uint8Array(await r.arrayBuffer());
      let s = ''; for (let i = 0; i < bytes.length; i += 16384) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 16384));
      return btoa(s);
    }, u).catch(e => 'ERR:' + e.message.slice(0, 40));
    if (!b64.startsWith('ERR')) { fs.writeFileSync(out, Buffer.from(b64, 'base64')); console.log('ok', out); }
    else console.log('bad', u, b64);
    await page.waitForTimeout(500);
  }
  await browser.close();
})().catch(e => { console.error('FAIL', e.message); process.exit(1); });
