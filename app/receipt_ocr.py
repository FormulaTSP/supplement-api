from fastapi import APIRouter, UploadFile, File
import os
import json
import io
from google.cloud import vision
from google.oauth2 import service_account
from pdf2image import convert_from_bytes
from app.nutrition_utils import categorize_items_with_llm, estimate_nutrients

router = APIRouter()

poppler_path = r"C:\Users\Fredr\Desktop\Backup\Other\School\Stockholm School of Economics\poppler-24.08.0\Library\bin"

# Load Google credentials from environment variable (JSON string)
creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
if creds_json:
    creds_info = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(creds_info)
else:
    credentials = None

# Create Vision client with credentials
client = vision.ImageAnnotatorClient(credentials=credentials)

@router.post("/process-receipt")
async def process_receipt(file: UploadFile = File(...)):
    content = await file.read()
    file_ext = file.filename.split(".")[-1].lower()

    if file_ext == "pdf":
        images = convert_from_bytes(content, poppler_path=poppler_path)
        # Convert first page to PNG bytes
        img_byte_arr = io.BytesIO()
        images[0].save(img_byte_arr, format='PNG')
        img_content = img_byte_arr.getvalue()
    else:
        img_content = content

    image = vision.Image(content=img_content)

    response = client.text_detection(image=image)
    text = response.text_annotations[0].description if response.text_annotations else ""

    lines = [line.strip() for line in text.split('\n') if line.strip()]
    items = [line for line in lines if not any(x in line.lower() for x in ["total", "$", "tax", "price", "subtotal"])]

    if not items:
        return {
            "error": "No readable items found in receipt.",
            "raw_receipt_text": text
        }

    categorized = categorize_items_with_llm(items)
    consumed_foods, dietary_intake = estimate_nutrients(categorized)

    return {
        "consumed_foods": consumed_foods,
        "dietary_intake": dietary_intake,
        "raw_receipt_text": text
    }