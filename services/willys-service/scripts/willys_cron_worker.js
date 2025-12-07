// services/willys-service/scripts/willys_cron_worker.js
// Lightweight cron/worker script:
// - Reads all user_ids from willys_sessions (Supabase, service role).
// - For each user, calls /willys/fetch-receipts-with-content on the running service.
// - The service will forward to the content edge function if configured; otherwise it returns
//   the receipts payload (you can extend this script to upsert directly if you prefer).

import "dotenv/config";
import fetch from "node-fetch";
import { extractPdfText } from "./pdf_extract.js";
import { parseReceiptText } from "../lib/willys_parse.js";
import crypto from "node:crypto";

const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const WILLYS_SESSION_TABLE =
  process.env.WILLYS_SESSION_TABLE || "willys_sessions";
const SERVICE_URL =
  process.env.WILLYS_SERVICE_URL ||
  `http://localhost:${process.env.PORT || 3031}`;
const DEFAULT_MONTHS = Number(process.env.RECEIPT_MONTHS_DEFAULT || 12);
const CONCURRENCY = Number(process.env.WILLYS_CRON_CONCURRENCY || 3);
const DIRECT_INGEST = /^true$/i.test(
  String(process.env.WILLYS_CRON_DIRECT_INGEST || "false")
);
const DIRECT_INGEST_TABLE =
  process.env.WILLYS_DIRECT_INGEST_TABLE || "willys_receipts_raw";
const GROCERY_TABLE = process.env.GROCERY_TABLE || "grocery_data";

if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
  console.error(
    "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY. Aborting cron run."
  );
  process.exit(1);
}

async function listSessions() {
  const url = `${SUPABASE_URL}/rest/v1/${WILLYS_SESSION_TABLE}?select=user_id`;
  const resp = await fetch(url, {
    headers: {
      apikey: SUPABASE_SERVICE_ROLE_KEY,
      Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
    },
  });
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`Failed to list sessions: ${resp.status} ${t.slice(0, 200)}`);
  }
  const data = await resp.json();
  return Array.from(new Set((data || []).map((r) => r.user_id).filter(Boolean)));
}

async function syncUser(userId) {
  try {
    const resp = await fetch(`${SERVICE_URL}/willys/fetch-receipts-with-content`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        supabase_user_id: userId,
        months: DEFAULT_MONTHS,
      }),
    });
    const text = await resp.text();
    let data = null;
    try {
      data = JSON.parse(text);
    } catch {}
    if (!resp.ok) {
      throw new Error(
        `HTTP ${resp.status}: ${data?.error || text.slice(0, 200)}`
      );
    }
    const desc = data?.descriptorsCount ?? data?.descriptors?.length ?? 0;
    const rec = data?.receiptsCount ?? data?.receipts?.length ?? 0;
    console.log(
      `[willys-cron] user=${userId} descriptors=${desc} receipts=${rec} forwarded=${data?.forwarded}`
    );

    if (DIRECT_INGEST && data?.receipts && Array.isArray(data.receipts)) {
      await upsertReceiptsDirect(userId, data.receipts);
    }
  } catch (e) {
    console.error(`[willys-cron] user=${userId} failed:`, e?.message || e);
  }
}

async function asyncPool(limit, items, worker) {
  const ret = [];
  const executing = new Set();
  for (const it of items) {
    const p = Promise.resolve().then(() => worker(it));
    ret.push(p);
    executing.add(p);
    const clean = () => executing.delete(p);
    p.then(clean, clean);
    if (executing.size >= limit) await Promise.race(executing);
  }
  return Promise.all(ret);
}

async function upsertReceiptsDirect(userId, receipts) {
  const rows = [];
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

    rows.push({
      user_id: userId,
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
      created_at: new Date().toISOString(),
    });

    // Map into grocery_data schema
    groceryRows.push({
      user_id: userId,
      store: r.store_name || "Willys",
      store_name: r.store_name || "Willys",
      receipt_date: r.receipt_date || null,
      products: parsed?.items || [],
      raw_receipt_text: raw_text || null,
      parsed_total: parsed?.total ?? null,
      parsed_item_count: parsed?.itemCount ?? null,
      connection_type: "willys",
      created_at: new Date().toISOString(),
    });
  }

  const resp = await fetch(`${SUPABASE_URL}/rest/v1/${DIRECT_INGEST_TABLE}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: SUPABASE_SERVICE_ROLE_KEY,
      Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
      Prefer: "resolution=merge-duplicates",
    },
    body: JSON.stringify(rows),
  });

  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(
      `[direct-ingest] Failed to upsert ${rows.length} receipts: ${resp.status} ${t.slice(
        0,
        200
      )}`
    );
  }
  console.log(
    `[direct-ingest] user=${userId} upserted=${rows.length} into ${DIRECT_INGEST_TABLE}`
  );

  if (groceryRows.length) {
    const resp2 = await fetch(`${SUPABASE_URL}/rest/v1/${GROCERY_TABLE}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        apikey: SUPABASE_SERVICE_ROLE_KEY,
        Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
        Prefer: "resolution=merge-duplicates",
      },
      body: JSON.stringify(groceryRows),
    });
    if (!resp2.ok) {
      const t = await resp2.text();
      throw new Error(
        `[direct-ingest] Failed to upsert ${groceryRows.length} rows into ${GROCERY_TABLE}: ${resp2.status} ${t.slice(
          0,
          200
        )}`
      );
    }
    console.log(
      `[direct-ingest] user=${userId} upserted=${groceryRows.length} into ${GROCERY_TABLE}`
    );
  }
}

async function main() {
  console.log("[willys-cron] Starting cron run");
  const users = await listSessions();
  console.log(`[willys-cron] Found ${users.length} user session(s) to sync`);
  await asyncPool(CONCURRENCY, users, syncUser);
  console.log("[willys-cron] Done");
}

main().catch((e) => {
  console.error("[willys-cron] Fatal error:", e?.message || e);
  process.exit(1);
});
