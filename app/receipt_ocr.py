# app/receipt_ocr.py

from fastapi import APIRouter, UploadFile, File
from google.cloud import vision
from app.nutrition_utils import categorize_items_with_llm, estimate_nutrients

router = APIRouter()
client = vision.ImageAnnotatorClient()

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