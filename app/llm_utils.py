import os
from openai import OpenAI
import json

client = OpenAI()

def parse_bloodtest_text(raw_text: str):
    # Try to see if input is JSON (Excel case)
    try:
        data = json.loads(raw_text)
        is_json = True
    except Exception:
        is_json = False

    if is_json:
        prompt = f"""
        You are a helpful assistant that extracts blood test results from JSON data representing tables.
        The JSON contains lists of records with various keys. Extract and return a JSON array of objects,
        each with keys: marker (string), value (float), unit (string).
        Example output:
        [
          {{"marker": "Hemoglobin", "value": 13.2, "unit": "g/dL"}},
          {{"marker": "WBC", "value": 6.1, "unit": "10^3/uL"}}
        ]

        Input JSON data:
        ```json
        {json.dumps(data, indent=2)}
        ```
        """
    else:
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
        messages=[
            {"role": "system", "content": "Extract blood test results as JSON."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
        max_tokens=500,
    )

    result_text = response.choices[0].message.content

    try:
        return json.loads(result_text)
    except Exception:
        return {"parsed_text": result_text}