// fetchReceipts.js
// Usage: node fetchReceipts.js
// Requires: npm i playwright
// Expects: willys-session.json from the login script.

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PRIMARY_URL = 'https://www.willys.se/mina-kop';
const FALLBACK_URLS = [
  'https://www.willys.se/mina-sidor/kop',
  'https://www.willys.se/mitt-konto/mina-kop',
  'https://www.willys.se/mitt-konto/mina-kvitton',
  'https://www.willys.se/mina-sidor/mina-kvitton'
];

const RECEIPT_DIR = path.join(process.cwd(), 'receipts');
if (!fs.existsSync(RECEIPT_DIR)) fs.mkdirSync(RECEIPT_DIR, { recursive: true });

function sanitize(s) {
  return (s || '').toString().replace(/[^\w.-]+/g, '_').slice(0, 120);
}

async function acceptCookies(page) {
  try {
    const btn = page.getByRole('button', {
      name: /Acceptera alla cookies|Godkänn alla|Godkänn|Tillåt alla|Accept all/i
    });
    await btn.waitFor({ state: 'visible', timeout: 3000 });
    await btn.click().catch(() => {});
    await page.waitForTimeout(250);
  } catch {}
}

async function ensureLoggedIn(page) {
  // If we see "Logga in" link, the session is not valid.
  const loginLink = await page.getByRole('link', { name: /Logga in/i }).first().count();
  return loginLink === 0;
}

async function autoScroll(page, maxSteps = 15, pause = 500) {
  let last = 0, stuck = 0;
  for (let i = 0; i < maxSteps; i++) {
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(pause);
    const curr = await page.evaluate(() => document.body.scrollHeight);
    if (curr === last) {
      stuck++;
      if (stuck >= 2) break; // likely no more lazy content
    } else {
      stuck = 0;
      last = curr;
    }
  }
}

async function scrapeReceiptLinks(page) {
  // 1) Direct anchors with /digitalreceipt in href
  const direct = await page.$$eval('a[href*="/digitalreceipt"]', els => els.map(a => a.href));

  // 2) Anything in the DOM that *contains* a /digitalreceipt URL (some sites embed it in data-attrs)
  const fromHTML = await page.evaluate(() => {
    const urls = new Set();
    const rx = /https?:\/\/[^"'<> ]+\/digitalreceipt[^"'<> ]*/gi;
    function scan(node) {
      if (!node) return;
      // attributes
      if (node.attributes) {
        for (const a of node.attributes) {
          const m = (a.value || '').matchAll(rx);
          for (const g of m) urls.add(g[0]);
        }
      }
      // innerHTML text
      if (node.innerHTML) {
        const m = node.innerHTML.matchAll(rx);
        for (const g of m) urls.add(g[0]);
      }
      // children
      for (const c of node.children || []) scan(c);
    }
    scan(document.body);
    return Array.from(urls);
  });

  // Merge + dedupe + normalize
  const all = Array.from(new Set([...direct, ...fromHTML]))
    .filter(u => /\/digitalreceipt/i.test(u));

  return all;
}

function buildFileName(href) {
  try {
    const u = new URL(href);
    const id = sanitize(u.pathname.split('/').pop() || 'receipt');
    const dateParam = sanitize(u.searchParams.get('date') || '');
    const dated = dateParam || '';
    return (dated ? `${dated}__${id}` : id) + '.pdf';
  } catch {
    return `${Date.now()}__receipt.pdf`;
  }
}

(async () => {
  // 1) Start headless with saved session
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    storageState: 'willys-session.json',
    userAgent:
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
  });
  const page = await ctx.newPage();

  // 2) Land on /mina-kop (try fallbacks if needed)
  let landed = null;
  const targets = [PRIMARY_URL, ...FALLBACK_URLS];
  for (const url of targets) {
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await acceptCookies(page);
      if (!(await ensureLoggedIn(page))) {
        console.error('❌ Session is not authenticated. Run the login script first.');
        await browser.close();
        process.exit(1);
      }
      // Give the page a little time to render order cards
      await page.waitForTimeout(1000);
      const links = await scrapeReceiptLinks(page);
      if (links.length > 0 || /mina-kop|mina-sidor|mitt-konto/.test(page.url())) {
        landed = url;
        break;
      }
    } catch {}
  }
  if (!landed) {
    console.error('❌ Could not reach a purchases page. Are you logged in?');
    await browser.close();
    process.exit(1);
  }
  console.log('✅ Purchases page:', landed);

  // 3) Lazy-load more orders
  await autoScroll(page, 18, 600);

  // 4) Collect all receipt links
  let links = await scrapeReceiptLinks(page);

  // Some UIs only render links for visible items. Try a second pass:
  if (links.length < 1) {
    await page.waitForTimeout(800);
    links = await scrapeReceiptLinks(page);
  }

  // 5) Deduplicate and keep only HTTPS
  const unique = Array.from(new Set(
    links.map(u => {
      try { return new URL(u).href; } catch { return null; }
    }).filter(Boolean)
  ));

  console.log(`🔗 Found ${unique.length} receipt link(s).`);

  // 6) Download each PDF using the context's request (preserves cookies)
  let ok = 0, fail = 0;
  for (const href of unique) {
    try {
      const fname = buildFileName(href);
      const outPath = path.join(RECEIPT_DIR, fname);

      const res = await ctx.request.get(href, {
        headers: {
          'Accept': 'application/pdf,*/*',
          'Referer': page.url()
        }
      });
      if (!res.ok()) throw new Error(`HTTP ${res.status()}`);

      const ctype = (res.headers()['content-type'] || '').toLowerCase();
      const buf = Buffer.from(await res.body());

      if (!ctype.includes('pdf') && buf.length < 10_000) {
        console.warn(`⚠️ Unexpected content for ${fname} (type=${ctype}, size=${buf.length}). Saving anyway.`);
      }

      fs.writeFileSync(outPath, buf);
      console.log('💾 Saved:', outPath, `(${buf.length} bytes)`);
      ok++;
    } catch (e) {
      console.error('❌ Failed for', href, e.message);
      fail++;
    }
  }

  console.log(`\nDone. ✅ ${ok} saved, ❌ ${fail} failed. Files in: ${RECEIPT_DIR}`);
  await browser.close();
})();