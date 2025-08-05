from fastapi import APIRouter, UploadFile, File, HTTPException
import os
import json
import io
import re
import logging
from google.cloud import vision
from google.oauth2 import service_account
from pdf2image import convert_from_bytes
from app.llm_utils import parse_bloodtest_text  # your GPT parser, now updated to handle chunked calls
import pandas as pd
import tiktoken  # for tokenizing and chunking text

router = APIRouter()

# Setup Google Vision client same as receipt_ocr.py
creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
if creds_json:
    creds_info = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(creds_info)
else:
    credentials = None

client = vision.ImageAnnotatorClient(credentials=credentials)
logger = logging.getLogger("uvicorn.error")

MAX_TOKENS = 1500  # max tokens per chunk, adjust as needed

def preprocess_text_for_chunking(raw_text: str) -> str:
    # Filter lines that likely contain blood test info
    pattern = re.compile(r".*\d+[\.,]?\d*\s*[a-zA-Z/%μ]*")  # rough heuristic
    lines = raw_text.split('\n')
    filtered_lines = [line.strip() for line in lines if pattern.match(line)]
    return "\n".join(filtered_lines)

def chunk_text(text: str, max_tokens=MAX_TOKENS):
    enc = tiktoken.get_encoding("cl100k_base")  # GPT-4o-mini encoding
    tokens = enc.encode(text)
    chunks = []
    for i in range(0, len(tokens), max_tokens):
        chunk_tokens = tokens[i:i+max_tokens]
        chunk_text = enc.decode(chunk_tokens)
        chunks.append(chunk_text)
    return chunks

@router.post("/process-bloodtest")
async def process_bloodtest(file: UploadFile = File(...)):
    content = await file.read()
    file_ext = file.filename.split(".")[-1].lower()

    try:
        # Convert Excel sheets to JSON text
        if file_ext in ["xlsx", "xls"]:
            try:
                xls = pd.ExcelFile(io.BytesIO(content))
                sheets_data = {}
                for sheet_name in xls.sheet_names:
                    df = xls.parse(sheet_name=sheet_name, dtype=str)
                    df = df.fillna("")
                    sheets_data[sheet_name] = df.to_dict(orient="records")

                raw_text = json.dumps(sheets_data, indent=2)

            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to parse Excel file: {str(e)}")

        # For PDF, OCR all pages
        elif file_ext == "pdf":
            images = convert_from_bytes(content)
            full_text = ""
            for image in images:
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='PNG')
                img_content = img_byte_arr.getvalue()
                image_vision = vision.Image(content=img_content)
                response = client.text_detection(image=image_vision)
                text = response.text_annotations[0].description if response.text_annotations else ""
                full_text += text + "\n"
            raw_text = full_text

        # For image files, OCR directly
        else:
            image_vision = vision.Image(content=content)
            response = client.text_detection(image=image_vision)
            raw_text = response.text_annotations[0].description if response.text_annotations else ""

        if not raw_text.strip():
            raise HTTPException(status_code=400, detail="No text detected in the blood test file.")

        # --- Chunking and GPT calls ---
        # Preprocess raw_text to reduce noise and focus on relevant lines
        preprocessed_text = preprocess_text_for_chunking(raw_text)

        # Chunk the preprocessed text respecting token limits
        chunks = chunk_text(preprocessed_text)

        # Call GPT parser for each chunk and aggregate results
        aggregated_results = []
        for chunk in chunks:
            try:
                partial_result = parse_bloodtest_text(chunk)
                # Expecting parse_bloodtest_text to return a list of dicts
                if isinstance(partial_result, list):
                    aggregated_results.extend(partial_result)
                elif isinstance(partial_result, dict) and "parsed_text" in partial_result:
                    # If parse_bloodtest_text returns raw string fallback, ignore or log
                    logger.warning("Received raw text fallback from GPT parser.")
                else:
                    logger.warning(f"Unexpected GPT parser response: {partial_result}")
            except Exception as e:
                logger.error(f"Error parsing chunk with GPT: {e}")
                # Optionally: continue or raise; here we continue to parse other chunks
                continue

        # Remove duplicates by (marker.lower(), value, unit.lower())
        unique_results = []
        seen = set()
        for entry in aggregated_results:
            key = (
                entry.get("marker", "").lower(),
                float(entry.get("value", 0)),
                entry.get("unit", "").lower()
            )
            if key not in seen:
                unique_results.append(entry)
                seen.add(key)

        return {
            "structured_bloodtest": unique_results,
            "raw_text": raw_text
        }

    except Exception as e:
        logger.error(f"Error processing blood test: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process blood test file.")