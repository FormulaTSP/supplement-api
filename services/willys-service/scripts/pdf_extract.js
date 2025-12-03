// services/willys-service/scripts/pdf_extract.js
import PDFParser from "pdf2json";

/**
 * Extracts text from a PDF buffer using pdf2json.
 * Handles embedded CID fonts better than pdf.js.
 */
export async function extractPdfText(buffer) {
  return await new Promise((resolve, reject) => {
    const parser = new PDFParser();

    parser.on("pdfParser_dataError", (err) => {
      reject(err.parserError || err);
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
