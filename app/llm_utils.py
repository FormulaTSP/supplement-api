import os
import json
from openai import OpenAI

client = OpenAI()

def parse_bloodtest_text(raw_text: str):
    """
    Extract blood test results from either raw text or JSON-like string input.
    Returns a list of dictionaries with keys: marker, value, unit.
    """

    # Try to detect if input is JSON (from Excel or structured data)
    try:
        data = json.loads(raw_text)
        is_json = True
    except Exception:
        is_json = False

    if is_json:
        pretty_json = json.dumps(data, indent=2)
        prompt = f"""You are a helpful assistant that extracts blood test results from JSON data representing tables.

The JSON contains lists of records with various keys. Extract and return a JSON array of objects, each with:
- marker (string)
- value (float)
- unit (string)

### Example output:
[
  {{"marker": "Hemoglobin", "value": 13.2, "unit": "g/dL"}},
  {{"marker": "WBC", "value": 6.1, "unit": "10^3/uL"}}
]

### Input JSON data:
```json
{pretty_json}
```"""
    else:
        prompt = f"""You are a helpful assistant that extracts blood test results from raw text.

The input text contains markers, values, and units mixed with other data.
Extract and return a JSON array of objects, each with:
- marker (string)
- value (float)
- unit (string)

### Example output:
[
  {{"marker": "Hemoglobin", "value": 13.2, "unit": "g/dL"}},
  {{"marker": "WBC", "value": 6.1, "unit": "10^3/uL"}}
]

### Input text:
```text
{raw_text}
```"""

    # Call OpenAI
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Extract blood test results as JSON."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
        max_tokens=500,
    )

    result_text = response.choices[0].message.content.strip()

    print("---- GPT RESPONSE ----")
    print(result_text)
    print("----------------------")

    # Try parsing result
    try:
        parsed = json.loads(result_text)
        return parsed if isinstance(parsed, list) else [parsed]
    except Exception:
        return {"parsed_text": result_text}