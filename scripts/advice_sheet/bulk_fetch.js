const { chromium } = require('playwright');
const fs = require('fs');
const listFile = process.argv[2], delayMs = parseInt(process.argv[3] || '400');
const GATE = 'https://www.hkmu.edu.hk/REG/reg_ftae/advice-on-course-selection/';
(async () => {
  const items = JSON.parse(fs.readFileSync(listFile, 'utf8'));
  const browser = await chromium.launch({ headless: false, ignoreDefaultArgs: ['--enable-automation'], args: ['--disable-blink-features=AutomationControlled'] });
  const ctx = await browser.newContext({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36', viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.goto(GATE, { waitUntil: 'domcontentloaded', timeout: 45000 });
  for (let i = 0; i < 40; i++) {
    await page.waitForTimeout(1000);
    if (!(await page.title()).includes('Just a moment')) { console.log('CF passed at', i+1, 's'); break; }
  }
  await page.goto(GATE, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(()=>{});
  await page.waitForTimeout(1500);
  const inPageFetch = async (url) => page.evaluate(async (u) => {
    try {
      const ac = new AbortController(); const t = setTimeout(() => ac.abort(), 15000);
        const r = await fetch(u, { credentials: 'include', signal: ac.signal });
      if (!r.ok) return 'ERR' + r.status;
      const bytes = new Uint8Array(await r.arrayBuffer());
      let s = ''; for (let i = 0; i < bytes.length; i += 8192) s += String.fromCharCode.apply(null, bytes.subarray(i, i+8192));
      clearTimeout(t); return btoa(s);
    } catch (e) { return 'ERR:' + e.message.slice(0, 40); }
  }, url);
  let ok = 0, skip = 0; const bad = [];
  for (const it of items) {
    if (fs.existsSync(it.out) && fs.statSync(it.out).size > 10000) { skip++; continue; }
    const withTimeout = (p, ms) => Promise.race([p, new Promise(_ => setTimeout(() => _('ERR:timeout'), ms))]);
    let b64 = await withTimeout(inPageFetch(it.url), 25000).catch(async e => {
      await page.goto(GATE, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(()=>{});
      await page.waitForTimeout(2000);
      return withTimeout(inPageFetch(it.url), 25000);
    }).catch(e => 'ERR:retry ' + String(e).slice(0,30));
    if (typeof b64 === 'string' && !b64.startsWith('ERR')) { fs.writeFileSync(it.out, Buffer.from(b64, 'base64')); ok++; }
    else bad.push(it.url.split('/').pop() + ' ' + b64);
    await page.waitForTimeout(delayMs);
  }
  console.log('ok:', ok, 'skip:', skip, 'bad:', bad.length, bad.slice(0, 5));
  await browser.close();
})().catch(e => { console.error('FAIL:', e.message); process.exit(1); });
