// services/willys-service/server.js
import express from "express";
import cors from "cors";
import { chromium, request } from "playwright";
import path from "node:path";
import fs from "node:fs";
import fetch from "node-fetch"; // for calling Supabase edge function

// ---------- constants ----------
const PORT = Number(process.env.PORT || process.env.WILLYS_SVC_PORT || 3031);
const LOGIN_URL = "https://www.willys.se/anvandare/inloggning";
const SESSION_PATH = path.resolve(process.cwd(), "willys-session.json");
const SESSION_DIR = path.resolve(process.cwd());

// Supabase edge function config
const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.SUPABASE_ANON_KEY;
const SUPABASE_WILLYS_FUNCTION =
  process.env.SUPABASE_WILLYS_FUNCTION || "store-willys-receipts";
const SUPABASE_WILLYS_FUNCTION_WITH_CONTENT =
  process.env.SUPABASE_WILLYS_FUNCTION_WITH_CONTENT ||
  "store-willys-receipts-with-content";
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const WILLYS_SESSION_TABLE =
  process.env.WILLYS_SESSION_TABLE || "willys_sessions";

// How far back to fetch receipts if caller doesn’t specify
const DEFAULT_RECEIPT_MONTHS = Number(
  process.env.RECEIPT_MONTHS_DEFAULT || 12
);

// ---------- tiny helpers ----------
function sseSend(res, event, data) {
  res.write(`event: ${event}\n`);
  res.write(`data: ${JSON.stringify(data)}\n\n`);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const sessionPathFor = (userId) => {
  if (!userId) return SESSION_PATH;
  const safe = String(userId).replace(/[^\w.-]/g, "_").slice(0, 120);
  return path.join(SESSION_DIR, `willys-session-${safe}.json`);
};

const haveSession = (p = SESSION_PATH) => {
  try {
    return fs.existsSync(p) && fs.statSync(p).size > 0;
  } catch {
    return false;
  }
};

async function safe(fn, label) {
  try {
    return await fn();
  } catch (e) {
    console.log(`[safe:${label}]`, e?.message || e);
    return undefined;
  }
}

// ---------- Supabase session store helpers (per-user storageState) ----------
async function saveSessionToStore(userId, storageState) {
  if (!userId || !SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) return false;
  try {
    const resp = await fetch(`${SUPABASE_URL}/rest/v1/${WILLYS_SESSION_TABLE}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        apikey: SUPABASE_SERVICE_ROLE_KEY,
        Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
        Prefer: "resolution=merge-duplicates",
      },
      body: JSON.stringify({
        user_id: userId,
        storage_state: storageState,
        updated_at: new Date().toISOString(),
      }),
    });
    if (!resp.ok) {
      const t = await resp.text();
      console.warn(
        `[willys-session] Failed to save session for ${userId}: ${resp.status} ${t.slice(
          0,
          200
        )}`
      );
      return false;
    }
    return true;
  } catch (e) {
    console.warn(
      `[willys-session] Error saving session for ${userId}:`,
      e?.message || e
    );
    return false;
  }
}

async function loadSessionFromStore(userId) {
  if (!userId || !SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) return null;
  try {
    const url = `${SUPABASE_URL}/rest/v1/${WILLYS_SESSION_TABLE}?user_id=eq.${encodeURIComponent(
      userId
    )}&select=storage_state&limit=1`;
    const resp = await fetch(url, {
      headers: {
        apikey: SUPABASE_SERVICE_ROLE_KEY,
        Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
        Accept: "application/json",
      },
    });
    if (!resp.ok) {
      const t = await resp.text();
      console.warn(
        `[willys-session] Failed to load session for ${userId}: ${resp.status} ${t.slice(
          0,
          200
        )}`
      );
      return null;
    }
    const data = await resp.json();
    return data?.[0]?.storage_state || null;
  } catch (e) {
    console.warn(
      `[willys-session] Error loading session for ${userId}:`,
      e?.message || e
    );
    return null;
  }
}

async function getStorageStateForUser(userId, sessionPath) {
  // Prefer Supabase store; fall back to file.
  const stateFromDb = await loadSessionFromStore(userId);
  if (stateFromDb) return stateFromDb;

  if (sessionPath && haveSession(sessionPath)) {
    try {
      const txt = fs.readFileSync(sessionPath, "utf8");
      return JSON.parse(txt);
    } catch {}
  }
  return null;
}

// ---------- date helpers (for API range) ----------
function pad2(n) {
  return String(n).padStart(2, "0");
}

function toYmd(d) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function todayYmd() {
  return toYmd(new Date());
}

function fromFirstDayForMonthsBuffered(months) {
  const m = Math.max(1, Number(months || 1));
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(1);
  d.setMonth(d.getMonth() - (m - 1));
  d.setDate(d.getDate() - 2); // 2-day safety buffer
  return toYmd(d);
}

// ---------- Willys API helpers using stored session ----------
async function createWillysApiContext({
  userId = null,
  sessionPath = SESSION_PATH,
} = {}) {
  const storageState = await getStorageStateForUser(userId, sessionPath);
  if (!storageState && !haveSession(sessionPath)) {
    throw new Error("No saved Willys session (storage missing)");
  }

  return await request.newContext({
    baseURL: "https://www.willys.se",
    storageState: storageState || sessionPath,
    extraHTTPHeaders: {
      accept: "application/json, text/plain, */*",
      "accept-language": "sv-SE,sv;q=0.9,en;q=0.8",
      referer: "https://www.willys.se/mina-kop",
    },
  });
}

async function getJsonWithRetry(req, absUrl, retries = 3) {
  let attempt = 0;
  let lastErr = null;

  while (attempt <= retries) {
    try {
      const resp = await req.get(absUrl, {
        headers: {
          accept: "application/json, text/plain, */*",
          referer: "https://www.willys.se/mina-kop",
          "accept-language": "sv-SE,sv;q=0.9,en;q=0.8",
        },
      });

      if (!resp.ok()) {
        throw new Error(`HTTP ${resp.status()} for ${absUrl}`);
      }

      const text = await resp.text();
      const ctype = (resp.headers()["content-type"] || "").toLowerCase();

      if (ctype.includes("text/html") || /^\s*<!doctype html/i.test(text)) {
        throw new Error(`Expected JSON, got HTML for ${absUrl}`);
      }

      return JSON.parse(text);
    } catch (e) {
      lastErr = e;
      const backoff = Math.min(2000, 300 * attempt);
      if (attempt < retries && backoff) {
        await sleep(backoff);
      }
    }
    attempt++;
  }

  throw lastErr || new Error("Unknown API error");
}

/**
 * Call /axfood/rest/account/pagedOrderBonusCombined and build
 * receipt descriptors with digitalreceipt URLs.
 */
async function fetchReceiptDescriptors(
  req,
  { fromDate, toDate, pageSize = 100, maxPages = null, retries = 3 } = {}
) {
  const BASE_URL = "https://www.willys.se";
  const out = [];

  let page = 0;
  let numberOfPages = 1;

  const isYmd = (s) =>
    typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s);

  const toYmdSafe = (v) => {
    try {
      const d = new Date(v);
      if (Number.isNaN(d.getTime())) return null;
      return toYmd(d);
    } catch {
      return null;
    }
  };

  while (true) {
    if (maxPages && page >= maxPages) {
      console.log(
        `[willys-service] Stopping at maxPages=${maxPages} (page=${page})`
      );
      break;
    }

    const rel =
      `/axfood/rest/account/pagedOrderBonusCombined` +
      `?fromDate=${fromDate}&toDate=${toDate}` +
      `&currentPage=${page}&pageSize=${Math.min(100, pageSize)}`;

    const abs = BASE_URL + rel;

    const json = await getJsonWithRetry(req, abs, retries);

    const results = json?.loyaltyTransactionsInPage || [];
    numberOfPages = json?.paginationData?.numberOfPages ?? 1;
    const serverPage = json?.paginationData?.currentPage ?? page;

    for (const t of results) {
      if (!t?.digitalReceiptAvailable || !t?.digitalReceiptReference) continue;

      const reference = String(t.digitalReceiptReference || "");

      // Derive datePart
      let datePart = null;
      const refPrefix = reference.includes("T")
        ? reference.split("T")[0]
        : null;

      if (refPrefix && isYmd(refPrefix)) {
        datePart = refPrefix;
      } else {
        datePart =
          toYmdSafe(t.bookingDate) ||
          toYmdSafe(t.orderDate) ||
          toYmdSafe(t.creationTime) ||
          null;
      }

      const storeId =
        t.storeCustomerId ||
        t.storeId ||
        (t.store && (t.store.id || t.store.code)) ||
        null;

      const source = t.receiptSource || "aws";

      const memberCard =
        t.memberCardNumber ||
        t.cardNumber ||
        t.memberCard ||
        null;

      if (!datePart || !storeId || !memberCard) continue;

      const digitalUrl =
        `${BASE_URL}/axfood/rest/order/orders/digitalreceipt/${encodeURIComponent(
          reference
        )}` +
        `?date=${encodeURIComponent(datePart)}` +
        `&storeId=${encodeURIComponent(storeId)}` +
        `&source=${encodeURIComponent(source)}` +
        `&memberCardNumber=${encodeURIComponent(memberCard)}`;

      out.push({
        receipt_date: datePart,
        store_name: t.store?.name || "Willys",
        digitalreceipt_url: digitalUrl,
        reference,
      });
    }

    console.log(
      `[willys-service] Page ${serverPage + 1}/${numberOfPages} → ${results.length} row(s), total descriptors=${out.length}`
    );

    if (serverPage + 1 >= numberOfPages) break;
    page = serverPage + 1;
  }

  // de-duplicate by URL just in case
  const seen = new Set();
  return out.filter((r) => {
    if (seen.has(r.digitalreceipt_url)) return false;
    seen.add(r.digitalreceipt_url);
    return true;
  });
}

// ---------- helper to call Supabase edge function ----------
async function forwardReceiptsToSupabase({ supabaseUserId, receipts }) {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    throw new Error("Missing SUPABASE_URL or SUPABASE_ANON_KEY in env");
  }

  const fnUrl = `${SUPABASE_URL}/functions/v1/${SUPABASE_WILLYS_FUNCTION}`;
  console.log("[supabase] Calling edge function:", fnUrl);

  const resp = await fetch(fnUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: SUPABASE_ANON_KEY,
      Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
    },
    body: JSON.stringify({
      supabase_user_id: supabaseUserId,
      receipts,
    }),
  });

  const text = await resp.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(
      `Supabase function returned non-JSON (${resp.status}): ${text.slice(
        0,
        200
      )}`
    );
  }

  if (!resp.ok) {
    throw new Error(
      `Supabase function error ${resp.status}: ${
        data.error || text.slice(0, 200)
      }`
    );
  }

  return data; // e.g. { receipts_imported, items_count, recent_items, ... }
}

// Helper to forward receipts with content to a dedicated edge function
async function forwardReceiptsWithContentToSupabase({ supabaseUserId, receipts }) {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    throw new Error("Missing SUPABASE_URL or SUPABASE_ANON_KEY in env");
  }

  const fnUrl = `${SUPABASE_URL}/functions/v1/${SUPABASE_WILLYS_FUNCTION_WITH_CONTENT}`;
  console.log("[supabase] Calling edge function (with content):", fnUrl);

  const resp = await fetch(fnUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: SUPABASE_ANON_KEY,
      Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
    },
    body: JSON.stringify({
      supabase_user_id: supabaseUserId,
      receipts,
    }),
  });

  const text = await resp.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(
      `Supabase function (with content) returned non-JSON (${resp.status}): ${text.slice(
        0,
        200
      )}`
    );
  }

  if (!resp.ok) {
    throw new Error(
      `Supabase function (with content) error ${resp.status}: ${
        data.error || text.slice(0, 200)
      }`
    );
  }

  return data;
}

// ---------- download receipt bodies with saved session ----------
async function fetchReceiptBodies({ storageState = null, sessionPath = null }, descriptors) {
  const ctx = await request.newContext({
    baseURL: "https://www.willys.se",
    storageState: storageState || sessionPath,
    extraHTTPHeaders: {
      accept: "application/json, text/plain, */*",
      referer: "https://www.willys.se/mina-kop",
      "accept-language": "sv-SE,sv;q=0.9,en;q=0.8",
    },
  });

  const out = [];
  for (const desc of descriptors) {
    try {
      const resp = await ctx.get(desc.digitalreceipt_url, {
        headers: {
          accept: "application/pdf, text/html, */*",
          referer: "https://www.willys.se/mina-kop",
          "accept-language": "sv-SE,sv;q=0.9,en;q=0.8",
        },
      });
      const ctype = resp.headers()["content-type"] || "application/octet-stream";
      const buf = Buffer.from(await resp.body());
      out.push({
        ...desc,
        content_type: ctype,
        content_base64: buf.toString("base64"),
        byte_length: buf.length,
      });
    } catch (e) {
      console.error(
        `[willys-service] Failed to download receipt ${desc.reference || desc.digitalreceipt_url}:`,
        e?.message || e
      );
    }
  }

  await ctx.dispose();
  return out;
}

// ---------- per-user helpers ----------
function resolveUserId(req) {
  return (
    req?.query?.supabase_user_id ||
    req?.query?.user_id ||
    req?.body?.supabase_user_id ||
    req?.headers["x-supabase-user-id"] ||
    null
  );
}

// ---------- page utilities (QR login flow) ----------
async function clickAnyText(page, patterns, scope) {
  const root = scope || page;
  for (const re of patterns) {
    const tries = [
      () => root.getByRole("button", { name: re }).first(),
      () => root.getByRole("link", { name: re }).first(),
      () => root.getByText(re).first(),
      () =>
        root
          .locator(
            `xpath=//*[contains(normalize-space(.), ${JSON.stringify(
              re.source.replace(/\\s\+/g, " ")
            )})]`
          )
          .first(),
    ];
    for (const mk of tries) {
      try {
        const loc = mk();
        if (await loc.isVisible({ timeout: 500 }).catch(() => false)) {
          await loc.click({ timeout: 1200 });
          return true;
        }
      } catch {}
    }
  }
  return false;
}

async function closeCookies(page) {
  const candidates = [
    page.locator("#onetrust-accept-btn-handler").first(),
    page.locator("#onetrust-reject-all-handler").first(),
    page.getByRole("button", { name: /Acceptera|Godkänn|Tillåt/i }).first(),
    page.getByRole("button", { name: /Avvisa|Neka/i }).first(),
  ];
  for (const loc of candidates) {
    try {
      if (await loc.isVisible({ timeout: 600 })) {
        await loc.click({ timeout: 1200 });
        return true;
      }
    } catch {}
  }
  // hide any banner if still around
  await safe(
    () =>
      page.addStyleTag({
        content: `
        #onetrust-banner-sdk, .onetrust-pc-dark-filter, [id*="cookie" i], [class*="cookie" i], [class*="consent" i] {
          visibility: hidden !important;
          opacity: 0 !important;
          pointer-events: none !important;
        }
      `,
      }),
    "injectCookieHideCss"
  );
  return false;
}

async function switchToMobiltBankID(page, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const dlg = page.locator('div[role="dialog"]').first();
    const scope = (await dlg.isVisible().catch(() => false)) ? dlg : page;

    const ok = await clickAnyText(scope, [
      /^Mobilt\s*BankID$/i,
      /Mobilt\s*BankID/i,
    ]);
    if (ok) return true;

    try {
      const candidate = scope
        .locator('button, [role="button"], [role="tab"], a')
        .filter({ hasText: /Mobilt\s*BankID/i })
        .first();

      if (await candidate.isVisible({ timeout: 800 }).catch(() => false)) {
        await candidate.click({ timeout: 1500 });
        return true;
      }
    } catch {}

    try {
      const clicked = await page.evaluate(() => {
        const re = /mobilt\s*bankid/i;
        const isVisible = (el) => {
          if (!el) return false;
          const style = window.getComputedStyle(el);
          if (
            style.display === "none" ||
            style.visibility === "hidden" ||
            style.opacity === "0"
          )
            return false;
          const rect = el.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        };

        const candidates = Array.from(
          document.querySelectorAll(
            "button,[role=button],[role=tab],a,div,span"
          )
        );
        for (const el of candidates) {
          if (!isVisible(el)) continue;
          const text = (el.textContent || "").trim();
          if (re.test(text)) {
            el.click();
            return true;
          }
        }
        return false;
      });
      if (clicked) return true;
    } catch {}

    await page.waitForTimeout(400);
  }

  return false;
}

async function clickToShowQR(page) {
  const dlg = page.locator('div[role="dialog"]').first();
  const scope = (await dlg.isVisible().catch(() => false)) ? dlg : page;

  let ok = await clickAnyText(scope, [
    /Mobilt\s*BankID\s*på\s*annan\s*enhet/i,
    /Logga in med Mobilt BankID/i,
    /Öppna BankID-appen/i,
  ]);
  if (ok) return true;

  try {
    await page.evaluate(() => {
      const el = document.querySelector('div[role="dialog"]');
      if (el) el.scrollTop = el.scrollHeight;
    });
  } catch {}

  ok = await clickAnyText(scope, [/annan enhet/i, /\bQR\b/i, /BankID/i]);
  return ok;
}

async function waitForQrHints(page, timeoutMs = 15000) {
  const until = Date.now() + timeoutMs;
  while (Date.now() < until) {
    const dlg = page.locator('div[role="dialog"]').first();
    if (await dlg.isVisible().catch(() => false)) {
      const hasCanvas = await dlg.locator("canvas").count().catch(() => 0);
      if (hasCanvas > 0) return { dom: true, type: "canvas" };
      const imgs = await dlg.locator("img").elementHandles().catch(() => []);
      if (imgs?.length) {
        const info = await Promise.all(
          imgs.map((h) =>
            h.evaluate((img) => ({
              src: img.src || "",
              nw: img.naturalWidth || 0,
              nh: img.naturalHeight || 0,
            }))
          )
        );
        if (info.some((x) => x.nw >= 150 && x.nh >= 150))
          return { dom: true, type: "img" };
      }
    }
    const hasSeenQr = await page
      .evaluate(() => !!window.__WL_LAST_QR_TOKEN__)
      .catch(() => false);
    if (hasSeenQr) return { net: true, type: "token" };
    await sleep(300);
  }
  return null;
}

function attachNetworkTaps(page, onEvent) {
  page.on("response", async (resp) => {
    try {
      const url = resp.url();
      if (
        /\/axfood\/rest\/checkout\/bankid\/qr\b/i.test(url) &&
        resp.status() === 200
      ) {
        const txt = await resp.text();
        if (txt && /^bankid\./i.test(txt)) {
          await page.evaluate((t) => {
            window.__WL_LAST_QR_TOKEN__ = t;
          }, txt);
          onEvent?.("qr-token", { token: txt });
        }
      }
      if (
        /\/axfood\/rest\/checkout\/bankid\/collect-login\b/i.test(url) &&
        resp.status() === 200
      ) {
        const json = await resp.json().catch(() => null);
        if (json?.status === "COMPLETE") {
          onEvent?.("done", { ok: true, result: json });
        } else if (json?.status && json?.hintCode) {
          onEvent?.("collect", {
            status: json.status,
            hintCode: json.hintCode,
          });
        }
      }
    } catch {}
  });
}

// ---------- core runner ----------
async function runBankIdLogin({
  headless = true,
  timeoutMs = 180_000,
  userId = null,
  sessionPath = SESSION_PATH,
  onEvent,
} = {}) {
  let browser, context, page;
  const log = (m) => onEvent?.("log", { msg: m });

  try {
    log?.("Launching Playwright headless...");
    browser = await chromium.launch({
      headless,
      args: ["--disable-dev-shm-usage"],
    });
    context = await browser.newContext({
      viewport: { width: 420, height: 640 },
    });

    context.on("request", async (req) => {
      try {
        if (req.resourceType() === "font") await req.abort();
      } catch {}
    });

    page = await context.newPage();
    attachNetworkTaps(page, (evt, data) => onEvent?.(evt, data));

    await page.goto(LOGIN_URL, { waitUntil: "domcontentloaded" });
    log?.("Opened /anvandare/inloggning");

    await closeCookies(page);
    log?.("Cookies: any visible banner has been handled/hidden");

    const switched = await switchToMobiltBankID(page);
    if (!switched) {
      onEvent?.("error", {
        msg: "Could not switch to 'Mobilt BankID' tab",
      });
      throw new Error("BankID tab not found");
    }
    log?.("Switched to Mobilt BankID");

    const clicked = await clickToShowQR(page);
    if (!clicked) {
      onEvent?.("error", {
        msg: "Could not find QR/annan enhet or 'Logga in med Mobilt BankID' button",
      });
    } else {
      log?.("Clicked login/QR CTA");
    }

    const hint = await waitForQrHints(page, 15_000);
    if (hint) log?.(`QR hint: ${JSON.stringify(hint)}`);

    await safe(
      () =>
        page.addStyleTag({
          content: `
          button[aria-label="Stäng"],
          button[aria-label="Close"],
          svg[aria-label="Stäng"],
          svg[aria-label="Close"] {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
          }
        `,
        }),
      "hideCloseButton"
    );

    const dlg = page.locator('div[role="dialog"]').first();
    const snapshotTimer = setInterval(async () => {
      try {
        if (!(await dlg.isVisible({ timeout: 200 }).catch(() => false))) return;
        const box = await dlg.boundingBox();
        if (!box) return;
        const png = await page.screenshot({
          type: "png",
          fullPage: false,
          clip: {
            x: Math.max(0, box.x - 2),
            y: Math.max(0, box.y - 2),
            width: Math.max(1, box.width + 4),
            height: Math.max(1, box.height + 4),
          },
        });
        onEvent?.("qr-image", {
          image: `data:image/png;base64,${png.toString("base64")}`,
        });
      } catch {}
    }, 1500);

    const started = Date.now();
    let final;
    const waiter = new Promise((resolve) => {
      const check = (evt, data) => {
        if (evt === "done" && data?.ok) {
          final = { ok: true, result: data.result };
          resolve();
        }
      };
      attachNetworkTaps(page, check);
      const i = setInterval(async () => {
        if (final) {
          clearInterval(i);
          return;
        }
        if (Date.now() - started > timeoutMs) {
          final = {
            ok: false,
            error: "Timed out waiting for BankID COMPLETE",
          };
          resolve();
        }
      }, 500);
    });

    await waiter;
    clearInterval(snapshotTimer);

    if (final?.ok) {
      log?.("Login COMPLETE → saving session.");
      await safe(() => fs.mkdirSync(path.dirname(sessionPath), { recursive: true }), "ensureSessionDir");
      const stateObj = await safe(() => context.storageState(), "getStateObj");
      await safe(() => context.storageState({ path: sessionPath }), "saveSessionFile");
      if (stateObj && userId) {
        await saveSessionToStore(userId, stateObj);
      }
    }

    await safe(() => browser.close(), "closeBrowser");
    onEvent?.(
      "done",
      final?.ok ? { ok: true, result: final.result } : { ok: false }
    );
    return final?.ok
      ? final
      : { ok: false, error: final?.error || "Unknown error" };
  } catch (err) {
    await safe(() => browser?.close(), "closeBrowserOnError");
    onEvent?.("error", { msg: err?.message || String(err) });
    return { ok: false, error: err?.message || String(err) };
  }
}

// ---------- server ----------
const app = express();
app.use(cors({ origin: "*" }));
app.use(express.json());

// --- SSE QR stream ---
app.get("/willys/login-stream/qr", async (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.flushHeaders?.();

  const userId = resolveUserId(req);
  const sessionPath = sessionPathFor(userId);

  const end = () => {
    try {
      res.end();
    } catch {}
  };

  const result = await runBankIdLogin({
    headless: true,
    userId,
    sessionPath,
    onEvent: (evt, data) => {
      sseSend(res, evt, data);
      if (evt === "done" && (data?.ok || data?.error)) end();
      if (evt === "error") end();
    },
  }).catch(() => null);

  if (result && !res.writableEnded) {
    sseSend(res, "done", result);
    end();
  }
});

// --- JSON login endpoint (no SSE) ---
app.post("/willys/login", async (req, res) => {
  const timeoutMs = Number(req.body?.timeoutMs ?? 180_000);
  const userId = resolveUserId(req);
  const sessionPath = sessionPathFor(userId);
  const r = await runBankIdLogin({
    headless: true,
    timeoutMs,
    userId,
    sessionPath,
    onEvent: (evt, data) => {
      if (evt === "log") console.log(`[willys-login] ${data.msg}`);
      if (evt === "collect")
        console.log(`[collect] ${data.status} ${data.hintCode}`);
    },
  });
  if (r.ok) return res.json(r);
  return res.status(504).json(r);
});

// --- Session probe using saved storage ---
app.get("/willys/me", async (_req, res) => {
  const userId = resolveUserId(_req);
  const sessionPath = sessionPathFor(userId);

  try {
    const storageState = await getStorageStateForUser(userId, sessionPath);
    if (!storageState && !haveSession(sessionPath)) {
      return res.status(401).json({ ok: false, error: "No saved session yet" });
    }

    const api = await request.newContext({
      baseURL: "https://www.willys.se",
      storageState: storageState || sessionPath,
      extraHTTPHeaders: { accept: "application/json, text/plain, */*" },
    });

    const r = await api.get("/axfood/rest/customer");
    const text = await r.text();
    const ct = r.headers()["content-type"] || "";
    const body = ct.includes("application/json") ? JSON.parse(text) : text;

    res.status(200).json({ ok: r.ok(), status: r.status(), body });
    await api.dispose();
  } catch (e) {
    res.status(500).json({ ok: false, error: e?.message || String(e) });
  }
});

// --- NEW: fetch Willys receipts and forward to Supabase edge ---
app.post("/willys/fetch-receipts", async (req, res) => {
  try {
    const userId = resolveUserId(req);
    const sessionPath = sessionPathFor(userId);

    const storageState = await getStorageStateForUser(userId, sessionPath);

    if (!storageState && !haveSession(sessionPath)) {
      return res.status(401).json({
        success: false,
        error: "No Willys session. Run QR login first.",
      });
    }

    const { supabase_user_id, months, pageSize, maxPages } = req.body || {};

    if (!supabase_user_id) {
      return res.status(400).json({
        success: false,
        error: "supabase_user_id is required",
      });
    }

    const rangeMonths = Number(months || DEFAULT_RECEIPT_MONTHS);
    const fromDate = fromFirstDayForMonthsBuffered(rangeMonths);
    const toDate = todayYmd();

    console.log(
      `[willys-service] Fetching receipts range ${fromDate} → ${toDate} (months=${rangeMonths})`
    );

    const ctx = await createWillysApiContext({ userId, sessionPath });
    const descriptors = await fetchReceiptDescriptors(ctx, {
      fromDate,
      toDate,
      pageSize: Number(pageSize || 100),
      maxPages: maxPages ? Number(maxPages) : null,
      retries: 3,
    });
    await ctx.dispose();

    console.log(
      `[willys-service] Collected ${descriptors.length} receipt descriptor(s)`
    );

    const supabaseResponse = await forwardReceiptsToSupabase({
      supabaseUserId: supabase_user_id,
      receipts: descriptors,
    });

    return res.json({
      success: true,
      ...supabaseResponse,
      meta: {
        descriptorsCount: descriptors.length,
        fromDate,
        toDate,
      },
    });
  } catch (err) {
    console.error("[/willys/fetch-receipts] Error:", err?.message || err);
    return res.status(500).json({
      success: false,
      error: err?.message || "Internal error while fetching/storing receipts",
    });
  }
});

// --- NEW: fetch receipts and include content (for server-side ingestion) ---
app.post("/willys/fetch-receipts-with-content", async (req, res) => {
  try {
    const userId = resolveUserId(req);
    const sessionPath = sessionPathFor(userId);

    const storageState = await getStorageStateForUser(userId, sessionPath);

    if (!storageState && !haveSession(sessionPath)) {
      return res.status(401).json({
        success: false,
        error: "No Willys session. Run QR login first.",
      });
    }

    const { supabase_user_id, months, pageSize, maxPages } = req.body || {};

    if (!supabase_user_id) {
      return res.status(400).json({
        success: false,
        error: "supabase_user_id is required",
      });
    }

    const rangeMonths = Number(months || DEFAULT_RECEIPT_MONTHS);
    const fromDate = fromFirstDayForMonthsBuffered(rangeMonths);
    const toDate = todayYmd();

    console.log(
      `[willys-service] (with-content) Fetching receipts range ${fromDate} → ${toDate} (months=${rangeMonths})`
    );

    const ctx = await createWillysApiContext({ userId, sessionPath });
    const descriptors = await fetchReceiptDescriptors(ctx, {
      fromDate,
      toDate,
      pageSize: Number(pageSize || 100),
      maxPages: maxPages ? Number(maxPages) : null,
      retries: 3,
    });
    await ctx.dispose();

    const receipts = await fetchReceiptBodies(
      { storageState, sessionPath },
      descriptors
    );

    let supabaseResponse = null;
    try {
      supabaseResponse = await forwardReceiptsWithContentToSupabase({
        supabaseUserId: supabase_user_id,
        receipts,
      });
    } catch (err) {
      console.warn(
        "[willys-service] Forward with content failed (edge function may not be deployed):",
        err?.message || err
      );
    }

    return res.json({
      success: true,
      descriptorsCount: descriptors.length,
      receiptsCount: receipts.length,
      meta: { fromDate, toDate },
      forwarded: Boolean(supabaseResponse),
      supabase: supabaseResponse || null,
      receipts: supabaseResponse ? undefined : receipts,
    });
  } catch (err) {
    console.error("[/willys/fetch-receipts-with-content] Error:", err?.message || err);
    return res.status(500).json({
      success: false,
      error: err?.message || "Internal error while fetching receipts with content",
    });
  }
});

app.listen(PORT, () => {
  console.log(`[willys-service] Running → http://localhost:${PORT}`);
});
