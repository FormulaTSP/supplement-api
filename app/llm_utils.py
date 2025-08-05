import os
import json
import re
from openai import OpenAI

client = OpenAI()

def try_parse_json_recursive(text):
    """
    Recursively attempts to parse JSON until it's no longer a string.
    Useful when output is stringified multiple times.
    """
    depth = 0
    while isinstance(text, str):
        try:
            text = json.loads(text)
            depth += 1
        except Exception:
            break
    return text

def parse_bloodtest_text(raw_text: str):
    """
    Uses GPT to extract blood test markers from either:
    - JSON data (e.g. from Excel)
    - Unstructured text (e.g. OCR, scanned PDF)

    Returns a dict with:
    - structured_bloodtest: { parsed_text: [...], message: "..." }
    - raw_text
    """

    # Attempt to detect if input is JSON-like
    try:
        data = json.loads(raw_text)
        is_json = True
    except Exception:
        is_json = False

    if is_json:
        pretty_json = json.dumps(data, indent=2)
        prompt = f"""
You are a helpful assistant that extracts blood test results from structured JSON data (e.g., from Excel exports).

Return a JSON array of objects. Do NOT wrap the result inside any additional objects or as a string.

Each object should contain:
- marker (string)
- value (float)
- unit (string, or empty string if not available)
- date (ISO 8601 format, if available)

Do NOT guess values or include unknown markers.

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
You are a helpful assistant that extracts blood test results from unstructured raw text (e.g., OCR from PDFs or scanned images).

Return a JSON array of objects. Do NOT wrap the result inside any additional objects or as a string.

Each object should contain:
- marker (string)
- value (float)
- unit (string)

Only include entries with clearly identified markers and numeric values.
Skip anything ambiguous or unclear.

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

    # Remove markdown-style code blocks
    if result_text.startswith("```"):
        result_text = re.sub(r"^```(?:json)?\n?", "", result_text)
        result_text = re.sub(r"\n```$", "", result_text)

    try:
        parsed = try_parse_json_recursive(result_text)

        if isinstance(parsed, dict) and "parsed_text" in parsed:
            parsed_inner = try_parse_json_recursive(parsed["parsed_text"])
            parsed_list = parsed_inner if isinstance(parsed_inner, list) else [parsed_inner]
        elif isinstance(parsed, list):
            parsed_list = parsed
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