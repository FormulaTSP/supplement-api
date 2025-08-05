import json
import re
from openai import OpenAI

client = OpenAI()

def try_parse_json_recursive(text):
    """
    Recursively tries to parse JSON strings until a real object (list/dict) is obtained.
    """
    attempts = 0
    while isinstance(text, str) and attempts < 5:
        text = text.strip()

        # Remove markdown code block markers if present
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n```$", "", text)

        try:
            text = json.loads(text)
            attempts += 1
        except Exception:
            break
    return text

def parse_bloodtest_text(raw_text: str):
    """
    Parses either raw OCR text or JSON to extract structured blood test values.
    Ensures consistent output format.
    """
    try:
        json.loads(raw_text)
        is_json = True
    except Exception:
        is_json = False

    if is_json:
        prompt = f"""
You are a helpful assistant extracting blood test results from JSON-like data.

Return only a JSON array of objects, no strings or wrapping.

Each object should include:
- marker (string)
- value (float)
- unit (string or empty)
- date (ISO 8601 string)

### Input:
{raw_text}
"""
    else:
        prompt = f"""
You are a helpful assistant extracting blood test results from messy OCR text.

Return only a JSON array of objects.

Each object should include:
- marker (string)
- value (float)
- unit (string or empty)

### Input:
{raw_text}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Extract structured blood test data as JSON."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
        max_tokens=2000,
    )

    result_text = response.choices[0].message.content.strip()
    parsed = try_parse_json_recursive(result_text)

    # Handle cases like { "parsed_text": "[...]" }
    if isinstance(parsed, dict) and "parsed_text" in parsed:
        pt = parsed["parsed_text"]

        if isinstance(pt, list) and len(pt) == 1 and isinstance(pt[0], str):
            # Unwrap ["[...]"]
            inner = try_parse_json_recursive(pt[0])
        elif isinstance(pt, str):
            inner = try_parse_json_recursive(pt)
        else:
            inner = pt
    else:
        inner = parsed

    # Final safety: if still a string, parse again
    if isinstance(inner, str):
        inner = try_parse_json_recursive(inner)

    # If somehow still not a list, wrap
    if not isinstance(inner, list):
        inner = [inner]

    return {
        "structured_bloodtest": {
            "parsed_text": inner
        },
        "raw_text": raw_text,
        "message": "Blood test data extracted successfully."
    }