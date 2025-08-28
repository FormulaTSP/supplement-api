// willysLogin.js
// Usage: node willysLogin.js
// Requires: npm i playwright

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

/** ====== CONFIG (tweak if needed) ======================================= **/
const LOGIN_URL = 'https://www.willys.se/anvandare/inloggning';
const PRIMARY_RECEIPTS_URL = 'https://www.willys.se/mina-kop';
const FALLBACK_RECEIPTS_URLS = [
  PRIMARY_RECEIPTS_URL,
  'https://www.willys.se/mina-sidor/kop',
  'https://www.willys.se/mitt-konto/mina-kop',
  'https://www.willys.se/mitt-konto/mina-kvitton',
  'https://www.willys.se/mina-sidor/mina-kvitton'
];
// How long to wait for BankID success/redirect before we force navigation:
const MAX_AUTH_WAIT_MS = 45_000; // shorter than before (was 180_000)
/** ======================================================================= **/

// ---- debug screenshots -------------------------------------------------------
const OUT_DIR = path.join(process.cwd(), 'login-debug');
if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

async function snap(page, name) {
  const p = path.join(OUT_DIR, `${Date.now()}-${name}.png`);
  try { await page.screenshot({ path: p, fullPage: true }); } catch {}
  console.log('📸', name, '→', p);
}

// ---- helpers ----------------------------------------------------------------
async function acceptCookies(page) {
  try {
    const btn = page.getByRole('button', {
      name: /Acceptera alla cookies|Godkänn alla|Godkänn|Tillåt alla|Accept all/i
    });
    await btn.waitFor({ state: 'visible', timeout: 4000 });
    await btn.click().catch(() => {});
    await page.waitForTimeout(150);
    await btn.click().catch(() => {});
    await page.waitForTimeout(250);
  } catch {}
}

async function openLoginDialog(page) {
  const dlg = page.getByRole('dialog').first();
  if (await dlg.isVisible().catch(() => false)) return;

  const triggers = [
    page.getByRole('link', { name: /Logga in/i }),
    page.getByRole('button', { name: /Logga in/i }),
    page.locator('[data-testid*="login"]')
  ];
  for (const t of triggers) {
    if (await t.count()) {
      try { await t.first().click({ timeout: 3000 }); } catch {}
      if (await dlg.isVisible().catch(() => false)) break;
    }
  }
}

async function selectBankIdTab(page) {
  const dlg = page.getByRole('dialog').first();
  await dlg.getByRole('tablist').waitFor({ state: 'visible', timeout: 8000 });

  const bankIdTab = dlg.getByRole('tab', { name: /Mobilt\s*BankID/i });
  await bankIdTab.waitFor({ state: 'visible', timeout: 4000 });

  await bankIdTab.click({ timeout: 2000 }).catch(async () => {
    await bankIdTab.click({ force: true });
  });

  await dlg.getByRole('button', { name: /Logga in med BankID|BankID/i })
           .waitFor({ state: 'visible', timeout: 6000 })
           .catch(() => {});
}

async function clickBankIdLogin(page) {
  const dlg = (await page.getByRole('dialog').count())
    ? page.getByRole('dialog').first()
    : page;

  const cta = dlg.getByRole('button', {
    name: /Logga in med BankID|Mobilt BankID|BankID|Fortsätt/i
  });

  await cta.waitFor({ state: 'visible', timeout: 8000 });
  await cta.click().catch(async () => { await cta.click({ force: true }); });

  // Capture popup if the flow spawns one
  const popupPromise = page.context().waitForEvent('page').catch(() => null);
  const popup = await Promise.race([
    popupPromise,
    page.waitForTimeout(1500).then(() => null)
  ]);
  if (popup) await popup.waitForLoadState('domcontentloaded').catch(() => {});
}

async function isAuthenticated(page) {
  const headerAccount = await page.getByRole('link', { name: /Mitt konto|Logga ut/i }).first().count();
  const loginStillThere = await page.getByRole('link', { name: /Logga in/i }).first().count();
  const urlLooksAuthed = /mitt-konto|mina-sidor|mina-kop/i.test(page.url());
  return headerAccount > 0 || urlLooksAuthed || loginStillThere === 0;
}

async function looksLikeReceipts(page) {
  const markers = await page.locator('text=/Mina\\s+(köp|kvitton)/i').first().count();
  const receiptLink = await page.locator('a[href*="/digitalreceipt"]').first().count();
  // On /mina-kop Willys often renders headings like "Mina köp" and order lists
  const orderCard = await page.locator('[href*="digitalreceipt"], [data-testid*="order"], a:has-text("Kvitto")').first().count();
  return markers > 0 || receiptLink > 0 || orderCard > 0;
}

// ---- main -------------------------------------------------------------------
(async () => {
  const browser = await chromium.launch({
    headless: false,
    args: ['--disable-blink-features=AutomationControlled']
  });
  const ctx = await browser.newContext({
    viewport: { width: 1400, height: 900 },
    userAgent:
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36'
  });
  const page = await ctx.newPage();

  try {
    console.log('→ Go to login URL:', LOGIN_URL);
    await page.goto(LOGIN_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await acceptCookies(page);
    await snap(page, 'login-arrived');

    await openLoginDialog(page);

    // Optional: log the tabs we see for quick debugging
    try {
      const tabs = await page.getByRole('tab').allTextContents();
      console.log('Tabs rendered:', tabs);
    } catch {}

    await selectBankIdTab(page);
    await clickBankIdLogin(page);
    console.log('⏳ Approve in BankID...');
    await snap(page, 'after-bankid-click');

    // Shorter wait for auth. As soon as we think we're authed, jump to /mina-kop
    await Promise.race([
      page.waitForURL(/mitt-konto|mina-sidor|mina-kop/i, { timeout: MAX_AUTH_WAIT_MS }).catch(() => {}),
      page.getByRole('link', { name: /Mitt konto|Logga ut/i })
          .waitFor({ state: 'visible', timeout: MAX_AUTH_WAIT_MS }).catch(() => {})
    ]);

    const authed = await isAuthenticated(page);
    console.log('Auth state:', authed ? '✅ authenticated (heuristic)' : '❓ not confirmed');

    // Always try the primary target first
    console.log('→ Navigating to receipts (primary):', PRIMARY_RECEIPTS_URL);
    await page.goto(PRIMARY_RECEIPTS_URL, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await acceptCookies(page);
    await page.waitForTimeout(500);

    let reached = await looksLikeReceipts(page);

    // If primary didn’t render receipts markers, try fallbacks briefly
    for (let pass = 0; pass < 2 && !reached; pass++) {
      for (const url of FALLBACK_RECEIPTS_URLS) {
        if (url === PRIMARY_RECEIPTS_URL) continue;
        try {
          console.log('→ Fallback receipts URL:', url);
          await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
          await acceptCookies(page);
          await page.waitForTimeout(400);
          if (await looksLikeReceipts(page)) { reached = true; break; }
        } catch {}
      }
    }

    await snap(page, reached ? 'receipts-detected' : 'receipts-not-detected');

    // Persist session for reuse
    const storage = await ctx.storageState();
    const storagePath = path.join(process.cwd(), 'willys-session.json');
    fs.writeFileSync(storagePath, JSON.stringify(storage, null, 2));
    console.log('💾 Session saved to', storagePath);
  } catch (err) {
    console.error('❌ Unhandled error:', err);
    await snap(page, 'error');
  } finally {
    await browser.close();
    console.log('✅ Done.');
  }
})();