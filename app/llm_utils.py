import os
import json
import re
from openai import OpenAI

client = OpenAI()

def parse_bloodtest_text(raw_text: str):
    """
    Uses GPT to extract blood test markers from either:
    - JSON data (e.g. from Excel) — may include date, marker, value
    - Unstructured text (e.g. from OCR PDF or images)

    Returns a dict with:
    - structured_bloodtest: { parsed_text: [...], message: "..." }
    - raw_text
    """

    # Try to detect if input is JSON-like
    try:
        data = json.loads(raw_text)
        is_json = True
    except Exception:
        is_json = False

    if is_json:
        pretty_json = json.dumps(data, indent=2)
        prompt = f"""
You are a helpful assistant that extracts blood test results from JSON data representing lab reports.

Extract and return a JSON array of objects, each with:
- marker (string)
- value (float)
- unit (string)
- if available: date (string in ISO format)

Do not guess unknown values. Only include rows where the marker is identifiable and value is numeric.

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
You are a helpful assistant that extracts blood test results from raw text (from OCR or scanned lab reports).

The input text contains blood test marker names, values, and units mixed with other data.

Extract and return a JSON array of objects with:
- marker (string)
- value (float)
- unit (string)

Only include entries with clearly identified markers and valid numeric values.
Do NOT guess marker names (e.g., do not use 'unknown_marker_1').
If a marker cannot be clearly identified, skip it.

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
        parsed = json.loads(result_text)

        # Case 1: If top-level is a dict with 'parsed_text' as a stringified list
        if isinstance(parsed, dict) and isinstance(parsed.get("parsed_text"), str):
            try:
                inner = json.loads(parsed["parsed_text"])
                parsed_list = inner if isinstance(inner, list) else [inner]
            except Exception as inner_e:
                return {
                    "structured_bloodtest": {
                        "parsed_text": parsed["parsed_text"]
                    },
                    "raw_text": raw_text,
                    "message": f"Failed to parse inner JSON: {str(inner_e)}"
                }

        # Case 2: If it's a valid list directly
        elif isinstance(parsed, list):
            parsed_list = parsed

        # Case 3: If it's a stringified list
        elif isinstance(parsed, str):
            parsed_list = json.loads(parsed)

        # Fallback: wrap in list
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