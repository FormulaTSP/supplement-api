def parse_bloodtest_text(raw_text: str):
    """
    Parses OCR or GPT JSON output into structured blood test data.
    Fixes cases where parsed_text is a string inside a list.
    """
    import json
    import re
    from openai import OpenAI

    client = OpenAI()

    def try_parse_json_recursive(text):
        attempts = 0
        while isinstance(text, str) and attempts < 5:
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n?", "", text)
                text = re.sub(r"\n```$", "", text)
            try:
                text = json.loads(text)
            except Exception:
                break
            attempts += 1
        return text

    is_json = False
    try:
        json.loads(raw_text)
        is_json = True
    except Exception:
        pass

    prompt = f"""
You are a helpful assistant extracting blood test results from {'JSON' if is_json else 'OCR'} text.

Return only a JSON array of objects (do not wrap in a string or another object).

Each object must include:
- marker (string)
- value (float)
- unit (optional)
- date (if available)

Input:
{raw_text}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Extract structured blood test data as JSON."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
        max_tokens=2000,
    )

    result_text = response.choices[0].message.content.strip()
    parsed = try_parse_json_recursive(result_text)

    # 🔥 Final unwrap fix
    def unwrap(parsed):
        if isinstance(parsed, dict) and "parsed_text" in parsed:
            pt = parsed["parsed_text"]

            # Case: ["{...}"]
            if isinstance(pt, list) and len(pt) == 1 and isinstance(pt[0], str):
                pt = try_parse_json_recursive(pt[0])
            elif isinstance(pt, str):
                pt = try_parse_json_recursive(pt)

            parsed["parsed_text"] = pt
            return parsed
        return {
            "structured_bloodtest": {
                "parsed_text": parsed if isinstance(parsed, list) else [parsed]
            }
        }

    final = unwrap(parsed)

    return {
        "structured_bloodtest": {
            "parsed_text": final["structured_bloodtest"]["parsed_text"]
        },
        "raw_text": raw_text,
        "message": "Blood test data extracted successfully."
    }