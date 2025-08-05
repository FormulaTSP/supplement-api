import os
import json
import re
from openai import OpenAI

client = OpenAI()

def try_parse_json_recursive(text):
    """
    Recursively attempts to parse a JSON string until it's a native Python object.
    """
    attempts = 0
    while isinstance(text, str) and attempts < 5:
        try:
            text = json.loads(text)
            attempts += 1
        except Exception:
            break
    return text

def parse_bloodtest_text(raw_text: str):
    """
    Uses GPT to extract blood test markers from:
    - JSON input (e.g., Excel exports)
    - Unstructured text (e.g., OCR, scanned PDFs)

    Returns a dict with:
    - structured_bloodtest: { parsed_text: list, message: string }
    - raw_text
    """

    # Detect whether input is JSON-like
    try:
        data = json.loads(raw_text)
        is_json = True
    except Exception:
        is_json = False

    if is_json:
        pretty_json = json.dumps(data, indent=2)
        prompt = f"""
You are a helpful assistant that extracts blood test results from structured JSON data (e.g., from Excel exports).

Return only a **JSON array of objects** — no extra wrapping, no stringification.

Each object should contain:
- marker (string)
- value (float)
- unit (string, or empty string if unknown)
- date (ISO 8601 format, if available)

Only include valid rows with identifiable markers and numeric values.

### Example output:
[
  {{
    "marker": "Hemoglobin",
    "value": 13.2,
    "unit": "g/dL",
    "date": "2023-07-01T08:00:00"
  }}
]

### Input JSON:
```json
{pretty_json}
```"""
    else:
        prompt = f"""
You are a helpful assistant that extracts blood test results from raw text (e.g., OCR from PDFs or images).

Return only a **JSON array of objects** — no extra wrapping, no stringification.

Each object should contain:
- marker (string)
- value (float)
- unit (string)

Only include entries with clearly identified markers and valid numeric values.
Do NOT include ambiguous or missing data.

### Example output:
[
  {{
    "marker": "Hemoglobin",
    "value": 13.2,
    "unit": "g/dL"
  }}
]

### Input text:
```text
{raw_text}
```"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Extract blood test results as JSON."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
        max_tokens=2000,
    )

    result_text = response.choices[0].message.content.strip()

    # Remove markdown-style ```json code blocks
    if result_text.startswith("```"):
        result_text = re.sub(r"^```(?:json)?\n?", "", result_text)
        result_text = re.sub(r"\n```$", "", result_text)

    try:
        parsed = try_parse_json_recursive(result_text)

        # Handle dictionary with 'parsed_text'
        if isinstance(parsed, dict) and "parsed_text" in parsed:
            pt = parsed["parsed_text"]

            # If it's a list of one stringified array
            if isinstance(pt, list) and len(pt) == 1 and isinstance(pt[0], str):
                parsed_inner = try_parse_json_recursive(pt[0])
            else:
                parsed_inner = try_parse_json_recursive(pt)

            parsed_list = parsed_inner if isinstance(parsed_inner, list) else [parsed_inner]

        # Top-level array (most common case)
        elif isinstance(parsed, list):
            parsed_list = parsed

        # Single object or fallback
        else:
            parsed_list = [parsed]

        return {
            "structured_bloodtest": {
                "parsed_text": parsed_list
            },
            "raw_text": raw_text,
            "message": "Blood test data extracted successfully."
        }

    except Exception as e:
        return {
            "structured_bloodtest": {
                "parsed_text": result_text
            },
            "raw_text": raw_text,
            "message": f"Failed to parse structured JSON: {str(e)}"
        }