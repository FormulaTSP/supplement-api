# app/receipt_ocr.py

from fastapi import APIRouter, UploadFile, File
import os
import json
from google.cloud import vision
from google.oauth2 import service_account
from app.nutrition_utils import categorize_items_with_llm, estimate_nutrients

router = APIRouter()

# Load Google credentials from environment variable (JSON string)
creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
if creds_json:
    creds_info = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(creds_info)
else:
    credentials = None  # or you can raise an error here if you want to enforce presence

# Create Vision client with credentials
client = vision.ImageAnnotatorClient(credentials=credentials)

@router.post("/process-receipt")
async def process_receipt(file: UploadFile = File(...)):
    # Read file content
    content = await file.read()
    image = vision.Image(content=content)

    # Extract text from image using Google Vision OCR
    response = client.text_detection(image=image)
    text = response.text_annotations[0].description if response.text_annotations else ""

    # Split lines and filter out totals, prices, and irrelevant rows
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    items = [line for line in lines if not any(x in line.lower() for x in ["total", "$", "tax", "price", "subtotal"])]

    if not items:
        return {
            "error": "No readable items found in receipt.",
            "raw_receipt_text": text
        }

    # Use GPT-4 to categorize items
    categorized = categorize_items_with_llm(items)

    # Estimate nutrients per item + totals
    consumed_foods, dietary_intake = estimate_nutrients(categorized)

    return {
        "consumed_foods": consumed_foods,
        "dietary_intake": dietary_intake,
        "raw_receipt_text": text
    }