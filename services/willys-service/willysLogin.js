import { chromium } from "playwright";

export async function loginAndGetSession({ onQR, headless = true }) {
  const browser = await chromium.launch({
    headless,   // headless:true on server, false if testing locally
  });
  const context = await browser.newContext({
    viewport: { width: 800, height: 900 },
  });
  const page = await context.newPage();

  // --- Intercept the QR WebSocket ---
  page.on("websocket", ws => {
    ws.on("framereceived", ({ payload }) => {
      try {
        const data = JSON.parse(payload);
        if (data.qrStartToken || data.qrStartSecret) {
          // Send QR Data back to server (which streams to FE)
          onQR({
            token: data.qrStartToken,
            secret: data.qrStartSecret,
            orderRef: data.orderRef,
          });
        }
      } catch (_) {}
    });
  });

  // --- Go to login page ---
  await page.goto("https://www.willys.se/mina-sidor/logga-in");

  // Wait for BankID login button and click
  await page.waitForSelector("[data-test='login-button']");
  await page.click("[data-test='login-button']");

  // Now let the QR stream until login completes
  await page.waitForSelector("[data-test='profile-avatar']", { timeout: 120000 });

  // ✅ Logged in — get session cookies
  const cookies = await context.cookies();

  await browser.close();
  return cookies;
}