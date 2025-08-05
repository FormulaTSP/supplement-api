import os
from openai import OpenAI

client = OpenAI()

def parse_bloodtest_text(raw_text: str):
    prompt = f"""
    You are a helpful assistant that extracts blood test results from raw text.
    The input text contains markers, values, and units mixed with other data.
    Extract and return a JSON array of objects, each with keys:
    - marker (string)
    - value (float)
    - unit (string)

    Example output:
    [
      {{"marker": "Hemoglobin", "value": 13.2, "unit": "g/dL"}},
      {{"marker": "WBC", "value": 6.1, "unit": "10^3/uL"}}
    ]

    Input text:
    \"\"\"
    {raw_text}
    \"\"\"
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": "Extract blood test results as JSON."},
                  {"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=300,
    )

    result_text = response.choices[0].message.content

    # Parse JSON safely
    import json
    try:
        return json.loads(result_text)
    except Exception:
        # fallback return raw result string if parsing fails
        return {"parsed_text": result_text}