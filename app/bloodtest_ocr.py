from fastapi import APIRouter, UploadFile, File, HTTPException
import os
import json
import io
from google.cloud import vision
from google.oauth2 import service_account
from pdf2image import convert_from_bytes
from app.llm_utils import parse_bloodtest_text  # your GPT parser
import pandas as pd
import logging

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

@router.post("/process-bloodtest")
async def process_bloodtest(file: UploadFile = File(...)):
    content = await file.read()
    file_ext = file.filename.split(".")[-1].lower()

    try:
        if file_ext in ["xlsx", "xls"]:
            # Parse Excel file
            try:
                df = pd.read_excel(io.BytesIO(content))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to parse Excel file: {str(e)}")

            # Normalize column names to lowercase
            df.columns = [col.lower() for col in df.columns]

            required_cols = {"marker", "value", "unit"}
            if not required_cols.issubset(set(df.columns)):
                raise HTTPException(status_code=400, detail=f"Excel file must contain columns: {required_cols}")

            blood_tests = df.to_dict(orient="records")

            return {
                "structured_bloodtest": blood_tests,
                "message": "Blood test data extracted successfully from Excel."
            }

        elif file_ext == "pdf":
            # OCR all pages of PDF
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

        else:
            # Treat as image file (png, jpeg, etc)
            image_vision = vision.Image(content=content)
            response = client.text_detection(image=image_vision)
            full_text = response.text_annotations[0].description if response.text_annotations else ""

        if not full_text.strip():
            raise HTTPException(status_code=400, detail="No text detected in the blood test file.")

        # Send text to GPT to parse markers, values, units
        structured_data = parse_bloodtest_text(full_text)

        return {
            "structured_bloodtest": structured_data,
            "raw_text": full_text
        }

    except Exception as e:
        logger.error(f"Error processing blood test: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process blood test file.")