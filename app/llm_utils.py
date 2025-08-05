import os
import json
import re
from openai import OpenAI

client = OpenAI()

def parse_bloodtest_text(raw_text: str):
    """
    Uses GPT to extract blood test markers from raw OCR text (PDF/image).
    Expects unstructured text and avoids guessing markers.
    """

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

Example output:
[
  {{"marker": "Hemoglobin", "value": 13.2, "unit": "g/dL"}},
  {{"marker": "WBC", "value": 6.1, "unit": "10^3/uL"}}
]

Input text:
```text
{raw_text}
```
"""

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

    # Debug print
    print("---- GPT RESPONSE ----")
    print(result_text)
    print("----------------------")

    # Strip markdown-style code blocks
    if result_text.startswith("```"):
        result_text = re.sub(r"^```(?:json)?\n", "", result_text)
        result_text = re.sub(r"\n```$", "", result_text)

    try:
        parsed = json.loads(result_text)
        return parsed if isinstance(parsed, list) else [parsed]
    except Exception:
        return {"parsed_text": result_text}