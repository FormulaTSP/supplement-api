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

# Setup Google Vision client
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
            try:
                xls = pd.ExcelFile(io.BytesIO(content))
                processed_records = []

                for sheet_name in xls.sheet_names:
                    df = xls.parse(sheet_name=sheet_name, dtype=str)
                    df = df.fillna("")

                    for _, row in df.iterrows():
                        date = row.get("Datum", "")

                        for col in df.columns:
                            if col == "Datum":
                                continue
                            value = row[col]
                            if not value.strip():
                                continue
                            try:
                                float_val = float(value.replace(",", "."))
                            except ValueError:
                                continue

                            marker_entry = {
                                "date": date,
                                "marker": col,
                                "value": value
                            }
                            processed_records.append(marker_entry)

                raw_text = json.dumps(processed_records, indent=2)

            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to parse Excel file: {str(e)}")

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

        else:
            image_vision = vision.Image(content=content)
            response = client.text_detection(image=image_vision)
            raw_text = response.text_annotations[0].description if response.text_annotations else ""

        if not raw_text.strip():
            raise HTTPException(status_code=400, detail="No text detected in the blood test file.")

        structured_data = parse_bloodtest_text(raw_text)

        return {
            "structured_bloodtest": structured_data,
            "raw_text": raw_text,
            "message": "Blood test data extracted successfully from Excel." if file_ext in ["xlsx", "xls"] else "Blood test data extracted successfully."
        }

    except Exception as e:
        logger.error(f"Error processing blood test: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process blood test file.")