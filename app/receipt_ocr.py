# app/receipt_ocr.py

from fastapi import APIRouter, UploadFile, File, HTTPException
import os
import io
import json
import re
from typing import List, Tuple, Optional

from google.cloud import vision
from google.oauth2 import service_account
from pdf2image import convert_from_bytes

# Optional: try to use PDF text layer first
try:
    from pdfminer.high_level import extract_text as pdf_extract_text
except ImportError:
    pdf_extract_text = None

from app.nutrition_utils import categorize_items_with_llm, estimate_nutrients

router = APIRouter()

# -----------------------------
# Google Vision client
# -----------------------------
# Load Google credentials from environment variable (JSON string)
creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
if creds_json:
    creds_info = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(creds_info)
else:
    credentials = None

# Create Vision client with credentials (works with None if ADC configured)
vision_client = vision.ImageAnnotatorClient(credentials=credentials)

# -----------------------------
# Helpers
# -----------------------------

def _ocr_image_bytes(img_bytes: bytes) -> str:
    """OCR one image with Google Vision."""
    image = vision.Image(content=img_bytes)
    resp = vision_client.text_detection(image=image)
    if resp.error and resp.error.message:
        # Avoid raising a hard error; return empty so caller can decide fallback
        return ""
    if resp.text_annotations:
        return resp.text_annotations[0].description or ""
    return ""

def _ocr_images_with_vision(image_bytes_list: List[bytes]) -> str:
    """OCR multiple images and concatenate text."""
    texts = []
    for b in image_bytes_list:
        txt = _ocr_image_bytes(b)
        if txt:
            texts.append(txt)
    return "\n".join(texts).strip()

def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract embedded text from PDF if pdfminer.six is available."""
    if pdf_extract_text is None:
        return ""
    try:
        return (pdf_extract_text(io.BytesIO(pdf_bytes)) or "").strip()
    except Exception:
        return ""

def _pdf_to_image_bytes_list(pdf_bytes: bytes, dpi: int = 300) -> List[bytes]:
    """Convert all pages of a PDF to PNG bytes."""
    images = convert_from_bytes(pdf_bytes, dpi=dpi)
    out = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out.append(buf.getvalue())
    return out

def _basic_line_filter(lines: List[str]) -> List[str]:
    """
    Keep likely item lines. Drop totals/tax headers and obvious price-only lines.
    This is intentionally conservative; the LLM categorizer can handle noise.
    """
    drop_tokens = ("total", "subtotal", "moms", "vat", "tax", "summa", "sum", "change", "cash", "card")
    price_line = re.compile(r"^\s*[\d\.,]+\s*(kr|usd|eur|sek|$)?\s*$", re.IGNORECASE)

    kept = []
    for ln in lines:
        low = ln.lower()
        if any(tok in low for tok in drop_tokens):
            continue
        if price_line.match(ln):
            continue
        # very short junk lines
        if len(ln.strip()) < 2:
            continue
        kept.append(ln.strip())
    return kept

# -----------------------------
# Endpoint
# -----------------------------

@router.post("/process-receipt")
async def process_receipt(file: UploadFile = File(...)):
    """
    Process an uploaded receipt (PDF or image).
    - If PDF: try embedded text first (pdfminer.six). If empty, fall back to OCR of all pages.
    - If image: OCR directly.
    Then:
    - Extract plausible item lines
    - LLM-categorize (keeps metrics if present)
    - Estimate nutrients (LLM or local, depending on USE_LLM_NUTRIENTS)
    """
    try:
        content = await file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to read uploaded file.")

    if not content:
        raise HTTPException(status_code=400, detail="Empty file.")

    file_ext = (file.filename or "").split(".")[-1].lower()
    ocr_dpi = int(os.getenv("RECEIPT_OCR_DPI", "300"))

    # --- Extract text ---
    text: str = ""
    source: str = "unknown"

    if file_ext == "pdf":
        # 1) Try embedded PDF text
        text = _extract_text_from_pdf_bytes(content)
        if text:
            source = "pdf_text"
        else:
            # 2) Fallback to OCR for all pages
            try:
                img_bytes_list = _pdf_to_image_bytes_list(content, dpi=ocr_dpi)
            except Exception:
                raise HTTPException(status_code=500, detail="Failed to render PDF pages for OCR.")
            text = _ocr_images_with_vision(img_bytes_list)
            source = "ocr_pdf_pages"
    else:
        # Assume image -> OCR
        text = _ocr_images_with_vision([content])
        source = "ocr_image"

    text = (text or "").strip()
    if not text:
        return {
            "error": "No readable text found in receipt.",
            "raw_receipt_text": "",
            "source": source,
        }

    # --- Split lines and keep plausible items ---
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    candidate_items = _basic_line_filter(lines)

    if not candidate_items:
        # Return raw text; let client decide next steps
        return {
            "error": "No plausible item lines found after filtering.",
            "raw_receipt_text": text,
            "source": source,
            "parsed_lines": lines[:300],  # debug/helper
        }

    # --- LLM categorize + nutrient estimation ---
    try:
        categorized = categorize_items_with_llm(candidate_items)
    except Exception as e:
        # Keep raw text to aid debugging
        raise HTTPException(status_code=502, detail=f"LLM categorization failed: {e}")

    try:
        consumed_foods, dietary_intake = estimate_nutrients(categorized)
    except Exception as e:
        # Still return categorized items if nutrient estimation fails
        return {
            "consumed_foods": [],
            "dietary_intake": {},
            "categorized_items": categorized,
            "raw_receipt_text": text,
            "source": source,
            "parsed_items": candidate_items,
            "warning": f"Nutrient estimation failed: {e}",
        }

    return {
        "consumed_foods": consumed_foods,       # per-food nutrients and used weights/volumes
        "dietary_intake": dietary_intake,       # totals
        "categorized_items": categorized,       # includes metrics if the LLM extracted them
        "raw_receipt_text": text,
        "source": source,                       # "pdf_text" | "ocr_pdf_pages" | "ocr_image"
        "parsed_items": candidate_items,        # the filtered lines sent to LLM
    }