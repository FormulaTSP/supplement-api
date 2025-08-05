def parse_bloodtest_text(raw_text: str, source_type: str = "auto"):
    """
    Parses raw blood test data from various sources.

    Args:
        raw_text (str): The raw input text, from OCR, JSON, Excel, etc.
        source_type (str): One of 'image', 'excel', or 'auto'.

    Behavior:
    - 'image': allow GPT fallback (for OCR from PDF/PNG/JPG)
    - 'excel': disable GPT fallback
    - 'auto': decide based on content
    """
    import json
    import re
    from openai import OpenAI

    client = OpenAI()

    def try_parse_json(text):
        if isinstance(text, str):
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n?", "", text)
                text = re.sub(r"\n```$", "", text)
            try:
                return json.loads(text)
            except Exception:
                return text
        return text

    def unwrap(data):
        attempts = 0
        while attempts < 10:
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    break
            elif isinstance(data, list):
                if all(isinstance(item, dict) for item in data):
                    return data
                elif len(data) == 1:
                    data = data[0]
                else:
                    break
            else:
                break
            attempts += 1
        return data

    def is_structured_bloodtest(data):
        if not isinstance(data, list):
            return False
        keys = {"marker", "value", "date"}
        return all(isinstance(item, dict) and keys.issubset(item.keys()) for item in data)

    def coerce_values(data):
        """Convert value fields to float where possible. Capture < / > qualifiers."""
        for item in data:
            val = item.get("value")
            qualifier = None

            if isinstance(val, str):
                val = val.strip()
                # Check for inequality
                if val.startswith("<") or val.startswith(">"):
                    qualifier = val[0]
                    val = val[1:].strip()

                try:
                    item["value"] = float(val.replace(",", "."))
                    if qualifier:
                        item["qualifier"] = qualifier
                except Exception:
                    item["value"] = None

        return data

    def extract_unit_from_marker(data):
        cleaned = []
        for item in data:
            marker = item.get("marker", "").strip()
            unit = None
            last_space_idx = marker.rfind(" ")
            if last_space_idx != -1:
                open_paren_idx = marker.find("(", last_space_idx)
                close_paren_idx = marker.rfind(")")
                if 0 <= open_paren_idx < close_paren_idx:
                    unit = marker[open_paren_idx + 1:close_paren_idx].strip()
                    marker = marker[:open_paren_idx].strip()
            item["marker"] = marker
            if unit:
                item["unit"] = unit
            cleaned.append(item)
        return cleaned

    # Step 1: Try structured JSON handling
    parsed = try_parse_json(raw_text)
    parsed = unwrap(parsed)

    if is_structured_bloodtest(parsed):
        structured = coerce_values(parsed)
        structured = extract_unit_from_marker(structured)
        return {
            "structured_bloodtest": {
                "parsed_text": structured
            },
            "raw_text": raw_text,
            "message": "Parsed from structured input (cleaned)"
        }

    # Step 2: Decide whether to use GPT fallback
    should_use_gpt = source_type == "image"

    if source_type == "auto":
        try:
            test = json.loads(raw_text)
            if isinstance(test, (list, dict)):
                should_use_gpt = False
        except Exception:
            should_use_gpt = True

    if not should_use_gpt:
        return {
            "structured_bloodtest": {
                "parsed_text": [],
            },
            "raw_text": raw_text,
            "message": "Unable to parse structured input. GPT fallback is disabled."
        }

    # Step 3: GPT fallback parsing
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
- marker (string) without unit
- value (float or null)
- unit (optional, string)
- date (if available)

If the unit is embedded in the marker, such as "Hemoglobin (g/L)", extract "g/L" as unit and remove from marker.

If values are written with symbols like "<0.05", extract the number as value and store "<" in a field named "qualifier".
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Extract structured blood test data as JSON."},
            {"role": "user", "content": f"{prompt}\n\nInput:\n{raw_text}"}
        ],
        temperature=0,
        max_tokens=2000,
    )

    result_text = response.choices[0].message.content.strip()
    parsed = try_parse_json(result_text)
    parsed = unwrap(parsed)

    structured = coerce_values(parsed)
    structured = extract_unit_from_marker(structured)

    return {
        "structured_bloodtest": {
            "parsed_text": structured if isinstance(structured, list) else [structured]
        },
        "raw_text": raw_text,
        "message": "Blood test data extracted via GPT fallback."
    }