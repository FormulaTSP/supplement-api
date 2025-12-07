// services/willys-service/server.js
import express from "express";
import cors from "cors";
import { chromium, request } from "playwright";
import path from "node:path";
import fs from "node:fs";
import fetch from "node-fetch"; // for calling Supabase edge function
import crypto from "node:crypto";
import { extractPdfText } from "./scripts/pdf_extract.js";
import { parseReceiptText } from "./lib/willys_parse.js";
import qrcode from "qrcode";

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
  process.env.SUPABASE_WILLYS_FUNCTION_WITH_CONTENT || null;
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const WILLYS_SESSION_TABLE =
  process.env.WILLYS_SESSION_TABLE || "willys_sessions";
const GROCERY_TABLE = process.env.GROCERY_TABLE || "grocery_data";
const DIRECT_INGEST_IMMEDIATE = /^true$/i.test(
  String(process.env.WILLYS_DIRECT_INGEST_IMMEDIATE || "false")
);
const WILLYS_WARM_CONTEXT_LIMIT = Number(
  process.env.WILLYS_WARM_CONTEXT_LIMIT || 3
);
const UA_CHROME =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

// Per-user warm contexts to avoid repeated cold loads
const warmContexts = new Map(); // userId -> { context, lastUsed }
function evictWarmContexts() {
  if (warmContexts.size <= WILLYS_WARM_CONTEXT_LIMIT) return;
  const entries = Array.from(warmContexts.entries()).sort(
    (a, b) => a[1].lastUsed - b[1].lastUsed
  );
  while (entries.length > WILLYS_WARM_CONTEXT_LIMIT) {
    const [uid, entry] = entries.shift();
    safe(() => entry.context.close(), `closeWarmContext:${uid}`);
    warmContexts.delete(uid);
  }
}

async function getWarmContext(userId, storageState, headless) {
  if (!userId || headless === false) return null; // don't cache visible runs
  const existing = warmContexts.get(userId);
  if (existing) {
    existing.lastUsed = Date.now();
    return existing.context;
  }
  const browser = await getSharedBrowser();
  const ctx = await browser.newContext({
    viewport: { width: 420, height: 640 },
    userAgent: UA_CHROME,
    locale: "sv-SE",
    storageState: storageState || SESSION_PATH,
  });
  warmContexts.set(userId, { context: ctx, lastUsed: Date.now() });
  evictWarmContexts();
  return ctx;
}

// Keep a shared Playwright browser to avoid cold starts per QR request.
let sharedBrowser = null;
async function getSharedBrowser() {
  if (sharedBrowser) return sharedBrowser;
  sharedBrowser = await chromium.launch({
    headless: true,
    args: ["--disable-dev-shm-usage", "--no-sandbox", "--disable-setuid-sandbox"],
  });
  sharedBrowser.on("disconnected", () => {
    sharedBrowser = null;
  });
  return sharedBrowser;
}

// Seed a permissive consent cookie/localStorage to avoid OneTrust blocking the UI
function buildConsentCookie() {
  const expires = Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 30; // 30 days
  const consentValue =
    "isGpcEnabled=0&datestamp=" +
    new Date().toISOString() +
    "&version=6.16.0&hosts=&landingPath=NotLandingPage&groups=C0001:1,C0002:1,C0003:1,C0004:1";
  return {
    name: "OptanonConsent",
    value: consentValue,
    domain: ".willys.se",
    path: "/",
    expires,
    httpOnly: false,
    secure: true,
    sameSite: "None",
  };
}

// How far back to fetch receipts if caller doesnâ€™t specify
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
      `[willys-service] Page ${serverPage + 1}/${numberOfPages} â†’ ${results.length} row(s), total descriptors=${out.length}`
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
  if (!SUPABASE_WILLYS_FUNCTION_WITH_CONTENT) return null;
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

// ---------- token-first BankID QR fetch (fast path) ----------
async function tryBankIdTokenFlow({
  userId,
  sessionPath,
  storageState,
  timeoutMs = 60_000,
  onEvent,
}) {
  try {
    const api = await request.newContext({
      baseURL: "https://www.willys.se",
      storageState: storageState || sessionPath,
      extraHTTPHeaders: {
        accept: "*/*",
        referer: "https://www.willys.se/anvandare/inloggning",
        "accept-language": "sv-SE,sv;q=0.9,en;q=0.8",
      },
    });

    const tokenResp = await api.get("/axfood/rest/checkout/bankid/qr");
    const tokenText = await tokenResp.text();
    if (!tokenResp.ok() || !tokenText || !/^bankid\./i.test(tokenText.trim())) {
      await api.dispose();
      return null;
    }

    // Stream generated QR immediately
    const dataUrl = await qrcode.toDataURL(tokenText.trim());
    onEvent?.("qr-image", { image: dataUrl });

    const started = Date.now();
    let final = null;
    // Poll collect-login until COMPLETE or timeout
    while (Date.now() - started < timeoutMs) {
      try {
        const collectResp = await api.get("/axfood/rest/checkout/bankid/collect-login");
        const status = await collectResp.json().catch(() => null);
        if (status?.status === "COMPLETE") {
          final = { ok: true, result: status };
          break;
        }
        if (status?.status && status?.hintCode) {
          onEvent?.("collect", { status: status.status, hintCode: status.hintCode });
        }
      } catch {}
      await sleep(800);
    }

    await api.dispose();
    return final || { ok: false, error: "Timed out waiting for BankID COMPLETE" };
  } catch (e) {
    return null;
  }
}

// ---------- direct ingest into Supabase grocery_data (and optional raw table) ----------
async function upsertIntoGrocery({
  supabaseUserId,
  receipts,
  rawTable = process.env.WILLYS_DIRECT_INGEST_TABLE || "willys_receipts_raw",
  groceryTable = GROCERY_TABLE,
}) {
  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
    throw new Error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY");
  }
  if (!Array.isArray(receipts) || receipts.length === 0) {
    return { inserted: 0 };
  }

  const now = new Date().toISOString();
  const rawRows = [];
  const groceryRows = [];

  for (const r of receipts) {
    let raw_text = null;
    let parsed = null;

    if (r?.content_base64 && /pdf/i.test(r.content_type || "")) {
      try {
        const buf = Buffer.from(r.content_base64, "base64");
        raw_text = await extractPdfText(buf);
        parsed = parseReceiptText(raw_text);
      } catch (e) {
        console.warn(
          `[direct-ingest] pdf parse failed for ${r.reference || "?"}:`,
          e?.message || e
        );
      }
    }

    if (rawTable) {
      rawRows.push({
        user_id: supabaseUserId,
        reference: r.reference || null,
        store_name: r.store_name || null,
        receipt_date: r.receipt_date || null,
        digitalreceipt_url: r.digitalreceipt_url || null,
        content_type: r.content_type || null,
        byte_length: r.byte_length || null,
        content_base64: r.content_base64 || null,
        raw_text,
        parsed_items: parsed?.items || null,
        parsed_item_count: parsed?.itemCount ?? null,
        parsed_total: parsed?.total ?? null,
        created_at: now,
      });
    }

    if (groceryTable) {
      groceryRows.push({
        user_id: supabaseUserId,
        store: r.store_name || "Willys",
        store_name: r.store_name || "Willys",
        receipt_date: r.receipt_date || null,
        products: parsed?.items || [],
        raw_receipt_text: raw_text || null,
        parsed_total: parsed?.total ?? null,
        parsed_item_count: parsed?.itemCount ?? null,
        connection_type: "willys",
        reference: r.reference || null,
        created_at: now,
      });
    }
  }

  const headers = {
    "Content-Type": "application/json",
    apikey: SUPABASE_SERVICE_ROLE_KEY,
    Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
    Prefer: "resolution=merge-duplicates",
  };

  if (rawTable && rawRows.length) {
    const resp = await fetch(`${SUPABASE_URL}/rest/v1/${rawTable}`, {
      method: "POST",
      headers,
      body: JSON.stringify(rawRows),
    });
    if (!resp.ok) {
      const t = await resp.text();
      throw new Error(
        `Raw ingest failed (${rawTable}): ${resp.status} ${t.slice(0, 200)}`
      );
    }
  }

  if (groceryTable && groceryRows.length) {
    const resp = await fetch(`${SUPABASE_URL}/rest/v1/${groceryTable}`, {
      method: "POST",
      headers,
      body: JSON.stringify(groceryRows),
    });
    if (!resp.ok) {
      const t = await resp.text();
      throw new Error(
        `Grocery ingest failed (${groceryTable}): ${resp.status} ${t.slice(0, 200)}`
      );
    }
  }

  return {
    inserted: groceryRows.length || rawRows.length,
    grocery_count: groceryRows.length,
    raw_count: rawRows.length,
  };
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


// Override with faster variants (keep name to supersede earlier definitions)
async function closeCookies(page) {
  const selectors = [
    "#onetrust-reject-all-handler",
    "#onetrust-accept-btn-handler",
    'button:has-text("Avvisa alla")',
    'button:has-text("Acceptera alla cookies")',
  ];
  for (const sel of selectors) {
    try {
      const btn = await page.$(sel);
      if (btn) {
        await btn.click({ timeout: 500 });
        break;
      }
    } catch {}
  }
  await safe(
    () =>
      page.addStyleTag({
        content: `
        #onetrust-banner-sdk,
        .onetrust-pc-dark-filter,
        [id*="cookie" i],
        [class*="cookie" i],
        [class*="consent" i] {
          visibility: hidden !important;
          opacity: 0 !important;
          pointer-events: none !important;
          display: none !important;
        }
      `,
      }),
    "injectCookieHideCssFast"
  );
  return true;
}

async function switchToMobiltBankID(page, timeoutMs = 15000) {
  try {
    await page.click("text=Mobilt BankID", { timeout: 3000 });
    return true;
  } catch {}

  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const dlg = page.locator('div[role="dialog"]').first();
    const scope = (await dlg.isVisible().catch(() => false)) ? dlg : page;
    const ok = await clickAnyText(scope, [/Mobilt\s*BankID/i]);
    if (ok) return true;
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

  ok = await clickAnyText(scope, [/annan enhet/i, /QR/i, /BankID/i]);
  return ok;
}

// More aggressive QR clicker for slower/variant UIs
async function clickToShowQR2(page) {
  const dlg = page.locator('div[role="dialog"]').first();
  const scope = (await dlg.isVisible().catch(() => false)) ? dlg : page;

  const patterns = [
    /Mobilt\s*BankID\s*på\s*annan\s*enhet/i,
    /Logga in med Mobilt BankID/i,
    /BankID-appen/i,
    /QR/i,
    /Skanna/i,
  ];

  const forceClick = async () => {
    return await page.evaluate((reSources) => {
      const res = reSources.map((s) => new RegExp(s, 'i'));
      const candidates = Array.from(
        document.querySelectorAll('button,[role=button],[role=tab],a,div,span')
      );
      for (const el of candidates) {
        const text = (el.textContent || '').trim();
        if (!text) continue;
        if (res.some((re) => re.test(text))) {
          el.click();
          return true;
        }
      }
      return false;
    }, patterns.map((p) => p.source));
  };

  const forceScroll = async () => {
    return await page.evaluate(() => {
      const el = document.querySelector('div[role="dialog"]');
      if (el) el.scrollTop = el.scrollHeight;
    });
  };

  for (let i = 0; i < patterns.length; i++) {
    const ok = await clickAnyText(scope, [patterns[i]]);
    if (ok) return true;
  }

  await forceScroll();
  const forced = await forceClick();
  return !!forced;
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
  const t0 = Date.now();
  const mark = (label) => {
    const ms = Date.now() - t0;
    log?.(`${label} (${ms}ms)`);
  };

  try {
    const storageState = await getStorageStateForUser(userId, sessionPath);
    // Fast path: only try token flow if we actually have a session
    if (storageState) {
      const tokenResult = await tryBankIdTokenFlow({
        userId,
        sessionPath,
        storageState,
        timeoutMs: Math.min(timeoutMs, 60_000),
        onEvent,
      });
      if (tokenResult?.ok) {
        onEvent?.("done", { ok: true, result: tokenResult.result });
        return tokenResult;
      }
    }

    log?.("Obtaining shared Playwright browser/context...");
    browser = await getSharedBrowser();
    // Try to reuse a warm context for this user (headless only)
    context =
      (await getWarmContext(userId, storageState, headless)) ||
      (await browser.newContext({
        viewport: { width: 420, height: 640 },
        userAgent: UA_CHROME,
        locale: "sv-SE",
        storageState: storageState || undefined,
      }));

    // Speed up: block heavy assets and seed consent to avoid cookie banners
    await safe(() => context.addCookies([buildConsentCookie()]), "seedConsentCookie");
    await safe(
      () =>
        context.addInitScript(() => {
          try {
            localStorage.setItem(
              "OptanonConsent",
              "isGpcEnabled=0&datestamp=" +
                new Date().toISOString() +
                "&version=6.16.0&hosts=&landingPath=NotLandingPage&groups=C0001:1,C0002:1,C0003:1,C0004:1"
            );
          } catch {}
          const css = `
            #onetrust-banner-sdk, .onetrust-pc-dark-filter, [id*="cookie" i], [class*="cookie" i], [class*="consent" i] {
              visibility: hidden !important; opacity: 0 !important; pointer-events: none !important; display: none !important;
            }
          `;
          const s = document.createElement("style");
          s.textContent = css;
          document.documentElement.appendChild(s);
        }),
      "seedConsentLS"
    );

    // Allow all willys assets (JS/CSS/fonts/images) but block obvious third-party trackers and heavy media elsewhere.
    await context.route("**/*", async (route) => {
      const url = route.request().url();
      const rt = route.request().resourceType();
      const isWillys = /https?:\/\/([^.]+\.)?willys\.se/i.test(url);

      if (isWillys) {
        return route.continue().catch(() => {});
      }

      // Drop known trackers/analytics CDNs that slow us down.
      if (/clarity\.ms|sitegainer\.com|hotjar|googletagmanager|google-analytics\.com/i.test(url)) {
        return route.abort().catch(() => {});
      }

      // Drop media/large streaming resources.
      if (rt === "media") {
        return route.abort().catch(() => {});
      }

      return route.continue().catch(() => {});
    });

    page = await context.newPage();
    attachNetworkTaps(page, (evt, data) => onEvent?.(evt, data));

    await page.goto(LOGIN_URL, { waitUntil: "domcontentloaded", timeout: 15000 });
    mark("Opened /anvandare/inloggning");

    await closeCookies(page);
    mark("Cookies: any visible banner has been handled/hidden");

    const switched = await switchToMobiltBankID(page);
    if (!switched) {
      onEvent?.("error", {
        msg: "Could not switch to 'Mobilt BankID' tab",
      });
      throw new Error("BankID tab not found");
    }
    mark("Switched to Mobilt BankID");

    const clicked = await clickToShowQR2(page);
    if (!clicked) {
      onEvent?.("error", {
        msg: "Could not find QR/annan enhet or 'Logga in med Mobilt BankID' button",
      });
    } else {
      mark("Clicked login/QR CTA");
    }

    const hint = await waitForQrHints(page, 15_000);
    if (hint) log?.(`QR hint: ${JSON.stringify(hint)}`);

    await safe(
      () =>
        page.addStyleTag({
          content: `
          button[aria-label="StÃ¤ng"],
          button[aria-label="Close"],
          svg[aria-label="StÃ¤ng"],
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
      log?.("Login COMPLETE â†’ saving session.");
      await safe(() => fs.mkdirSync(path.dirname(sessionPath), { recursive: true }), "ensureSessionDir");
      const stateObj = await safe(() => context.storageState(), "getStateObj");
      await safe(() => context.storageState({ path: sessionPath }), "saveSessionFile");
      if (stateObj && userId) {
        await saveSessionToStore(userId, stateObj);
      }
    }

    // Keep warm contexts alive for reuse; close otherwise
    if (!userId || headless === false) {
      await safe(() => context?.close(), "closeContext");
    } else {
      const entry = warmContexts.get(userId);
      if (entry) entry.lastUsed = Date.now();
    }
    onEvent?.(
      "done",
      final?.ok ? { ok: true, result: final.result } : { ok: false }
    );
    return final?.ok
      ? final
      : { ok: false, error: final?.error || "Unknown error" };
  } catch (err) {
    await safe(() => context?.close(), "closeContextOnError");
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
  const headless = req.query?.headless === "false" ? false : true;

  const end = () => {
    try {
      res.end();
    } catch {}
  };

  const result = await runBankIdLogin({
    headless,
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
  const headless = req.query?.headless === "false" || req.body?.headless === false ? false : true;
  const r = await runBankIdLogin({
    headless,
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
      `[willys-service] Fetching receipts range ${fromDate} â†’ ${toDate} (months=${rangeMonths})`
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
      `[willys-service] (with-content) Fetching receipts range ${fromDate} â†’ ${toDate} (months=${rangeMonths})`
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

    const directIngest = DIRECT_INGEST_IMMEDIATE || !!req.body?.direct_ingest;

    let supabaseResponse = null;
    if (!directIngest) {
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
    }

    let ingestResult = null;
    if (directIngest) {
      try {
        ingestResult = await upsertIntoGrocery({
          supabaseUserId: supabase_user_id,
          receipts,
          rawTable: process.env.WILLYS_DIRECT_INGEST_TABLE || null,
          groceryTable: GROCERY_TABLE,
        });
      } catch (e) {
        console.warn("[willys-service] Direct ingest failed:", e?.message || e);
      }
    }

    return res.json({
      success: true,
      descriptorsCount: descriptors.length,
      receiptsCount: receipts.length,
      meta: { fromDate, toDate },
      forwarded: Boolean(supabaseResponse),
      supabase: supabaseResponse || null,
      ingested: ingestResult || null,
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
  console.log(`[willys-service] Running â†’ http://localhost:${PORT}`);
});

// --- Lightweight read endpoint for frontend (grocery_data) ---
app.get("/willys/receipts", async (req, res) => {
  const userId = resolveUserId(req);
  if (!userId) {
    return res.status(400).json({ ok: false, error: "supabase_user_id is required" });
  }
  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
    return res.status(500).json({ ok: false, error: "Missing Supabase service role env" });
  }
  try {
    const url =
      `${SUPABASE_URL}/rest/v1/${GROCERY_TABLE}` +
      `?user_id=eq.${encodeURIComponent(userId)}` +
      `&select=receipt_date,store_name,store,products,parsed_total,parsed_item_count,reference` +
      `&order=receipt_date.desc`;

    const resp = await fetch(url, {
      headers: {
        apikey: SUPABASE_SERVICE_ROLE_KEY,
        Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
      },
    });
    const text = await resp.text();
    if (!resp.ok) {
      return res
        .status(502)
        .json({ ok: false, error: `Supabase query failed: ${resp.status} ${text.slice(0, 200)}` });
    }
    const data = text ? JSON.parse(text) : [];
    return res.json({ ok: true, receipts: data });
  } catch (e) {
    return res.status(500).json({ ok: false, error: e?.message || String(e) });
  }
});








