// services/willys-service/server.js
import express from "express";
import cors from "cors";
import { chromium, request } from "playwright";
import path from "node:path";
import fs from "node:fs";

// ---------- constants ----------
const PORT = Number(process.env.PORT || process.env.WILLYS_SVC_PORT || 3031);
const LOGIN_URL = "https://www.willys.se/anvandare/inloggning";
const SESSION_PATH = path.resolve(process.cwd(), "willys-session.json");

// ---------- tiny helpers ----------
function sseSend(res, event, data) {
  res.write(`event: ${event}\n`);
  res.write(`data: ${JSON.stringify(data)}\n\n`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const haveSession = () => {
  try {
    return fs.existsSync(SESSION_PATH) && fs.statSync(SESSION_PATH).size > 0;
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

// ---------- page utilities ----------
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

async function switchToMobiltBankID(page) {
  const dlg = page.locator('div[role="dialog"]').first();
  const scope = (await dlg.isVisible().catch(() => false)) ? dlg : page;
  const ok = await clickAnyText(scope, [
    /^Mobilt\s*BankID$/i,
    /Mobilt\s*BankID/i,
  ]);
  if (ok) return true;
  try {
    const tab = scope
      .getByRole("tab", { name: /^Mobilt\s*BankID$/i })
      .first();
    if (await tab.isVisible({ timeout: 600 })) {
      await tab.click({ timeout: 1200 });
      return true;
    }
  } catch {}
  return false;
}

async function clickToShowQR(page) {
  const dlg = page.locator('div[role="dialog"]').first();
  const scope = (await dlg.isVisible().catch(() => false)) ? dlg : page;

  // common exact labels
  let ok = await clickAnyText(scope, [
    /Mobilt\s*BankID\s*på\s*annan\s*enhet/i,
    /Logga in med Mobilt BankID/i,
    /Öppna BankID-appen/i,
  ]);
  if (ok) return true;

  // try after a small scroll in the dialog
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

    // reduce noise
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

    // ⭐ NEW: hide ONLY the close "X" button inside the dialog
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

    // snapshot the dialog periodically (full dialog, now without X)
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

    // wait loop for COMPLETE
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
      await safe(
        () => context.storageState({ path: SESSION_PATH }),
        "saveSession"
      );
    }

    await safe(() => browser.close(), "closeBrowser");
    onEvent?.(
      "done",
      final?.ok ? { ok: true, result: final.result } : { ok: false }
    );
    return final?.ok ? final : { ok: false, error: final?.error || "Unknown error" };
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

  const end = () => {
    try {
      res.end();
    } catch {}
  };

  const result = await runBankIdLogin({
    headless: true,
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
  const r = await runBankIdLogin({
    headless: true,
    timeoutMs,
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
  if (!haveSession()) {
    return res.status(401).json({ ok: false, error: "No saved session yet" });
  }

  try {
    // Use the saved cookies/session, no browser needed
    const api = await request.newContext({
      baseURL: "https://www.willys.se",
      storageState: SESSION_PATH,
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

app.listen(PORT, () => {
  console.log(`[willys-service] Running → http://localhost:${PORT}`);
});