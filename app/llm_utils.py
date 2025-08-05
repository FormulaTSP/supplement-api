import os
import json
import re
from openai import OpenAI

client = OpenAI()

def try_parse_json_recursive(text):
    """
    Recursively attempts to parse a JSON string until it's a Python object.
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
    Uses GPT to extract structured blood test data from either JSON (Excel-like) or raw OCR text.
    Ensures the final output is a list of dicts under 'structured_bloodtest' -> 'parsed_text'.
    """

    # Detect JSON input
    try:
        data = json.loads(raw_text)
        is_json = True
    except Exception:
        is_json = False

    if is_json:
        pretty_json = json.dumps(data, indent=2)
        prompt = f"""
You are a helpful assistant extracting blood test results from structured JSON (e.g., from Excel exports).

Return **only** a JSON array of objects (no strings, no wrapping).

Each object should include:
- marker (string)
- value (float)
- unit (string or empty)
- date (ISO 8601 string if available)

### Input JSON:
```json
{pretty_json}
```"""
    else:
        prompt = f"""
You are a helpful assistant extracting blood test results from unstructured text (e.g., OCR scans).

Return **only** a JSON array of objects (no wrapping).

Each object should include:
- marker (string)
- value (float)
- unit (string)

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

    # Clean up markdown-style code block if GPT uses it
    if result_text.startswith("```"):
        result_text = re.sub(r"^```(?:json)?\n?", "", result_text)
        result_text = re.sub(r"\n```$", "", result_text)

    try:
        parsed = try_parse_json_recursive(result_text)

        # If GPT wrapped in dict with 'parsed_text'
        if isinstance(parsed, dict) and "parsed_text" in parsed:
            pt = parsed["parsed_text"]

            # Case: parsed_text is a list of one string
            if isinstance(pt, list) and len(pt) == 1 and isinstance(pt[0], str):
                parsed_inner = try_parse_json_recursive(pt[0])
            else:
                parsed_inner = try_parse_json_recursive(pt)

            parsed_list = parsed_inner if isinstance(parsed_inner, list) else [parsed_inner]

        # If top-level result is a list (ideal)
        elif isinstance(parsed, list):
            parsed_list = parsed

        # If it's a stringified list at the top level
        elif isinstance(parsed, str):
            parsed_inner = try_parse_json_recursive(parsed)
            parsed_list = parsed_inner if isinstance(parsed_inner, list) else [parsed_inner]

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