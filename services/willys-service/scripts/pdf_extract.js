// services/willys-service/scripts/pdf_extract.js
import PDFParser from "pdf2json";
import path from "node:path";
import { fileURLToPath } from "node:url";

async function extractWithPdf2Json(buffer) {
  return await new Promise((resolve, reject) => {
    const parser = new PDFParser();

    parser.on("pdfParser_dataError", (err) => {
      reject(err?.parserError || err);
    });

    parser.on("pdfParser_dataReady", () => {
      try {
        const text = parser.getRawTextContent();
        resolve(text || "");
      } catch (e) {
        reject(e);
      }
    });

    parser.parseBuffer(buffer);
  });
}

async function extractWithPdfJs(buffer) {
  const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const fontPath = path.join(__dirname, "../../node_modules/pdfjs-dist/standard_fonts/");

  const data = new Uint8Array(buffer);
  const loadingTask = pdfjs.getDocument({
    data,
    disableWorker: true,
    disableFontFace: true,
    standardFontDataUrl: fontPath.endsWith("/") ? fontPath : fontPath + "/",
  });
  const pdf = await loadingTask.promise;
  const lines = [];
  for (let p = 1; p <= pdf.numPages; p++) {
    const page = await pdf.getPage(p);
    const content = await page.getTextContent();
    const items = content.items
      .map((it) => ({
        str: it.str,
        x: it.transform?.[4] ?? 0,
        y: it.transform?.[5] ?? 0,
      }))
      .sort((a, b) => b.y - a.y || a.x - b.x);
    const yThreshold = 2.0;
    let currentY = null,
      current = [];
    for (const it of items) {
      if (currentY === null || Math.abs(it.y - currentY) <= yThreshold) {
        currentY = currentY ?? it.y;
        current.push(it.str);
      } else {
        lines.push(current.join(" ").replace(/\s+/g, " ").trim());
        currentY = it.y;
        current = [it.str];
      }
    }
    if (current.length) lines.push(current.join(" ").replace(/\s+/g, " ").trim());
    lines.push("");
  }
  return lines.filter(Boolean).join("\n");
}

/**
 * Extracts text from a PDF buffer with fallback:
 * 1) pdf2json
 * 2) pdfjs-dist (legacy)
 */
export async function extractPdfText(buffer) {
  try {
    return await extractWithPdf2Json(buffer);
  } catch (e) {
    console.warn("[pdf-extract] pdf2json failed, falling back to pdfjs:", e?.message || e);
    try {
      return await extractWithPdfJs(buffer);
    } catch (e2) {
      console.warn("[pdf-extract] pdfjs fallback failed:", e2?.message || e2);
      return "";
    }
  }
}
